import sqlite3
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
