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
    fahrzeug_id = _fahrzeug(conn, kennzeichen=" HVL X 1 ", typ="")
    f = fp.get_fahrzeug(conn, fahrzeug_id)
    assert f["kennzeichen"] == "HVL X 1"
    assert f["typ"] is None
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
