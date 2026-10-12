from datetime import date

import pytest

from app import fuhrpark as fp
from app.db import connect


@pytest.fixture
def conn():
    c = connect(":memory:")
    yield c
    c.close()


def _fahrzeug(conn, name="JD 5720", **daten):
    fahrzeug_id, fehler = fp.save_fahrzeug(conn, None, {"name": name, "einheit": "h", "tank_liter": 100.0, **daten})
    assert fehler is None
    return fahrzeug_id


# --- Fahrzeuge ---


def test_fahrzeug_anlegen_und_aendern(conn):
    fahrzeug_id = _fahrzeug(conn, kennzeichen=" HVL X 1 ", modell="", seriennummer="L05720X123", baujahr=2008)
    f = fp.get_fahrzeug(conn, fahrzeug_id)
    assert f["kennzeichen"] == "HVL X 1"
    assert f["modell"] is None
    assert (f["seriennummer"], f["baujahr"]) == ("L05720X123", 2008)
    assert f["aktiv"] == 1

    _, fehler = fp.save_fahrzeug(conn, fahrzeug_id, {"name": "JD 5720 R", "einheit": "", "aktiv": False})
    assert fehler is None
    f = fp.get_fahrzeug(conn, fahrzeug_id)
    assert f["name"] == "JD 5720 R"
    assert f["einheit"] is None
    assert f["aktiv"] == 0


def test_fahrzeugname_ist_eindeutig(conn):
    _fahrzeug(conn)
    _, fehler = fp.save_fahrzeug(conn, None, {"name": "JD 5720"})
    assert "gibt es schon" in fehler


@pytest.mark.parametrize(
    "daten, meldung",
    [
        ({"name": ""}, "Namen"),
        ({"name": "X", "einheit": "Meilen"}, "Zählereinheit"),
        ({"name": "X", "tank_liter": 0.0}, "Tankgröße"),
        ({"name": "X", "tuev_faellig": "2026-13"}, "TÜV"),
        ({"name": "X", "baujahr": 1850}, "Baujahr"),
    ],
)
def test_fahrzeug_ungueltige_eingaben(conn, daten, meldung):
    _, fehler = fp.save_fahrzeug(conn, None, daten)
    assert meldung in fehler


# --- Fahrzeugbuch ---


def _eintrag(conn, fahrzeug_id, datum="2026-04-01", art="Tanken", **daten):
    eintrag_id, fehler = fp.save_eintrag(conn, None, {"fahrzeug_id": fahrzeug_id, "datum": datum, "art": art, **daten})
    assert fehler is None
    return eintrag_id


def test_tankmenge_aus_prozent_und_tankgroesse():
    assert fp.tankmenge(120.0, 90, None) == (108.0, 90, None)
    assert fp.tankmenge(45.0, 30, None) == (13.5, 30, None)


def test_genaue_liter_haben_vorrang():
    assert fp.tankmenge(120.0, 90, 69.57) == (69.57, None, None)


def test_tankmenge_ohne_angaben():
    assert fp.tankmenge(120.0, None, None) == (None, None, None)


def test_tankmenge_ohne_tankgroesse_ist_fehler():
    *_, fehler = fp.tankmenge(None, 90, None)
    assert "keine Tankgröße" in fehler


def test_aktueller_stand_ist_neuester_eintrag_mit_zaehlerstand(conn):
    fahrzeug_id = _fahrzeug(conn)
    _eintrag(conn, fahrzeug_id, "2026-01-18", "Zählerstand", zaehlerstand=3054.0)
    _eintrag(conn, fahrzeug_id, "2026-07-01", "Ölwechsel", zaehlerstand=3077.0)
    _eintrag(conn, fahrzeug_id, "2026-04-04", "Tanken", zaehlerstand=3058.0, prozent=90)
    _eintrag(conn, fahrzeug_id, "2026-08-01", "Reparatur")  # ohne Stand: zählt nicht

    f = fp.get_fahrzeug(conn, fahrzeug_id)
    assert f["stand"] == 3077.0
    assert f["stand_datum"] == "2026-07-01"


