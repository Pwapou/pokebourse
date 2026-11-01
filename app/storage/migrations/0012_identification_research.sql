BEGIN IMMEDIATE;

ALTER TABLE pokemon_reference_cards ADD COLUMN normalized_name TEXT NOT NULL DEFAULT '';
ALTER TABLE pokemon_reference_cards ADD COLUMN normalized_set_name TEXT NOT NULL DEFAULT '';
ALTER TABLE pokemon_reference_cards ADD COLUMN canonical_local_id TEXT NOT NULL DEFAULT '';
ALTER TABLE pokemon_reference_cards ADD COLUMN reference_language TEXT NOT NULL DEFAULT 'fr';

UPDATE pokemon_reference_cards SET
    normalized_name = lower(name),
    normalized_set_name = lower(set_name),
    canonical_local_id = local_id;

CREATE INDEX pokemon_ref_cards_normalized_lookup
    ON pokemon_reference_cards(normalized_name, canonical_local_id);
CREATE INDEX pokemon_ref_cards_normalized_set
    ON pokemon_reference_cards(normalized_set_name, canonical_local_id);

CREATE TABLE listing_identity_evidence (
    id INTEGER PRIMARY KEY,
    listing_id INTEGER NOT NULL REFERENCES catalog_items(id) ON DELETE CASCADE,
    evidence_hash TEXT NOT NULL,
    normalization_version TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    attributes_json TEXT NOT NULL,
    image_evidence_ref TEXT,
    incomplete INTEGER NOT NULL DEFAULT 0 CHECK(incomplete IN (0, 1)),
    captured_at TEXT NOT NULL,
    UNIQUE(listing_id, evidence_hash)
);
CREATE INDEX listing_identity_evidence_current
    ON listing_identity_evidence(listing_id, id DESC);

CREATE TABLE listing_identification_decisions (
    id INTEGER PRIMARY KEY,
    listing_id INTEGER NOT NULL REFERENCES catalog_items(id) ON DELETE CASCADE,
    evidence_hash TEXT NOT NULL,
    action TEXT NOT NULL CHECK(action IN ('confirm', 'revoke', 'reclassify_unit')),
    reference_card_id INTEGER REFERENCES pokemon_reference_cards(id),
    tcgdex_id TEXT,
    expected_revision INTEGER NOT NULL CHECK(expected_revision >= 0),
    previous_decision_id INTEGER REFERENCES listing_identification_decisions(id),
    operator TEXT NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL,
    CHECK((action = 'confirm' AND reference_card_id IS NOT NULL AND tcgdex_id IS NOT NULL)
       OR (action <> 'confirm' AND reference_card_id IS NULL AND tcgdex_id IS NULL))
);
CREATE INDEX listing_identification_decisions_current
    ON listing_identification_decisions(listing_id, id DESC);

CREATE TABLE identification_searches (
    id INTEGER PRIMARY KEY,
    criteria_hash TEXT NOT NULL UNIQUE,
    criteria_json TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'fr',
    strategy_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('queued', 'running', 'completed', 'empty', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts >= 0),
    next_attempt_at TEXT NOT NULL,
    lease_owner TEXT,
    lease_expires_at TEXT,
    result_card_ids_json TEXT NOT NULL DEFAULT '[]',
    partial INTEGER NOT NULL DEFAULT 0 CHECK(partial IN (0, 1)),
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE INDEX identification_searches_due
    ON identification_searches(status, next_attempt_at);

CREATE TABLE identification_search_listings (
    search_id INTEGER NOT NULL REFERENCES identification_searches(id) ON DELETE CASCADE,
    listing_id INTEGER NOT NULL REFERENCES catalog_items(id) ON DELETE CASCADE,
    evidence_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(search_id, listing_id, evidence_hash)
);
CREATE INDEX identification_search_listings_listing
    ON identification_search_listings(listing_id, search_id);

INSERT INTO schema_migrations (version)
VALUES ('0012_identification_research.sql');

COMMIT;
