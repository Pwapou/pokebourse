BEGIN IMMEDIATE;

ALTER TABLE catalog_items ADD COLUMN variant TEXT;
ALTER TABLE catalog_items ADD COLUMN edition TEXT;
ALTER TABLE catalog_items ADD COLUMN grading_company TEXT;
ALTER TABLE catalog_items ADD COLUMN grade TEXT;
ALTER TABLE catalog_items ADD COLUMN certification_number TEXT;

ALTER TABLE market_references ADD COLUMN variant TEXT;
ALTER TABLE market_references ADD COLUMN edition TEXT;
ALTER TABLE market_references ADD COLUMN grading_company TEXT;
ALTER TABLE market_references ADD COLUMN grade TEXT;
ALTER TABLE market_references ADD COLUMN certification_number TEXT;
ALTER TABLE market_references ADD COLUMN source_name TEXT;
ALTER TABLE market_references ADD COLUMN reference_kind TEXT
    CHECK (reference_kind IN ('ventes_conclues', 'annonces', 'estimation_manuelle'));
ALTER TABLE market_references ADD COLUMN observed_at TEXT;
ALTER TABLE market_references ADD COLUMN source_url TEXT;
ALTER TABLE market_references ADD COLUMN sample_size INTEGER CHECK (sample_size >= 1);

CREATE TABLE fee_profile_legacy_assumptions (
    fee_profile_id INTEGER PRIMARY KEY,
    buyer_shipping_cents INTEGER NOT NULL,
    platform_fee_bps INTEGER NOT NULL,
    seller_fixed_fee_cents INTEGER NOT NULL,
    shipping_packaging_cents INTEGER NOT NULL,
    archived_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

INSERT INTO fee_profile_legacy_assumptions (
    fee_profile_id, buyer_shipping_cents, platform_fee_bps,
    seller_fixed_fee_cents, shipping_packaging_cents
)
SELECT id, buyer_shipping_cents, platform_fee_bps,
       seller_fixed_fee_cents, shipping_packaging_cents
FROM fee_profiles;

CREATE TABLE fee_profiles_v11 (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    currency TEXT NOT NULL DEFAULT 'EUR' CHECK (length(currency) = 3),
    buyer_shipping_cents INTEGER CHECK (buyer_shipping_cents >= 0),
    platform_fee_bps INTEGER CHECK (platform_fee_bps >= 0 AND platform_fee_bps <= 10000),
    seller_fixed_fee_cents INTEGER CHECK (seller_fixed_fee_cents >= 0),
    shipping_packaging_cents INTEGER CHECK (shipping_packaging_cents >= 0),
    min_net_profit_cents INTEGER NOT NULL DEFAULT 500 CHECK (min_net_profit_cents >= 0),
    min_roi_bps INTEGER NOT NULL DEFAULT 1500 CHECK (min_roi_bps >= 0 AND min_roi_bps <= 100000),
    min_catalog_samples INTEGER NOT NULL DEFAULT 2 CHECK (min_catalog_samples >= 2 AND min_catalog_samples <= 100),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

INSERT INTO fee_profiles_v11 (
    id, name, currency, buyer_shipping_cents, platform_fee_bps,
    seller_fixed_fee_cents, shipping_packaging_cents,
    min_net_profit_cents, min_roi_bps, min_catalog_samples, is_active, updated_at
)
SELECT
    id, name, currency, NULL, NULL, NULL, NULL,
    min_net_profit_cents, min_roi_bps, min_catalog_samples, is_active, updated_at
FROM fee_profiles;

DROP TABLE fee_profiles;
ALTER TABLE fee_profiles_v11 RENAME TO fee_profiles;

INSERT INTO schema_migrations (version)
VALUES ('0005_profitability_v11.sql');

COMMIT;
