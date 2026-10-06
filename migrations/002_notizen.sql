-- Eigene Daten: eine Notiz je Anwendung.
-- Verknüpft über datensatz_key (die guid aus dem Export) statt über
-- applications.id, weil die id beim Neuaufbau der Datenbank neu vergeben wird.
-- Kein ON DELETE CASCADE: der Import darf eigene Daten nie mitlöschen.
CREATE TABLE notizen (
    datensatz_key TEXT PRIMARY KEY REFERENCES applications(datensatz_key),
    text TEXT NOT NULL,
    geaendert_am TEXT NOT NULL
);
