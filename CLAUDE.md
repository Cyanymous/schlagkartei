# Schlagkartei

Kleine, selbst gehostete Web-App: liest die Exporte von PSM-DOK
(Pflanzenschutz-Dokumentation) aus einem Ordner und zeigt sie als
Gesamtübersicht für zwei landwirtschaftliche Betriebe. Jeder Export ist eine
ZIP-Datei mit einer JSON- und einer PDF-Datei; gelesen wird nur die JSON.
Läuft per Docker Compose auf einem Homeserver im internen Netz.

Vollständige Anforderungen: @SPEC.md. Bei Widerspruch gilt SPEC.md.

## Aktueller Stand

Stufe 1 (Import, Übersicht mit Filtern, CSV-Export, Notizen) ist fertig.
Stufe 2 (Schlagkartei, SPEC.md Abschnitt 12) und der **Fuhrpark** (SPEC.md
Abschnitt 13, eigener Teil derselben App) sind gebaut, die Prüfung durch den
Betreiber steht aus. Nichts aus Stufe 3 umsetzen, auch nicht vorbereitend.

Die Erfassen-Seite des Fuhrparks ist mit HTMX + Alpine.js umgebaut
(29.10.2026), die Prüfung durch den Betreiber steht aus. **Nächster
Schritt:** SPEC.md Abschnitt 13, „Nächster Schritt“; jeweils erst einen Plan
vorlegen und die Freigabe abwarten.

## Oberstes Ziel: Einfachheit

Der Betreiber pflegt den Code allein und ist kein Berufsentwickler. Bevorzuge
immer die Lösung mit weniger Code und weniger Abhängigkeiten. Keine
Abstraktionsschichten, Basisklassen oder Konfigurationsoptionen ohne konkreten
heutigen Bedarf.

## Stack

- Python 3.12+, FastAPI, Uvicorn, Jinja2
- SQLite über `sqlite3` aus der Standardbibliothek, reines SQL, kein ORM
- Schemaänderungen als nummerierte Dateien in `migrations/`
- JavaScript ist ausdrücklich erlaubt, aber sparsam: HTMX + Alpine.js nur
  dort, wo es die Bedienung spürbar verbessert (SPEC.md Abschnitt 4,
  „JavaScript“); eigener Code in `app/static/app.js`, Bibliotheken als
  lokale Dateien; der Server prüft und berechnet alles, was gespeichert
  wird; Formulare funktionieren auch ohne JavaScript
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
- Keine Ressourcen von CDNs. npm und ein JavaScript-Build sind erlaubt, aber
  nur mit konkretem Bedarf und nach Rückfrage (Stand 12.10.2026).
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
