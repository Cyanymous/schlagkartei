import csv
import io
import re
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import parse_qs, quote

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from app import config, fuhrpark, queries, schlagkartei
from app.db import connect, taegliche_sicherung
from app.importer import import_exports


def _get_conn():
    return connect(config.db_path())


@contextmanager
def _db():
    # Die erste Anfrage des Tages sichert den Stand vom Tagesbeginn.
    taegliche_sicherung(config.db_path())
    conn = _get_conn()
    try:
        yield conn
    finally:
        conn.close()


async def _formular(request: Request) -> dict[str, list[str]]:
    # Formular selbst auslesen statt FastAPIs Form(), das python-multipart bräuchte.
    return parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)


def _feld(formular: dict[str, list[str]], name: str) -> str:
    return formular.get(name, [""])[0].strip()


def _zahl(text: str) -> float | None:
    """Liest Zahlen mit deutschem Komma; leer ergibt None."""
    text = text.strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _zaehlerstand(text: str) -> float | None:
    """Wie _zahl, aber ein Punkt vor genau drei Ziffern ist ein Tausenderpunkt.

    In der Fuhrpark-Tabelle stehen Stände als 150.637 km; als Dezimalzahl
    gelesen wären das 150 km.
    """
    return _zahl(re.sub(r"\.(?=\d{3}(\D|$))", "", text))


def _jahr(text: str, standard: int) -> int:
    try:
        return int(text)
    except ValueError:
        return standard


def _zurueck(url: str, fehler: str | None = None, hinweis: str | None = None) -> RedirectResponse:
    """Nach dem Speichern zurück zur Seite; Fehler und Hinweise erscheinen dort als Meldung."""
    for name, text in [("fehler", fehler), ("hinweis", hinweis)]:
        if text:
            url += ("&" if "?" in url else "?") + name + "=" + quote(text)
    return RedirectResponse(url, status_code=303)


def _aktuelles_jahr() -> int:
    return datetime.now().year


def _importieren(conn) -> list[dict]:
    ergebnisse = import_exports(config.export_dir(), conn, config.betrieb_zuordnung())
    schlagkartei.kulturen_aus_import_uebernehmen(conn)
    return ergebnisse


def _filters_aus_query(request: Request) -> dict:
    return {
        "jahr": request.query_params.get("jahr", ""),
        "betrieb": request.query_params.get("betrieb", ""),
        "schlag": request.query_params.get("schlag", ""),
        "kultur": request.query_params.get("kultur", ""),
        "mittel": request.query_params.get("mittel", ""),
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    with _db() as conn:
        _importieren(conn)
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _ortszeit(wert: str | None) -> str:
    # Gespeichert wird UTC; angezeigt in der Zeitzone aus TZ (compose.yaml).
    if not wert:
        return ""
    return datetime.fromisoformat(wert).astimezone().strftime("%d.%m.%Y %H:%M")


def _datum_de(wert: str | None) -> str:
    if not wert:
        return ""
    try:
        return datetime.strptime(wert, "%Y-%m-%d").strftime("%d.%m.%Y")
    except ValueError:
        return wert


def _ha(wert: float | None) -> str:
    """Hektar mit deutschem Komma, ohne überflüssige Nullen (1,15 statt 1.1500)."""
    if wert is None:
        return ""
    return f"{wert:.4f}".rstrip("0").rstrip(".").replace(".", ",")


def _monat_de(wert: str | None) -> str:
    """JJJJ-MM als MM/JJJJ, wie es auf der TÜV-Plakette steht."""
    if not wert:
        return ""
    return f"{wert[5:7]}/{wert[:4]}"


MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
          "August", "September", "Oktober", "November", "Dezember"]


def _monat_name(wert: str) -> str:
    """JJJJ-MM als Zwischenüberschrift, z. B. „Oktober 2026“."""
    return f"{MONATE[int(wert[5:7]) - 1]} {wert[:4]}"


templates.env.filters["ha"] = _ha
templates.env.filters["monat_name"] = _monat_name
templates.env.filters["monat_de"] = _monat_de
templates.env.filters["zahl"] = fuhrpark.zahl_de


def _anzahl_ueberfaellig() -> int:
    """Für den Menüpunkt Fuhrpark, damit Überfälliges auf jeder Seite auffällt."""
    conn = _get_conn()
    try:
        return fuhrpark.anzahl_ueberfaellig(conn, date.today())
    finally:
        conn.close()


templates.env.globals["anzahl_ueberfaellig"] = _anzahl_ueberfaellig
templates.env.filters["ortszeit"] = _ortszeit
templates.env.filters["datum_de"] = _datum_de


