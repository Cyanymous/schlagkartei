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


def _fahrzeug_anlegen(client, name="JD 5720", einheit="h", tank="120"):
    return client.post("/fuhrpark/fahrzeuge", data={"name": name, "einheit": einheit, "tank_liter": tank})


def test_fahrzeug_anlegen_und_bearbeiten(client):
    r = _fahrzeug_anlegen(client)
    assert r.status_code == 200
    assert "<h1>JD 5720" in r.text

    r = client.post(
        "/fuhrpark/fahrzeuge/1",
        data={"name": "JD 5720", "einheit": "h", "tank_liter": "120", "kennzeichen": "HVL X 1",
              "tuev_faellig": "2027-03", "aktiv": "1"},
    )
    assert "HVL X 1" in r.text
    assert "03/2027" in r.text

    liste = client.get("/fuhrpark").text
    assert "JD 5720" in liste
    assert "03/2027" in liste


def test_fahrzeug_fehler_wird_angezeigt(client):
    _fahrzeug_anlegen(client)
    r = _fahrzeug_anlegen(client)
    assert "gibt es schon" in r.text
