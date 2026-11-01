BEGIN IMMEDIATE;

CREATE TABLE listing_decisions (
    listing_id INTEGER PRIMARY KEY REFERENCES catalog_items(id) ON DELETE CASCADE,
    state TEXT NOT NULL CHECK (state IN ('a_examiner', 'ecartee')),
    reason TEXT,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE TABLE listing_observations (
    id INTEGER PRIMARY KEY,
    listing_id INTEGER NOT NULL REFERENCES catalog_items(id) ON DELETE CASCADE,
    price_cents INTEGER NOT NULL CHECK (price_cents >= 0),
    shipping_cents INTEGER CHECK (shipping_cents >= 0),
    currency TEXT NOT NULL,
    available INTEGER CHECK (available IN (0, 1)),
    observed_at TEXT NOT NULL,
    origin TEXT NOT NULL CHECK (origin IN ('etat_migration', 'collecteur', 'import', 'extension'))
);
CREATE INDEX listing_observations_listing_index ON listing_observations(listing_id, id DESC);
CREATE TABLE listing_events (
    id INTEGER PRIMARY KEY,
    listing_id INTEGER NOT NULL REFERENCES catalog_items(id) ON DELETE CASCADE,
    observation_id INTEGER NOT NULL UNIQUE REFERENCES listing_observations(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('creation', 'baisse_prix', 'changement')),
    created_at TEXT NOT NULL
);
CREATE INDEX listing_events_listing_kind_index ON listing_events(listing_id, kind, id DESC);

INSERT INTO listing_observations (listing_id, price_cents, shipping_cents, currency, available, observed_at, origin)
SELECT id, price_cents, shipping_cents, currency, NULL,
       COALESCE(last_seen_at, imported_at), 'etat_migration'
FROM catalog_items;

INSERT INTO schema_migrations (version) VALUES ('0019_radar_observations.sql');
COMMIT;
