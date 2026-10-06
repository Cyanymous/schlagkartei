from datetime import date, timedelta

from app.db import BACKUPS_BEHALTEN, connect, taegliche_sicherung


def test_sicherung_einmal_pro_tag_und_alte_werden_entfernt(tmp_path):
    db = tmp_path / "schlagkartei.db"
    conn = connect(str(db))
    conn.execute("INSERT INTO kulturen (name) VALUES ('Testkultur')")
    conn.commit()
    conn.close()

    start = date(2026, 1, 1)
    for tag in range(BACKUPS_BEHALTEN + 5):
        taegliche_sicherung(str(db), start + timedelta(days=tag))
        taegliche_sicherung(str(db), start + timedelta(days=tag))  # zweiter Aufruf am selben Tag: nichts

    dateien = sorted((tmp_path / "backup").glob("*.db"))
    assert len(dateien) == BACKUPS_BEHALTEN
    assert dateien[0].name == "schlagkartei-2026-01-06.db"
    assert not list((tmp_path / "backup").glob("*.tmp"))

    kopie = connect(str(dateien[-1]))
    assert kopie.execute("SELECT 1 FROM kulturen WHERE name = 'Testkultur'").fetchone()


def test_keine_sicherung_ohne_datenbankdatei(tmp_path):
    taegliche_sicherung(str(tmp_path / "gibtsnicht.db"))
    assert not (tmp_path / "backup").exists()
