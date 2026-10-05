import csv
import io
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from app import config, queries
from app.db import connect
from app.importer import import_exports


def _get_conn():
    return connect(config.db_path())


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
    conn = _get_conn()
    try:
        import_exports(config.export_dir(), conn, config.betrieb_zuordnung())
    finally:
        conn.close()
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


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
    conn = _get_conn()
    try:
        import_exports(config.export_dir(), conn, config.betrieb_zuordnung())
    finally:
        conn.close()
    return RedirectResponse("/import", status_code=303)


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
            [r["datum"], r["betrieb"], r["kulturen"] or "", r["schlaege"] or "", r["mittel"] or "", r["anwender"] or ""]
        )
    puffer.seek(0)
    return StreamingResponse(
        puffer,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=schlagkartei.csv"},
    )
