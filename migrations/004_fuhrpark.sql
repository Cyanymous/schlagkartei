-- Fuhrpark (SPEC.md Abschnitt 13). Alles hier sind eigene Daten.

-- einheit NULL: Fahrzeug ohne Zähler (z. B. Anhänger). Fahrzeuge werden nicht
-- gelöscht, sondern auf inaktiv gesetzt, damit ihr Fahrzeugbuch erhalten bleibt.
CREATE TABLE fahrzeuge (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    typ TEXT,
    kennzeichen TEXT,
    oelfilter TEXT,
    einheit TEXT CHECK (einheit IN ('h', 'km', 'Stück')),
    tank_liter REAL,
    tuev_faellig TEXT,  -- JJJJ-MM, Monat der Plakette; NULL = kein TÜV
    bemerkung TEXT,
    aktiv INTEGER NOT NULL DEFAULT 1
);

-- prozent ist nur gesetzt, wenn die Liter aus der Tankgröße geschätzt wurden.
-- Die Liter werden beim Speichern ausgerechnet und festgehalten, damit eine
-- spätere Änderung der Tankgröße alte Einträge nicht verschiebt.
CREATE TABLE fahrzeug_eintraege (
    id INTEGER PRIMARY KEY,
    fahrzeug_id INTEGER NOT NULL REFERENCES fahrzeuge(id) ON DELETE CASCADE,
    datum TEXT NOT NULL,
    art TEXT NOT NULL,
    zaehlerstand REAL,
    liter REAL,
    prozent INTEGER,
    beleg TEXT,
    bemerkung TEXT
);

CREATE INDEX idx_fahrzeug_eintraege ON fahrzeug_eintraege(fahrzeug_id, datum);

-- Erledigt ist eine Aufgabe durch einen Eintrag, dessen art gleich aufgabe ist.
CREATE TABLE wartungsaufgaben (
    id INTEGER PRIMARY KEY,
    fahrzeug_id INTEGER NOT NULL REFERENCES fahrzeuge(id) ON DELETE CASCADE,
    aufgabe TEXT NOT NULL,
    intervall_zaehler REAL,
    intervall_monate INTEGER,
    UNIQUE (fahrzeug_id, aufgabe)
);
