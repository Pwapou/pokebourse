BEGIN IMMEDIATE;

CREATE TABLE seller_profiles (
    id INTEGER PRIMARY KEY,
    platform TEXT NOT NULL CHECK (platform IN ('vinted', 'leboncoin')),
    seller_external_id TEXT NOT NULL CHECK (length(trim(seller_external_id)) > 0),
    login TEXT CHECK (login IS NULL OR length(login) <= 200),
    feedback_count INTEGER CHECK (feedback_count IS NULL OR feedback_count >= 0),
    positive_count INTEGER CHECK (positive_count IS NULL OR positive_count >= 0),
    neutral_count INTEGER CHECK (neutral_count IS NULL OR neutral_count >= 0),
    negative_count INTEGER CHECK (negative_count IS NULL OR negative_count >= 0),
    reputation_bps INTEGER CHECK (reputation_bps IS NULL OR reputation_bps BETWEEN 0 AND 10000),
    item_count INTEGER CHECK (item_count IS NULL OR item_count >= 0),
    response_rate_percent INTEGER CHECK (response_rate_percent IS NULL OR response_rate_percent BETWEEN 0 AND 100),
    account_type TEXT CHECK (account_type IS NULL OR length(account_type) <= 30),
    is_banned INTEGER NOT NULL DEFAULT 0 CHECK (is_banned IN (0, 1)),
    profile_url TEXT CHECK (profile_url IS NULL OR length(profile_url) <= 2048),
    fetched_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (platform, seller_external_id)
);

CREATE TABLE seller_enrichment_queue (
    id INTEGER PRIMARY KEY,
    platform TEXT NOT NULL CHECK (platform IN ('vinted', 'leboncoin')),
    seller_external_id TEXT NOT NULL CHECK (length(trim(seller_external_id)) > 0),
    login TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'done', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    last_error TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (platform, seller_external_id)
);

CREATE INDEX seller_enrichment_queue_status_index
    ON seller_enrichment_queue(status, id);

ALTER TABLE catalog_items ADD COLUMN seller_external_id TEXT;
ALTER TABLE catalog_items ADD COLUMN seller_profile_id INTEGER REFERENCES seller_profiles(id);

CREATE INDEX catalog_items_seller_profile_index ON catalog_items(seller_profile_id);
CREATE INDEX catalog_items_seller_external_index ON catalog_items(source_id, seller_external_id);

INSERT INTO schema_migrations (version)
VALUES ('0009_create_seller_profiles.sql');

COMMIT;
