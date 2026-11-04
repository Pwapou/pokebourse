BEGIN IMMEDIATE;

-- Conservation explicite et contrôlée des preuves visuelles (T04).
-- L'OCR reste éphémère par défaut : rien n'est conservé sans appel explicite
-- au magasin de preuves. Les octets stockés sont dépourvus de métadonnées
-- EXIF ; l'orientation d'origine et une référence de pixels orientés sont
-- conservées comme repères pour le futur OCR spatial (T06).

CREATE TABLE listing_image_evidence (
    id INTEGER PRIMARY KEY,
    sha256 TEXT NOT NULL UNIQUE,
    pixel_sha256 TEXT NOT NULL,
    storage_path TEXT NOT NULL UNIQUE,
    byte_size INTEGER NOT NULL CHECK(byte_size > 0),
    mime_type TEXT NOT NULL DEFAULT 'image/png',
    width INTEGER NOT NULL CHECK(width > 0),
    height INTEGER NOT NULL CHECK(height > 0),
    exif_orientation INTEGER CHECK(exif_orientation IS NULL OR (exif_orientation >= 1 AND exif_orientation <= 8)),
    purpose TEXT NOT NULL CHECK(purpose IN ('benchmark', 'annotation', 'confirmation')),
    listing_id INTEGER REFERENCES catalog_items(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    deleted_at TEXT
);
CREATE INDEX listing_image_evidence_listing ON listing_image_evidence(listing_id);
CREATE INDEX listing_image_evidence_created ON listing_image_evidence(created_at);

CREATE TABLE listing_image_evidence_readings (
    id INTEGER PRIMARY KEY,
    image_evidence_id INTEGER NOT NULL REFERENCES listing_image_evidence(id),
    listing_id INTEGER REFERENCES catalog_items(id) ON DELETE SET NULL,
    snapshot_id INTEGER REFERENCES listing_identification_snapshots(id) ON DELETE SET NULL,
    field TEXT NOT NULL CHECK(field IN ('name', 'card_number', 'set_name', 'language', 'condition', 'variant', 'edition', 'grading_company', 'grade')),
    value TEXT NOT NULL,
    source TEXT NOT NULL CHECK(source IN ('ocr', 'manual', 'prefill')),
    region_json TEXT,
    transform_version TEXT NOT NULL,
    extractor_version TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX listing_image_readings_evidence ON listing_image_evidence_readings(image_evidence_id);
CREATE INDEX listing_image_readings_snapshot ON listing_image_evidence_readings(snapshot_id);

-- Reconstruction additive de la table des lectures : la base de preuve
-- accepte désormais « image » et « both », et référence la preuve visuelle.
-- Les enregistrements existants sont repris à l'identique (image_evidence_id
-- NULL, base « text »). Aucune ancienne preuve ni décision n'est réécrite.
ALTER TABLE listing_identification_reviews RENAME TO listing_identification_reviews_legacy;

CREATE TABLE listing_identification_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    evidence_basis TEXT NOT NULL CHECK(evidence_basis IN ('text', 'image', 'both')),
    text_sufficient INTEGER NOT NULL CHECK(text_sufficient IN (0, 1)),
    catalog_version TEXT NOT NULL REFERENCES identification_catalog_versions(version),
    sampling_probability REAL CHECK(sampling_probability > 0 AND sampling_probability <= 1),
    comment TEXT CHECK(length(comment) <= 2000),
    image_evidence_id INTEGER REFERENCES listing_image_evidence(id),
    CHECK((outcome = 'matched' AND validated_card_id IS NOT NULL AND validated_tcgdex_id IS NOT NULL)
        OR (outcome <> 'matched' AND validated_card_id IS NULL AND validated_tcgdex_id IS NULL)),
    CHECK(review_kind <> 'annotation' OR outcome <> 'withdrawn')
);

INSERT INTO listing_identification_reviews
    (id, snapshot_id, outcome, validated_card_id, validated_tcgdex_id, review_kind,
     supersedes_review_id, legacy_revision, reviewed_annotation_ids_json, verified_attributes_json,
     validated_by, validated_at, evidence_basis, text_sufficient, catalog_version,
     sampling_probability, comment)
SELECT id, snapshot_id, outcome, validated_card_id, validated_tcgdex_id, review_kind,
       supersedes_review_id, legacy_revision, reviewed_annotation_ids_json, verified_attributes_json,
       validated_by, validated_at, evidence_basis, text_sufficient, catalog_version,
       sampling_probability, comment
FROM listing_identification_reviews_legacy;

DROP TABLE listing_identification_reviews_legacy;

CREATE INDEX identification_reviews_latest ON listing_identification_reviews(snapshot_id, id DESC);

INSERT INTO schema_migrations (version) VALUES ('0023_visual_evidence.sql');

COMMIT;
