import json
import shutil
import zipfile
from pathlib import Path

import pytest

from app.db import connect
from app.importer import import_exports

FIXTURES = Path(__file__).parent / "fixtures"

# Die Fixtures wurden mit demselben PSM-DOK-Benutzerkonto erzeugt und teilen
# sich deshalb dieselbe betrieb.guid; in echten Exporten unterscheidet sie
# sich je Betrieb.
GEMEINSAME_GUID = "75176d09-ae04-41ae-859a-26381a5b54c7"


@pytest.fixture
def conn():
    c = connect(":memory:")
    yield c
    c.close()


@pytest.fixture
def export_dir(tmp_path):
    ziel = tmp_path / "exports"
    ziel.mkdir()
    for pfad in FIXTURES.glob("*.zip"):
        shutil.copy(pfad, ziel)
    return ziel


def test_import_liest_beide_fixtures_korrekt(conn, export_dir):
    import_exports(export_dir, conn, {})
    rows = conn.execute("SELECT * FROM applications ORDER BY datum").fetchall()
    assert len(rows) == 2

    benevia = rows[0]
    assert benevia["datum"] == "2026-05-04"
    assert benevia["jahr"] == 2026
    assert benevia["uhrzeit"] == "21:00"
    assert benevia["anwender"] == "Hans Vader"
    assert benevia["betrieb"] == "Testunternehmen"

    mittel = conn.execute(
        "SELECT * FROM anwendung_mittel WHERE application_id = ?", (benevia["id"],)
    ).fetchall()
    assert len(mittel) == 1
    assert mittel[0]["name"] == "BENEVIA"
    assert mittel[0]["zulassungsnr"] == "00A175-00"
    assert mittel[0]["aufwand_menge"] == 0.7

    kulturen = conn.execute(
        "SELECT * FROM anwendung_kulturen WHERE application_id = ?", (benevia["id"],)
    ).fetchall()
    assert kulturen[0]["name"] == "Spargel"
    assert kulturen[0]["eppo_code"] == "ASPOF"
    assert kulturen[0]["bbch_code"] == "19"

    einsatzorte = conn.execute(
        "SELECT * FROM anwendung_einsatzorte WHERE application_id = ?", (benevia["id"],)
    ).fetchall()
    assert einsatzorte[0]["geo_typ"] == "Schlag-ID"
    assert einsatzorte[0]["geo_wert"] == "1"
    assert einsatzorte[0]["flaeche_volumen"] == 1.15

    mospilan = rows[1]
    assert mospilan["betrieb"] == "Hofladen Lietzow"
    assert mospilan["anwender"] == "Peter Horst"


def test_betrieb_zuordnung_per_guid_hat_vorrang_vor_firma(conn, export_dir):
    import_exports(export_dir, conn, {GEMEINSAME_GUID: "Hof Nord"})
    betriebe = {r[0] for r in conn.execute("SELECT DISTINCT betrieb FROM applications")}
    assert betriebe == {"Hof Nord"}


def test_ohne_zuordnung_fallback_auf_firma(conn, export_dir):
    import_exports(export_dir, conn, {})
    betriebe = {r[0] for r in conn.execute("SELECT DISTINCT betrieb FROM applications")}
    assert betriebe == {"Testunternehmen", "Hofladen Lietzow"}


def test_erneuter_import_erzeugt_keine_duplikate(conn, export_dir):
    import_exports(export_dir, conn, {})
    import_exports(export_dir, conn, {})
    assert conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM import_files").fetchone()[0] == 2


def test_ueberlappender_export_dedupliziert_ueber_guid(conn, export_dir):
    quelle = next(export_dir.glob("*Benevia*"))
    with zipfile.ZipFile(quelle) as zf:
        json_name = next(n for n in zf.namelist() if n.endswith(".json"))
        inhalt = zf.read(json_name)

    with zipfile.ZipFile(export_dir / "ueberlappend.zip", "w") as zf:
        zf.writestr(Path(json_name).name, inhalt)

    import_exports(export_dir, conn, {})
    assert conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0] == 2
    dateien = {r[0]: r[1] for r in conn.execute("SELECT dateiname, status FROM import_files")}
    assert dateien["ueberlappend.zip"] == "ok"


