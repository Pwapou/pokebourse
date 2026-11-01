BEGIN IMMEDIATE;

CREATE TABLE listing_watches (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    platform TEXT NOT NULL CHECK (platform IN ('vinted', 'leboncoin')),
    search_params TEXT NOT NULL CHECK (json_valid(search_params)),
    interval_seconds INTEGER NOT NULL DEFAULT 120 CHECK (interval_seconds >= 1),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    last_run_at TEXT
);

CREATE INDEX listing_watches_active_index ON listing_watches(is_active, platform);

CREATE TABLE listing_watch_runs (
    id INTEGER PRIMARY KEY,
    watch_id INTEGER NOT NULL REFERENCES listing_watches(id) ON DELETE CASCADE,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'success', 'failed')),
    result_count INTEGER NOT NULL DEFAULT 0 CHECK (result_count >= 0),
    created_count INTEGER NOT NULL DEFAULT 0 CHECK (created_count >= 0),
    updated_count INTEGER NOT NULL DEFAULT 0 CHECK (updated_count >= 0),
    invalid_count INTEGER NOT NULL DEFAULT 0 CHECK (invalid_count >= 0),
    error_message TEXT,
    import_batch_id INTEGER REFERENCES import_batches(id)
);

CREATE UNIQUE INDEX listing_watch_runs_active_index
    ON listing_watch_runs(watch_id) WHERE finished_at IS NULL;

CREATE INDEX listing_watch_runs_watch_index ON listing_watch_runs(watch_id, started_at DESC);
CREATE INDEX listing_watch_runs_status_index ON listing_watch_runs(status, started_at DESC);

ALTER TABLE catalog_items ADD COLUMN original_title TEXT;
ALTER TABLE catalog_items ADD COLUMN first_seen_at TEXT;
ALTER TABLE catalog_items ADD COLUMN last_seen_at TEXT;
ALTER TABLE catalog_items ADD COLUMN published_at TEXT;
ALTER TABLE catalog_items ADD COLUMN image_url TEXT;
ALTER TABLE catalog_items ADD COLUMN shipping_cents INTEGER CHECK (shipping_cents >= 0);
ALTER TABLE catalog_items ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1));
ALTER TABLE catalog_items ADD COLUMN raw_data TEXT CHECK (raw_data IS NULL OR json_valid(raw_data));

CREATE INDEX catalog_items_seen_index ON catalog_items(last_seen_at);
CREATE INDEX catalog_items_source_seen_index ON catalog_items(source_id, last_seen_at);

INSERT INTO schema_migrations (version)
VALUES ('0006_create_listing_watches.sql');

COMMIT;
