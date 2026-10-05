-- eine Zeile je physischer Datei im Export-Ordner (ZIP oder lose JSON)
CREATE TABLE import_files (
    id INTEGER PRIMARY KEY,
    dateiname TEXT NOT NULL,
    sha256 TEXT NOT NULL UNIQUE,
    importiert_am TEXT NOT NULL,
    anzahl_datensaetze INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL CHECK (status IN ('ok', 'fehler')),
    fehlermeldung TEXT
);

-- eine Zeile je PSM-Anwendung
CREATE TABLE applications (
    id INTEGER PRIMARY KEY,
    datensatz_key TEXT NOT NULL UNIQUE,
    inhalt_hash TEXT NOT NULL,
    betrieb TEXT NOT NULL,
    quelle TEXT NOT NULL DEFAULT 'psmdok',
    datum TEXT NOT NULL,
    jahr INTEGER NOT NULL,
    uhrzeit TEXT,
    anwender TEXT,
    verantwortlich TEXT,
    art_verwendung TEXT,
    betrieb_guid TEXT,
    betrieb_firma TEXT,
    betrieb_name TEXT,
    betrieb_ort TEXT,
    betrieb_gps_hochwert TEXT,
    betrieb_gps_rechtswert TEXT,
    export_version TEXT,
    import_file_id INTEGER NOT NULL REFERENCES import_files(id),
    json_name TEXT,
    zuerst_gesehen_am TEXT NOT NULL,
    geaendert_am TEXT,
    roh_json TEXT NOT NULL
);

CREATE INDEX idx_applications_jahr ON applications(jahr);
CREATE INDEX idx_applications_betrieb ON applications(betrieb);

CREATE TABLE anwendung_mittel (
    id INTEGER PRIMARY KEY,
    application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    name TEXT,
    zulassungsnr TEXT,
    aufwand_menge REAL,
    aufwand_einheit TEXT,
    wirkstoffe TEXT,
    bienen TEXT
);

CREATE INDEX idx_mittel_name ON anwendung_mittel(name);
CREATE INDEX idx_mittel_application ON anwendung_mittel(application_id);

CREATE TABLE anwendung_einsatzorte (
    id INTEGER PRIMARY KEY,
    application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    name TEXT,
    anwendungsbereich TEXT,
    geo_typ TEXT,
    geo_wert TEXT,
    flaeche_volumen REAL,
    einheit TEXT
);

CREATE INDEX idx_einsatzorte_name ON anwendung_einsatzorte(name);
CREATE INDEX idx_einsatzorte_application ON anwendung_einsatzorte(application_id);

CREATE TABLE anwendung_kulturen (
    id INTEGER PRIMARY KEY,
    application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    name TEXT,
    eppo_code TEXT,
    bbch_code TEXT,
    bbch_name TEXT,
    satzweise TEXT
);

CREATE INDEX idx_kulturen_name ON anwendung_kulturen(name);
CREATE INDEX idx_kulturen_application ON anwendung_kulturen(application_id);

-- Feldnamen unbekannt (in den Fixtures bisher immer leer), deshalb roh_json
-- je Eintrag statt geratener Spalten. Sobald ein Fixture mit Inhalt vorliegt,
-- wird das Schema darauf aufbauend erweitert.
CREATE TABLE anwendung_zusatzstoffe (
    id INTEGER PRIMARY KEY,
    application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    roh_json TEXT NOT NULL
);

CREATE INDEX idx_zusatzstoffe_application ON anwendung_zusatzstoffe(application_id);
