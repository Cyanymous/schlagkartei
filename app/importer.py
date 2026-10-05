import hashlib
import json
import sqlite3
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class NormalizedApplication:
    datensatz_key: str
    inhalt_hash: str
    betrieb: str
    betrieb_guid: str | None
    betrieb_firma: str | None
    betrieb_name: str | None
    betrieb_ort: str | None
    betrieb_gps_hochwert: str | None
    betrieb_gps_rechtswert: str | None
    datum: str
    jahr: int
    uhrzeit: str | None
    anwender: str | None
    verantwortlich: str | None
    art_verwendung: str | None
    export_version: str | None
    json_name: str
    roh_json: str
    mittel: list[dict] = field(default_factory=list)
    einsatzorte: list[dict] = field(default_factory=list)
    kulturen: list[dict] = field(default_factory=list)
    zusatzstoffe: list[dict] = field(default_factory=list)


def _kanonisch(record: dict) -> str:
    return json.dumps(record, sort_keys=True, ensure_ascii=False)


def _inhalt_hash(record: dict) -> str:
    return hashlib.sha256(_kanonisch(record).encode("utf-8")).hexdigest()


def _sha256_datei(pfad: Path) -> str:
    return hashlib.sha256(pfad.read_bytes()).hexdigest()


def resolve_betrieb(betrieb: dict, zuordnung: dict[str, str]) -> str:
    guid = betrieb.get("guid")
    if guid and guid in zuordnung:
        return zuordnung[guid]
    return betrieb.get("firma") or betrieb.get("name") or "unbekannt"


def normalize_record(
    record: dict, json_name: str, zuordnung: dict[str, str]
) -> NormalizedApplication:
    betrieb = record.get("betrieb", {})
    anwendung = record.get("anwendung", {})
    datum = anwendung.get("datum", "")
    guid = record.get("guid")
    key = guid if guid else "hash:" + _inhalt_hash(record)

    einsatzorte = []
    for ort in record.get("einsatzorte", []):
        geo_typ = ort.get("geoTyp")
        einsatzorte.append(
            {
                "name": ort.get("name"),
                "anwendungsbereich": ort.get("anwendungsbereich"),
                "geo_typ": geo_typ,
                "geo_wert": ort.get(geo_typ) if geo_typ else None,
                "flaeche_volumen": ort.get("flaecheVolumen"),
                "einheit": ort.get("einheit"),
            }
        )

    mittel = [
        {
            "name": m.get("name"),
            "zulassungsnr": m.get("zulassungsnr"),
            "aufwand_menge": m.get("aufwandMenge"),
            "aufwand_einheit": m.get("aufwandEinheit"),
            "wirkstoffe": m.get("wirkstoffe"),
            "bienen": m.get("bienen"),
        }
        for m in record.get("pflanzenschutzmittel", [])
    ]

    kulturen = [
        {
            "name": k.get("name"),
            "eppo_code": k.get("eppoCode"),
            "bbch_code": k.get("bbchCode"),
            "bbch_name": k.get("bbchName"),
            "satzweise": k.get("satzweise"),
        }
        for k in record.get("kulturen", [])
    ]

    zusatzstoffe = [
        {"roh_json": json.dumps(z, ensure_ascii=False)}
        for z in record.get("zusatzstoffe", [])
    ]

    return NormalizedApplication(
        datensatz_key=key,
        inhalt_hash=_inhalt_hash(record),
        betrieb=resolve_betrieb(betrieb, zuordnung),
        betrieb_guid=betrieb.get("guid"),
        betrieb_firma=betrieb.get("firma"),
        betrieb_name=betrieb.get("name"),
        betrieb_ort=betrieb.get("ort"),
        betrieb_gps_hochwert=betrieb.get("gpsHochwert"),
        betrieb_gps_rechtswert=betrieb.get("gpsRechtswert"),
        datum=datum,
        jahr=int(datum[:4]) if len(datum) >= 4 and datum[:4].isdigit() else 0,
        uhrzeit=anwendung.get("uhrzeit"),
        anwender=anwendung.get("anwender"),
        verantwortlich=anwendung.get("verantwortlich"),
        art_verwendung=anwendung.get("artVerwendung"),
        export_version=record.get("version"),
        json_name=json_name,
        roh_json=_kanonisch(record),
        mittel=mittel,
        einsatzorte=einsatzorte,
        kulturen=kulturen,
        zusatzstoffe=zusatzstoffe,
    )


