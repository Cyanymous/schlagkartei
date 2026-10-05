# Test-Fixtures: PSM-DOK-Beispielexporte

In diesem Ordner liegen echte PSM-DOK-Exporte mit verfremdeten Betriebsdaten.
Sie sind die einzige Quelle für das Import-Schema und die Grundlage aller
Importer-Tests.

## Format

PSM-DOK liefert je Download eine **ZIP-Datei** mit zwei Inhalten:

- eine JSON-Datei mit den Aufzeichnungen (wird importiert)
- eine PDF-Datei mit derselben Information in lesbarer Form (wird ignoriert)

Die Fixtures liegen hier ebenfalls als ZIP, damit die Tests denselben Weg gehen
wie der echte Import.

## Was hier liegen sollte

- Mindestens **zwei ZIP-Dateien, die nacheinander entstanden sind** (erst ein
  Eintrag, dann ein weiterer). Daran lässt sich erkennen, ob PSM-DOK jeweils den
  Gesamtbestand oder nur den neuen Eintrag exportiert.
- Wenn möglich je ein Beispiel für:
  - eine Tankmischung mit mehreren Mitteln
  - eine Anwendung mit Uhrzeit (zeitliche Einschränkung, z. B. Bienenauflage)
  - eine Anwendung mit BBCH-Angabe
  - je eine Datei aus beiden Betrieben
  - einen nachträglich in PSM-DOK korrigierten Eintrag

## Verfremden

Achtung: **Auch die PDF in der ZIP enthält die echten Betriebsdaten.** Es
genügt deshalb nicht, nur die JSON zu bearbeiten.

Vorgehen je Beispiel:

1. ZIP entpacken.
2. In der JSON nur die **Werte** dieser Angaben ersetzen:
   - Namen von Betrieb, Betriebsleiter und Anwendern
   - Anschrift
   - Betriebs- bzw. InVeKoS-Nummern
   - GPS-Koordinaten und Schlagnamen, falls sie Rückschlüsse zulassen
3. Die PDF löschen (der Importer kommt ohne sie aus) oder durch eine leere
   Platzhalter-PDF gleichen Namens ersetzen.
4. Neu packen, den ursprünglichen Namen der JSON-Datei dabei beibehalten:

   ```bash
   zip 01_erster_eintrag.zip name-der-json-datei.json
   ```

**Feldnamen, Verschachtelung, Datums- und Zahlenformate unverändert lassen.**
Mittel, Zulassungsnummern, Kulturen, EPPO-Codes und Mengen können original
bleiben; sie sind nicht personenbezogen und machen die Tests realistischer.

## Benennung

Sprechende Namen helfen in den Tests, zum Beispiel:

```
01_erster_eintrag.zip
02_zweiter_eintrag.zip
03_tankmischung.zip
```

Die Reihenfolge der Entstehung sollte am Namen erkennbar sein. Das ursprüngliche
Namensschema von PSM-DOK bitte einmal in SPEC.md, Abschnitt 11, Frage 7 notieren,
da es durch das Umbenennen hier verloren geht.
