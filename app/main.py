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
from app.db import connect
from app.importer import import_exports


def _get_conn():
    return connect(config.db_path())


@contextmanager
def _db():
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
    conn = _get_conn()
    try:
        rows = queries.get_applications(conn, filters)
        optionen = queries.get_filter_optionen(conn)
    finally:
        conn.close()
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
    conn = _get_conn()
    try:
        daten = queries.get_application_detail(conn, application_id)
    finally:
        conn.close()
    return templates.TemplateResponse(request, "detail.html", {"daten": daten})


@app.post("/anwendung/{application_id}/notiz")
async def notiz_speichern(request: Request, application_id: int) -> RedirectResponse:
    text = (await _formular(request)).get("text", [""])[0]
    with _db() as conn:
        queries.save_notiz(conn, application_id, text, datetime.now(UTC).isoformat())
    return _zurueck(f"/anwendung/{application_id}")


@app.get("/import", response_class=HTMLResponse)
def import_status(request: Request) -> HTMLResponse:
    conn = _get_conn()
    try:
        dateien = queries.get_import_files(conn)
    finally:
        conn.close()
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
        fehler = schlagkartei.save_kultur(conn, None, _feld(f, "name"), _feld(f, "eppo_code"))
    return _zurueck("/kulturen", fehler)


@app.post("/kulturen/{kultur_id}")
async def kultur_speichern(request: Request, kultur_id: int) -> RedirectResponse:
    f = await _formular(request)
    with _db() as conn:
        fehler = schlagkartei.save_kultur(conn, kultur_id, _feld(f, "name"), _feld(f, "eppo_code"))
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
    return templates.TemplateResponse(
        request,
        "schlag.html",
        {"schlag": schlag, "staende": staende, "betriebe": betriebe, "jahr": jahr},
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


# --- CSV-Export Pflanzenschutz -------------------------------------------------


@app.get("/export.csv")
def export_csv(request: Request) -> StreamingResponse:
    filters = _filters_aus_query(request)
    conn = _get_conn()
    try:
        rows = queries.get_applications(conn, filters)
    finally:
        conn.close()

    puffer = io.StringIO()
    puffer.write("﻿")
    writer = csv.writer(puffer, delimiter=";")
    writer.writerow(["Datum", "Betrieb", "Kultur", "Schlag", "Mittel", "Anwender"])
    for r in rows:
        writer.writerow(
            [
                r["datum"],
                r["betrieb"],
                ", ".join(r["kulturen"]),
                ", ".join(r["schlaege"]),
                ", ".join(r["mittel"]),
                r["anwender"] or "",
            ]
        )
    puffer.seek(0)
    return StreamingResponse(
        puffer,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=schlagkartei.csv"},
    )
