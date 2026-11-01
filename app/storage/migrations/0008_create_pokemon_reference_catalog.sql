BEGIN IMMEDIATE;

CREATE TABLE pokemon_reference_sets (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    series TEXT,
    card_count_total INTEGER,
    card_count_official INTEGER,
    release_date TEXT,
    logo_url TEXT,
    symbol_url TEXT,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX pokemon_ref_sets_name_index ON pokemon_reference_sets(name);

CREATE TABLE pokemon_reference_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tcgdex_id TEXT NOT NULL UNIQUE,
    local_id TEXT NOT NULL,
    name TEXT NOT NULL,
    set_id TEXT NOT NULL REFERENCES pokemon_reference_sets(id),
    set_name TEXT NOT NULL,
    rarity TEXT,
    category TEXT,
    types TEXT,
    hp INTEGER,
    stage TEXT,
    illustrator TEXT,
    image_url TEXT,
    raw_data TEXT,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX pokemon_ref_cards_name_index ON pokemon_reference_cards(name);
CREATE INDEX pokemon_ref_cards_set_index ON pokemon_reference_cards(set_id);
CREATE INDEX pokemon_ref_cards_local_id_index ON pokemon_reference_cards(local_id);
CREATE INDEX pokemon_ref_cards_lookup_index ON pokemon_reference_cards(name, local_id);

ALTER TABLE catalog_items ADD COLUMN identification_status TEXT NOT NULL DEFAULT 'unidentified'
    CHECK (identification_status IN ('identified', 'ambiguous', 'unidentified', 'lot'));
ALTER TABLE catalog_items ADD COLUMN reference_card_id INTEGER REFERENCES pokemon_reference_cards(id);
ALTER TABLE catalog_items ADD COLUMN identification_confidence INTEGER
    CHECK (identification_confidence IS NULL OR (identification_confidence >= 0 AND identification_confidence <= 100));
ALTER TABLE catalog_items ADD COLUMN identification_reason TEXT;
ALTER TABLE catalog_items ADD COLUMN is_lot INTEGER NOT NULL DEFAULT 0 CHECK (is_lot IN (0, 1));

CREATE INDEX catalog_items_ident_status_index ON catalog_items(identification_status);
CREATE INDEX catalog_items_ref_card_index ON catalog_items(reference_card_id);

INSERT INTO schema_migrations (version)
VALUES ('0008_create_pokemon_reference_catalog.sql');

COMMIT;