@app.get("/", response_class=HTMLResponse)
def uebersicht(request: Request) -> HTMLResponse:
    filters = _filters_aus_query(request)
    with _db() as conn:
        rows = queries.get_applications(conn, filters)
        optionen = queries.get_filter_optionen(conn)
    return templates.TemplateResponse(
        request,
        "uebersicht.html",
        {
            "rows": rows,
            "filters": filters,
            "optionen": optionen,
            "querystring": str(request.query_params),
        },
    )


@app.get("/anwendung/{application_id}", response_class=HTMLResponse)
def detail(request: Request, application_id: int) -> HTMLResponse:
    with _db() as conn:
        daten = queries.get_application_detail(conn, application_id)
        schlaege_zuordnung = schlagkartei.schlaege_fuer_anwendung(conn, application_id)
    return templates.TemplateResponse(
        request, "detail.html", {"daten": daten, "schlaege_zuordnung": schlaege_zuordnung}
    )


@app.post("/anwendung/{application_id}/notiz")
async def notiz_speichern(request: Request, application_id: int) -> RedirectResponse:
    text = (await _formular(request)).get("text", [""])[0]
    with _db() as conn:
        queries.save_notiz(conn, application_id, text, datetime.now(UTC).isoformat())
    return _zurueck(f"/anwendung/{application_id}")


@app.get("/import", response_class=HTMLResponse)
def import_status(request: Request) -> HTMLResponse:
    with _db() as conn:
        dateien = queries.get_import_files(conn)
    return templates.TemplateResponse(request, "import_status.html", {"dateien": dateien})


@app.post("/import")
def import_jetzt() -> RedirectResponse:
    with _db() as conn:
        ergebnisse = _importieren(conn)
    neu = [e["dateiname"] for e in ergebnisse if e["status"] != "entfernt"]
    entfernt = [e["dateiname"] for e in ergebnisse if e["status"] == "entfernt"]
    teile = []
    if neu:
        teile.append(f"Neu eingelesen: {', '.join(neu)}.")
    if entfernt:
        teile.append(f"Entfernt, weil nicht mehr im Export-Ordner: {', '.join(entfernt)}.")
    hinweis = " ".join(teile) or "Keine neuen oder entfernten Dateien."
    return RedirectResponse("/import?hinweis=" + quote(hinweis), status_code=303)


# --- Schlagkartei: Kulturen ----------------------------------------------------


@app.get("/kulturen", response_class=HTMLResponse)
def kulturen(request: Request) -> HTMLResponse:
    with _db() as conn:
        liste = schlagkartei.get_kulturen(conn)
    bearbeiten = _jahr(request.query_params.get("bearbeiten", ""), 0)
    return templates.TemplateResponse(
        request, "kulturen.html", {"kulturen": liste, "bearbeiten": bearbeiten}
    )


@app.post("/kulturen")
async def kultur_anlegen(request: Request) -> RedirectResponse:
    f = await _formular(request)
    with _db() as conn:
        fehler = schlagkartei.save_kultur(
            conn, None, _feld(f, "name"), _feld(f, "eppo_code"), _feld(f, "mehrjaehrig") == "1"
        )
    return _zurueck("/kulturen", fehler)


@app.post("/kulturen/{kultur_id}")
async def kultur_speichern(request: Request, kultur_id: int) -> RedirectResponse:
    f = await _formular(request)
    with _db() as conn:
        fehler = schlagkartei.save_kultur(
            conn, kultur_id, _feld(f, "name"), _feld(f, "eppo_code"), _feld(f, "mehrjaehrig") == "1"
        )
    return _zurueck("/kulturen", fehler)


@app.post("/kulturen/{kultur_id}/loeschen")
def kultur_loeschen(kultur_id: int) -> RedirectResponse:
    with _db() as conn:
        fehler = schlagkartei.delete_kultur(conn, kultur_id)
    return _zurueck("/kulturen", fehler)


# --- Schlagkartei: Schläge -----------------------------------------------------


@app.get("/schlaege", response_class=HTMLResponse)
def schlaege(request: Request) -> HTMLResponse:
    jahr = _aktuelles_jahr()
    with _db() as conn:
        liste = schlagkartei.get_schlaege(conn, jahr)
        betriebe = schlagkartei.get_betriebe(conn)
    return templates.TemplateResponse(
        request,
        "schlaege.html",
        {"schlaege": liste, "betriebe": betriebe, "jahr": jahr, "erstes_jahr": schlagkartei.ERSTES_JAHR},
    )


