import csv
import io
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, quote

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from app import config, queries, schlagkartei
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


def _jahr(text: str, standard: int) -> int:
    try:
        return int(text)
    except ValueError:
        return standard


def _zurueck(url: str, fehler: str | None = None) -> RedirectResponse:
    """Nach dem Speichern zurück zur Seite; Fehler erscheinen dort als Hinweis."""
    if fehler:
        url += ("&" if "?" in url else "?") + "fehler=" + quote(fehler)
    return RedirectResponse(url, status_code=303)


def _aktuelles_jahr() -> int:
    return datetime.now().year


def _importieren(conn) -> None:
    import_exports(config.export_dir(), conn, config.betrieb_zuordnung())
    schlagkartei.kulturen_aus_import_uebernehmen(conn)


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


templates.env.filters["ha"] = _ha
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
        _importieren(conn)
    return _zurueck("/import")


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