def test_defekte_zip_wird_als_fehler_vermerkt_andere_bleiben_unberuehrt(conn, export_dir):
    (export_dir / "defekt.zip").write_bytes(b"das ist keine ZIP-Datei")
    import_exports(export_dir, conn, {})
    status = {r[0]: r[1] for r in conn.execute("SELECT dateiname, status FROM import_files")}
    assert status["defekt.zip"] == "fehler"
    assert conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0] == 2


def test_zip_ohne_json_wird_als_fehler_vermerkt(conn, export_dir):
    with zipfile.ZipFile(export_dir / "ohne_json.zip", "w") as zf:
        zf.writestr("leer.pdf", b"%PDF-1.4 Platzhalter")

    import_exports(export_dir, conn, {})
    status = {r[0]: r[1] for r in conn.execute("SELECT dateiname, status FROM import_files")}
    assert status["ohne_json.zip"] == "fehler"


def test_zip_mit_pdf_wird_normal_importiert_pdf_wird_nicht_angefasst(conn, export_dir):
    quelle = next(export_dir.glob("*Benevia*"))
    with zipfile.ZipFile(quelle) as zf:
        json_name = next(n for n in zf.namelist() if n.endswith(".json"))
        record = json.loads(zf.read(json_name))
    record["guid"] = "11111111-1111-1111-1111-111111111111"

    with zipfile.ZipFile(export_dir / "mit_pdf.zip", "w") as zf:
        zf.writestr("mit_pdf.json", json.dumps(record))
        zf.writestr("mit_pdf.pdf", b"%PDF-1.4 Platzhalter")

    import_exports(export_dir, conn, {})
    status = {r[0]: r[1] for r in conn.execute("SELECT dateiname, status FROM import_files")}
    assert status["mit_pdf.zip"] == "ok"
    assert conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0] == 3


def test_exportordner_bleibt_unveraendert(conn, export_dir):
    vorher = {p.name: p.read_bytes() for p in export_dir.glob("*.zip")}
    import_exports(export_dir, conn, {})
    nachher = {p.name: p.read_bytes() for p in export_dir.glob("*.zip")}
    assert vorher == nachher
    assert {p.name for p in export_dir.iterdir()} == set(vorher)


def test_korrigierter_eintrag_aktualisiert_bestehende_zeile(conn, export_dir):
    quelle = next(export_dir.glob("*Benevia*"))
    with zipfile.ZipFile(quelle) as zf:
        json_name = next(n for n in zf.namelist() if n.endswith(".json"))
        record = json.loads(zf.read(json_name))

    import_exports(export_dir, conn, {})
    vorher = conn.execute("SELECT id, zuerst_gesehen_am FROM applications WHERE datensatz_key = ?", (record["guid"],)).fetchone()

    record["anwendung"]["uhrzeit"] = "22:00"
    with zipfile.ZipFile(export_dir / "korrektur.zip", "w") as zf:
        zf.writestr(json_name, json.dumps(record))

    import_exports(export_dir, conn, {})
    assert conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0] == 2
    nachher = conn.execute("SELECT id, uhrzeit, zuerst_gesehen_am, geaendert_am FROM applications WHERE datensatz_key = ?", (record["guid"],)).fetchone()
    assert nachher["id"] == vorher["id"]
    assert nachher["uhrzeit"] == "22:00"
    assert nachher["zuerst_gesehen_am"] == vorher["zuerst_gesehen_am"]
    assert nachher["geaendert_am"] is not None