@app.post("/schlaege")
async def schlag_anlegen(request: Request) -> RedirectResponse:
    f = await _formular(request)
    with _db() as conn:
        schlag_id, fehler = schlagkartei.create_schlag(
            conn,
            _feld(f, "betrieb"),
            _feld(f, "name"),
            _jahr(_feld(f, "ab_jahr"), schlagkartei.ERSTES_JAHR),
            _feld(f, "schlagnummer"),
            _zahl(_feld(f, "groesse_ha")),
        )
    if fehler:
        return _zurueck("/schlaege", fehler)
    return _zurueck(f"/schlaege/{schlag_id}")


@app.get("/schlaege/{schlag_id}", response_class=HTMLResponse)
def schlag_detail(request: Request, schlag_id: int) -> HTMLResponse:
    jahr = _aktuelles_jahr()
    with _db() as conn:
        schlag = schlagkartei.get_schlag(conn, schlag_id, jahr)
        staende = schlagkartei.get_staende(conn, schlag_id)
        betriebe = schlagkartei.get_betriebe(conn)
        matrix = schlagkartei.anbau_matrix(schlagkartei.get_anbau(conn, schlag_id))
        zeitleiste = schlagkartei.zeitleiste(
            schlagkartei.get_feldarbeiten(conn, schlag_id=str(schlag_id)),
            schlagkartei.get_psm_anwendungen(conn, schlag_id),
        )
    return templates.TemplateResponse(
        request,
        "schlag.html",
        {
            "schlag": schlag,
            "staende": staende,
            "betriebe": betriebe,
            "jahr": jahr,
            "jahre": _jahre(),
            "matrix": matrix,
            "wiederholt": schlagkartei.wiederholte_hauptkultur(matrix),
            "zeitleiste": zeitleiste,
        },
    )


@app.post("/schlaege/{schlag_id}")
async def schlag_speichern(request: Request, schlag_id: int) -> RedirectResponse:
    f = await _formular(request)
    with _db() as conn:
        fehler = schlagkartei.update_schlag(
            conn, schlag_id, _feld(f, "betrieb"), _feld(f, "name"), _feld(f, "aktiv") == "1"
        )
    return _zurueck(f"/schlaege/{schlag_id}", fehler)


@app.post("/schlaege/{schlag_id}/staende")
async def stand_speichern(request: Request, schlag_id: int) -> RedirectResponse:
    f = await _formular(request)
    with _db() as conn:
        fehler = schlagkartei.save_stand(
            conn,
            schlag_id,
            _jahr(_feld(f, "ab_jahr"), _aktuelles_jahr()),
            _feld(f, "schlagnummer"),
            _zahl(_feld(f, "groesse_ha")),
        )
    return _zurueck(f"/schlaege/{schlag_id}", fehler)


@app.post("/schlaege/{schlag_id}/staende/{stand_id}/loeschen")
def stand_loeschen(schlag_id: int, stand_id: int) -> RedirectResponse:
    with _db() as conn:
        fehler = schlagkartei.delete_stand(conn, stand_id)
    return _zurueck(f"/schlaege/{schlag_id}", fehler)


# --- Schlagkartei: Anbauplan ---------------------------------------------------


def _jahre() -> list[int]:
    """2020 bis zum nächsten Jahr; das letzte ist die Planung."""
    return list(range(schlagkartei.ERSTES_JAHR, _aktuelles_jahr() + 2))


@app.get("/anbauplan", response_class=HTMLResponse)
def anbauplan(request: Request) -> HTMLResponse:
    betrieb = request.query_params.get("betrieb", "")
    with _db() as conn:
        schlaege_liste = [
            s for s in schlagkartei.get_schlaege(conn, _aktuelles_jahr()) if not betrieb or s["betrieb"] == betrieb
        ]
        matrix = schlagkartei.anbau_matrix(schlagkartei.get_anbau(conn))
        umfang = schlagkartei.anbauumfang(conn, betrieb)
        betriebe = schlagkartei.get_betriebe(conn)
    return templates.TemplateResponse(
        request,
        "anbauplan.html",
        {
            "schlaege": schlaege_liste,
            "jahre": _jahre(),
            "matrix": matrix,
            "wiederholt": schlagkartei.wiederholte_hauptkultur(matrix),
            "umfang": umfang,
            "betriebe": betriebe,
            "betrieb": betrieb,
        },
    )


