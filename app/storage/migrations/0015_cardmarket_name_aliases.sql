BEGIN IMMEDIATE;

-- Nom de base normalisé pour la correspondance multi-langues
-- (« Charizard [Fire Spin | Wing Attack] » → « charizard »).
ALTER TABLE cardmarket_prices ADD COLUMN name_base TEXT;

CREATE INDEX cardmarket_prices_name_base_index ON cardmarket_prices(name_base);

-- Alias multilingues des cartes (TCGdex : même identifiant de carte dans
-- toutes les langues, noms localisés par endpoint /v2/{locale}/cards).
CREATE TABLE card_name_aliases (
    id INTEGER PRIMARY KEY,
    card_id INTEGER NOT NULL REFERENCES pokemon_reference_cards(id) ON DELETE CASCADE,
    locale TEXT NOT NULL CHECK (locale IN ('fr', 'en', 'ko', 'ja', 'zh-tw')),
    name TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (card_id, locale)
);

CREATE INDEX card_name_aliases_lookup_index ON card_name_aliases(locale, name);
CREATE INDEX card_name_aliases_card_index ON card_name_aliases(card_id);

INSERT INTO schema_migrations (version)
VALUES ('0015_cardmarket_name_aliases.sql');

COMMIT;
