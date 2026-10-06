import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def client(tmp_path, monkeypatch):
    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    for pfad in FIXTURES.glob("*.zip"):
        shutil.copy(pfad, export_dir)

    monkeypatch.setenv("EXPORT_DIR", str(export_dir))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "schlagkartei.db"))
    monkeypatch.setenv("BETRIEB_ZUORDNUNG", "")

    from app.main import app

    with TestClient(app) as c:
        yield c


def test_uebersicht_laedt_und_zeigt_anwendungen(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Spargel" in r.text
    assert "BENEVIA" in r.text


def _tabellenzeilen(html: str) -> str:
    return html.split("<tbody>")[1].split("</tbody>")[0]


def test_filter_nach_mittel_wirkt(client):
    r = client.get("/", params={"mittel": "BENEVIA"})
    zeilen = _tabellenzeilen(r.text)
    assert "BENEVIA" in zeilen
    assert "Mospilan" not in zeilen


def test_filter_nach_betrieb_wirkt(client):
    r = client.get("/", params={"betrieb": "Hofladen Lietzow"})
    zeilen = _tabellenzeilen(r.text)
    assert "Peter Horst" in zeilen
    assert "Hans Vader" not in zeilen


def test_detailansicht_zeigt_original_datensatz(client):
    r = client.get("/")
    assert r.status_code == 200
    detail = client.get("/anwendung/1")
    assert detail.status_code == 200
    assert "Original-Datensatz" in detail.text


def test_import_status_zeigt_dateien(client):
    r = client.get("/import")
    assert r.status_code == 200
    assert "ok" in r.text


def test_csv_export_enthaelt_nur_gefilterte_zeilen(client):
    r = client.get("/export.csv", params={"mittel": "BENEVIA"})
    assert r.status_code == 200
    text = r.content.decode("utf-8-sig")
    assert ";" in text
    assert "BENEVIA" in text
    assert "Mospilan" not in text


def test_detail_trennt_bbch_code_und_name(client):
    r = client.get("/", params={"mittel": "BENEVIA"})
    link = _tabellenzeilen(r.text).split('href="')[1].split('"')[0]
    r = client.get(link)
    assert "19 – 9 oder mehr Laubblätter" in r.text


def test_ortszeit_rechnet_utc_in_lokale_zeit_um(monkeypatch):
    import time

    from app.main import _ortszeit

    monkeypatch.setenv("TZ", "Europe/Berlin")
    time.tzset()
    try:
        assert _ortszeit("2026-10-05T20:01:12+00:00") == "05.10.2026 22:01"
        assert _ortszeit(None) == ""
    finally:
        monkeypatch.undo()
        time.tzset()


def _detail_link(client) -> str:
    r = client.get("/", params={"mittel": "BENEVIA"})
    return _tabellenzeilen(r.text).split('href="')[1].split('"')[0]


def test_notiz_speichern_anzeigen_und_loeschen(client):
    link = _detail_link(client)

    r = client.post(f"{link}/notiz", data={"text": "Wind aus West, Wirkung gut"})
    assert r.status_code == 200  # Redirect zurück auf die Detailseite
    assert "Wind aus West, Wirkung gut" in r.text
    assert "Notiz vorhanden" in client.get("/").text

    r = client.post(f"{link}/notiz", data={"text": "  "})
    assert "Wind aus West" not in r.text
    assert "Notiz vorhanden" not in client.get("/").text


def test_uebersicht_zeigt_deutsches_datum_und_trefferzahl(client):
    r = client.get("/")
    assert "04.05.2026" in r.text
    assert "2026-05-04" not in _tabellenzeilen(r.text)
    assert "2 Anwendungen" in r.text
