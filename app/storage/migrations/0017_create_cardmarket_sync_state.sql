BEGIN IMMEDIATE;

-- État de la synchronisation Cardmarket quotidienne (worker).
-- Une seule ligne (key = 'daily') : dernier succès, dernière tentative
-- (anti-rebond en cas d'échec réseau) et compte-rendu court.
CREATE TABLE cardmarket_sync_state (
    key TEXT PRIMARY KEY CHECK (key = 'daily'),
    last_success_at TEXT,
    last_attempt_at TEXT NOT NULL,
    detail TEXT,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

INSERT INTO schema_migrations (version)
VALUES ('0017_create_cardmarket_sync_state.sql');

COMMIT;
