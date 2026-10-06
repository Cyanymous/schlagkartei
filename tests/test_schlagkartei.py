import json
import shutil
import zipfile
from pathlib import Path

import pytest

from app import schlagkartei as sk
from app.db import connect
from app.importer import import_exports

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def conn():
    c = connect(":memory:")
    yield c
    c.close()


def _kultur_id(conn, name):
    return conn.execute("SELECT id FROM kulturen WHERE name = ?", (name,)).fetchone()[0]


# --- Kulturen ---


def test_kulturen_sind_vorbelegt(conn):
    assert conn.execute("SELECT eppo_code FROM kulturen WHERE name = 'Winterweizen'").fetchone()[0] == "TRZAW"


def _import_mit_kultur(tmp_path, conn, name, eppo_code):
    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    with zipfile.ZipFile(FIXTURES / "2026-05-04-Benevia.zip") as zf:
        record = json.loads(zf.read(next(n for n in zf.namelist() if n.endswith(".json"))))
    record["guid"] = "test-" + name
    record["kulturen"][0]["name"] = name
    record["kulturen"][0]["eppoCode"] = eppo_code
    (export_dir / "x.json").write_text(json.dumps(record))
    import_exports(str(export_dir), conn)
    sk.kulturen_aus_import_uebernehmen(conn)


def test_neue_kultur_aus_import_wird_uebernommen(tmp_path, conn):
    _import_mit_kultur(tmp_path, conn, "Hopfen", "HUMLU")
    assert conn.execute("SELECT eppo_code FROM kulturen WHERE name = 'Hopfen'").fetchone()[0] == "HUMLU"


def test_import_erzeugt_keine_dublette_bei_bekanntem_eppo_code(tmp_path, conn):
    _import_mit_kultur(tmp_path, conn, "Bleichspargel", "ASPOF")
    assert conn.execute("SELECT COUNT(*) FROM kulturen WHERE eppo_code = 'ASPOF'").fetchone()[0] == 1


def test_import_ueberschreibt_eigene_kultur_nicht(tmp_path, conn):
    conn.execute("UPDATE kulturen SET eppo_code = 'XXXXX' WHERE name = 'Spargel'")
    _import_mit_kultur(tmp_path, conn, "Spargel", "ASPOF")
    assert conn.execute("SELECT eppo_code FROM kulturen WHERE name = 'Spargel'").fetchone()[0] == "XXXXX"


def test_verwendete_kultur_kann_nicht_geloescht_werden(conn):
    schlag_id, _ = sk.create_schlag(conn, "Hof", "Acker", 2020, "1", 2.0)
    kultur = _kultur_id(conn, "Hafer")
    conn.execute(
        "INSERT INTO anbau (schlag_id, jahr, kultur_id, art) VALUES (?, 2024, ?, 'Hauptkultur')",
        (schlag_id, kultur),
    )
    assert sk.delete_kultur(conn, kultur) is not None
    assert sk.delete_kultur(conn, _kultur_id(conn, "Sorghum")) is None


# --- Schläge und Stände ---


def test_stand_gilt_bis_zum_naechsten_stand(conn):
    schlag_id, fehler = sk.create_schlag(conn, "Hof", "Hinterm Hof", 2020, "22", 3.5)
    assert fehler is None
    sk.save_stand(conn, schlag_id, 2024, "22a", 3.1)

    assert sk.get_schlag(conn, schlag_id, 2023)["schlagnummer"] == "22"
    assert sk.get_schlag(conn, schlag_id, 2024)["schlagnummer"] == "22a"
    assert sk.get_schlag(conn, schlag_id, 2026)["groesse_ha"] == 3.1


def test_schlagnummer_ist_je_jahr_eindeutig(conn):
    sk.create_schlag(conn, "Hof", "Acker A", 2020, "5", 1.0)
    _, fehler = sk.create_schlag(conn, "Hof", "Acker B", 2022, "5", 1.0)
    assert fehler and "Acker A" in fehler


def test_schlag_fuer_nummer_beachtet_das_jahr(conn):
    a, _ = sk.create_schlag(conn, "Hof", "Acker A", 2020, "7", 1.0)
    sk.save_stand(conn, a, 2025, "70", 1.0)
    b, _ = sk.create_schlag(conn, "Hof", "Acker B", 2025, "7", 1.0)

    assert sk.schlag_fuer_nummer(conn, "7", 2024) == a
    assert sk.schlag_fuer_nummer(conn, "7", 2025) == b
    assert sk.schlag_fuer_nummer(conn, "70", 2026) == a


def test_letzter_stand_kann_nicht_geloescht_werden(conn):
    schlag_id, _ = sk.create_schlag(conn, "Hof", "Acker", 2020, "1", 1.0)
    stand_id = sk.get_staende(conn, schlag_id)[0]["id"]
    assert sk.delete_stand(conn, stand_id) is not None


# --- Anbau ---


