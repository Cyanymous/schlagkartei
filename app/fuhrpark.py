"""SQL für den Fuhrpark (SPEC.md Abschnitt 13): Fahrzeuge, Fahrzeugbuch, Wartung."""

import re
import sqlite3
from datetime import date

EINHEITEN = ["h", "km", "Stück"]
# Vorschläge für das Feld „Art“, ergänzt um alles, was schon erfasst wurde.
ARTEN = ["Tanken", "Zählerstand", "Ölwechsel", "Inspektion", "Reparatur", "TÜV"]
PROZENTE = list(range(10, 101, 10))

# Der aktuelle Stand ist der Zählerstand des neuesten Eintrags, der einen hat.
_STAND = """(SELECT e.{spalte} FROM fahrzeug_eintraege e
             WHERE e.fahrzeug_id = f.id AND e.zaehlerstand IS NOT NULL
             ORDER BY e.datum DESC, e.id DESC LIMIT 1)"""
_MIT_STAND = f"""f.*, {_STAND.format(spalte="zaehlerstand")} AS stand,
                 {_STAND.format(spalte="datum")} AS stand_datum"""


def zahl_de(wert: float | None) -> str:
    """Zählerstände und Liter wie in der Tabelle gewohnt: 150.637 bzw. 69,6."""
    if wert is None:
        return ""
    text = f"{wert:,.1f}".removesuffix(".0")
    return text.replace(",", " ").replace(".", ",").replace(" ", ".")


# --- Fahrzeuge --------------------------------------------------------------


def get_fahrzeuge(conn: sqlite3.Connection, nur_aktive: bool = False) -> list[sqlite3.Row]:
    bedingung = "WHERE f.aktiv = 1" if nur_aktive else ""
    return conn.execute(
        f"SELECT {_MIT_STAND} FROM fahrzeuge f {bedingung} ORDER BY f.aktiv DESC, f.name"
    ).fetchall()


def get_fahrzeug(conn: sqlite3.Connection, fahrzeug_id: int) -> sqlite3.Row | None:
    return conn.execute(f"SELECT {_MIT_STAND} FROM fahrzeuge f WHERE f.id = ?", (fahrzeug_id,)).fetchone()


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


# --- Fahrzeugbuch -----------------------------------------------------------


def get_arten(conn: sqlite3.Connection) -> list[str]:
    erfasst = {r[0] for r in conn.execute("SELECT art FROM fahrzeug_eintraege UNION SELECT aufgabe FROM wartungsaufgaben")}
    return sorted(set(ARTEN) | erfasst)


