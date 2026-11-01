BEGIN IMMEDIATE;

CREATE TABLE fee_profiles (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    currency TEXT NOT NULL DEFAULT 'EUR' CHECK (length(currency) = 3),
    buyer_shipping_cents INTEGER NOT NULL DEFAULT 0 CHECK (buyer_shipping_cents >= 0),
    platform_fee_bps INTEGER NOT NULL DEFAULT 500 CHECK (platform_fee_bps >= 0 AND platform_fee_bps <= 10000),
    seller_fixed_fee_cents INTEGER NOT NULL DEFAULT 0 CHECK (seller_fixed_fee_cents >= 0),
    shipping_packaging_cents INTEGER NOT NULL DEFAULT 200 CHECK (shipping_packaging_cents >= 0),
    min_net_profit_cents INTEGER NOT NULL DEFAULT 500 CHECK (min_net_profit_cents >= 0),
    min_roi_bps INTEGER NOT NULL DEFAULT 1500 CHECK (min_roi_bps >= 0 AND min_roi_bps <= 100000),
    min_catalog_samples INTEGER NOT NULL DEFAULT 2 CHECK (min_catalog_samples >= 2 AND min_catalog_samples <= 100),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

INSERT INTO fee_profiles (
    name,
    currency,
    buyer_shipping_cents,
    platform_fee_bps,
    seller_fixed_fee_cents,
    shipping_packaging_cents,
    min_net_profit_cents,
    min_roi_bps,
    min_catalog_samples,
    is_active
) VALUES (
    'Standard',
    'EUR',
    0,
    500,
    0,
    200,
    500,
    1500,
    2,
    1
);

CREATE TABLE market_references (
    id INTEGER PRIMARY KEY,
    card_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    set_name TEXT NOT NULL,
    card_number TEXT,
    language TEXT NOT NULL DEFAULT 'fr',
    condition TEXT,
    reference_price_cents INTEGER NOT NULL CHECK (reference_price_cents >= 0),
    currency TEXT NOT NULL DEFAULT 'EUR' CHECK (length(currency) = 3),
    source_kind TEXT NOT NULL DEFAULT 'manual' CHECK (source_kind IN ('manual', 'jsonl')),
    note TEXT,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX market_references_lookup_index ON market_references(set_name, name);

INSERT INTO schema_migrations (version)
VALUES ('0003_create_profitability.sql');

COMMIT;
