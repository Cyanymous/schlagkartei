# Schlagkartei

Schlagkartei für zwei Betriebe: Schläge, Fruchtfolge mit Anbauplanung und
Feldarbeiten, dazu die Pflanzenschutz-Anwendungen aus den ZIP-Exporten von
PSM-DOK. Hintergrund und Spezifikation: [SPEC.md](SPEC.md).

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
„Jetzt importieren“ auf der Import-Seite. Ein erneuter Import
derselben Dateien erzeugt keine Duplikate.

**Datei versehentlich abgelegt?** Datei aus `exports/` löschen und auf der
Import-Seite „Jetzt importieren“ klicken (oder die App neu starten). Die
Behandlungen aus dieser Datei verschwinden dann samt ihren Notizen – außer
sie stehen auch noch in einer anderen Datei im Ordner.

## Bedienung

### Schlagkartei

- **Schläge** (`/schlaege`): alle Schläge mit Schlagnummer und Größe des
  aktuellen Jahres und der Summe je Betrieb. „Neuen Schlag anlegen“ öffnet
  das Formular. Ein Klick auf einen Schlag öffnet seine Schlagkartei.
- **Schlag-Seite**: Fruchtfolge ab 2020 samt Planung, darunter alle
  Maßnahmen als Zeitleiste – eigene Feldarbeiten und Pflanzenschutz aus
  PSM-DOK gemeinsam. Unten werden Schlagnummer und Größe gepflegt: Ein
  Stand gilt ab seinem Jahr, bis ein neuerer eingetragen wird. Ändert sich
  im Agrarantrag etwas, also einfach einen Stand für das neue Jahr anlegen.
  Schläge werden nicht gelöscht, sondern auf „inaktiv“ gesetzt.
- **Pflanzenschutz-Zuordnung**: Eine PSM-Anwendung erscheint bei einem
  Schlag, wenn in PSM-DOK als **Schlag-ID die Schlagnummer** eingetragen
  ist, die der Schlag im Jahr der Anwendung hat.
- **Anbauplan** (`/anbauplan`): alle Schläge × Jahre von 2020 bis zum
  nächsten Jahr (Planung, gelb hinterlegt). Zelle anklicken, um Kulturen
  einzutragen – Hauptkultur, Zwischenfrucht, Untersaat oder Zweitfrucht,
  jeweils mit Bemerkung. ⚠ markiert dieselbe Hauptkultur wie im Vorjahr
  (außer bei mehrjährigen Kulturen). Darunter der Anbauumfang in ha je
  Kultur und Jahr; CSV-Export oben.
- **Feldarbeiten** (`/feldarbeiten`): Liste mit Filter nach Jahr, Schlag
  und Art; CSV-Export. „+ Neue Feldarbeit“: Datum, Art, Bemerkung und
  beliebig viele Schläge ankreuzen. Die Knöpfe „alle mit Winterroggen“
  usw. kreuzen alle Schläge mit dieser Hauptkultur auf einmal an.
- **Kulturen** (`/kulturen`): Zuordnung Kultur → EPPO-Code, vorbelegt mit
  gängigen Ackerkulturen. Kulturen aus den PSM-DOK-Exporten kommen beim
  Import automatisch dazu. „mehrjährig“ für Dauerkulturen wie Spargel.

### Pflanzenschutz (PSM-DOK)

- **Pflanzenschutz** (`/`): Tabelle aller Anwendungen, neueste
  zuerst. Über das Formular lässt sich nach Jahr, Betrieb, Schlag, Kultur
  und Mittel filtern; die Auswahl steht in der URL, eine gefilterte
  Ansicht lässt sich also als Lesezeichen speichern oder verschicken.
- **Zeile anklicken** öffnet die Detailansicht einer Anwendung mit allen
  Feldern, der Herkunftsdatei, einem Link zum zugeordneten Schlag und dem
  unveränderten Original-Datensatz.
- **Notiz**: In der Detailansicht kannst du zu jeder Anwendung eine Notiz
  schreiben und mit „Speichern“ sichern. Leer speichern löscht sie.
  Anwendungen mit Notiz tragen in der Übersicht ein ✎ neben dem Datum.
- **CSV-Export**: Der Link neben dem Filter-Formular exportiert genau die
  aktuell gefilterte Ansicht als `;`-getrennte CSV-Datei (UTF-8, öffnet
  direkt in Excel/LibreOffice mit deutscher Einstellung).
- **Import** (`/import`): Liste aller eingelesenen Dateien mit
  Zeitpunkt, Anzahl Datensätzen und eventuellen Fehlern. Der Knopf „Jetzt
  importieren“ liest den `exports/`-Ordner erneut ein, ohne die App neu
  zu starten.

Die Oberfläche folgt automatisch der Hell/Dunkel-Einstellung des Geräts.

## Datensicherung

- `exports/` enthält die Original-Exporte – der rechtlich maßgebliche
  Bestand. Unbedingt sichern.
- `data/` enthält die Datenbank. Die importierten Daten ließen sich aus
  `exports/` neu einlesen, **Schläge, Anbauplan, Feldarbeiten, Kulturen und
  Notizen aber nicht**. Deshalb `data/` ebenfalls sichern. Ein Neustart oder
  Neubau des Containers lässt beide Ordner unangetastet.
- Zusätzlich legt die App einmal am Tag eine Kopie der Datenbank in
  `data/backup/` ab (die letzten 30 Tage). Wiederherstellen: Container
  stoppen, die gewünschte Kopie als `data/schlagkartei.db` zurückkopieren,
  Container starten. Die Kopien ersetzen keine Sicherung auf einem anderen
  Datenträger.

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
