import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    monkeypatch.setenv("EXPORT_DIR", str(export_dir))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "schlagkartei.db"))

    from app.main import app

    with TestClient(app) as c:
        yield c


def test_schlag_anlegen_und_anzeigen(client):
    r = client.post(
        "/schlaege",
        data={"betrieb": "Hof Nord", "name": "Hinterm Hof", "schlagnummer": "22", "groesse_ha": "3,25", "ab_jahr": "2020"},
    )
    assert r.status_code == 200
    assert "Hinterm Hof" in r.text
    assert "3,25" in r.text

    liste = client.get("/schlaege").text
    assert "Hinterm Hof" in liste
    assert "Summe aktive Schläge Hof Nord" in liste


def test_fehler_wird_angezeigt(client):
    r = client.post("/schlaege", data={"betrieb": "Hof", "name": "", "schlagnummer": "1"})
    assert "Bitte Betrieb und Namen angeben." in r.text


def test_kulturen_seite_zeigt_eppo_codes(client):
    r = client.get("/kulturen")
    assert "Winterweizen" in r.text
    assert "TRZAW" in r.text