@app.get("/anbauplan/{schlag_id}/{jahr}", response_class=HTMLResponse)
def anbau_zelle(request: Request, schlag_id: int, jahr: int) -> HTMLResponse:
    with _db() as conn:
        schlag = schlagkartei.get_schlag(conn, schlag_id, jahr)
        eintraege = [e for e in schlagkartei.get_anbau(conn, schlag_id) if e["jahr"] == jahr]
        vorjahr = [e for e in schlagkartei.get_anbau(conn, schlag_id) if e["jahr"] == jahr - 1]
        kulturen_liste = schlagkartei.get_kulturen(conn)
    return templates.TemplateResponse(
        request,
        "anbau_zelle.html",
        {
            "schlag": schlag,
            "jahr": jahr,
            "planung": jahr > _aktuelles_jahr(),
            "eintraege": eintraege,
            "vorjahr": vorjahr,
            "kulturen": kulturen_liste,
            "arten": schlagkartei.ANBAU_ARTEN,
        },
    )


@app.post("/anbauplan/{schlag_id}/{jahr}")
async def anbau_anlegen(request: Request, schlag_id: int, jahr: int) -> RedirectResponse:
    f = await _formular(request)
    with _db() as conn:
        fehler = schlagkartei.add_anbau(
            conn, schlag_id, jahr, _jahre()[-1], _jahr(_feld(f, "kultur_id"), 0), _feld(f, "art"), _feld(f, "bemerkung")
        )
    return _zurueck(f"/anbauplan/{schlag_id}/{jahr}", fehler)


@app.post("/anbau/{anbau_id}")
async def anbau_speichern(request: Request, anbau_id: int) -> RedirectResponse:
    f = await _formular(request)
    with _db() as conn:
        fehler = schlagkartei.update_anbau(
            conn, anbau_id, _jahre()[-1], _jahr(_feld(f, "kultur_id"), 0), _feld(f, "art"), _feld(f, "bemerkung")
        )
    return _zurueck(_feld(f, "zurueck") or "/anbauplan", fehler)


@app.post("/anbau/{anbau_id}/loeschen")
async def anbau_loeschen(request: Request, anbau_id: int) -> RedirectResponse:
    f = await _formular(request)
    with _db() as conn:
        schlagkartei.delete_anbau(conn, anbau_id)
    return _zurueck(_feld(f, "zurueck") or "/anbauplan")


@app.get("/anbauplan.csv")
def anbauplan_csv(request: Request) -> StreamingResponse:
    betrieb = request.query_params.get("betrieb", "")
    with _db() as conn:
        schlaege_nach_id = {s["id"]: s for s in schlagkartei.get_schlaege(conn, _aktuelles_jahr())}
        zeilen = []
        for e in schlagkartei.get_anbau(conn):
            s = schlaege_nach_id[e["schlag_id"]]
            if betrieb and s["betrieb"] != betrieb:
                continue
            stand = schlagkartei.get_schlag(conn, s["id"], e["jahr"])
            zeilen.append(
                [
                    s["betrieb"],
                    s["name"],
                    stand["schlagnummer"] or "",
                    _ha(stand["groesse_ha"]),
                    e["jahr"],
                    e["art"],
                    e["kultur"],
                    e["eppo_code"] or "",
                    e["bemerkung"] or "",
                ]
            )
    kopf = ["Betrieb", "Schlag", "Schlagnummer", "Größe (ha)", "Jahr", "Art", "Kultur", "EPPO-Code", "Bemerkung"]
    return _csv_antwort("anbauplan.csv", kopf, zeilen)


# --- Schlagkartei: Feldarbeiten -----------------------------------------------


def _feldarbeit_filter(request: Request) -> dict:
    return {
        "jahr": request.query_params.get("jahr", ""),
        "schlag_id": request.query_params.get("schlag", ""),
        "art": request.query_params.get("art", ""),
    }


@app.get("/feldarbeiten", response_class=HTMLResponse)
def feldarbeiten(request: Request) -> HTMLResponse:
    filter_ = _feldarbeit_filter(request)
    with _db() as conn:
        liste = schlagkartei.get_feldarbeiten(conn, **filter_)
        schlaege_liste = schlagkartei.get_schlaege(conn, _aktuelles_jahr())
        jahre = schlagkartei.get_feldarbeit_jahre(conn)
        arten = schlagkartei.get_arbeitsarten(conn)
    return templates.TemplateResponse(
        request,
        "feldarbeiten.html",
        {
            "feldarbeiten": liste,
            "filter": filter_,
            "schlaege": schlaege_liste,
            "jahre": jahre,
            "arten": arten,
            "querystring": str(request.query_params),
        },
    )


