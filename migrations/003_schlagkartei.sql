-- Stufe 2: Schlagkartei. Alles hier sind eigene Daten (SPEC.md Abschnitt 12).

CREATE TABLE schlaege (
    id INTEGER PRIMARY KEY,
    betrieb TEXT NOT NULL,
    name TEXT NOT NULL,
    aktiv INTEGER NOT NULL DEFAULT 1
);

-- Schlagnummer und Größe ändern sich im Agrarantrag mitunter. Ein Stand gilt
-- ab seinem Jahr, bis ein neuerer eingetragen wird.
CREATE TABLE schlag_staende (
    id INTEGER PRIMARY KEY,
    schlag_id INTEGER NOT NULL REFERENCES schlaege(id) ON DELETE CASCADE,
    ab_jahr INTEGER NOT NULL,
    schlagnummer TEXT NOT NULL,
    groesse_ha REAL,
    UNIQUE (schlag_id, ab_jahr)
);

-- mehrjaehrig: Dauerkulturen wie Spargel stehen gewollt mehrere Jahre auf
-- demselben Schlag; für sie gibt es keinen Fruchtfolge-Hinweis.
CREATE TABLE kulturen (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    eppo_code TEXT,
    mehrjaehrig INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE anbau (
    id INTEGER PRIMARY KEY,
    schlag_id INTEGER NOT NULL REFERENCES schlaege(id) ON DELETE CASCADE,
    jahr INTEGER NOT NULL,
    kultur_id INTEGER NOT NULL REFERENCES kulturen(id),
    art TEXT NOT NULL CHECK (art IN ('Hauptkultur', 'Zwischenfrucht', 'Untersaat', 'Zweitfrucht')),
    bemerkung TEXT
);

CREATE INDEX idx_anbau_schlag_jahr ON anbau(schlag_id, jahr);

CREATE TABLE feldarbeiten (
    id INTEGER PRIMARY KEY,
    datum TEXT NOT NULL,
    art TEXT NOT NULL,
    bemerkung TEXT
);

CREATE TABLE feldarbeit_schlaege (
    feldarbeit_id INTEGER NOT NULL REFERENCES feldarbeiten(id) ON DELETE CASCADE,
    schlag_id INTEGER NOT NULL REFERENCES schlaege(id) ON DELETE CASCADE,
    PRIMARY KEY (feldarbeit_id, schlag_id)
);

-- Vorbelegung; jeder Code am 06.10.2026 auf gd.eppo.int geprüft.
INSERT INTO kulturen (name, eppo_code) VALUES
    ('Winterweizen', 'TRZAW'),
    ('Sommerweizen', 'TRZAS'),
    ('Dinkel', 'TRZSP'),
    ('Winterroggen', 'SECCW'),
    ('Sommerroggen', 'SECCS'),
    ('Wintergerste', 'HORVW'),
    ('Sommergerste', 'HORVS'),
    ('Wintertriticale', 'TTLWI'),
    ('Sommertriticale', 'TTLSO'),
    ('Hafer', 'AVESA'),
    ('Winterraps', 'BRSNW'),
    ('Sommerraps', 'BRSNS'),
    ('Mais', 'ZEAMX'),
    ('Zuckerrübe', 'BEAVA'),
    ('Kartoffel', 'SOLTU'),
    ('Spargel', 'ASPOF'),
    ('Ackerbohne', 'VICFX'),
    ('Erbse', 'PIBSX'),
    ('Blaue Lupine', 'LUPAN'),
    ('Sojabohne', 'GLXMA'),
    ('Sonnenblume', 'HELAN'),
    ('Lein', 'LIUUT'),
    ('Rispenhirse', 'PANMI'),
    ('Sorghum', 'SORVU'),
    ('Buchweizen', 'FAGES'),
    ('Luzerne', 'MEDSA'),
    ('Rotklee', 'TRFPR'),
    ('Alexandrinerklee', 'TRFAL'),
    ('Saatwicke', 'VICSA'),
    ('Welsches Weidelgras', 'LOLMU'),
    ('Deutsches Weidelgras', 'LOLPE'),
    ('Weißer Senf', 'SINAL'),
    ('Phacelia', 'PHCTA'),
    ('Ölrettich', 'RAPSO');

UPDATE kulturen SET mehrjaehrig = 1 WHERE name IN ('Spargel', 'Luzerne');