def test_fruchtfolge_hinweis_bei_wiederholter_hauptkultur(conn):
    schlag_id, _ = sk.create_schlag(conn, "Hof", "Acker", 2020, "1", 2.0)
    weizen = _kultur_id(conn, "Winterweizen")
    sk.add_anbau(conn, schlag_id, 2024, 2027, weizen, "Hauptkultur", "")
    sk.add_anbau(conn, schlag_id, 2025, 2027, weizen, "Hauptkultur", "")
    sk.add_anbau(conn, schlag_id, 2025, 2027, _kultur_id(conn, "Phacelia"), "Zwischenfrucht", "")
    sk.add_anbau(conn, schlag_id, 2026, 2027, _kultur_id(conn, "Phacelia"), "Hauptkultur", "")

    wiederholt = sk.wiederholte_hauptkultur(sk.anbau_matrix(sk.get_anbau(conn)))
    # Zwischenfrucht im Vorjahr zählt nicht als Wiederholung
    assert wiederholt == {(schlag_id, 2025)}


def test_kein_fruchtfolge_hinweis_bei_mehrjaehriger_kultur(conn):
    schlag_id, _ = sk.create_schlag(conn, "Hof", "Spargelfeld", 2020, "1", 1.0)
    spargel = _kultur_id(conn, "Spargel")
    for jahr in (2024, 2025, 2026):
        sk.add_anbau(conn, schlag_id, jahr, 2027, spargel, "Hauptkultur", "")
    assert sk.wiederholte_hauptkultur(sk.anbau_matrix(sk.get_anbau(conn))) == set()


def test_anbau_nur_bis_zum_planungsjahr(conn):
    schlag_id, _ = sk.create_schlag(conn, "Hof", "Acker", 2020, "1", 2.0)
    hafer = _kultur_id(conn, "Hafer")
    assert sk.add_anbau(conn, schlag_id, 2028, 2027, hafer, "Hauptkultur", "") is not None
    assert sk.add_anbau(conn, schlag_id, 2019, 2027, hafer, "Hauptkultur", "") is not None
    assert sk.add_anbau(conn, schlag_id, 2027, 2027, hafer, "Hauptkultur", "") is None


def test_anbauumfang_nutzt_groesse_des_jeweiligen_jahres(conn):
    a, _ = sk.create_schlag(conn, "Hof", "Acker A", 2020, "1", 2.0)
    sk.save_stand(conn, a, 2025, "1", 2.5)
    b, _ = sk.create_schlag(conn, "Hof", "Acker B", 2020, "2", 1.0)
    hafer = _kultur_id(conn, "Hafer")
    for jahr in (2024, 2025):
        sk.add_anbau(conn, a, jahr, 2027, hafer, "Hauptkultur", "")
        sk.add_anbau(conn, b, jahr, 2027, hafer, "Hauptkultur", "")

    umfang = {(r["jahr"], r["kultur"]): r["ha"] for r in sk.anbauumfang(conn)}
    assert umfang == {(2024, "Hafer"): 3.0, (2025, "Hafer"): 3.5}


# --- Feldarbeiten ---


def test_feldarbeit_fuer_mehrere_schlaege(conn):
    a, _ = sk.create_schlag(conn, "Hof", "Acker A", 2020, "1", 1.0)
    b, _ = sk.create_schlag(conn, "Hof", "Acker B", 2020, "2", 1.0)
    c, _ = sk.create_schlag(conn, "Hof", "Acker C", 2020, "3", 1.0)
    fa_id, fehler = sk.save_feldarbeit(conn, None, "2026-09-08", "Scheiben", "Roggen scheiben", [a, b])
    assert fehler is None
    sk.save_feldarbeit(conn, None, "2025-04-01", "Walzen", "", [c])

    alle = sk.get_feldarbeiten(conn)
    assert [f["art"] for f in alle] == ["Scheiben", "Walzen"]  # neueste zuerst
    assert [s["name"] for s in alle[0]["schlaege"]] == ["Acker A", "Acker B"]

    assert [f["id"] for f in sk.get_feldarbeiten(conn, schlag_id=str(b))] == [fa_id]
    assert [f["art"] for f in sk.get_feldarbeiten(conn, jahr="2025")] == ["Walzen"]

    # Ändern ersetzt die Schlagauswahl
    sk.save_feldarbeit(conn, fa_id, "2026-09-08", "Scheiben", "", [c])
    assert sk.get_feldarbeit(conn, fa_id)[1] == {c}


def test_feldarbeit_pruefungen(conn):
    a, _ = sk.create_schlag(conn, "Hof", "Acker", 2020, "1", 1.0)
    assert sk.save_feldarbeit(conn, None, "08.09.2026", "Scheiben", "", [a])[1] is not None
    assert sk.save_feldarbeit(conn, None, "2026-09-08", " ", "", [a])[1] is not None
    assert sk.save_feldarbeit(conn, None, "2026-09-08", "Scheiben", "", [])[1] is not None
    assert conn.execute("SELECT COUNT(*) FROM feldarbeiten").fetchone()[0] == 0
