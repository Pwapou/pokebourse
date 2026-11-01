BEGIN IMMEDIATE;

-- 1. listing_watches avec support de 'ebay' et 'wallapop'
CREATE TABLE listing_watches_new (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    platform TEXT NOT NULL CHECK (platform IN ('vinted', 'leboncoin', 'ebay', 'wallapop')),
    search_params TEXT NOT NULL CHECK (json_valid(search_params)),
    interval_seconds INTEGER NOT NULL DEFAULT 120 CHECK (interval_seconds >= 1),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    last_run_at TEXT
);
INSERT INTO listing_watches_new SELECT * FROM listing_watches;
DROP TABLE listing_watches;
ALTER TABLE listing_watches_new RENAME TO listing_watches;
CREATE INDEX listing_watches_active_index ON listing_watches(is_active, platform);

-- 2. seller_profiles avec support de 'ebay' et 'wallapop'
CREATE TABLE seller_profiles_new (
    id INTEGER PRIMARY KEY,
    platform TEXT NOT NULL CHECK (platform IN ('vinted', 'leboncoin', 'ebay', 'wallapop')),
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
    is_favorite INTEGER NOT NULL DEFAULT 0,
    user_notes TEXT,
    UNIQUE (platform, seller_external_id)
);
INSERT INTO seller_profiles_new SELECT * FROM seller_profiles;
DROP TABLE seller_profiles;
ALTER TABLE seller_profiles_new RENAME TO seller_profiles;

-- 3. seller_enrichment_queue avec support de 'ebay' et 'wallapop'
CREATE TABLE seller_enrichment_queue_new (
    id INTEGER PRIMARY KEY,
    platform TEXT NOT NULL CHECK (platform IN ('vinted', 'leboncoin', 'ebay', 'wallapop')),
    seller_external_id TEXT NOT NULL CHECK (length(trim(seller_external_id)) > 0),
    login TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'done', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    last_error TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (platform, seller_external_id)
);
INSERT INTO seller_enrichment_queue_new SELECT * FROM seller_enrichment_queue;
DROP TABLE seller_enrichment_queue;
ALTER TABLE seller_enrichment_queue_new RENAME TO seller_enrichment_queue;
CREATE INDEX seller_enrichment_queue_status_index ON seller_enrichment_queue(status, id);

INSERT INTO schema_migrations (version)
VALUES ('0016_add_ebay_wallapop_platforms.sql');

COMMIT;
