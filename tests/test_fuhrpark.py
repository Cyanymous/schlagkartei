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
