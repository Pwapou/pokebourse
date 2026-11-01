BEGIN IMMEDIATE;

CREATE TABLE identification_catalog_versions (
    version TEXT PRIMARY KEY,
    cards_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE listing_identification_snapshots (
    id INTEGER PRIMARY KEY,
    listing_id INTEGER REFERENCES catalog_items(id) ON DELETE SET NULL,
    input_hash TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    attributes_json TEXT NOT NULL,
    input_origin TEXT NOT NULL CHECK(input_origin IN ('original_text', 'structured_import', 'legacy_unknown')),
    source_kind TEXT NOT NULL,
    platform TEXT NOT NULL CHECK(platform IN ('vinted', 'leboncoin', 'manual', 'unknown')),
    group_key TEXT NOT NULL,
    normalization_version TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    UNIQUE(listing_id, input_hash)
);

CREATE TABLE listing_identification_reviews (
    id INTEGER PRIMARY KEY,
    snapshot_id INTEGER NOT NULL REFERENCES listing_identification_snapshots(id),
    outcome TEXT NOT NULL CHECK(outcome IN (
        'matched', 'lot', 'not_card', 'no_catalog_match', 'insufficient_evidence', 'withdrawn')),
    validated_card_id INTEGER REFERENCES pokemon_reference_cards(id),
    validated_tcgdex_id TEXT,
    review_kind TEXT NOT NULL CHECK(review_kind IN ('annotation', 'decision', 'adjudication')),
    supersedes_review_id INTEGER REFERENCES listing_identification_reviews(id),
    legacy_revision INTEGER NOT NULL DEFAULT 0 CHECK(legacy_revision >= 0),
    reviewed_annotation_ids_json TEXT NOT NULL DEFAULT '[]',
    verified_attributes_json TEXT NOT NULL DEFAULT '{}',
    validated_by TEXT NOT NULL CHECK(length(trim(validated_by)) > 0),
    validated_at TEXT NOT NULL,
    evidence_basis TEXT NOT NULL CHECK(evidence_basis = 'text'),
    text_sufficient INTEGER NOT NULL CHECK(text_sufficient IN (0, 1)),
    catalog_version TEXT NOT NULL REFERENCES identification_catalog_versions(version),
    sampling_probability REAL CHECK(sampling_probability > 0 AND sampling_probability <= 1),
    comment TEXT CHECK(length(comment) <= 2000),
    CHECK((outcome = 'matched' AND validated_card_id IS NOT NULL AND validated_tcgdex_id IS NOT NULL)
        OR (outcome <> 'matched' AND validated_card_id IS NULL AND validated_tcgdex_id IS NULL)),
    CHECK(review_kind <> 'annotation' OR outcome <> 'withdrawn')
);

ALTER TABLE catalog_items ADD COLUMN identification_snapshot_id INTEGER
    REFERENCES listing_identification_snapshots(id) ON DELETE SET NULL;

CREATE INDEX identification_reviews_latest ON listing_identification_reviews(snapshot_id, id DESC);
CREATE INDEX identification_snapshots_listing ON listing_identification_snapshots(listing_id, id DESC);

INSERT INTO schema_migrations(version) VALUES ('0013_identification_reviews.sql');
COMMIT;
