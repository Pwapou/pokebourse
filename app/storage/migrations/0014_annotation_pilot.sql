BEGIN IMMEDIATE;

CREATE TABLE annotation_pilots (
    id INTEGER PRIMARY KEY,
    target_size INTEGER NOT NULL CHECK(target_size BETWEEN 1 AND 5000),
    strategy_version TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE annotation_sampling_batches (
    id INTEGER PRIMARY KEY,
    pilot_id INTEGER NOT NULL REFERENCES annotation_pilots(id),
    seed TEXT NOT NULL,
    frame_json TEXT NOT NULL,
    selected_count INTEGER NOT NULL CHECK(selected_count > 0),
    double_count INTEGER NOT NULL CHECK(double_count >= 0 AND double_count <= selected_count),
    catalog_version TEXT NOT NULL REFERENCES identification_catalog_versions(version),
    created_at TEXT NOT NULL
);

CREATE TABLE annotation_pilot_items (
    id INTEGER PRIMARY KEY,
    pilot_id INTEGER NOT NULL REFERENCES annotation_pilots(id),
    batch_id INTEGER NOT NULL REFERENCES annotation_sampling_batches(id),
    snapshot_id INTEGER NOT NULL REFERENCES listing_identification_snapshots(id),
    initial_status TEXT NOT NULL CHECK(initial_status IN ('identified', 'ambiguous', 'unidentified', 'lot')),
    stratum_key TEXT NOT NULL,
    selected_in_stratum INTEGER NOT NULL CHECK(selected_in_stratum > 0),
    population_in_stratum INTEGER NOT NULL CHECK(population_in_stratum >= selected_in_stratum),
    requires_second INTEGER NOT NULL CHECK(requires_second IN (0, 1)),
    automatic_top1_tcgdex_id TEXT,
    candidate_tcgdex_ids_json TEXT NOT NULL,
    first_review_id INTEGER UNIQUE REFERENCES listing_identification_reviews(id),
    second_review_id INTEGER UNIQUE REFERENCES listing_identification_reviews(id),
    final_review_id INTEGER UNIQUE REFERENCES listing_identification_reviews(id),
    UNIQUE(pilot_id, snapshot_id),
    CHECK(second_review_id IS NULL OR (first_review_id IS NOT NULL AND requires_second = 1)),
    CHECK(final_review_id IS NULL OR first_review_id IS NOT NULL)
);

CREATE INDEX annotation_pilot_items_pilot ON annotation_pilot_items(pilot_id, id);

INSERT INTO schema_migrations(version) VALUES ('0014_annotation_pilot.sql');
COMMIT;