def get_eintraege(
    conn: sqlite3.Connection, fahrzeug_id: str = "", jahr: str = "", art: str = ""
) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT e.*, f.name AS fahrzeug, f.einheit
           FROM fahrzeug_eintraege e JOIN fahrzeuge f ON f.id = e.fahrzeug_id
           WHERE (:fahrzeug = '' OR e.fahrzeug_id = :fahrzeug)
             AND (:jahr = '' OR substr(e.datum, 1, 4) = :jahr)
             AND (:art = '' OR e.art = :art)
           ORDER BY e.datum DESC, e.id DESC""",
        {"fahrzeug": fahrzeug_id, "jahr": jahr, "art": art},
    ).fetchall()


def get_eintrag_jahre(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT DISTINCT substr(datum, 1, 4) FROM fahrzeug_eintraege ORDER BY 1 DESC"
    )]


def get_eintrag(conn: sqlite3.Connection, eintrag_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM fahrzeug_eintraege WHERE id = ?", (eintrag_id,)).fetchone()


def tankmenge(
    tank_liter: float | None, prozent: int | None, liter: float | None
) -> tuple[float | None, int | None, str | None]:
    """Liter und Prozent, wie sie gespeichert werden, oder eine Fehlermeldung.

    Genaue Liter vom Beleg haben Vorrang. Sonst werden die Liter aus Prozent
    und Tankgröße geschätzt, weil der Hoftank keine Messuhr hat.
    """
    if liter is not None:
        if liter <= 0:
            return None, None, "Die Liter müssen größer als 0 sein."
        return liter, None, None
    if prozent is None:
        return None, None, None
    if prozent not in PROZENTE:
        return None, None, "Unbekannter Prozentwert."
    if not tank_liter:
        return None, None, (
            "Für dieses Fahrzeug ist keine Tankgröße hinterlegt. Bitte die Liter eintragen "
            "oder die Tankgröße in den Stammdaten ergänzen."
        )
    return round(tank_liter * prozent / 100, 1), prozent, None


def save_eintrag(conn: sqlite3.Connection, eintrag_id: int | None, daten: dict) -> tuple[int | None, str | None]:
    """Legt einen Eintrag im Fahrzeugbuch an (eintrag_id None) oder ändert ihn.

    `daten`: fahrzeug_id, datum, art, zaehlerstand, prozent, liter, beleg, bemerkung.
    """
    fahrzeug = get_fahrzeug(conn, daten["fahrzeug_id"]) if daten.get("fahrzeug_id") else None
    if fahrzeug is None:
        return None, "Bitte ein Fahrzeug auswählen."
    try:
        date.fromisoformat(daten.get("datum", ""))
    except ValueError:
        return None, "Bitte ein gültiges Datum angeben."
    art = (daten.get("art") or "").strip()
    if not art:
        return None, "Bitte die Art des Eintrags angeben."
    stand = daten.get("zaehlerstand")
    if stand is not None and not fahrzeug["einheit"]:
        return None, f"„{fahrzeug['name']}“ hat keinen Zähler. Zählereinheit in den Stammdaten eintragen."
    if stand is not None and stand < 0:
        return None, "Der Zählerstand darf nicht negativ sein."
    liter, prozent, fehler = tankmenge(fahrzeug["tank_liter"], daten.get("prozent"), daten.get("liter"))
    if fehler:
        return None, fehler

    werte = (
        fahrzeug["id"], daten["datum"], art, stand, liter, prozent,
        (daten.get("beleg") or "").strip() or None, (daten.get("bemerkung") or "").strip() or None,
    )
    if eintrag_id is None:
        eintrag_id = conn.execute(
            """INSERT INTO fahrzeug_eintraege
               (fahrzeug_id, datum, art, zaehlerstand, liter, prozent, beleg, bemerkung)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            werte,
        ).lastrowid
    else:
        conn.execute(
            """UPDATE fahrzeug_eintraege SET fahrzeug_id = ?, datum = ?, art = ?, zaehlerstand = ?,
                   liter = ?, prozent = ?, beleg = ?, bemerkung = ?
               WHERE id = ?""",
            (*werte, eintrag_id),
        )
    conn.commit()
    return eintrag_id, None


def zaehlerstand_hinweis(conn: sqlite3.Connection, eintrag_id: int) -> str | None:
    """Warnt, wenn ein Stand kleiner ist als ein früherer desselben Fahrzeugs.

    Kein Fehler, weil Zähler getauscht werden können – aber meist ein Tippfehler.
    """
    e = get_eintrag(conn, eintrag_id)
    if e is None or e["zaehlerstand"] is None:
        return None
    frueher = conn.execute(
        """SELECT datum, zaehlerstand FROM fahrzeug_eintraege
           WHERE fahrzeug_id = ? AND id != ? AND datum <= ? AND zaehlerstand > ?
           ORDER BY zaehlerstand DESC LIMIT 1""",
        (e["fahrzeug_id"], e["id"], e["datum"], e["zaehlerstand"]),
    ).fetchone()
    if frueher is None:
        return None
    return (
        f"Achtung: Der Zählerstand ist kleiner als am {date.fromisoformat(frueher['datum']):%d.%m.%Y} "
        f"({zahl_de(frueher['zaehlerstand'])}). Bitte prüfen."
    )


def delete_eintrag(conn: sqlite3.Connection, eintrag_id: int) -> None:
    conn.execute("DELETE FROM fahrzeug_eintraege WHERE id = ?", (eintrag_id,))
    conn.commit()
