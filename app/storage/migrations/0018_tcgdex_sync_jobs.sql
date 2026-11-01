BEGIN IMMEDIATE;

CREATE TABLE tcgdex_sync_jobs (
    id INTEGER PRIMARY KEY,
    resource_key TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL CHECK(kind IN ('directory', 'set')),
    set_id TEXT,
    status TEXT NOT NULL CHECK(status IN ('queued', 'running', 'paused', 'completed', 'failed')),
    stage TEXT NOT NULL CHECK(stage IN ('manifest', 'details', 'done')),
    include_details INTEGER NOT NULL DEFAULT 1 CHECK(include_details IN (0, 1)),
    manifest_json TEXT,
    expected_count INTEGER CHECK(expected_count IS NULL OR expected_count >= 0),
    summary_count INTEGER NOT NULL DEFAULT 0 CHECK(summary_count >= 0),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts >= 0),
    next_attempt_at TEXT NOT NULL,
    lease_owner TEXT,
    lease_expires_at TEXT,
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_success_at TEXT,
    CHECK((kind='directory' AND set_id IS NULL) OR (kind='set' AND set_id IS NOT NULL))
);

CREATE TABLE tcgdex_sync_cards (
    job_id INTEGER NOT NULL REFERENCES tcgdex_sync_jobs(id) ON DELETE CASCADE,
    tcgdex_id TEXT NOT NULL,
    position INTEGER NOT NULL CHECK(position >= 0),
    summary_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'completed')),
    completed_at TEXT,
    PRIMARY KEY(job_id, tcgdex_id)
);

CREATE INDEX tcgdex_sync_cards_pending ON tcgdex_sync_cards(job_id, status, position);
CREATE INDEX tcgdex_sync_jobs_due ON tcgdex_sync_jobs(status, next_attempt_at);

CREATE TABLE tcgdex_sync_control (
    id INTEGER PRIMARY KEY CHECK(id=1),
    next_request_at TEXT NOT NULL,
    lease_owner TEXT,
    lease_expires_at TEXT
);
INSERT INTO tcgdex_sync_control(id, next_request_at) VALUES (1, '1970-01-01T00:00:00.000Z');

INSERT INTO schema_migrations(version) VALUES ('0018_tcgdex_sync_jobs.sql');
COMMIT;
