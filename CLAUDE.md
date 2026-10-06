# Schlagkartei

Kleine, selbst gehostete Web-App: liest die Exporte von PSM-DOK
(Pflanzenschutz-Dokumentation) aus einem Ordner und zeigt sie als
Gesamtübersicht für zwei landwirtschaftliche Betriebe. Jeder Export ist eine
ZIP-Datei mit einer JSON- und einer PDF-Datei; gelesen wird nur die JSON.
Läuft per Docker Compose auf einem Homeserver im internen Netz.

Vollständige Anforderungen: @SPEC.md. Bei Widerspruch gilt SPEC.md.

## Aktueller Stand

Stufe 1 (Import, Übersicht mit Filtern, CSV-Export, Notizen) ist fertig.
Gebaut wird **Stufe 2** (Schlagkartei, SPEC.md Abschnitt 12). Nichts aus
Stufe 3 umsetzen, auch nicht vorbereitend.

## Oberstes Ziel: Einfachheit

Der Betreiber pflegt den Code allein und ist kein Berufsentwickler. Bevorzuge
immer die Lösung mit weniger Code und weniger Abhängigkeiten. Keine
Abstraktionsschichten, Basisklassen oder Konfigurationsoptionen ohne konkreten
heutigen Bedarf.

## Stack

- Python 3.12+, FastAPI, Uvicorn, Jinja2
- SQLite über `sqlite3` aus der Standardbibliothek, reines SQL, kein ORM
- Schemaänderungen als nummerierte Dateien in `migrations/`
- Optional HTMX als lokale Datei in `app/static/`
- Tests: pytest

## Befehle

Sobald vorhanden, hier aktuell halten:

- Einmalig (lokale Tests, ohne Docker): `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
- Starten: `docker compose up --build`
  - Auf Systemen mit SELinux (z. B. Fedora) stehen die Volume-Mounts in
    `compose.yaml` deshalb mit `:z`/`:ro,z`; ohne das Flag schlägt der
    Start mit `unable to open database file` fehl.
- Tests: `.venv/bin/pytest` (oder `pytest` bei aktivierter venv)

## Feste Regeln

- Dateien im Export-Ordner niemals verändern, verschieben oder löschen. Der
  Mount ist read-only und bleibt es.
- ZIP-Dateien nie auf die Platte entpacken: die JSON mit `zipfile` direkt in
  den Speicher lesen. Die PDF in der ZIP ignorieren, nicht parsen.
- Das Export-Schema nicht raten. Es wird aus `tests/fixtures/` abgeleitet; ist
  dort etwas unklar oder fehlen Beispiele, nachfragen.
- Importierte und eigene Daten in getrennten Tabellen halten.
- Jede Anwendung hat die Spalten `betrieb` und `quelle`.
- Keine neuen Abhängigkeiten ohne Rückfrage.
- Kein npm, kein JavaScript-Build, keine Ressourcen von CDNs.
- Keine echten Betriebsdaten ins Repo: `exports/` und `data/` sind in der
  `.gitignore` und bleiben dort.
- Änderungen am Importer immer mit Test gegen die Fixtures.

## Konventionen

- Code, Bezeichner und Commit-Nachrichten auf Englisch; Texte der Oberfläche
  auf Deutsch.
- Fachbegriffe, die als Spaltenwerte oder in der Oberfläche vorkommen, bleiben
  deutsch (Schlag, Kultur, Betrieb, Zulassungsnummer).
- Kommentare erklären das Warum, nicht das Was.

## Arbeitsweise

- Vor größeren Änderungen einen Plan vorlegen und Freigabe abwarten.
- Kleine Schritte, ein Commit pro abgeschlossener Funktion.
- Offene Fragen aus SPEC.md Abschnitt 11 klären, bevor darauf aufbauender Code
  entsteht; die Antworten dort eintragen.
- Entscheidungen, die von SPEC.md abweichen, erst ansprechen, dann SPEC.md
  anpassen.
