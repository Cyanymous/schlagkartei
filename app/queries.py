import sqlite3


def _build_where(filters: dict) -> tuple[str, list]:
    bedingungen = ["1=1"]
    parameter: list = []

    if filters.get("jahr"):
        bedingungen.append("a.jahr = ?")
        parameter.append(int(filters["jahr"]))
    if filters.get("betrieb"):
        bedingungen.append("a.betrieb = ?")
        parameter.append(filters["betrieb"])
    if filters.get("schlag"):
        bedingungen.append(
            "EXISTS (SELECT 1 FROM anwendung_einsatzorte e "
            "WHERE e.application_id = a.id AND e.name = ?)"
        )
        parameter.append(filters["schlag"])
    if filters.get("kultur"):
        bedingungen.append(
            "EXISTS (SELECT 1 FROM anwendung_kulturen k "
            "WHERE k.application_id = a.id AND k.name = ?)"
        )
        parameter.append(filters["kultur"])
    if filters.get("mittel"):
        bedingungen.append(
            "EXISTS (SELECT 1 FROM anwendung_mittel m "
            "WHERE m.application_id = a.id AND m.name = ?)"
        )
        parameter.append(filters["mittel"])

    return " AND ".join(bedingungen), parameter


def get_applications(conn: sqlite3.Connection, filters: dict) -> list[sqlite3.Row]:
    where, parameter = _build_where(filters)
    sql = f"""
        SELECT a.id, a.datum, a.uhrzeit, a.betrieb, a.anwender,
            (SELECT GROUP_CONCAT(DISTINCT k.name) FROM anwendung_kulturen k
             WHERE k.application_id = a.id) AS kulturen,
            (SELECT GROUP_CONCAT(DISTINCT e.name) FROM anwendung_einsatzorte e
             WHERE e.application_id = a.id) AS schlaege,
            (SELECT GROUP_CONCAT(DISTINCT m.name) FROM anwendung_mittel m
             WHERE m.application_id = a.id) AS mittel,
            EXISTS (SELECT 1 FROM notizen n WHERE n.datensatz_key = a.datensatz_key) AS hat_notiz
        FROM applications a
        WHERE {where}
        ORDER BY a.datum DESC, a.uhrzeit DESC, a.id DESC
    """
    return conn.execute(sql, parameter).fetchall()


def get_filter_optionen(conn: sqlite3.Connection) -> dict:
    return {
        "jahre": [r[0] for r in conn.execute(
            "SELECT DISTINCT jahr FROM applications ORDER BY jahr DESC"
        )],
        "betriebe": [r[0] for r in conn.execute(
            "SELECT DISTINCT betrieb FROM applications ORDER BY betrieb"
        )],
        "schlaege": [r[0] for r in conn.execute(
            "SELECT DISTINCT name FROM anwendung_einsatzorte WHERE name IS NOT NULL ORDER BY name"
        )],
        "kulturen": [r[0] for r in conn.execute(
            "SELECT DISTINCT name FROM anwendung_kulturen WHERE name IS NOT NULL ORDER BY name"
        )],
        "mittel": [r[0] for r in conn.execute(
            "SELECT DISTINCT name FROM anwendung_mittel WHERE name IS NOT NULL ORDER BY name"
        )],
    }


def get_application_detail(conn: sqlite3.Connection, application_id: int) -> dict | None:
    anwendung = conn.execute(
        "SELECT * FROM applications WHERE id = ?", (application_id,)
    ).fetchone()
    if anwendung is None:
        return None

    import_datei = conn.execute(
        "SELECT dateiname FROM import_files WHERE id = ?", (anwendung["import_file_id"],)
    ).fetchone()

    notiz = conn.execute(
        "SELECT text, geaendert_am FROM notizen WHERE datensatz_key = ?",
        (anwendung["datensatz_key"],),
    ).fetchone()

    return {
        "anwendung": anwendung,
        "notiz": notiz,
        "mittel": conn.execute(
            "SELECT * FROM anwendung_mittel WHERE application_id = ?", (application_id,)
        ).fetchall(),
        "einsatzorte": conn.execute(
            "SELECT * FROM anwendung_einsatzorte WHERE application_id = ?", (application_id,)
        ).fetchall(),
        "kulturen": conn.execute(
            "SELECT * FROM anwendung_kulturen WHERE application_id = ?", (application_id,)
        ).fetchall(),
        "zusatzstoffe": conn.execute(
            "SELECT * FROM anwendung_zusatzstoffe WHERE application_id = ?", (application_id,)
        ).fetchall(),
        "import_datei": import_datei["dateiname"] if import_datei else None,
    }


def save_notiz(conn: sqlite3.Connection, application_id: int, text: str, jetzt: str) -> None:
    key = conn.execute(
        "SELECT datensatz_key FROM applications WHERE id = ?", (application_id,)
    ).fetchone()
    if key is None:
        return
    if text.strip():
        conn.execute(
            """INSERT INTO notizen (datensatz_key, text, geaendert_am) VALUES (?, ?, ?)
               ON CONFLICT (datensatz_key) DO UPDATE SET
                   text = excluded.text, geaendert_am = excluded.geaendert_am""",
            (key[0], text.strip(), jetzt),
        )
    else:
        conn.execute("DELETE FROM notizen WHERE datensatz_key = ?", (key[0],))
    conn.commit()


def get_import_files(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM import_files ORDER BY importiert_am DESC").fetchall()