def test_notiz_bleibt_bei_korrigiertem_reimport_erhalten(tmp_path):
    from app.queries import save_notiz

    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    shutil.copy(FIXTURES / "2026-05-04-Benevia.zip", export_dir)
    conn = connect(str(tmp_path / "db.sqlite"))
    import_exports(str(export_dir), conn)
    app_id = conn.execute("SELECT id FROM applications").fetchone()[0]
    save_notiz(conn, app_id, "meine Notiz", "2026-10-06T08:00:00+00:00")

    # Gleiche guid, geänderter Inhalt -> Importer aktualisiert die Anwendung.
    with zipfile.ZipFile(FIXTURES / "2026-05-04-Benevia.zip") as zf:
        name = next(n for n in zf.namelist() if n.endswith(".json"))
        record = json.loads(zf.read(name))
    record["anwendung"]["anwender"] = "Korrigiert"
    (export_dir / "korrektur.json").write_text(json.dumps(record))
    import_exports(str(export_dir), conn)

    assert conn.execute("SELECT anwender FROM applications").fetchone()[0] == "Korrigiert"
    assert conn.execute("SELECT text FROM notizen").fetchone()[0] == "meine Notiz"


def _benevia_record(export_dir):
    with zipfile.ZipFile(next(export_dir.glob("*Benevia*"))) as zf:
        return json.loads(zf.read(next(n for n in zf.namelist() if n.endswith(".json"))))


def test_entfernte_datei_entfernt_ihre_anwendung_samt_notiz(conn, export_dir):
    from app.queries import save_notiz

    import_exports(export_dir, conn, {})
    benevia_id = conn.execute(
        "SELECT a.id FROM applications a JOIN anwendung_mittel m ON m.application_id = a.id WHERE m.name = 'BENEVIA'"
    ).fetchone()[0]
    save_notiz(conn, benevia_id, "versehentlich", "2026-10-06T08:00:00+00:00")

    next(export_dir.glob("*Benevia*")).unlink()
    ergebnis = import_exports(export_dir, conn, {})

    assert {"dateiname": "2026-05-04-Benevia.zip", "status": "entfernt"} in ergebnis
    assert conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM anwendung_mittel WHERE name = 'BENEVIA'").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM notizen").fetchone()[0] == 0
    assert [r[0] for r in conn.execute("SELECT dateiname FROM import_files")] == ["2026-05-24 Mospilan.zip"]

    # Datei wieder zurücklegen: Anwendung ist wieder da.
    shutil.copy(FIXTURES / "2026-05-04-Benevia.zip", export_dir)
    import_exports(export_dir, conn, {})
    assert conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0] == 2


def test_anwendung_bleibt_wenn_sie_noch_in_anderer_datei_steht(conn, export_dir):
    guid = _benevia_record(export_dir)["guid"]
    (export_dir / "kopie.json").write_text(json.dumps(_benevia_record(export_dir)))
    import_exports(export_dir, conn, {})

    # Die Datei entfernen, auf die die Anwendung gerade zeigt.
    datei = conn.execute(
        """SELECT f.dateiname FROM applications a JOIN import_files f ON f.id = a.import_file_id
           WHERE a.datensatz_key = ?""",
        (guid,),
    ).fetchone()[0]
    (export_dir / datei).unlink()
    import_exports(export_dir, conn, {})

    assert conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0] == 2
    verbleibend = conn.execute(
        """SELECT f.dateiname FROM applications a JOIN import_files f ON f.id = a.import_file_id
           WHERE a.datensatz_key = ?""",
        (guid,),
    ).fetchone()[0]
    assert verbleibend != datei
    assert conn.execute("SELECT COUNT(*) FROM anwendung_mittel WHERE name = 'BENEVIA'").fetchone()[0] == 1


def test_entfernte_korrektur_stellt_vorige_fassung_wieder_her(conn, export_dir):
    import_exports(export_dir, conn, {})
    korrektur = _benevia_record(export_dir)
    korrektur["anwendung"]["anwender"] = "Korrigiert"
    (export_dir / "zz-korrektur.json").write_text(json.dumps(korrektur))
    import_exports(export_dir, conn, {})
    assert conn.execute("SELECT COUNT(*) FROM applications WHERE anwender = 'Korrigiert'").fetchone()[0] == 1

    (export_dir / "zz-korrektur.json").unlink()
    import_exports(export_dir, conn, {})
    assert conn.execute("SELECT COUNT(*) FROM applications WHERE anwender = 'Korrigiert'").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0] == 2