def test_geschaetzte_liter_bleiben_bei_neuer_tankgroesse(conn):
    fahrzeug_id = _fahrzeug(conn)  # Tank 100 L
    eintrag_id = _eintrag(conn, fahrzeug_id, prozent=90)
    fp.save_fahrzeug(conn, fahrzeug_id, {"name": "JD 5720", "einheit": "h", "tank_liter": 200.0})
    e = fp.get_eintrag(conn, eintrag_id)
    assert (e["liter"], e["prozent"]) == (90.0, 90)


def test_zaehlerstand_ohne_zaehler_ist_fehler(conn):
    fahrzeug_id, _ = fp.save_fahrzeug(conn, None, {"name": "Humbaur"})
    _, fehler = fp.save_eintrag(
        conn, None, {"fahrzeug_id": fahrzeug_id, "datum": "2026-04-01", "art": "TÜV", "zaehlerstand": 5.0}
    )
    assert "keinen Zähler" in fehler


def test_hinweis_bei_kleinerem_zaehlerstand(conn):
    fahrzeug_id = _fahrzeug(conn)
    _eintrag(conn, fahrzeug_id, "2026-05-12", "Ölwechsel", zaehlerstand=464.0)
    spaeter = _eintrag(conn, fahrzeug_id, "2026-06-01", "Zählerstand", zaehlerstand=441.0)
    assert "kleiner als am 12.05.2026 (464)" in fp.zaehlerstand_hinweis(conn, spaeter)
    groesser = _eintrag(conn, fahrzeug_id, "2026-06-02", "Zählerstand", zaehlerstand=470.0)
    assert fp.zaehlerstand_hinweis(conn, groesser) is None


def test_zahl_de():
    assert fp.zahl_de(150637.0) == "150.637"
    assert fp.zahl_de(2372703.0) == "2.372.703"
    assert fp.zahl_de(69.57) == "69,6"
    assert fp.zahl_de(108.0) == "108"
    assert fp.zahl_de(None) == ""


# --- Wartungsplan ---

HEUTE = date(2026, 10, 12)


def _letzte(datum, stand=None):
    return {"datum": datum, "zaehlerstand": stand}


def test_faelligkeit_nach_zaehler():
    # JD 5720: Ölwechsel bei 3077 h, alle 500 h, aktuell 3100 h
    f = fp.faelligkeit(500.0, None, _letzte("2026-07-01", 3077.0), 3100.0, "h", HEUTE)
    assert f == {"status": "gruen", "text": "bei 3.577 h (noch 477 h)"}


def test_faelligkeit_bald_unter_zehn_prozent():
    f = fp.faelligkeit(500.0, None, _letzte("2026-07-01", 3077.0), 3540.0, "h", HEUTE)
    assert f["status"] == "gelb"


def test_faelligkeit_ueberfaellig():
    f = fp.faelligkeit(150.0, None, _letzte("2021-07-29", 1327.0), 1500.0, "h", HEUTE)
    assert f == {"status": "rot", "text": "bei 1.477 h (23 h überfällig)"}


def test_faelligkeit_nach_monaten():
    # Baroness: 1x jährlich, zuletzt 06.06.2023
    f = fp.faelligkeit(None, 12, _letzte("2023-06-06"), None, None, HEUTE)
    assert f["status"] == "rot"
    assert f["text"].startswith("am 06.06.2024")

    f = fp.faelligkeit(None, 12, _letzte("2026-04-30"), None, None, HEUTE)
    assert f == {"status": "gruen", "text": "am 30.04.2027 (noch 200 Tage)"}


def test_faelligkeit_was_zuerst_kommt():
    # Stunden noch reichlich, aber das Jahr ist um.
    f = fp.faelligkeit(500.0, 12, _letzte("2025-09-01", 3000.0), 3100.0, "h", HEUTE)
    assert f["status"] == "rot"
    assert "noch 400 h" in f["text"] and "überfällig" in f["text"]


