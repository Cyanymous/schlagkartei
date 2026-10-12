"""SQL für den Fuhrpark (SPEC.md Abschnitt 13): Fahrzeuge, Fahrzeugbuch, Wartung."""

import calendar
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
    if werte.get("baujahr") is not None and not 1900 <= werte["baujahr"] <= date.today().year + 1:
        return None, "Bitte ein gültiges Baujahr angeben."
    if werte.get("tuev_faellig") and not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", werte["tuev_faellig"]):
        return None, "Bitte die TÜV-Fälligkeit als Monat angeben."
    vorhanden = conn.execute(
        "SELECT id FROM fahrzeuge WHERE name = ? AND id IS NOT ?", (werte["name"], fahrzeug_id)
    ).fetchone()
    if vorhanden:
        return None, f"Das Fahrzeug „{werte['name']}“ gibt es schon."

    spalten = [
        "name", "modell", "seriennummer", "baujahr", "kennzeichen", "oelfilter",
        "einheit", "tank_liter", "tuev_faellig", "bemerkung", "aktiv",
    ]
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
        """SELECT e.*, f.name AS fahrzeug, f.einheit,
               EXISTS (SELECT 1 FROM wartungsaufgaben w
                       WHERE w.fahrzeug_id = e.fahrzeug_id AND w.aufgabe = e.art) AS ist_wartung
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


# --- Wartungsplan -----------------------------------------------------------

# Gelb, sobald weniger als 10 % des Zählerintervalls oder weniger als 30 Tage übrig sind.
BALD_ANTEIL = 0.1
BALD_TAGE = 30
# Dringendstes zuerst; grau (nie erledigt, Stand fehlt) braucht eher Aufmerksamkeit als grün.
DRINGLICHKEIT = {"rot": 0, "gelb": 1, "grau": 2, "gruen": 3}


def get_aufgaben(conn: sqlite3.Connection, fahrzeug_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM wartungsaufgaben WHERE fahrzeug_id = ? ORDER BY aufgabe", (fahrzeug_id,)
    ).fetchall()


def save_aufgabe(
    conn: sqlite3.Connection,
    fahrzeug_id: int,
    aufgabe_id: int | None,
    aufgabe: str,
    intervall_zaehler: float | None,
    intervall_monate: float | None,
) -> str | None:
    """Legt eine Wartungsaufgabe an (aufgabe_id None) oder ändert sie."""
    fahrzeug = get_fahrzeug(conn, fahrzeug_id)
    aufgabe = aufgabe.strip()
    if fahrzeug is None:
        return "Fahrzeug nicht gefunden."
    if not aufgabe:
        return "Bitte die Aufgabe benennen, z. B. Ölwechsel."
    if intervall_zaehler is None and intervall_monate is None:
        return "Bitte ein Intervall angeben (Zählerstand, Monate oder beides)."
    if intervall_zaehler is not None and not fahrzeug["einheit"]:
        return f"„{fahrzeug['name']}“ hat keinen Zähler; bitte das Intervall in Monaten angeben."
    if (intervall_zaehler is not None and intervall_zaehler <= 0) or (
        intervall_monate is not None and (intervall_monate <= 0 or intervall_monate != int(intervall_monate))
    ):
        return "Intervalle müssen größer als 0 sein, Monate eine ganze Zahl."
    if conn.execute(
        "SELECT 1 FROM wartungsaufgaben WHERE fahrzeug_id = ? AND aufgabe = ? AND id IS NOT ?",
        (fahrzeug_id, aufgabe, aufgabe_id),
    ).fetchone():
        return f"Die Aufgabe „{aufgabe}“ gibt es für dieses Fahrzeug schon."

    monate = int(intervall_monate) if intervall_monate is not None else None
    if aufgabe_id is None:
        conn.execute(
            """INSERT INTO wartungsaufgaben (fahrzeug_id, aufgabe, intervall_zaehler, intervall_monate)
               VALUES (?, ?, ?, ?)""",
            (fahrzeug_id, aufgabe, intervall_zaehler, monate),
        )
    else:
        alt = conn.execute("SELECT aufgabe FROM wartungsaufgaben WHERE id = ?", (aufgabe_id,)).fetchone()
        # Erledigt-Einträge finden ihre Aufgabe über den Namen; beim Umbenennen
        # ziehen sie mit, sonst stünde die Aufgabe wieder auf „nie erledigt“.
        if alt and alt["aufgabe"] != aufgabe:
            conn.execute(
                "UPDATE fahrzeug_eintraege SET art = ? WHERE fahrzeug_id = ? AND art = ?",
                (aufgabe, fahrzeug_id, alt["aufgabe"]),
            )
        conn.execute(
            "UPDATE wartungsaufgaben SET aufgabe = ?, intervall_zaehler = ?, intervall_monate = ? WHERE id = ?",
            (aufgabe, intervall_zaehler, monate, aufgabe_id),
        )
    conn.commit()
    return None


def delete_aufgabe(conn: sqlite3.Connection, aufgabe_id: int) -> None:
    conn.execute("DELETE FROM wartungsaufgaben WHERE id = ?", (aufgabe_id,))
    conn.commit()


def _plus_monate(tag: date, monate: int) -> date:
    jahr, monat = divmod(tag.month - 1 + monate, 12)
    jahr, monat = tag.year + jahr, monat + 1
    return date(jahr, monat, min(tag.day, calendar.monthrange(jahr, monat)[1]))


def _ampel(rest: float, bald: float) -> str:
    if rest < 0:
        return "rot"
    if rest < bald:
        return "gelb"
    return "gruen"


def _rest_text(rest: float, einheit: str) -> str:
    if einheit == "Tage" and abs(rest) == 1:
        einheit = "Tag"
    if rest < 0:
        return f"{zahl_de(-rest)} {einheit} überfällig"
    return f"noch {zahl_de(rest)} {einheit}"


def faelligkeit(
    intervall_zaehler: float | None,
    intervall_monate: int | None,
    letzte: dict | None,
    stand: float | None,
    einheit: str | None,
    heute: date,
) -> dict:
    """Nächste Fälligkeit einer Aufgabe aus dem letzten Erledigt-Eintrag.

    `letzte` hat datum und zaehlerstand des letzten Eintrags mit dieser Art,
    `stand` ist der aktuelle Zählerstand. Bei beiden Intervallen gilt, was
    zuerst kommt: Der Status ist der dringendere der beiden.
    """
    if letzte is None:
        return {"status": "grau", "text": "noch nie erledigt"}
    stati, texte = [], []
    if intervall_zaehler:
        if letzte["zaehlerstand"] is None:
            texte.append("Zählerstand beim letzten Mal fehlt")
        else:
            faellig_bei = letzte["zaehlerstand"] + intervall_zaehler
            text = f"bei {zahl_de(faellig_bei)} {einheit}"
            if stand is not None:
                rest = faellig_bei - stand
                stati.append(_ampel(rest, intervall_zaehler * BALD_ANTEIL))
                text += f" ({_rest_text(rest, einheit)})"
            texte.append(text)
    if intervall_monate:
        faellig_am = _plus_monate(date.fromisoformat(letzte["datum"]), intervall_monate)
        rest_tage = (faellig_am - heute).days
        stati.append(_ampel(rest_tage, BALD_TAGE))
        texte.append(f"am {faellig_am:%d.%m.%Y} ({_rest_text(rest_tage, 'Tage')})")
    status = min(stati, key=DRINGLICHKEIT.get) if stati else "grau"
    return {"status": status, "text": " oder ".join(texte)}


def tuev_faelligkeit(tuev_faellig: str, heute: date) -> dict:
    """Die Plakette gilt bis zum Ende ihres Monats."""
    jahr, monat = int(tuev_faellig[:4]), int(tuev_faellig[5:7])
    rest_tage = (date(jahr, monat, calendar.monthrange(jahr, monat)[1]) - heute).days
    return {"status": _ampel(rest_tage, BALD_TAGE), "text": f"{monat:02d}/{jahr} ({_rest_text(rest_tage, 'Tage')})"}


def wartungsplan(conn: sqlite3.Connection, fahrzeug: sqlite3.Row, heute: date) -> list[dict]:
    """Alle Fälligkeiten eines Fahrzeugs (Aufgaben und TÜV), Dringendstes zuerst."""
    punkte = []
    for a in get_aufgaben(conn, fahrzeug["id"]):
        letzte = conn.execute(
            """SELECT datum, zaehlerstand FROM fahrzeug_eintraege
               WHERE fahrzeug_id = ? AND art = ? ORDER BY datum DESC, id DESC LIMIT 1""",
            (fahrzeug["id"], a["aufgabe"]),
        ).fetchone()
        anzahl = conn.execute(
            "SELECT COUNT(*) FROM fahrzeug_eintraege WHERE fahrzeug_id = ? AND art = ?",
            (fahrzeug["id"], a["aufgabe"]),
        ).fetchone()[0]
        punkt = dict(a) | {"name": a["aufgabe"], "letzte": letzte, "anzahl": anzahl}
        punkt |= faelligkeit(
            a["intervall_zaehler"], a["intervall_monate"], letzte, fahrzeug["stand"], fahrzeug["einheit"], heute
        )
        punkte.append(punkt)
    if fahrzeug["tuev_faellig"]:
        punkte.append({"name": "TÜV", "id": None} | tuev_faelligkeit(fahrzeug["tuev_faellig"], heute))
    return sorted(punkte, key=lambda p: DRINGLICHKEIT[p["status"]])


def uebersicht(conn: sqlite3.Connection, heute: date) -> list[dict]:
    """Aktive Fahrzeuge mit ihren Fälligkeiten; Fahrzeuge mit dem dringendsten Punkt zuerst."""
    zeilen = []
    for f in get_fahrzeuge(conn, nur_aktive=True):
        punkte = wartungsplan(conn, f, heute)
        status = punkte[0]["status"] if punkte else "gruen"
        zeilen.append({"fahrzeug": f, "punkte": punkte, "status": status})
    return sorted(zeilen, key=lambda z: (DRINGLICHKEIT[z["status"]], z["fahrzeug"]["name"]))


def anzahl_ueberfaellig(conn: sqlite3.Connection, heute: date) -> int:
    return sum(p["status"] == "rot" for z in uebersicht(conn, heute) for p in z["punkte"])
