BEGIN IMMEDIATE;

CREATE TABLE catalog_items (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    import_batch_id INTEGER NOT NULL REFERENCES import_batches(id),
    external_id TEXT NOT NULL,
    name TEXT NOT NULL,
    set_name TEXT NOT NULL,
    card_number TEXT,
    language TEXT NOT NULL DEFAULT 'fr',
    condition TEXT,
    price_cents INTEGER NOT NULL CHECK (price_cents >= 0),
    currency TEXT NOT NULL DEFAULT 'EUR' CHECK (length(currency) = 3),
    seller TEXT,
    url TEXT,
    imported_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (source_id, external_id)
);

CREATE INDEX catalog_items_name_index ON catalog_items(name);
CREATE INDEX catalog_items_set_name_index ON catalog_items(set_name);
CREATE INDEX catalog_items_batch_index ON catalog_items(import_batch_id);

INSERT INTO schema_migrations (version)
VALUES ('0002_create_catalog.sql');

COMMIT;
