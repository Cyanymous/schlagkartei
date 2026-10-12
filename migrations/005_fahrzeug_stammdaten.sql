-- „Typ / Serie“ war missverständlich: In der Fuhrpark-Tabelle stand dort eine
-- Beschreibung (z. B. Motor, Leistung), keine Seriennummer. Beides bekommt
-- jetzt ein eigenes Feld.
ALTER TABLE fahrzeuge RENAME COLUMN typ TO modell;
ALTER TABLE fahrzeuge ADD COLUMN seriennummer TEXT;
ALTER TABLE fahrzeuge ADD COLUMN baujahr INTEGER;