def _lies_json_eintraege(pfad: Path) -> list[tuple[str, dict]]:
    """Liest alle JSON-Datensätze aus einer Datei; wirft bei Fehlern.

    Eine ZIP ohne PDF ist kein Fehler (wir suchen ohnehin nur *.json); eine
    ZIP ohne JSON-Datei dagegen schon.
    """
    if pfad.suffix.lower() == ".json":
        return [(pfad.name, json.loads(pfad.read_bytes()))]

    with zipfile.ZipFile(pfad) as zf:
        namen = [n for n in zf.namelist() if n.lower().endswith(".json")]
        if not namen:
            raise ValueError("keine JSON-Datei in der ZIP enthalten")
        eintraege = []
        for name in namen:
            with zf.open(name) as f:
                eintraege.append((Path(name).name, json.loads(f.read())))
        return eintraege


def _upsert_application(
    conn: sqlite3.Connection,
    app: NormalizedApplication,
    import_file_id: int,
    jetzt: str,
) -> None:
    vorhanden = conn.execute(
        "SELECT id, inhalt_hash FROM applications WHERE datensatz_key = ?",
        (app.datensatz_key,),
    ).fetchone()

    if vorhanden and vorhanden["inhalt_hash"] == app.inhalt_hash:
        return  # unveränderter Datensatz, nichts zu tun

    if vorhanden:
        application_id = vorhanden["id"]
        conn.execute(
            """UPDATE applications SET
                inhalt_hash=:inhalt_hash, betrieb=:betrieb, datum=:datum, jahr=:jahr,
                uhrzeit=:uhrzeit, anwender=:anwender, verantwortlich=:verantwortlich,
                art_verwendung=:art_verwendung, betrieb_guid=:betrieb_guid,
                betrieb_firma=:betrieb_firma, betrieb_name=:betrieb_name,
                betrieb_ort=:betrieb_ort, betrieb_gps_hochwert=:betrieb_gps_hochwert,
                betrieb_gps_rechtswert=:betrieb_gps_rechtswert, export_version=:export_version,
                import_file_id=:import_file_id, json_name=:json_name, geaendert_am=:geaendert_am,
                roh_json=:roh_json
               WHERE id=:id""",
            {
                **app.__dict__,
                "import_file_id": import_file_id,
                "geaendert_am": jetzt,
                "id": application_id,
            },
        )
        for tabelle in (
            "anwendung_mittel",
            "anwendung_einsatzorte",
            "anwendung_kulturen",
            "anwendung_zusatzstoffe",
        ):
            conn.execute(f"DELETE FROM {tabelle} WHERE application_id=?", (application_id,))
    else:
        cur = conn.execute(
            """INSERT INTO applications (
                datensatz_key, inhalt_hash, betrieb, datum, jahr, uhrzeit, anwender,
                verantwortlich, art_verwendung, betrieb_guid, betrieb_firma, betrieb_name,
                betrieb_ort, betrieb_gps_hochwert, betrieb_gps_rechtswert, export_version,
                import_file_id, json_name, zuerst_gesehen_am, roh_json
            ) VALUES (
                :datensatz_key, :inhalt_hash, :betrieb, :datum, :jahr, :uhrzeit, :anwender,
                :verantwortlich, :art_verwendung, :betrieb_guid, :betrieb_firma, :betrieb_name,
                :betrieb_ort, :betrieb_gps_hochwert, :betrieb_gps_rechtswert, :export_version,
                :import_file_id, :json_name, :zuerst_gesehen_am, :roh_json
            )""",
            {
                **app.__dict__,
                "import_file_id": import_file_id,
                "zuerst_gesehen_am": jetzt,
            },
        )
        application_id = cur.lastrowid

    for m in app.mittel:
        conn.execute(
            """INSERT INTO anwendung_mittel
               (application_id, name, zulassungsnr, aufwand_menge, aufwand_einheit, wirkstoffe, bienen)
               VALUES (?,?,?,?,?,?,?)""",
            (
                application_id,
                m["name"],
                m["zulassungsnr"],
                m["aufwand_menge"],
                m["aufwand_einheit"],
                m["wirkstoffe"],
                m["bienen"],
            ),
        )
    for e in app.einsatzorte:
        conn.execute(
            """INSERT INTO anwendung_einsatzorte
               (application_id, name, anwendungsbereich, geo_typ, geo_wert, flaeche_volumen, einheit)
               VALUES (?,?,?,?,?,?,?)""",
            (
                application_id,
                e["name"],
                e["anwendungsbereich"],
                e["geo_typ"],
                e["geo_wert"],
                e["flaeche_volumen"],
                e["einheit"],
            ),
        )
    for k in app.kulturen:
        conn.execute(
            """INSERT INTO anwendung_kulturen
               (application_id, name, eppo_code, bbch_code, bbch_name, satzweise)
               VALUES (?,?,?,?,?,?)""",
            (application_id, k["name"], k["eppo_code"], k["bbch_code"], k["bbch_name"], k["satzweise"]),
        )
    for z in app.zusatzstoffe:
        conn.execute(
            "INSERT INTO anwendung_zusatzstoffe (application_id, roh_json) VALUES (?,?)",
            (application_id, z["roh_json"]),
        )