def _feldarbeit_formular(
    request: Request, conn, feldarbeit, ausgewaehlt: set[int], fehler: str | None = None
) -> HTMLResponse:
    datum = (feldarbeit or {}).get("datum") or ""
    jahr = int(datum[:4]) if datum[:4].isdigit() else _aktuelles_jahr()
    # Inaktive Schläge nur zeigen, wenn sie schon zu dieser Arbeit gehören.
    schlaege_liste = [s for s in schlagkartei.get_schlaege(conn, jahr) if s["aktiv"] or s["id"] in ausgewaehlt]
    return templates.TemplateResponse(
        request,
        "feldarbeit.html",
        {
            "feldarbeit": feldarbeit,
            "ausgewaehlt": ausgewaehlt,
            "schlaege": schlaege_liste,
            "kultur_je_schlag": schlagkartei.hauptkultur_je_schlag(conn, jahr),
            "jahr": jahr,
            "arten": schlagkartei.get_arbeitsarten(conn),
            "heute": datetime.now().date().isoformat(),
            "fehler": fehler,
        },
        status_code=400 if fehler else 200,
    )


@app.get("/feldarbeiten/neu", response_class=HTMLResponse)
def feldarbeit_neu(request: Request) -> HTMLResponse:
    vorauswahl = {_jahr(request.query_params.get("schlag", ""), 0)} - {0}
    with _db() as conn:
        return _feldarbeit_formular(request, conn, None, vorauswahl)


@app.get("/feldarbeiten/{feldarbeit_id}", response_class=HTMLResponse)
def feldarbeit_bearbeiten(request: Request, feldarbeit_id: int) -> HTMLResponse:
    with _db() as conn:
        feldarbeit, schlag_ids = schlagkartei.get_feldarbeit(conn, feldarbeit_id)
        if feldarbeit is None:
            return HTMLResponse("Feldarbeit nicht gefunden.", status_code=404)
        return _feldarbeit_formular(request, conn, dict(feldarbeit), schlag_ids)


async def _feldarbeit_speichern(request: Request, feldarbeit_id: int | None):
    f = await _formular(request)
    schlag_ids = [_jahr(x, 0) for x in f.get("schlag", [])]
    eingabe = {"id": feldarbeit_id, "datum": _feld(f, "datum"), "art": _feld(f, "art"), "bemerkung": _feld(f, "bemerkung")}
    with _db() as conn:
        _, fehler = schlagkartei.save_feldarbeit(
            conn, feldarbeit_id, eingabe["datum"], eingabe["art"], eingabe["bemerkung"], schlag_ids
        )
        if fehler:
            # Formular mit den Eingaben erneut zeigen, damit die Schlagauswahl nicht verloren geht.
            return _feldarbeit_formular(request, conn, eingabe, set(schlag_ids), fehler)
    return _zurueck(_feld(f, "zurueck") or "/feldarbeiten")


@app.post("/feldarbeiten")
async def feldarbeit_anlegen(request: Request) -> RedirectResponse:
    return await _feldarbeit_speichern(request, None)


@app.post("/feldarbeiten/{feldarbeit_id}")
async def feldarbeit_aendern(request: Request, feldarbeit_id: int) -> RedirectResponse:
    return await _feldarbeit_speichern(request, feldarbeit_id)


@app.post("/feldarbeiten/{feldarbeit_id}/loeschen")
def feldarbeit_loeschen(feldarbeit_id: int) -> RedirectResponse:
    with _db() as conn:
        schlagkartei.delete_feldarbeit(conn, feldarbeit_id)
    return _zurueck("/feldarbeiten")


@app.get("/feldarbeiten.csv")
def feldarbeiten_csv(request: Request) -> StreamingResponse:
    with _db() as conn:
        liste = schlagkartei.get_feldarbeiten(conn, **_feldarbeit_filter(request))
    zeilen = [
        [f["datum"], f["art"], ", ".join(s["name"] for s in f["schlaege"]), f["bemerkung"] or ""]
        for f in liste
    ]
    return _csv_antwort("feldarbeiten.csv", ["Datum", "Art", "Schläge", "Bemerkung"], zeilen)


# --- Fuhrpark: Fahrzeuge -------------------------------------------------------


def _fahrzeug_daten(f: dict[str, list[str]], neu: bool) -> dict:
    daten = {
        name: _feld(f, name)
        for name in ["name", "modell", "seriennummer", "kennzeichen", "oelfilter", "einheit", "tuev_faellig", "bemerkung"]
    }
    daten["tank_liter"] = _zahl(_feld(f, "tank_liter"))
    daten["baujahr"] = _jahr(_feld(f, "baujahr"), 0) or None
    # Beim Anlegen gibt es kein Häkchen „aktiv“; neue Fahrzeuge sind immer aktiv.
    daten["aktiv"] = neu or _feld(f, "aktiv") == "1"
    return daten


