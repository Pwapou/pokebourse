BEGIN IMMEDIATE;

ALTER TABLE seller_profiles ADD COLUMN is_favorite INTEGER NOT NULL DEFAULT 0;
ALTER TABLE seller_profiles ADD COLUMN user_notes TEXT;

CREATE TABLE purchases (
    id INTEGER PRIMARY KEY,
    catalog_item_id INTEGER REFERENCES catalog_items(id) ON DELETE SET NULL,
    seller_profile_id INTEGER REFERENCES seller_profiles(id) ON DELETE SET NULL,
    seller_name TEXT NOT NULL,
    card_name TEXT NOT NULL,
    set_name TEXT,
    card_number TEXT,
    condition TEXT,
    price_paid_cents INTEGER NOT NULL CHECK (price_paid_cents >= 0),
    shipping_paid_cents INTEGER NOT NULL DEFAULT 0 CHECK (shipping_paid_cents >= 0),
    currency TEXT NOT NULL DEFAULT 'EUR',
    platform TEXT,
    status TEXT NOT NULL DEFAULT 'recu' CHECK (status IN ('commande', 'recu', 'en_vente', 'vendu')),
    notes TEXT,
    purchased_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX purchases_seller_profile_index ON purchases(seller_profile_id);
CREATE INDEX purchases_purchased_at_index ON purchases(purchased_at);
CREATE INDEX purchases_status_index ON purchases(status);

INSERT INTO schema_migrations (version)
VALUES ('0010_create_purchases_and_seller_stats.sql');

COMMIT;
