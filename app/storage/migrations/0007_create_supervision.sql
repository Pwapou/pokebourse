BEGIN IMMEDIATE;

CREATE TABLE supervision_agents (
    id INTEGER PRIMARY KEY,
    agent_key TEXT NOT NULL UNIQUE CHECK (length(trim(agent_key)) > 0),
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    deployment_id TEXT NOT NULL CHECK (length(trim(deployment_id)) > 0),
    process_state TEXT NOT NULL DEFAULT 'starting'
        CHECK (process_state IN ('starting', 'operational', 'degraded', 'blocked', 'offline', 'stopped')),
    public_ip TEXT,
    last_heartbeat_at TEXT,
    last_heartbeat_received_at TEXT,
    last_seen_at TEXT,
    stop_reason TEXT CHECK (stop_reason IN ('voluntary', 'lost')),
    started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE supervision_collectors (
    id INTEGER PRIMARY KEY,
    agent_id INTEGER NOT NULL REFERENCES supervision_agents(id) ON DELETE CASCADE,
    collector_key TEXT NOT NULL CHECK (length(trim(collector_key)) > 0),
    site TEXT NOT NULL CHECK (length(trim(site)) > 0),
    state TEXT NOT NULL DEFAULT 'starting'
        CHECK (state IN ('starting', 'operational', 'degraded', 'blocked', 'offline', 'stopped')),
    public_ip TEXT,
    last_success_at TEXT,
    last_error_at TEXT,
    last_error_code TEXT,
    last_error_message TEXT,
    last_error_correlation_id TEXT,
    last_error_http_status INTEGER,
    suspended_until TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (agent_id, collector_key)
);

CREATE TABLE supervision_incidents (
    id INTEGER PRIMARY KEY,
    agent_id INTEGER NOT NULL REFERENCES supervision_agents(id) ON DELETE CASCADE,
    collector_key TEXT,
    error_code TEXT NOT NULL CHECK (length(trim(error_code)) > 0),
    message TEXT NOT NULL CHECK (length(trim(message)) > 0),
    http_status INTEGER,
    correlation_id TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    occurrence_count INTEGER NOT NULL DEFAULT 1 CHECK (occurrence_count >= 1),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE INDEX supervision_incidents_active_index
    ON supervision_incidents(is_active, agent_id, collector_key);
CREATE INDEX supervision_incidents_seen_index
    ON supervision_incidents(last_seen_at DESC);

CREATE TABLE supervision_events (
    id INTEGER PRIMARY KEY,
    agent_id INTEGER NOT NULL REFERENCES supervision_agents(id) ON DELETE CASCADE,
    collector_key TEXT,
    event_type TEXT NOT NULL CHECK (event_type IN ('lifecycle', 'heartbeat', 'state_change', 'error')),
    from_state TEXT,
    to_state TEXT,
    error_code TEXT,
    message TEXT,
    http_status INTEGER,
    correlation_id TEXT,
    occurred_at TEXT NOT NULL,
    received_at TEXT NOT NULL
);

CREATE INDEX supervision_events_agent_index
    ON supervision_events(agent_id, occurred_at DESC, id DESC);
CREATE INDEX supervision_events_type_index
    ON supervision_events(event_type, occurred_at DESC);

INSERT INTO schema_migrations (version)
VALUES ('0007_create_supervision.sql');

COMMIT;