@app.get("/fuhrpark", response_class=HTMLResponse)
def fuhrpark_uebersicht(request: Request) -> HTMLResponse:
    with _db() as conn:
        zeilen = fuhrpark.uebersicht(conn, date.today())
        inaktive = [f for f in fuhrpark.get_fahrzeuge(conn) if not f["aktiv"]]
    return templates.TemplateResponse(
        request,
        "fuhrpark.html",
        {"zeilen": zeilen, "inaktive": inaktive, "einheiten": fuhrpark.EINHEITEN},
    )


@app.post("/fuhrpark/fahrzeuge")
async def fahrzeug_anlegen(request: Request) -> RedirectResponse:
    f = await _formular(request)
    with _db() as conn:
        fahrzeug_id, fehler = fuhrpark.save_fahrzeug(conn, None, _fahrzeug_daten(f, neu=True))
    if fehler:
        return _zurueck("/fuhrpark", fehler)
    return _zurueck(f"/fuhrpark/fahrzeuge/{fahrzeug_id}")


@app.get("/fuhrpark/fahrzeuge/{fahrzeug_id}", response_class=HTMLResponse)
def fahrzeug_detail(request: Request, fahrzeug_id: int) -> HTMLResponse:
    with _db() as conn:
        fahrzeug = fuhrpark.get_fahrzeug(conn, fahrzeug_id)
        if fahrzeug is None:
            return HTMLResponse("Fahrzeug nicht gefunden.", status_code=404)
        eintraege = fuhrpark.get_eintraege(conn, fahrzeug_id=str(fahrzeug_id))
        punkte = fuhrpark.wartungsplan(conn, fahrzeug, date.today())
    return templates.TemplateResponse(
        request,
        "fahrzeug.html",
        {
            "fahrzeug": fahrzeug,
            "einheiten": fuhrpark.EINHEITEN,
            # Auf der Fahrzeugseite nur die letzten Einträge; der Rest steht im Fahrzeugbuch.
            "eintraege": eintraege[:10],
            "anzahl_eintraege": len(eintraege),
            "punkte": punkte,
            "bearbeiten": _jahr(request.query_params.get("bearbeiten", ""), 0),
        },
    )


@app.post("/fuhrpark/fahrzeuge/{fahrzeug_id}")
async def fahrzeug_speichern(request: Request, fahrzeug_id: int) -> RedirectResponse:
    f = await _formular(request)
    with _db() as conn:
        _, fehler = fuhrpark.save_fahrzeug(conn, fahrzeug_id, _fahrzeug_daten(f, neu=False))
    return _zurueck(f"/fuhrpark/fahrzeuge/{fahrzeug_id}", fehler)


@app.post("/fuhrpark/fahrzeuge/{fahrzeug_id}/aufgaben")
async def aufgabe_anlegen(request: Request, fahrzeug_id: int) -> RedirectResponse:
    return await _aufgabe_speichern(request, fahrzeug_id, None)


@app.post("/fuhrpark/fahrzeuge/{fahrzeug_id}/aufgaben/{aufgabe_id}")
async def aufgabe_aendern(request: Request, fahrzeug_id: int, aufgabe_id: int) -> RedirectResponse:
    return await _aufgabe_speichern(request, fahrzeug_id, aufgabe_id)


async def _aufgabe_speichern(request: Request, fahrzeug_id: int, aufgabe_id: int | None) -> RedirectResponse:
    f = await _formular(request)
    with _db() as conn:
        fehler = fuhrpark.save_aufgabe(
            conn,
            fahrzeug_id,
            aufgabe_id,
            _feld(f, "aufgabe"),
            _zaehlerstand(_feld(f, "intervall_zaehler")),
            _zahl(_feld(f, "intervall_monate")),
        )
    return _zurueck(f"/fuhrpark/fahrzeuge/{fahrzeug_id}", fehler)


@app.post("/fuhrpark/fahrzeuge/{fahrzeug_id}/aufgaben/{aufgabe_id}/loeschen")
def aufgabe_loeschen(fahrzeug_id: int, aufgabe_id: int) -> RedirectResponse:
    with _db() as conn:
        fuhrpark.delete_aufgabe(conn, aufgabe_id)
    return _zurueck(f"/fuhrpark/fahrzeuge/{fahrzeug_id}")


# --- Fuhrpark: Fahrzeugbuch ----------------------------------------------------


def _eintrag_daten(f: dict[str, list[str]]) -> dict:
    return {
        "fahrzeug_id": _jahr(_feld(f, "fahrzeug_id"), 0),
        "datum": _feld(f, "datum"),
        "art": _feld(f, "art"),
        "zaehlerstand": _zaehlerstand(_feld(f, "zaehlerstand")),
        "prozent": _jahr(_feld(f, "prozent"), 0) or None,
        "liter": _zahl(_feld(f, "liter")),
        "beleg": _feld(f, "beleg"),
        "bemerkung": _feld(f, "bemerkung"),
    }