def test_faelligkeit_monatsende():
    # 31. Januar + 1 Monat = 28. Februar, nicht 3. März
    assert fp._plus_monate(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert fp._plus_monate(date(2026, 11, 15), 3) == date(2027, 2, 15)


def test_faelligkeit_grau():
    assert fp.faelligkeit(500.0, None, None, 3000.0, "h", HEUTE)["text"] == "noch nie erledigt"
    f = fp.faelligkeit(500.0, None, _letzte("2026-01-01"), 3000.0, "h", HEUTE)
    assert f == {"status": "grau", "text": "Zählerstand beim letzten Mal fehlt"}


def test_tuev_gilt_bis_monatsende():
    assert fp.tuev_faelligkeit("2026-10", HEUTE) == {"status": "gelb", "text": "10/2026 (noch 19 Tage)"}
    assert fp.tuev_faelligkeit("2026-09", HEUTE)["status"] == "rot"
    assert fp.tuev_faelligkeit("2027-03", HEUTE)["status"] == "gruen"


def test_wartungsplan_aus_fahrzeugbuch(conn):
    fahrzeug_id = _fahrzeug(conn, tuev_faellig="2026-09")
    assert fp.save_aufgabe(conn, fahrzeug_id, None, "Ölwechsel", 500.0, None) is None
    assert fp.save_aufgabe(conn, fahrzeug_id, None, "Inspektion", None, 24) is None
    _eintrag(conn, fahrzeug_id, "2026-07-01", "Ölwechsel", zaehlerstand=3077.0)
    _eintrag(conn, fahrzeug_id, "2026-08-01", "Zählerstand", zaehlerstand=3100.0)

    punkte = fp.wartungsplan(conn, fp.get_fahrzeug(conn, fahrzeug_id), HEUTE)
    assert [(p["name"], p["status"]) for p in punkte] == [
        ("TÜV", "rot"), ("Inspektion", "grau"), ("Ölwechsel", "gruen"),
    ]
    assert fp.anzahl_ueberfaellig(conn, HEUTE) == 1


def test_umbenennen_nimmt_eintraege_mit(conn):
    fahrzeug_id = _fahrzeug(conn)
    andere_id = _fahrzeug(conn, "JD 6620")
    fp.save_aufgabe(conn, fahrzeug_id, None, "Ölwechsel", 500.0, None)
    _eintrag(conn, fahrzeug_id, "2026-07-01", "Ölwechsel", zaehlerstand=3077.0)
    _eintrag(conn, andere_id, "2026-07-01", "Ölwechsel", zaehlerstand=8213.0)
    aufgabe_id = fp.get_aufgaben(conn, fahrzeug_id)[0]["id"]

    assert fp.save_aufgabe(conn, fahrzeug_id, aufgabe_id, "Motoröl", 500.0, None) is None
    punkte = fp.wartungsplan(conn, fp.get_fahrzeug(conn, fahrzeug_id), HEUTE)
    assert punkte[0]["name"] == "Motoröl"
    assert punkte[0]["status"] != "grau"
    # Das andere Fahrzeug behält seinen Eintrag.
    assert fp.get_eintraege(conn, fahrzeug_id=str(andere_id))[0]["art"] == "Ölwechsel"


@pytest.mark.parametrize(
    "aufgabe, zaehler, monate, meldung",
    [
        ("", 500.0, None, "benennen"),
        ("Ölwechsel", None, None, "Intervall"),
        ("Ölwechsel", -1.0, None, "größer als 0"),
        ("Ölwechsel", None, 1.5, "ganze Zahl"),
    ],
)
def test_aufgabe_ungueltig(conn, aufgabe, zaehler, monate, meldung):
    fahrzeug_id = _fahrzeug(conn)
    assert meldung in fp.save_aufgabe(conn, fahrzeug_id, None, aufgabe, zaehler, monate)


def test_aufgabe_mit_zaehlerintervall_braucht_zaehler(conn):
    fahrzeug_id, _ = fp.save_fahrzeug(conn, None, {"name": "Kompressor"})
    assert "keinen Zähler" in fp.save_aufgabe(conn, fahrzeug_id, None, "Wartung", 1000.0, None)
