# Schlagkartei – Spezifikation

Stand: 06.10.2026 · Status: Stufe 1 umgesetzt

## 1. Ziel

Eine kleine, selbst gehostete Web-Anwendung, die die Pflanzenschutz-Aufzeichnungen
zweier landwirtschaftlicher Betriebe (ein konventioneller, ein ökologischer) in einer
Gesamtübersicht zeigt.

Die Eingabe der Pflanzenschutzmittel-Anwendungen (PSM-Anwendungen) erfolgt weiterhin
in der Web-Anwendung **PSM-DOK** (https://www.psmdok.de). PSM-DOK speichert nichts
selbst; nach jeder Eintragung wird eine **ZIP-Datei** heruntergeladen. Sie enthält
eine JSON-Datei mit den Aufzeichnungen und eine PDF-Datei mit derselben
Information in lesbarer Form. Die ZIP-Dateien werden unverändert in einem Ordner
auf dem Homeserver abgelegt. Die Anwendung liest die JSON-Datei aus jeder ZIP und
stellt die Aufzeichnungen durchsuchbar dar. Die PDF-Datei wird ignoriert.

Später soll die Anwendung eigene Daten aufnehmen (Notizen, Berechnungen) und
schrittweise zu einer vollständigen Schlagkartei ausbaubar sein.

**Oberstes Entwurfsziel ist Einfachheit.** Der Betreiber ist technisch versiert
(Python, R, Docker), aber kein Berufsentwickler, und muss den Code allein pflegen
können. Im Zweifel gewinnt die Lösung mit weniger Code, weniger Abhängigkeiten und
weniger beweglichen Teilen.

## 2. Ausbaustufen

| Stufe | Inhalt | Status |
|-------|--------|--------|
| 1 | Import der PSM-DOK-Exporte, Gesamtübersicht mit Filtern, CSV-Export, Notizen je Anwendung | **jetzt** |
| 2 | Schlag-Stammdaten, einfache Berechnungen | später |
| 3 | Eigene Eingabemaske als Ersatz für PSM-DOK (volle Schlagkartei) | später |

Notizen je Anwendung wurden am 06.10.2026 auf Wunsch des Betreibers aus
Stufe 2 in Stufe 1 vorgezogen.

Es wird immer nur die aktuelle Stufe gebaut. Spätere Stufen beeinflussen das
Datenmodell (siehe Abschnitt 5), aber es entsteht kein Code "auf Vorrat".

### Nicht-Ziele in Stufe 1

- Keine Eingabe oder Bearbeitung von PSM-Anwendungen in der App
- Keine Benutzerverwaltung, kein Login
- Keine Düngedokumentation, keine Flächenplanung, keine Karten
- Kein Audit-Trail (nicht nötig, solange die PSM-DOK-Dateien das Original sind)

## 3. Rechtlicher Rahmen (Hintergrund)

- Aufzeichnungspflicht: Art. 67 VO (EG) 1107/2009, § 11 PflSchG,
  Durchführungsverordnung (EU) 2023/564.
- Ab 01.01.2027 müssen die Aufzeichnungen elektronisch und maschinenlesbar
  vorliegen (z. B. JSON, XML, CSV; PDF genügt nicht).
- Aufbewahrung: mindestens drei volle Kalenderjahre nach dem Anwendungsjahr.

**Folge für diese Anwendung:** In Stufe 1 und 2 sind die PSM-DOK-Exportdateien der
rechtlich maßgebliche Nachweis, nicht die Datenbank der App. Die App ist eine
Lesesicht. Sie darf die Exportdateien deshalb unter keinen Umständen verändern,
verschieben oder löschen.

Pflichtangaben je Anwendung, die das Datenmodell abbilden können muss:

- Anwender (Name)
- Art der Verwendung (Fläche / geschlossener Raum / Saat- bzw. Pflanzgut)
- Kultur und EPPO-Code
- BBCH-Stadium (nur bei Indikationen mit Stadiumsbeschränkung, also optional)
- Bezeichnung der Fläche (Schlag / Teilschlag)
- Lage (z. B. InVeKoS-Bezeichnung oder GPS-Punkt)
- Umfang der behandelten Einheit (Wert und Einheit)
- Datum der Anwendung
- Uhrzeit (nur bei zeitlicher Einschränkung, also optional)
- Genaue Bezeichnung des Pflanzenschutzmittels
- Zulassungsnummer
- Verwendete Menge (Wert und Einheit)

## 4. Architektur

```
PSM-DOK (Browser)
      │  Download der ZIP-Datei (JSON + PDF), Ablage im Export-Ordner
      ▼
./exports/   (read-only in den Container gemountet)
      │
      ▼
Importer (liest nur die JSON aus der ZIP) ──► SQLite-Datei in ./data/
      │
      ▼
Web-Oberfläche (Browser im Hofnetz)
```

- **Ein Container, eine `compose.yaml`.** Kein separater Datenbank-Container.
- **Betrieb:** Homeserver mit Docker Compose, ein Ordner pro Dienst, die
  `compose.yaml` liegt direkt im Dienst-Ordner (= Wurzel dieses Repos).
- **Zugriff:** nur aus dem internen Netz. Der Port wird nicht ins Internet
  freigegeben; deshalb gibt es in Stufe 1 kein Login.

### Stack

- Python 3.12+, FastAPI, Uvicorn
- SQLite über das `sqlite3`-Modul der Standardbibliothek, reines SQL, kein ORM
- Servergerenderte HTML-Seiten mit Jinja2
- Optional HTMX als einzelne, lokal abgelegte Datei (kein CDN, kein npm, kein
  Build-Schritt)
- Tests mit pytest

### Vorgeschlagene Struktur

```
compose.yaml
Dockerfile
requirements.txt
app/
  main.py          FastAPI-App und Routen
  db.py            Verbindung, Migrationen
  importer.py      Einlesen und Normalisieren der Exporte
  queries.py       SQL-Abfragen für die Übersicht
  templates/       Jinja2-Templates
  static/          CSS, ggf. htmx.min.js
migrations/
  001_initial.sql  nummerierte SQL-Dateien, beim Start angewendet
tests/
  fixtures/        verfremdete PSM-DOK-Beispielexporte (ZIP)
  test_importer.py
exports/           (nicht im Repo) echte PSM-DOK-ZIP-Dateien
data/              (nicht im Repo) SQLite-Datenbank
```

Die Struktur ist ein Vorschlag; weniger Dateien sind in Ordnung, mehr nur mit
Begründung.

## 5. Datenmodell – feste Regeln

Diese drei Regeln gelten für alle Stufen und dürfen nicht aufgeweicht werden:

1. **Exportdateien sind das unveränderliche Original.** Die App liest nur.
2. **Importierte und eigene Daten liegen in getrennten Tabellen.** Eigene Daten
   (ab Stufe 1 die Notizen) verweisen per Fremdschlüssel auf importierte Datensätze, werden
   aber nie in dieselbe Tabelle geschrieben. Der Import darf eigene Daten nie
   überschreiben.
3. **Jede Anwendung trägt die Spalten `betrieb` und `quelle`.** `betrieb`
   unterscheidet die beiden Betriebe; `quelle` ist in Stufe 1 immer `psmdok`
   und erlaubt später manuelle Einträge ohne Umbau.

### Tabellen in Stufe 1

- `import_files`: Dateiname, SHA-256 der Datei (ZIP oder lose JSON),
  Zeitpunkt des Imports, Anzahl gelesener Datensätze, Status, ggf.
  Fehlermeldung. Der Name der gelesenen JSON steht auf `applications`, nicht
  hier, weil eine ZIP laut Abschnitt 6 mehrere JSON-Dateien enthalten darf.
- `applications`: eine Zeile je PSM-Anwendung mit den Pflichtangaben aus
  Abschnitt 3, dazu `betrieb`, `quelle`, `jahr` (aus `datum` abgeleitet,
  für den Filter), Verweis auf `import_files`, Name der gelesenen JSON-Datei,
  eindeutiger Datensatz-Schlüssel (siehe Abschnitt 6, Frage 3),
  Inhalts-Hash zur Erkennung von Korrekturen, `zuerst_gesehen_am` /
  `geaendert_am` und der unveränderte Original-Datensatz als JSON-Text.
- `anwendung_mittel`, `anwendung_einsatzorte`, `anwendung_kulturen`: je eine
  Zeile pro Listenelement aus dem Export (`pflanzenschutzmittel`,
  `einsatzorte`, `kulturen`), mit Fremdschlüssel auf `applications`. Eine
  Tankmischung erzeugt mehrere Zeilen in `anwendung_mittel` zur selben
  Anwendung.
- `anwendung_zusatzstoffe`: eine Zeile pro Element aus `zusatzstoffe`, bisher
  nur mit `roh_json`, weil die Feldnamen in den Fixtures noch nicht belegt
  sind (siehe Abschnitt 11, letzter Absatz). Sobald ein Fixture mit Inhalt
  vorliegt, wird die Tabelle um konkrete Spalten erweitert.
- `notizen` (eigene Daten): höchstens eine Notiz je Anwendung mit Text und
  `geaendert_am`. Verweist über `datensatz_key` (die `guid` aus dem Export)
  auf `applications`, nicht über die interne `id`, weil diese beim Neuaufbau
  der Datenbank neu vergeben wird. Eine leer gespeicherte Notiz wird gelöscht.

**Das konkrete Schema wird aus den Beispieldateien in `tests/fixtures/`
abgeleitet, nicht geraten.** Felder, die PSM-DOK liefert, aber oben nicht genannt
sind, gehen nicht verloren: Der Original-Datensatz wird immer mitgespeichert.

Schemaänderungen laufen über nummerierte SQL-Dateien in `migrations/`, die beim
Start in Reihenfolge angewendet werden (Stand über `PRAGMA user_version`).

## 6. Import

- Auslöser: beim Start der Anwendung und über einen Knopf "Jetzt importieren"
  in der Oberfläche. Kein Hintergrunddienst, kein Dateisystem-Watcher.
- Gelesen werden alle `*.zip` im Export-Ordner (Pfad per Umgebungsvariable,
  Standard `/exports`).
- **Umgang mit den ZIP-Dateien:**
  - Die JSON-Datei wird mit dem `zipfile`-Modul der Standardbibliothek direkt
    aus der ZIP in den Speicher gelesen. Es wird nichts auf die Platte entpackt.
  - Die PDF-Datei und alle anderen Inhalte werden ignoriert. Eine ZIP ohne PDF
    ist kein Fehler.
  - Erwartet wird genau eine JSON-Datei je ZIP. Enthält eine ZIP keine
    JSON-Datei, wird sie mit Status "Fehler" vermerkt; enthält sie mehrere,
    werden alle gelesen.
  - Lose `*.json`-Dateien im Export-Ordner werden ebenfalls gelesen (praktisch
    für Tests und von Hand entpackte Dateien).
- **Idempotent:** Ein erneuter Import derselben Dateien erzeugt keine Duplikate.
  - Dateien mit bereits bekanntem SHA-256 werden übersprungen.
  - Zusätzlich wird auf Datensatzebene dedupliziert, weil neuere Exporte
    möglicherweise ältere Einträge erneut enthalten. Schlüssel ist eine stabile
    ID aus dem Export, falls vorhanden, sonst ein Hash über den normalisierten
    Datensatz.
- **Fehlertolerant:** Eine beschädigte ZIP, eine unlesbare oder eine unerwartet
  aufgebaute JSON-Datei bricht den Import nicht ab. Sie wird mit Status "Fehler"
  und Meldung in `import_files` vermerkt und in der Oberfläche angezeigt.
- Da der importierte Teil vollständig aus dem Export-Ordner rekonstruierbar ist,
  muss "Datenbank löschen und neu importieren" jederzeit dasselbe Ergebnis
  liefern. Das gilt nur für die importierten Daten: Notizen gehen dabei
  verloren (siehe Abschnitt 9, Backup).

## 7. Oberfläche in Stufe 1

Sprache der Oberfläche: Deutsch. Schlicht, tabellenorientiert, auf Laptop und
Tablet gut lesbar.

1. **Übersicht** (Startseite): Tabelle aller Anwendungen, standardmäßig neueste
   zuerst. Filter nach Jahr, Betrieb, Schlag, Kultur und Mittel; die Filter
   stehen in der URL, damit Ansichten als Lesezeichen funktionieren.
2. **Detailansicht** einer Anwendung: alle Felder plus Herkunftsdatei und
   Original-Datensatz, dazu ein Textfeld für die eigene Notiz. In der
   Übersicht markiert ein Symbol Anwendungen mit Notiz. Notizen sind nicht
   Teil des CSV-Exports.
3. **Import-Status:** Liste der eingelesenen Dateien mit Zeitpunkt, Anzahl
   Datensätze und Fehlern; Knopf "Jetzt importieren".
4. **CSV-Export** der aktuell gefilterten Ansicht (UTF-8, Semikolon als
   Trennzeichen, damit Tabellenprogramme mit deutscher Einstellung die Datei
   direkt öffnen).

## 8. Tests

Der Importer ist der fehleranfälligste Teil und wird gegen die Fixtures getestet:

- Aus jeder Beispieldatei entsteht die erwartete Anzahl Anwendungen mit
  korrekten Feldwerten.
- Ein zweiter Import derselben Dateien ändert nichts.
- Überlappende Exporte (ältere Einträge erneut enthalten) erzeugen keine
  Duplikate.
- Eine defekte Datei wird als Fehler vermerkt, die übrigen werden importiert.
- Die JSON wird aus der ZIP gelesen; die PDF wird nicht angefasst.
- Eine ZIP ohne PDF wird normal importiert; eine ZIP ohne JSON und eine
  beschädigte ZIP werden als Fehler vermerkt.
- Nach dem Import liegen im Export-Ordner keine zusätzlichen Dateien, und die
  Exportdateien sind bytegleich.

Für die Oberfläche genügen wenige Tests: Übersicht lädt, Filter wirken,
CSV-Export enthält die gefilterten Zeilen.

## 9. Betrieb und Deployment

- Volumes: `./exports:/exports:ro` und `./data:/data`. Auf Systemen mit
  aktivem SELinux (z. B. Fedora, vermutlich auch der Homeserver) brauchen
  beide Mounts zusätzlich das Relabeling-Flag `z`
  (`./exports:/exports:ro,z` bzw. `./data:/data:z`), sonst verweigert der
  Container den Zugriff mit `unable to open database file`. Ohne SELinux ist
  das Flag wirkungslos, aber unschädlich.
- Konfiguration über Umgebungsvariablen in der `compose.yaml`: Export-Pfad
  (`EXPORT_DIR`), Datenbank-Pfad (`DB_PATH`), Port sowie `BETRIEB_ZUORDNUNG`
  zur Zuordnung von `betrieb.guid` zu einem Anzeigenamen (siehe Abschnitt 11,
  Frage 5); keine Zugangsdaten nötig
- Update auf dem Server: `git pull && docker compose up -d --build`
- Backup: `exports/` ist der rechtlich relevante Bestand und gehört in die
  Serversicherung. Seit es Notizen gibt, gehört auch `data/` in die
  Sicherung, weil dort eigene, nicht rekonstruierbare Daten liegen.

## 10. Abnahmekriterien für Stufe 1

- [ ] `docker compose up -d --build` startet die Anwendung ohne weitere Schritte
- [ ] Alle Dateien im Export-Ordner werden eingelesen; Fehler sind sichtbar
- [ ] Die Übersicht zeigt alle Anwendungen beider Betriebe und lässt sich nach
      Jahr, Betrieb, Schlag, Kultur und Mittel filtern
- [ ] Wiederholter Import erzeugt keine Duplikate
- [ ] Datenbank löschen und neu starten stellt denselben Stand der importierten
      Daten wieder her
- [ ] CSV-Export der gefilterten Ansicht funktioniert
- [ ] Die Exportdateien bleiben unverändert (Mount ist read-only)
- [ ] Tests laufen grün

## 11. Offene Fragen

Vor oder während der Umsetzung anhand der Fixtures zu klären. Antworten bitte
hier eintragen.

1. **Exportstruktur** (anhand `tests/fixtures/*.zip`): Ein JSON-Objekt pro
   Datei, flach verschachtelt. Oberste Schlüssel: `version`, `guid`,
   `betrieb` (Objekt), `anwendung` (Objekt mit `datum`, `uhrzeit`, `anwender`,
   `verantwortlich`, `artVerwendung`), `einsatzorte` (Liste), `kulturen`
   (Liste), `pflanzenschutzmittel` (Liste), `zusatzstoffe` (Liste, in beiden
   Fixtures leer). Datum ISO (`"2026-05-04"`), Uhrzeit `"HH:MM"`, Mengen als
   JSON-Zahlen mit Punkt. Jeder Einsatzort trägt `geoTyp` (z. B. `"Schlag-ID"`)
   und zusätzlich einen Schlüssel, der genau so heißt wie dieser Wert, mit dem
   eigentlichen Ortswert (`ort[ort["geoTyp"]]`) – andere `geoTyp`-Werte als
   `"Schlag-ID"` sind noch nicht belegt.
2. **Umfang je Datei:** Nur der neue Eintrag. `anwendung`, `guid` usw. sind
   Einzelwerte, keine Listen – die Struktur kann gar keinen Gesamtbestand
   abbilden.
3. **Stabile ID:** Ja, das Feld `guid` auf oberster Ebene. Dient als
   Dedup-Schlüssel; Fallback (Hash über den normalisierten Datensatz) für
   Exporte ohne dieses Feld bleibt im Importer vorgesehen.
4. **Korrekturen:** Noch kein Fixture mit nachträglich geändertem Eintrag
   vorhanden. Bis dahin: Dedup über `guid`, zusätzlich ein Inhalts-Hash. Kommt
   dieselbe `guid` mit geändertem Inhalt erneut, wird die vorhandene Zeile
   aktualisiert (Feld `geaendert_am`), keine neue Zeile. Bleibt die `guid`
   bei einer Korrektur in PSM-DOK nicht erhalten, entstehen zwei Zeilen; der
   Dublettenhinweis in der Übersicht wird dann nachgerüstet. **Fixture folgt.**
5. **Betriebszuordnung:** Über `betrieb.guid` aus der Datei. In den Fixtures
   ist dieser Wert identisch, weil beide mit demselben PSM-DOK-Benutzerkonto
   erzeugt wurden; in echten Exporten unterscheidet er sich je Betrieb. Die
   Zuordnung GUID → Anzeigename steht in der Umgebungsvariable
   `BETRIEB_ZUORDNUNG` (Format `guid1:Name1,guid2:Name2`), damit sie sich ohne
   Codeänderung pflegen lässt. Ist eine GUID dort nicht eingetragen, fällt der
   Importer auf `betrieb.firma`, sonst `betrieb.name` zurück.
6. **Tankmischungen:** `pflanzenschutzmittel` ist eine Liste – ein Datensatz
   mit mehreren Einträgen, keine mehreren Datensätze. Ebenso `einsatzorte` und
   `kulturen`. In den Fixtures hat jede Liste genau ein Element; ein Beispiel
   mit mehreren fehlt noch. **Fixture folgt.**
7. **Dateinamen:** `PSMDOK_<JJJJMMTT>_<Mittelname, Leerzeichen→_>_<HHMM>_<fünfstellige Zahl>.json`,
   z. B. `PSMDOK_20260504_BENEVIA_2100_31758.json`. Der ursprüngliche
   ZIP-Name ist durch das Verfremden der Fixtures verloren; ob er dem
   JSON-Namen entsprach, ist offen. Der Importer verlässt sich ohnehin nicht
   auf Dateinamen, nur auf den Inhalt.

Noch offen, nicht blockierend für Stufe 1: ein Fixture mit korrigiertem
Eintrag, eines mit Tankmischung, eines mit einem `geoTyp` ungleich
`"Schlag-ID"`, und eines mit befüllten `zusatzstoffe`.
