# Schlagkartei

Liest die ZIP-Exporte von PSM-DOK aus einem Ordner und zeigt die
Pflanzenschutz-Anwendungen beider Betriebe in einer durchsuchbaren
Übersicht. Hintergrund und Spezifikation: [SPEC.md](SPEC.md).

## Starten

Im Projektordner:

```bash
mkdir -p exports data
docker compose up --build
```

Die Oberfläche ist danach unter <http://localhost:8000> erreichbar (bzw.
unter der Adresse des Rechners, auf dem der Container läuft, wenn du von
einem anderen Gerät im selben Netz zugreifst).

Mit `docker compose up -d --build` läuft der Dienst im Hintergrund;
`docker compose logs -f web` zeigt die Logs, `docker compose down` stoppt ihn.

## ZIP-Dateien ablegen

Die PSM-DOK-Exporte (ZIP mit JSON + PDF) kommen unverändert in den Ordner
**`exports/`** im Projektordner. Die App mountet ihn read-only in den
Container – es wird dort nichts verändert, verschoben oder gelöscht.

Eingelesen wird automatisch beim Start der App sowie über den Knopf
„Jetzt importieren“ auf der Import-Status-Seite. Ein erneuter Import
derselben Dateien erzeugt keine Duplikate.

## Bedienung

- **Übersicht** (Startseite, `/`): Tabelle aller Anwendungen, neueste
  zuerst. Über das Formular lässt sich nach Jahr, Betrieb, Schlag, Kultur
  und Mittel filtern; die Auswahl steht in der URL, eine gefilterte
  Ansicht lässt sich also als Lesezeichen speichern oder verschicken.
- **Datum anklicken** öffnet die Detailansicht einer Anwendung mit allen
  Feldern, der Herkunftsdatei und dem unveränderten Original-Datensatz.
- **CSV-Export**: Der Link neben dem Filter-Formular exportiert genau die
  aktuell gefilterte Ansicht als `;`-getrennte CSV-Datei (UTF-8, öffnet
  direkt in Excel/LibreOffice mit deutscher Einstellung).
- **Import-Status** (`/import`): Liste aller eingelesenen Dateien mit
  Zeitpunkt, Anzahl Datensätzen und eventuellen Fehlern. Der Knopf „Jetzt
  importieren“ liest den `exports/`-Ordner erneut ein, ohne die App neu
  zu starten.

## Betriebszuordnung konfigurieren

Welcher `betrieb.guid`-Wert aus dem Export zu welchem Betrieb gehört, trägst
du in der Umgebungsvariable `BETRIEB_ZUORDNUNG` in `compose.yaml` ein:

```yaml
environment:
  - BETRIEB_ZUORDNUNG=<guid-betrieb-1>:Hof Nord,<guid-betrieb-2>:Hof Süd
```

Ohne Eintrag fällt der Importer auf den Firmennamen aus dem Export zurück.

## Reichweite

Die App hat in dieser Ausbaustufe kein Login. Sie ist nur für den Betrieb
im internen Netz gedacht (Homeserver oder, zum Ausprobieren, dieser
Rechner) – der Port darf nicht ins Internet freigegeben werden.

## Tests

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/pytest
```