def import_exports(
    export_dir: str | Path,
    conn: sqlite3.Connection,
    zuordnung: dict[str, str] | None = None,
) -> list[dict]:
    zuordnung = zuordnung or {}
    export_dir = Path(export_dir)
    bekannte_hashes = {
        r["sha256"] for r in conn.execute("SELECT sha256 FROM import_files")
    }

    ergebnisse = []
    dateien = sorted(
        p for p in export_dir.iterdir() if p.is_file() and p.suffix.lower() in (".zip", ".json")
    )

    for pfad in dateien:
        sha256 = _sha256_datei(pfad)
        if sha256 in bekannte_hashes:
            continue

        jetzt = datetime.now(UTC).isoformat()

        try:
            eintraege = _lies_json_eintraege(pfad)
        except (zipfile.BadZipFile, ValueError, json.JSONDecodeError, OSError) as exc:
            conn.execute(
                """INSERT INTO import_files
                   (dateiname, sha256, importiert_am, anzahl_datensaetze, status, fehlermeldung)
                   VALUES (?,?,?,0,'fehler',?)""",
                (pfad.name, sha256, jetzt, str(exc)),
            )
            conn.commit()
            ergebnisse.append({"dateiname": pfad.name, "status": "fehler", "fehlermeldung": str(exc)})
            continue

        import_file_id = conn.execute(
            """INSERT INTO import_files (dateiname, sha256, importiert_am, anzahl_datensaetze, status)
               VALUES (?,?,?,?,'ok')""",
            (pfad.name, sha256, jetzt, len(eintraege)),
        ).lastrowid

        fehlermeldungen = []
        for json_name, record in eintraege:
            try:
                app = normalize_record(record, json_name, zuordnung)
            except (KeyError, TypeError, ValueError) as exc:
                fehlermeldungen.append(f"{json_name}: {exc}")
                continue
            _upsert_application(conn, app, import_file_id, jetzt)

        if fehlermeldungen:
            conn.execute(
                "UPDATE import_files SET status='fehler', fehlermeldung=? WHERE id=?",
                ("; ".join(fehlermeldungen), import_file_id),
            )

        conn.commit()
        ergebnisse.append(
            {
                "dateiname": pfad.name,
                "status": "fehler" if fehlermeldungen else "ok",
                "anzahl_datensaetze": len(eintraege),
            }
        )

    return ergebnisse
