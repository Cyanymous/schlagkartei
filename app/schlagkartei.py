"""SQL für die Schlagkartei (Stufe 2): Schläge, Kulturen, Anbau, Feldarbeiten."""

import sqlite3

ERSTES_JAHR = 2020
ANBAU_ARTEN = ["Hauptkultur", "Zwischenfrucht", "Untersaat", "Zweitfrucht"]

# Der jeweils gültige Stand eines Schlags in einem Jahr: der neueste Stand,
# der in diesem Jahr oder davor begonnen hat.
_STAND = """
    SELECT {spalte} FROM schlag_staende st
    WHERE st.schlag_id = s.id AND st.ab_jahr <= :jahr
    ORDER BY st.ab_jahr DESC LIMIT 1
"""


# --- Kulturen ---------------------------------------------------------------


def get_kulturen(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT k.*, (SELECT COUNT(*) FROM anbau a WHERE a.kultur_id = k.id) AS verwendet
           FROM kulturen k ORDER BY k.name"""
    ).fetchall()


def save_kultur(
    conn: sqlite3.Connection, kultur_id: int | None, name: str, eppo_code: str, mehrjaehrig: bool = False
) -> str | None:
    """Gibt eine Fehlermeldung zurück oder None."""
    name = name.strip()
    eppo_code = eppo_code.strip().upper() or None
    if not name:
        return "Bitte einen Namen angeben."
    vorhanden = conn.execute(
        "SELECT id FROM kulturen WHERE name = ? AND id IS NOT ?", (name, kultur_id)
    ).fetchone()
    if vorhanden:
        return f"Die Kultur „{name}“ gibt es schon."
    if kultur_id is None:
        conn.execute(
            "INSERT INTO kulturen (name, eppo_code, mehrjaehrig) VALUES (?, ?, ?)",
            (name, eppo_code, int(mehrjaehrig)),
        )
    else:
        conn.execute(
            "UPDATE kulturen SET name = ?, eppo_code = ?, mehrjaehrig = ? WHERE id = ?",
            (name, eppo_code, int(mehrjaehrig), kultur_id),
        )
    conn.commit()
    return None


def delete_kultur(conn: sqlite3.Connection, kultur_id: int) -> str | None:
    if conn.execute("SELECT 1 FROM anbau WHERE kultur_id = ?", (kultur_id,)).fetchone():
        return "Die Kultur wird im Anbauplan verwendet und kann nicht gelöscht werden."
    conn.execute("DELETE FROM kulturen WHERE id = ?", (kultur_id,))
    conn.commit()
    return None


def kulturen_aus_import_uebernehmen(conn: sqlite3.Connection) -> None:
    """Übernimmt Kulturen aus den PSM-DOK-Exporten in die eigene Liste.

    Nur Kulturen, deren Name und EPPO-Code beide noch unbekannt sind: so
    entstehen keine Dubletten zur Vorbelegung, und eigene Einträge werden
    nie überschrieben.
    """
    conn.execute(
        """INSERT INTO kulturen (name, eppo_code)
           SELECT name, MAX(eppo_code) FROM anwendung_kulturen ak
           WHERE name IS NOT NULL
             AND NOT EXISTS (SELECT 1 FROM kulturen k WHERE k.name = ak.name)
             AND (ak.eppo_code IS NULL
                  OR NOT EXISTS (SELECT 1 FROM kulturen k WHERE k.eppo_code = ak.eppo_code))
           GROUP BY name"""
    )
    conn.commit()


# --- Schläge ----------------------------------------------------------------


def get_betriebe(conn: sqlite3.Connection) -> list[str]:
    return [
        r[0]
        for r in conn.execute(
            "SELECT betrieb FROM applications UNION SELECT betrieb FROM schlaege ORDER BY 1"
        )
    ]


def get_schlaege(conn: sqlite3.Connection, jahr: int, nur_aktive: bool = False) -> list[sqlite3.Row]:
    """Alle Schläge mit Schlagnummer und Größe, wie sie im Jahr `jahr` gelten."""
    bedingung = "WHERE s.aktiv = 1" if nur_aktive else ""
    return conn.execute(
        f"""SELECT s.*,
               ({_STAND.format(spalte="schlagnummer")}) AS schlagnummer,
               ({_STAND.format(spalte="groesse_ha")}) AS groesse_ha
           FROM schlaege s {bedingung}
           ORDER BY s.betrieb, s.name""",
        {"jahr": jahr},
    ).fetchall()


def get_schlag(conn: sqlite3.Connection, schlag_id: int, jahr: int) -> sqlite3.Row | None:
    return conn.execute(
        f"""SELECT s.*,
               ({_STAND.format(spalte="schlagnummer")}) AS schlagnummer,
               ({_STAND.format(spalte="groesse_ha")}) AS groesse_ha
           FROM schlaege s WHERE s.id = :id""",
        {"jahr": jahr, "id": schlag_id},
    ).fetchone()


def get_staende(conn: sqlite3.Connection, schlag_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM schlag_staende WHERE schlag_id = ? ORDER BY ab_jahr", (schlag_id,)
    ).fetchall()


def schlag_fuer_nummer(conn: sqlite3.Connection, schlagnummer: str, jahr: int) -> int | None:
    """Welcher Schlag trägt diese Schlagnummer im Jahr `jahr`?"""
    row = conn.execute(
        f"""SELECT s.id FROM schlaege s
           WHERE ({_STAND.format(spalte="schlagnummer")}) = :nummer""",
        {"jahr": jahr, "nummer": schlagnummer},
    ).fetchone()
    return row[0] if row else None


def _pruefe_stand(conn, schlag_id, ab_jahr, schlagnummer, groesse) -> str | None:
    if not schlagnummer:
        return "Bitte eine Schlagnummer angeben."
    if ab_jahr < ERSTES_JAHR or ab_jahr > 2100:
        return f"Das Jahr muss ab {ERSTES_JAHR} liegen."
    if groesse is not None and groesse < 0:
        return "Die Größe darf nicht negativ sein."
    anderer = schlag_fuer_nummer(conn, schlagnummer, ab_jahr)
    if anderer is not None and anderer != schlag_id:
        name = conn.execute("SELECT name FROM schlaege WHERE id = ?", (anderer,)).fetchone()[0]
        return f"Schlagnummer {schlagnummer} gehört {ab_jahr} schon zum Schlag „{name}“."
    return None


def create_schlag(
    conn: sqlite3.Connection, betrieb: str, name: str, ab_jahr: int, schlagnummer: str, groesse: float | None
) -> tuple[int | None, str | None]:
    if not betrieb.strip() or not name.strip():
        return None, "Bitte Betrieb und Namen angeben."
    fehler = _pruefe_stand(conn, None, ab_jahr, schlagnummer.strip(), groesse)
    if fehler:
        return None, fehler
    schlag_id = conn.execute(
        "INSERT INTO schlaege (betrieb, name) VALUES (?, ?)", (betrieb.strip(), name.strip())
    ).lastrowid
    conn.execute(
        "INSERT INTO schlag_staende (schlag_id, ab_jahr, schlagnummer, groesse_ha) VALUES (?, ?, ?, ?)",
        (schlag_id, ab_jahr, schlagnummer.strip(), groesse),
    )
    conn.commit()
    return schlag_id, None


def update_schlag(conn: sqlite3.Connection, schlag_id: int, betrieb: str, name: str, aktiv: bool) -> str | None:
    if not betrieb.strip() or not name.strip():
        return "Bitte Betrieb und Namen angeben."
    conn.execute(
        "UPDATE schlaege SET betrieb = ?, name = ?, aktiv = ? WHERE id = ?",
        (betrieb.strip(), name.strip(), int(aktiv), schlag_id),
    )
    conn.commit()
    return None


def save_stand(
    conn: sqlite3.Connection, schlag_id: int, ab_jahr: int, schlagnummer: str, groesse: float | None
) -> str | None:
    """Legt einen Stand an oder überschreibt den Stand desselben Jahres."""
    fehler = _pruefe_stand(conn, schlag_id, ab_jahr, schlagnummer.strip(), groesse)
    if fehler:
        return fehler
    conn.execute(
        """INSERT INTO schlag_staende (schlag_id, ab_jahr, schlagnummer, groesse_ha) VALUES (?, ?, ?, ?)
           ON CONFLICT (schlag_id, ab_jahr) DO UPDATE SET
               schlagnummer = excluded.schlagnummer, groesse_ha = excluded.groesse_ha""",
        (schlag_id, ab_jahr, schlagnummer.strip(), groesse),
    )
    conn.commit()
    return None


def delete_stand(conn: sqlite3.Connection, stand_id: int) -> str | None:
    stand = conn.execute("SELECT schlag_id FROM schlag_staende WHERE id = ?", (stand_id,)).fetchone()
    if stand is None:
        return None
    anzahl = conn.execute(
        "SELECT COUNT(*) FROM schlag_staende WHERE schlag_id = ?", (stand["schlag_id"],)
    ).fetchone()[0]
    if anzahl <= 1:
        return "Der letzte Stand eines Schlags kann nicht gelöscht werden."
    conn.execute("DELETE FROM schlag_staende WHERE id = ?", (stand_id,))
    conn.commit()
    return None


# --- Anbau ------------------------------------------------------------------


def get_anbau(conn: sqlite3.Connection, schlag_id: int | None = None) -> list[sqlite3.Row]:
    bedingung = "WHERE a.schlag_id = :schlag_id" if schlag_id is not None else ""
    return conn.execute(
        f"""SELECT a.*, k.name AS kultur, k.eppo_code, k.mehrjaehrig
           FROM anbau a JOIN kulturen k ON k.id = a.kultur_id
           {bedingung}
           ORDER BY a.jahr,
               CASE a.art WHEN 'Hauptkultur' THEN 1 WHEN 'Untersaat' THEN 2
                          WHEN 'Zweitfrucht' THEN 3 ELSE 4 END,
               k.name""",
        {"schlag_id": schlag_id},
    ).fetchall()


def anbau_matrix(anbau: list[sqlite3.Row]) -> dict[tuple[int, int], list[sqlite3.Row]]:
    """Ordnet die Einträge nach (schlag_id, jahr) für die Tabelle Schläge × Jahre."""
    matrix: dict[tuple[int, int], list[sqlite3.Row]] = {}
    for eintrag in anbau:
        matrix.setdefault((eintrag["schlag_id"], eintrag["jahr"]), []).append(eintrag)
    return matrix


def wiederholte_hauptkultur(matrix: dict[tuple[int, int], list[sqlite3.Row]]) -> set[tuple[int, int]]:
    """Zellen, deren Hauptkultur schon im Vorjahr auf demselben Schlag stand.

    Mehrjährige Kulturen zählen nicht, sie stehen gewollt mehrere Jahre.
    """
    def hauptkulturen(schluessel):
        return {
            e["kultur_id"]
            for e in matrix.get(schluessel, [])
            if e["art"] == "Hauptkultur" and not e["mehrjaehrig"]
        }

    treffer = set()
    for schlag_id, jahr in matrix:
        if hauptkulturen((schlag_id, jahr)) & hauptkulturen((schlag_id, jahr - 1)):
            treffer.add((schlag_id, jahr))
    return treffer


def anbauumfang(conn: sqlite3.Connection, betrieb: str = "") -> list[sqlite3.Row]:
    """Summe der Fläche je Betrieb, Jahr und Hauptkultur."""
    return conn.execute(
        """SELECT s.betrieb, a.jahr, k.name AS kultur,
               SUM((SELECT st.groesse_ha FROM schlag_staende st
                    WHERE st.schlag_id = a.schlag_id AND st.ab_jahr <= a.jahr
                    ORDER BY st.ab_jahr DESC LIMIT 1)) AS ha
           FROM anbau a
           JOIN kulturen k ON k.id = a.kultur_id
           JOIN schlaege s ON s.id = a.schlag_id
           WHERE a.art = 'Hauptkultur' AND (:betrieb = '' OR s.betrieb = :betrieb)
           GROUP BY s.betrieb, a.jahr, k.name
           ORDER BY s.betrieb, k.name, a.jahr""",
        {"betrieb": betrieb},
    ).fetchall()


def _pruefe_anbau(conn, jahr, letztes_jahr, kultur_id, art) -> str | None:
    if not ERSTES_JAHR <= jahr <= letztes_jahr:
        return f"Anbau kann nur für {ERSTES_JAHR} bis {letztes_jahr} erfasst werden."
    if art not in ANBAU_ARTEN:
        return "Unbekannte Art."
    if not conn.execute("SELECT 1 FROM kulturen WHERE id = ?", (kultur_id,)).fetchone():
        return "Bitte eine Kultur auswählen."
    return None


def add_anbau(
    conn: sqlite3.Connection, schlag_id: int, jahr: int, letztes_jahr: int, kultur_id: int, art: str, bemerkung: str
) -> str | None:
    fehler = _pruefe_anbau(conn, jahr, letztes_jahr, kultur_id, art)
    if fehler:
        return fehler
    conn.execute(
        "INSERT INTO anbau (schlag_id, jahr, kultur_id, art, bemerkung) VALUES (?, ?, ?, ?, ?)",
        (schlag_id, jahr, kultur_id, art, bemerkung.strip() or None),
    )
    conn.commit()
    return None


def update_anbau(
    conn: sqlite3.Connection, anbau_id: int, letztes_jahr: int, kultur_id: int, art: str, bemerkung: str
) -> str | None:
    eintrag = conn.execute("SELECT jahr FROM anbau WHERE id = ?", (anbau_id,)).fetchone()
    if eintrag is None:
        return None
    fehler = _pruefe_anbau(conn, eintrag["jahr"], letztes_jahr, kultur_id, art)
    if fehler:
        return fehler
    conn.execute(
        "UPDATE anbau SET kultur_id = ?, art = ?, bemerkung = ? WHERE id = ?",
        (kultur_id, art, bemerkung.strip() or None, anbau_id),
    )
    conn.commit()
    return None


def delete_anbau(conn: sqlite3.Connection, anbau_id: int) -> None:
    conn.execute("DELETE FROM anbau WHERE id = ?", (anbau_id,))
    conn.commit()
