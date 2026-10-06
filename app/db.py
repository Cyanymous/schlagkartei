import sqlite3
from datetime import date
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    aktuell = conn.execute("PRAGMA user_version").fetchone()[0]
    for pfad in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = int(pfad.name.split("_", 1)[0])
        if version <= aktuell:
            continue
        conn.executescript(pfad.read_text())
        conn.execute(f"PRAGMA user_version = {version}")
    conn.commit()


BACKUPS_BEHALTEN = 30


def taegliche_sicherung(db_path: str, heute: date | None = None) -> None:
    """Legt einmal am Tag eine Kopie der Datenbank in backup/ neben der Datenbank an.

    Seit Stufe 2 stehen Schläge, Anbau und Feldarbeiten nur in der Datenbank.
    Die Kopie schützt vor versehentlichem Löschen in der App; die
    Serversicherung von data/ ersetzt sie nicht.
    """
    quelle = Path(db_path)
    if not quelle.is_file():
        return
    ordner = quelle.parent / "backup"
    ziel = ordner / f"{quelle.stem}-{(heute or date.today()).isoformat()}.db"
    if ziel.exists():
        return
    ordner.mkdir(exist_ok=True)

    # Über die Backup-API statt Dateikopie, damit auch eine gerade
    # schreibende Verbindung eine konsistente Kopie ergibt.
    zwischendatei = ziel.with_suffix(".tmp")
    src = sqlite3.connect(quelle)
    dst = sqlite3.connect(zwischendatei)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    zwischendatei.rename(ziel)

    for alt in sorted(ordner.glob(f"{quelle.stem}-*.db"))[:-BACKUPS_BEHALTEN]:
        alt.unlink()
