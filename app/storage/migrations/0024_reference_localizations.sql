BEGIN IMMEDIATE;

-- Séparation identité / localisations (T05) : une même identité TCGdex peut
-- désormais porter plusieurs localisations (fr, en, ja…) sans écrasement.
-- L'unicité porte sur le couple (tcgdex_id, reference_language) au lieu du
-- seul tcgdex_id. Les identifiants SQLite internes, les clés externes et
-- toutes les données existantes sont conservés à l'identique ; la locale
-- historique « fr » demeure la localisation de référence par défaut.

ALTER TABLE pokemon_reference_cards RENAME TO pokemon_reference_cards_legacy;

CREATE TABLE pokemon_reference_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tcgdex_id TEXT NOT NULL,
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
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    normalized_name TEXT NOT NULL DEFAULT '',
    normalized_set_name TEXT NOT NULL DEFAULT '',
    canonical_local_id TEXT NOT NULL DEFAULT '',
    reference_language TEXT NOT NULL DEFAULT 'fr',
    UNIQUE(tcgdex_id, reference_language)
);

INSERT INTO pokemon_reference_cards
    (id, tcgdex_id, local_id, name, set_id, set_name, rarity, category, types, hp,
     stage, illustrator, image_url, raw_data, updated_at,
     normalized_name, normalized_set_name, canonical_local_id, reference_language)
SELECT id, tcgdex_id, local_id, name, set_id, set_name, rarity, category, types, hp,
       stage, illustrator, image_url, raw_data, updated_at,
       normalized_name, normalized_set_name, canonical_local_id, reference_language
FROM pokemon_reference_cards_legacy;

DROP TABLE pokemon_reference_cards_legacy;

CREATE INDEX pokemon_ref_cards_name_index ON pokemon_reference_cards(name);
CREATE INDEX pokemon_ref_cards_set_index ON pokemon_reference_cards(set_id);
CREATE INDEX pokemon_ref_cards_local_id_index ON pokemon_reference_cards(local_id);
CREATE INDEX pokemon_ref_cards_lookup_index ON pokemon_reference_cards(name, local_id);
CREATE INDEX pokemon_ref_cards_normalized_lookup ON pokemon_reference_cards(normalized_name, canonical_local_id);
CREATE INDEX pokemon_ref_cards_normalized_set ON pokemon_reference_cards(normalized_set_name, canonical_local_id);
CREATE INDEX pokemon_ref_cards_language_index ON pokemon_reference_cards(reference_language);
CREATE INDEX IF NOT EXISTS pokemon_ref_cards_rarity_index ON pokemon_reference_cards(rarity);

INSERT INTO schema_migrations (version) VALUES ('0024_reference_localizations.sql');

COMMIT;
