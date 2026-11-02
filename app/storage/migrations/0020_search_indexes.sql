BEGIN IMMEDIATE;

-- Index justifiés par EXPLAIN QUERY PLAN pour la recherche avancée :
-- 1. Filtrage et tri par prix sur les annonces
CREATE INDEX IF NOT EXISTS catalog_items_price_index ON catalog_items(price_cents);

-- 2. Filtrage des lots
CREATE INDEX IF NOT EXISTS catalog_items_is_lot_index ON catalog_items(is_lot);

-- 3. Filtrage par rareté sur les cartes du référentiel
CREATE INDEX IF NOT EXISTS pokemon_ref_cards_rarity_index ON pokemon_reference_cards(rarity);

INSERT INTO schema_migrations (version) VALUES ('0020_search_indexes.sql');

COMMIT;
