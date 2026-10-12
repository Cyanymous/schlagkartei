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
              "tuev_faellig": "2027-03", "aktiv": "1", "modell": "5720 Premium", "seriennummer": "L05720X123",
              "baujahr": "2008"},
    )
    assert "HVL X 1" in r.text
    assert "5720 Premium" in r.text and "L05720X123" in r.text and "2008" in r.text
    assert "03/2027" in r.text

    liste = client.get("/fuhrpark").text
    assert "JD 5720" in liste
    assert "03/2027" in liste


def test_fahrzeug_fehler_wird_angezeigt(client):
    _fahrzeug_anlegen(client)
    r = _fahrzeug_anlegen(client)
    assert "gibt es schon" in r.text


def test_tanken_mit_prozent(client):
    _fahrzeug_anlegen(client)
    r = client.post(
        "/fuhrpark/eintraege",
        data={"fahrzeug_id": "1", "datum": "2026-04-04", "art": "Tanken", "zaehlerstand": "3.058",
              "prozent": "90", "liter": "", "zurueck": "/fuhrpark/erfassen"},
    )
    assert r.status_code == 200
    assert "Gespeichert: JD 5720 – Tanken, 108 L (90 %)." in r.text

    seite = client.get("/fuhrpark/fahrzeuge/1").text
    assert "3.058 h" in seite
    assert "≈ 108" in seite

    csv = client.get("/fuhrpark/buch.csv").text
    assert "2026-04-04;JD 5720;Tanken;3058;h;108;90;;" in csv


def test_tanken_an_der_tankstelle_mit_genauen_litern(client):
    _fahrzeug_anlegen(client, "VW LT28", "km", "80")
    client.post(
        "/fuhrpark/eintraege",
        data={"fahrzeug_id": "1", "datum": "2026-02-03", "art": "Tanken", "zaehlerstand": "123.456",
              "prozent": "90", "liter": "69,57", "beleg": "4711/0815"},
    )
    buch = client.get("/fuhrpark/buch?fahrzeug=1").text
    assert "123.456 km" in buch
    assert "69,6" in buch and "≈" not in buch.split("<tbody>")[1].split("</tbody>")[0]
    assert "4711/0815" in buch


def test_fehlerhafter_eintrag_zeigt_formular_mit_eingaben(client):
    client.post("/fuhrpark/fahrzeuge", data={"name": "Gator", "einheit": "h"})  # ohne Tankgröße
    r = client.post(
        "/fuhrpark/eintraege",
        data={"fahrzeug_id": "1", "datum": "2026-04-01", "art": "Tanken", "zaehlerstand": "456", "prozent": "90"},
    )
    assert r.status_code == 400
    assert "keine Tankgröße" in r.text
    assert 'value="456"' in r.text


def test_eintrag_bearbeiten_und_loeschen(client):
    _fahrzeug_anlegen(client)
    client.post("/fuhrpark/eintraege", data={"fahrzeug_id": "1", "datum": "2026-04-04", "art": "Tanken", "prozent": "50"})
    formular = client.get("/fuhrpark/eintraege/1").text
    assert '<option value="50" selected>' in formular

    r = client.post(
        "/fuhrpark/eintraege/1",
        data={"fahrzeug_id": "1", "datum": "2026-04-05", "art": "Tanken", "prozent": "", "liter": "40"},
    )
    assert "Gespeichert: JD 5720 – Tanken, 40 L." in r.text
    assert "05.04.2026" in r.text

    r = client.post("/fuhrpark/eintraege/1/loeschen")
    assert "Keine Einträge." in r.text


def test_warnung_bei_kleinerem_zaehlerstand(client):
    _fahrzeug_anlegen(client)
    client.post("/fuhrpark/eintraege", data={"fahrzeug_id": "1", "datum": "2026-05-12", "art": "Ölwechsel", "zaehlerstand": "464"})
    r = client.post("/fuhrpark/eintraege", data={"fahrzeug_id": "1", "datum": "2026-06-01", "art": "Zählerstand", "zaehlerstand": "441"})
    assert "kleiner als am 12.05.2026" in r.text
    assert "441 h" in r.text  # trotzdem gespeichert


def test_wartungsplan_und_uebersicht(client):
    _fahrzeug_anlegen(client, "Ford 6410")
    r = client.post("/fuhrpark/fahrzeuge/1/aufgaben", data={"aufgabe": "Ölwechsel", "intervall_zaehler": "150"})
    assert "alle 150 h" in r.text
    client.post("/fuhrpark/eintraege", data={"fahrzeug_id": "1", "datum": "2021-07-29", "art": "Ölwechsel", "zaehlerstand": "1.327"})
    client.post("/fuhrpark/eintraege", data={"fahrzeug_id": "1", "datum": "2026-01-18", "art": "Zählerstand", "zaehlerstand": "1.500"})

    uebersicht = client.get("/fuhrpark").text
    assert "bei 1.477 h (23 h überfällig)" in uebersicht
    assert 'class="menuezahl"' in uebersicht

    r = client.post("/fuhrpark/fahrzeuge/1/aufgaben/1", data={"aufgabe": "Motoröl", "intervall_zaehler": "150"})
    assert "Motoröl" in r.text
    assert "29.07.2021" in r.text  # Eintrag hängt weiter an der Aufgabe

    r = client.post("/fuhrpark/fahrzeuge/1/aufgaben/1/loeschen")
    assert "Noch keine Wartungsaufgaben." in r.text
    assert 'class="menuezahl"' not in r.text


def test_erfassen_zeigt_letzten_stand_und_90_prozent(client):
    _fahrzeug_anlegen(client)
    client.post("/fuhrpark/eintraege", data={"fahrzeug_id": "1", "datum": "2026-01-18", "art": "Zählerstand", "zaehlerstand": "3.054"})
    seite = client.get("/fuhrpark/erfassen?fahrzeug=1").text
    assert "zuletzt 3.054 h" in seite
    assert '<option value="90" selected>' in seite
    assert 'name="zurueck" value="/fuhrpark/fahrzeuge/1"' in seite
