BEGIN IMMEDIATE;

CREATE TABLE import_failures (
    id INTEGER PRIMARY KEY,
    source_name TEXT NOT NULL,
    filename TEXT NOT NULL,
    input_checksum TEXT NOT NULL,
    error_message TEXT NOT NULL,
    failed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX import_failures_recent_index ON import_failures(failed_at);

INSERT INTO schema_migrations (version)
VALUES ('0004_create_import_failures.sql');

COMMIT;
