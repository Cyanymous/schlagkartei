import os


def export_dir() -> str:
    return os.environ.get("EXPORT_DIR", "/exports")


def db_path() -> str:
    return os.environ.get("DB_PATH", "/data/schlagkartei.db")


def betrieb_zuordnung() -> dict[str, str]:
    """Ordnet die betrieb.guid aus dem Export einem Anzeigenamen zu.

    Format der Umgebungsvariable: "guid1:Name1,guid2:Name2". Fehlt eine GUID
    in der Zuordnung (z. B. beim ersten Start), fällt der Importer auf
    betrieb.firma bzw. betrieb.name zurück.
    """
    raw = os.environ.get("BETRIEB_ZUORDNUNG", "")
    zuordnung: dict[str, str] = {}
    for teil in raw.split(","):
        teil = teil.strip()
        if not teil or ":" not in teil:
            continue
        guid, name = teil.split(":", 1)
        zuordnung[guid.strip()] = name.strip()
    return zuordnung