@app.get("/fuhrpark/erfassen", response_class=HTMLResponse)
def fuhrpark_erfassen(request: Request) -> HTMLResponse:
    with _db() as conn:
        fahrzeuge = fuhrpark.get_fahrzeuge(conn, nur_aktive=True)
        arten = fuhrpark.get_arten(conn)
    return templates.TemplateResponse(
        request,
        "fuhrpark_erfassen.html",
        {
            "fahrzeuge": fahrzeuge,
            "arten": arten,
            "vorauswahl": _jahr(request.query_params.get("fahrzeug", ""), 0),
            "prozente": fuhrpark.PROZENTE,
            "heute": datetime.now().date().isoformat(),
        },
    )


@app.get("/fuhrpark/erfassen/fahrzeug", response_class=HTMLResponse)
def fuhrpark_erfassen_fahrzeug(request: Request) -> HTMLResponse:
    with _db() as conn:
        fahrzeug = fuhrpark.get_fahrzeug(conn, _jahr(request.query_params.get("fahrzeug_id", ""), 0))
        punkte = fuhrpark.wartungsplan(conn, fahrzeug, date.today()) if fahrzeug else []
    return templates.TemplateResponse(
        request, "fuhrpark_erfassen_fahrzeug.html", {"fahrzeug": fahrzeug, "punkte": punkte}
    )


def _eintrag_formular(request: Request, conn, eintrag: dict, fehler: str | None = None) -> HTMLResponse:
    # Inaktive Fahrzeuge nur anbieten, wenn der Eintrag schon zu einem gehört.
    fahrzeuge = [f for f in fuhrpark.get_fahrzeuge(conn) if f["aktiv"] or f["id"] == eintrag.get("fahrzeug_id")]
    return templates.TemplateResponse(
        request,
        "fahrzeug_eintrag.html",
        {
            "eintrag": eintrag,
            "fahrzeuge": fahrzeuge,
            "arten": fuhrpark.get_arten(conn),
            "prozente": fuhrpark.PROZENTE,
            "fehler": fehler,
        },
        status_code=400 if fehler else 200,
    )


async def _eintrag_speichern(request: Request, eintrag_id: int | None):
    f = await _formular(request)
    daten = _eintrag_daten(f)
    ziel = _feld(f, "zurueck")
    # Von HTMX (Erfassen-Seite) gesendet: nur das Ergebnis zurückgeben, die Seite bleibt stehen.
    htmx = request.headers.get("HX-Request") == "true"
    with _db() as conn:
        gespeichert_id, fehler = fuhrpark.save_eintrag(conn, eintrag_id, daten)
        if fehler and htmx:
            return templates.TemplateResponse(request, "fuhrpark_erfassen_ergebnis.html", {"fehler": fehler})
        if fehler:
            # Formular mit den Eingaben erneut zeigen, damit auf dem Handy nichts neu getippt werden muss.
            eingabe = daten | {
                "id": eintrag_id,
                "zaehlerstand": _feld(f, "zaehlerstand"),
                "liter": _feld(f, "liter"),
                "zurueck": ziel,
            }
            return _eintrag_formular(request, conn, eingabe, fehler)
        e = fuhrpark.get_eintrag(conn, gespeichert_id)
        hinweis = f"Gespeichert: {fuhrpark.get_fahrzeug(conn, e['fahrzeug_id'])['name']} – {e['art']}"
        if e["liter"] is not None:
            hinweis += f", {fuhrpark.zahl_de(e['liter'])} L" + (f" ({e['prozent']} %)" if e["prozent"] else "")
        warnung = fuhrpark.zaehlerstand_hinweis(conn, gespeichert_id)
        if htmx:
            return templates.TemplateResponse(
                request,
                "fuhrpark_erfassen_ergebnis.html",
                {
                    "hinweis": hinweis + ".",
                    "warnung": warnung,
                    "eintraege": fuhrpark.get_eintraege(conn, fahrzeug_id=str(e["fahrzeug_id"]))[:5],
                    "fahrzeug_id": e["fahrzeug_id"],
                },
                # Leert das Formular und lädt Stand und Fälligkeiten des Fahrzeugs neu.
                headers={"HX-Trigger": "eintrag-gespeichert"},
            )
    if not ziel.startswith("/"):
        ziel = f"/fuhrpark/fahrzeuge/{e['fahrzeug_id']}"
    return _zurueck(ziel, warnung, hinweis + ".")


@app.post("/fuhrpark/eintraege")
async def eintrag_anlegen(request: Request):
    return await _eintrag_speichern(request, None)


