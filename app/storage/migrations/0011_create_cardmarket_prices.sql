BEGIN IMMEDIATE;

CREATE TABLE cardmarket_prices (
    id INTEGER PRIMARY KEY,
    product_id INTEGER NOT NULL UNIQUE,
    tcg_dex_id TEXT,
    card_name TEXT NOT NULL,
    expansion_name TEXT,
    language TEXT NOT NULL DEFAULT 'en',
    trend_price_cents INTEGER CHECK (trend_price_cents >= 0),
    avg1_price_cents INTEGER CHECK (avg1_price_cents >= 0),
    avg7_price_cents INTEGER CHECK (avg7_price_cents >= 0),
    avg30_price_cents INTEGER CHECK (avg30_price_cents >= 0),
    currency TEXT NOT NULL DEFAULT 'EUR' CHECK (length(currency) = 3),
    fetched_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX cardmarket_prices_name_index ON cardmarket_prices(card_name);
CREATE INDEX cardmarket_prices_tcgdex_index ON cardmarket_prices(tcg_dex_id);

INSERT INTO schema_migrations (version)
VALUES ('0011_create_cardmarket_prices.sql');

COMMIT;
