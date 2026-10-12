"""SQL für den Fuhrpark (SPEC.md Abschnitt 13): Fahrzeuge, Fahrzeugbuch, Wartung."""

import re
import sqlite3

EINHEITEN = ["h", "km", "Stück"]


# --- Fahrzeuge --------------------------------------------------------------


def get_fahrzeuge(conn: sqlite3.Connection, nur_aktive: bool = False) -> list[sqlite3.Row]:
    bedingung = "WHERE f.aktiv = 1" if nur_aktive else ""
    return conn.execute(
        f"SELECT f.* FROM fahrzeuge f {bedingung} ORDER BY f.aktiv DESC, f.name"
    ).fetchall()


def get_fahrzeug(conn: sqlite3.Connection, fahrzeug_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM fahrzeuge WHERE id = ?", (fahrzeug_id,)).fetchone()


def save_fahrzeug(conn: sqlite3.Connection, fahrzeug_id: int | None, daten: dict) -> tuple[int | None, str | None]:
    """Legt ein Fahrzeug an (fahrzeug_id None) oder ändert es.

    `daten` hat die Spalten der Tabelle fahrzeuge (ohne id); Texte dürfen leer
    sein und werden dann als NULL gespeichert.
    """
    werte = {k: (v.strip() or None) if isinstance(v, str) else v for k, v in daten.items()}
    if not werte.get("name"):
        return None, "Bitte einen Namen angeben."
    if werte.get("einheit") not in [None, *EINHEITEN]:
        return None, "Unbekannte Zählereinheit."
    if werte.get("tank_liter") is not None and werte["tank_liter"] <= 0:
        return None, "Die Tankgröße muss größer als 0 sein."
    if werte.get("tuev_faellig") and not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", werte["tuev_faellig"]):
        return None, "Bitte die TÜV-Fälligkeit als Monat angeben."
    vorhanden = conn.execute(
        "SELECT id FROM fahrzeuge WHERE name = ? AND id IS NOT ?", (werte["name"], fahrzeug_id)
    ).fetchone()
    if vorhanden:
        return None, f"Das Fahrzeug „{werte['name']}“ gibt es schon."

    spalten = ["name", "typ", "kennzeichen", "oelfilter", "einheit", "tank_liter", "tuev_faellig", "bemerkung", "aktiv"]
    parameter = [werte.get(s) for s in spalten]
    parameter[-1] = int(werte.get("aktiv", True))
    if fahrzeug_id is None:
        fahrzeug_id = conn.execute(
            f"INSERT INTO fahrzeuge ({', '.join(spalten)}) VALUES ({', '.join('?' * len(spalten))})", parameter
        ).lastrowid
    else:
        conn.execute(
            f"UPDATE fahrzeuge SET {', '.join(s + ' = ?' for s in spalten)} WHERE id = ?", (*parameter, fahrzeug_id)
        )
    conn.commit()
    return fahrzeug_id, None