@app.get("/fuhrpark/eintraege/{eintrag_id}", response_class=HTMLResponse)
def eintrag_bearbeiten(request: Request, eintrag_id: int) -> HTMLResponse:
    with _db() as conn:
        eintrag = fuhrpark.get_eintrag(conn, eintrag_id)
        if eintrag is None:
            return HTMLResponse("Eintrag nicht gefunden.", status_code=404)
        daten = dict(eintrag)
        daten["zaehlerstand"] = fuhrpark.zahl_de(eintrag["zaehlerstand"])
        # Geschätzte Liter nicht ins Literfeld, sonst hätten sie beim Speichern Vorrang vor dem Prozentwert.
        daten["liter"] = "" if eintrag["prozent"] else fuhrpark.zahl_de(eintrag["liter"])
        return _eintrag_formular(request, conn, daten)


@app.post("/fuhrpark/eintraege/{eintrag_id}")
async def eintrag_aendern(request: Request, eintrag_id: int):
    return await _eintrag_speichern(request, eintrag_id)


@app.post("/fuhrpark/eintraege/{eintrag_id}/loeschen")
def eintrag_loeschen(eintrag_id: int) -> RedirectResponse:
    with _db() as conn:
        eintrag = fuhrpark.get_eintrag(conn, eintrag_id)
        fuhrpark.delete_eintrag(conn, eintrag_id)
    return _zurueck(f"/fuhrpark/fahrzeuge/{eintrag['fahrzeug_id']}" if eintrag else "/fuhrpark")


def _buch_filter(request: Request) -> dict:
    return {
        "fahrzeug_id": request.query_params.get("fahrzeug", ""),
        "jahr": request.query_params.get("jahr", ""),
        "art": request.query_params.get("art", ""),
    }


@app.get("/fuhrpark/buch", response_class=HTMLResponse)
def fahrzeugbuch(request: Request) -> HTMLResponse:
    filter_ = _buch_filter(request)
    with _db() as conn:
        eintraege = fuhrpark.get_eintraege(conn, **filter_)
        fahrzeuge = fuhrpark.get_fahrzeuge(conn)
        jahre = fuhrpark.get_eintrag_jahre(conn)
        arten = sorted({r["art"] for r in fuhrpark.get_eintraege(conn)})
    return templates.TemplateResponse(
        request,
        "fahrzeugbuch.html",
        {
            "eintraege": eintraege,
            "filter": filter_,
            "fahrzeuge": fahrzeuge,
            "jahre": jahre,
            "arten": arten,
            "querystring": str(request.query_params),
        },
    )


@app.get("/fuhrpark/buch.csv")
def fahrzeugbuch_csv(request: Request) -> StreamingResponse:
    with _db() as conn:
        eintraege = fuhrpark.get_eintraege(conn, **_buch_filter(request))
    zeilen = [
        [
            e["datum"], e["fahrzeug"], e["art"], _ha(e["zaehlerstand"]), e["einheit"] or "",
            _ha(e["liter"]), e["prozent"] or "", e["beleg"] or "", e["bemerkung"] or "",
        ]
        for e in eintraege
    ]
    kopf = ["Datum", "Fahrzeug", "Art", "Zählerstand", "Einheit", "Liter", "geschätzt aus %", "Beleg", "Bemerkung"]
    return _csv_antwort("fahrzeugbuch.csv", kopf, zeilen)


# --- CSV-Export Pflanzenschutz -------------------------------------------------


@app.get("/export.csv")
def export_csv(request: Request) -> StreamingResponse:
    filters = _filters_aus_query(request)
    with _db() as conn:
        rows = queries.get_applications(conn, filters)

    kopf = ["Datum", "Betrieb", "Kultur", "Schlag", "Mittel", "Anwender"]
    zeilen = [
        [
            r["datum"],
            r["betrieb"],
            ", ".join(r["kulturen"]),
            ", ".join(r["schlaege"]),
            ", ".join(r["mittel"]),
            r["anwender"] or "",
        ]
        for r in rows
    ]
    return _csv_antwort("schlagkartei.csv", kopf, zeilen)


def _csv_antwort(dateiname: str, kopf: list[str], zeilen: list[list]) -> StreamingResponse:
    """CSV mit BOM und Semikolon, damit Excel/LibreOffice mit deutscher Einstellung sie direkt öffnen."""
    puffer = io.StringIO()
    puffer.write("\ufeff")
    writer = csv.writer(puffer, delimiter=";")
    writer.writerow(kopf)
    writer.writerows(zeilen)
    puffer.seek(0)
    return StreamingResponse(
        puffer,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={dateiname}"},
    )
