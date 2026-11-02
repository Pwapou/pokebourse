BEGIN IMMEDIATE;

ALTER TABLE listing_identity_evidence ADD COLUMN observations_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE listing_identity_evidence ADD COLUMN pipeline_version TEXT NOT NULL DEFAULT 'lexical-v1';
ALTER TABLE listing_identity_evidence ADD COLUMN observations_explicit INTEGER NOT NULL DEFAULT 0 CHECK(observations_explicit IN (0, 1));
ALTER TABLE listing_identification_snapshots ADD COLUMN observations_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE listing_identification_snapshots ADD COLUMN pipeline_version TEXT NOT NULL DEFAULT 'lexical-v1';

INSERT INTO schema_migrations (version) VALUES ('0022_identification_observations.sql');
COMMIT;
