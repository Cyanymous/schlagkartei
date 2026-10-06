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


def _schlag_anlegen(client, name="Acker", nummer="1"):
    client.post(
        "/schlaege",
        data={"betrieb": "Hof", "name": name, "schlagnummer": nummer, "groesse_ha": "2", "ab_jahr": "2020"},
    )


def test_anbau_erfassen_und_im_plan_sehen(client):
    _schlag_anlegen(client)
    kulturen = client.get("/anbauplan/1/2025").text
    hafer_id = kulturen.split(">Hafer (AVESA)<")[0].rsplit('value="', 1)[1].split('"')[0]

    r = client.post("/anbauplan/1/2025", data={"art": "Hauptkultur", "kultur_id": hafer_id, "bemerkung": "gut"})
    assert r.status_code == 200
    assert 'value="gut"' in r.text

    plan = client.get("/anbauplan").text
    assert "Hafer" in plan
    assert "Planung" in plan

    csv = client.get("/anbauplan.csv").text
    assert "Hof;Acker;1;2;2025;Hauptkultur;Hafer;AVESA;gut" in csv
