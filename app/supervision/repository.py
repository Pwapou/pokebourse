"""Persistance SQLite de la supervision (agents, collecteurs, incidents, événements)."""

import json
import sqlite3
from typing import Any

from app.supervision.models import AGENT_STATES, StructuredError, utc_now

DEFAULT_COLLECTORS: tuple[tuple[str, str], ...] = (
    ("vinted", "Vinted"),
    ("leboncoin", "Leboncoin"),
)


def _parse_time(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def register_agent(
    connection: sqlite3.Connection,
    *,
    agent_key: str,
    name: str,
    deployment_id: str,
    public_ip: str | None = None,
    collectors: tuple[tuple[str, str], ...] = DEFAULT_COLLECTORS,
    now: str | None = None,
) -> int:
    """Enregistre un déploiement et ses collecteurs, ou le réactive."""

    current = now or utc_now()
    with connection:
        row = connection.execute(
            "SELECT id FROM supervision_agents WHERE agent_key = ?", (agent_key,)
        ).fetchone()
        if row is None:
            cursor = connection.execute(
                """
                INSERT INTO supervision_agents (
                    agent_key, name, deployment_id, process_state, public_ip,
                    last_heartbeat_at, last_heartbeat_received_at, started_at
                ) VALUES (?, ?, ?, 'starting', ?, ?, ?, ?)
                """,
                (agent_key, name, deployment_id, public_ip, current, current, current),
            )
            agent_id = int(cursor.lastrowid)
        else:
            agent_id = int(row["id"])
            connection.execute(
                """
                UPDATE supervision_agents SET
                    name = ?, deployment_id = ?, public_ip = ?,
                    process_state = 'starting', stop_reason = NULL, updated_at = ?
                WHERE id = ?
                """,
                (name, deployment_id, public_ip, current, agent_id),
            )
        for collector_key, site in collectors:
            connection.execute(
                """
                INSERT INTO supervision_collectors (agent_id, collector_key, site)
                VALUES (?, ?, ?)
                ON CONFLICT (agent_id, collector_key) DO NOTHING
                """,
                (agent_id, collector_key, site),
            )
    return agent_id


def record_heartbeat(
    connection: sqlite3.Connection,
    *,
    agent_id: int,
    public_ip: str | None = None,
    collector_ips: dict[str, str | None] | None = None,
    occurred_at: str | None = None,
) -> None:
    """Reçoit un signal de vie ; ne modifie jamais l'état des collecteurs."""

    received_at = utc_now()
    current = occurred_at or received_at
    with connection:
        connection.execute(
            """
            UPDATE supervision_agents SET
                last_heartbeat_at = ?, last_heartbeat_received_at = ?,
                last_seen_at = ?, public_ip = COALESCE(?, public_ip), updated_at = ?
            WHERE id = ?
            """,
            (current, received_at, received_at, public_ip, received_at, agent_id),
        )
        connection.execute(
            """
            INSERT INTO supervision_events (
                agent_id, event_type, occurred_at, received_at
            ) VALUES (?, 'heartbeat', ?, ?)
            """,
            (agent_id, current, received_at),
        )
        for collector_key, ip in (collector_ips or {}).items():
            connection.execute(
                """
                UPDATE supervision_collectors SET
                    public_ip = COALESCE(?, public_ip), updated_at = ?
                WHERE agent_id = ? AND collector_key = ?
                """,
                (ip, received_at, agent_id, collector_key),
            )


def set_process_state(
    connection: sqlite3.Connection,
    *,
    agent_id: int,
    to_state: str,
    message: str | None = None,
    correlation_id: str | None = None,
    stop_reason: str | None = None,
    occurred_at: str | None = None,
) -> None:
    """Change l'état du processus agent et journalise la transition."""

    if to_state not in AGENT_STATES:
        raise ValueError(f"État inconnu : {to_state}")
    received_at = utc_now()
    current = occurred_at or received_at
    with connection:
        row = connection.execute(
            "SELECT process_state FROM supervision_agents WHERE id = ?", (agent_id,)
        ).fetchone()
        if row is None:
            raise LookupError(f"Agent introuvable : {agent_id}")
        from_state = str(row["process_state"])
        connection.execute(
            """
            UPDATE supervision_agents SET
                process_state = ?, stop_reason = ?, updated_at = ?
            WHERE id = ?
            """,
            (to_state, stop_reason, received_at, agent_id),
        )
        connection.execute(
            """
            INSERT INTO supervision_events (
                agent_id, event_type, from_state, to_state, message,
                correlation_id, occurred_at, received_at
            ) VALUES (?, 'state_change', ?, ?, ?, ?, ?, ?)
            """,
            (
                agent_id,
                from_state,
                to_state,
                message,
                correlation_id,
                current,
                received_at,
            ),
        )


def record_collector_state(
    connection: sqlite3.Connection,
    *,
    agent_id: int,
    collector_key: str,
    to_state: str,
    message: str | None = None,
    correlation_id: str | None = None,
    suspended_until: str | None = None,
    public_ip: str | None = None,
    occurred_at: str | None = None,
) -> None:
    """Change l'état d'un collecteur et journalise la transition."""

    if to_state not in AGENT_STATES:
        raise ValueError(f"État inconnu : {to_state}")
    received_at = utc_now()
    current = occurred_at or received_at
    with connection:
        row = connection.execute(
            """
            SELECT id, state FROM supervision_collectors
            WHERE agent_id = ? AND collector_key = ?
            """,
            (agent_id, collector_key),
        ).fetchone()
        if row is None:
            raise LookupError(f"Collecteur introuvable : {collector_key}")
        connection.execute(
            """
            UPDATE supervision_collectors SET
                state = ?, suspended_until = ?,
                public_ip = COALESCE(?, public_ip), updated_at = ?
            WHERE id = ?
            """,
            (to_state, suspended_until, public_ip, received_at, int(row["id"])),
        )
        connection.execute(
            """
            INSERT INTO supervision_events (
                agent_id, collector_key, event_type, from_state, to_state,
                message, correlation_id, occurred_at, received_at
            ) VALUES (?, ?, 'state_change', ?, ?, ?, ?, ?, ?)
            """,
            (
                agent_id,
                collector_key,
                str(row["state"]),
                to_state,
                message,
                correlation_id,
                current,
                received_at,
            ),
        )


def record_collector_success(
    connection: sqlite3.Connection,
    *,
    agent_id: int,
    collector_key: str,
    result_count: int,
    occurred_at: str | None = None,
) -> None:
    """Consigne une collecte réussie et résout l'incident actif éventuel."""

    received_at = utc_now()
    current = occurred_at or received_at
    with connection:
        row = connection.execute(
            """
            SELECT id, state FROM supervision_collectors
            WHERE agent_id = ? AND collector_key = ?
            """,
            (agent_id, collector_key),
        ).fetchone()
        if row is None:
            raise LookupError(f"Collecteur introuvable : {collector_key}")
        collector_id = int(row["id"])
        from_state = str(row["state"])
        to_state = "operational" if from_state in {"degraded", "blocked", "starting"} else from_state
        connection.execute(
            """
            UPDATE supervision_collectors SET
                state = ?, last_success_at = ?, suspended_until = NULL, updated_at = ?
            WHERE id = ?
            """,
            (to_state, current, received_at, collector_id),
        )
        if to_state != from_state:
            connection.execute(
                """
                INSERT INTO supervision_events (
                    agent_id, collector_key, event_type, from_state, to_state,
                    message, occurred_at, received_at
                ) VALUES (?, ?, 'state_change', ?, ?, 'Collecte réussie.', ?, ?)
                """,
                (agent_id, collector_key, from_state, to_state, current, received_at),
            )
        connection.execute(
            """
            UPDATE supervision_incidents SET is_active = 0, resolved_at = ?
            WHERE agent_id = ? AND collector_key = ? AND is_active = 1
            """,
            (current, agent_id, collector_key),
        )


def record_collector_error(
    connection: sqlite3.Connection,
    *,
    agent_id: int,
    collector_key: str,
    error: StructuredError,
    to_state: str | None = None,
    suspended_until: str | None = None,
) -> None:
    """Consigne une erreur structurée et déduit l'état du collecteur.

    Les occurrences d'un même incident actif sont dédupliquées et comptabilisées.
    Les événements reçus en retard n'écrasent jamais un état plus récent.
    """

    received_at = utc_now()
    with connection:
        row = connection.execute(
            """
            SELECT id, state, last_error_at FROM supervision_collectors
            WHERE agent_id = ? AND collector_key = ?
            """,
            (agent_id, collector_key),
        ).fetchone()
        if row is None:
            raise LookupError(f"Collecteur introuvable : {collector_key}")
        collector_id = int(row["id"])
        if row["last_error_at"] is not None and str(row["last_error_at"]) > error.occurred_at:
            # Événement ancien reçu en retard : on journalise sans écraser l'état.
            connection.execute(
                """
                INSERT INTO supervision_events (
                    agent_id, collector_key, event_type, error_code, message,
                    http_status, correlation_id, occurred_at, received_at
                ) VALUES (?, ?, 'error', ?, ?, ?, ?, ?, ?)
                """,
                (
                    agent_id,
                    collector_key,
                    error.code,
                    error.message,
                    error.http_status,
                    error.correlation_id,
                    error.occurred_at,
                    received_at,
                ),
            )
            return
        target_state = to_state or str(row["state"])
        connection.execute(
            """
            UPDATE supervision_collectors SET
                state = ?, last_error_at = ?, last_error_code = ?,
                last_error_message = ?, last_error_correlation_id = ?,
                last_error_http_status = ?, suspended_until = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                target_state,
                error.occurred_at,
                error.code,
                error.message,
                error.correlation_id,
                error.http_status,
                suspended_until,
                received_at,
                collector_id,
            ),
        )
        if str(row["state"]) != target_state:
            connection.execute(
                """
                INSERT INTO supervision_events (
                    agent_id, collector_key, event_type, from_state, to_state,
                    error_code, message, http_status, correlation_id,
                    occurred_at, received_at
                ) VALUES (?, ?, 'state_change', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    agent_id,
                    collector_key,
                    str(row["state"]),
                    target_state,
                    error.code,
                    error.message,
                    error.http_status,
                    error.correlation_id,
                    error.occurred_at,
                    received_at,
                ),
            )
        connection.execute(
            """
            INSERT INTO supervision_events (
                agent_id, collector_key, event_type, error_code, message,
                http_status, correlation_id, occurred_at, received_at
            ) VALUES (?, ?, 'error', ?, ?, ?, ?, ?, ?)
            """,
            (
                agent_id,
                collector_key,
                error.code,
                error.message,
                error.http_status,
                error.correlation_id,
                error.occurred_at,
                received_at,
            ),
        )
        _deduplicate_incident(
            connection,
            agent_id=agent_id,
            collector_key=collector_key,
            error=error,
        )


def _deduplicate_incident(
    connection: sqlite3.Connection,
    *,
    agent_id: int,
    collector_key: str,
    error: StructuredError,
) -> None:
    active = connection.execute(
        """
        SELECT id, occurrence_count FROM supervision_incidents
        WHERE agent_id = ? AND collector_key = ? AND error_code = ? AND is_active = 1
        """,
        (agent_id, collector_key, error.code),
    ).fetchone()
    if active is None:
        connection.execute(
            """
            INSERT INTO supervision_incidents (
                agent_id, collector_key, error_code, message, http_status,
                correlation_id, is_active, occurrence_count,
                first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, 1, 1, ?, ?)
            """,
            (
                agent_id,
                collector_key,
                error.code,
                error.message,
                error.http_status,
                error.correlation_id,
                error.occurred_at,
                error.occurred_at,
            ),
        )
    else:
        connection.execute(
            """
            UPDATE supervision_incidents SET
                occurrence_count = occurrence_count + 1,
                last_seen_at = ?, message = ?, http_status = ?
            WHERE id = ?
            """,
            (error.occurred_at, error.message, error.http_status, int(active["id"])),
        )


def mark_lost_agents(
    connection: sqlite3.Connection,
    *,
    now: str,
    offline_after_seconds: float,
) -> list[int]:
    """Passe hors ligne les agents sans signal de vie au-delà du délai."""

    with connection:
        rows = connection.execute(
            """
            SELECT id, last_heartbeat_received_at, process_state
            FROM supervision_agents
            WHERE process_state NOT IN ('offline', 'stopped')
            """
        ).fetchall()
        lost: list[int] = []
        for row in rows:
            heartbeat = _parse_time(row["last_heartbeat_received_at"])
            if heartbeat is None:
                continue
            from app.supervision.thresholds import is_stale

            if is_stale(heartbeat, now, offline_after_seconds):
                lost.append(int(row["id"]))
                connection.execute(
                    """
                    UPDATE supervision_agents SET
                        process_state = 'offline', stop_reason = 'lost', updated_at = ?
                    WHERE id = ?
                    """,
                    (utc_now(), int(row["id"])),
                )
                connection.execute(
                    """
                    INSERT INTO supervision_events (
                        agent_id, event_type, from_state, to_state, message,
                        occurred_at, received_at
                    ) VALUES (?, 'state_change', ?, 'offline',
                              'Signal de vie perdu.', ?, ?)
                    """,
                    (int(row["id"]), str(row["process_state"]), now, utc_now()),
                )
        return lost


def list_agents(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT
            a.id, a.agent_key, a.name, a.deployment_id, a.process_state,
            a.public_ip, a.last_heartbeat_at, a.last_seen_at, a.stop_reason,
            a.started_at,
            c.id AS collector_id, c.collector_key, c.site, c.state,
            c.public_ip AS collector_public_ip, c.last_success_at,
            c.last_error_at, c.last_error_code, c.last_error_message,
            c.last_error_correlation_id, c.last_error_http_status, c.suspended_until
        FROM supervision_agents a
        LEFT JOIN supervision_collectors c ON c.agent_id = a.id
        ORDER BY a.id, c.collector_key
        """
    ).fetchall()
    agents: dict[int, dict[str, Any]] = {}
    for row in rows:
        agent = agents.setdefault(
            int(row["id"]),
            {
                "id": int(row["id"]),
                "agent_key": row["agent_key"],
                "name": row["name"],
                "deployment_id": row["deployment_id"],
                "process_state": row["process_state"],
                "public_ip": row["public_ip"],
                "last_heartbeat_at": row["last_heartbeat_at"],
                "last_seen_at": row["last_seen_at"],
                "stop_reason": row["stop_reason"],
                "started_at": row["started_at"],
                "collectors": [],
            },
        )
        if row["collector_id"] is not None:
            agent["collectors"].append(
                {
                    "collector_key": row["collector_key"],
                    "site": row["site"],
                    "state": row["state"],
                    "public_ip": row["collector_public_ip"],
                    "last_success_at": row["last_success_at"],
                    "last_error_at": row["last_error_at"],
                    "last_error_code": row["last_error_code"],
                    "last_error_message": row["last_error_message"],
                    "last_error_correlation_id": row["last_error_correlation_id"],
                    "last_error_http_status": row["last_error_http_status"],
                    "suspended_until": row["suspended_until"],
                }
            )
    return list(agents.values())


def agent_detail(
    connection: sqlite3.Connection, agent_id: int
) -> dict[str, Any] | None:
    agents = {agent["id"]: agent for agent in list_agents(connection)}
    agent = agents.get(agent_id)
    if agent is None:
        return None
    agent["active_incidents"] = [
        dict(row)
        for row in connection.execute(
            """
            SELECT id, collector_key, error_code, message, http_status,
                   correlation_id, occurrence_count, first_seen_at, last_seen_at
            FROM supervision_incidents
            WHERE agent_id = ? AND is_active = 1
            ORDER BY last_seen_at DESC, id DESC
            """,
            (agent_id,),
        ).fetchall()
    ]
    agent["history"] = [
        dict(row)
        for row in connection.execute(
            """
            SELECT id, collector_key, event_type, from_state, to_state,
                   error_code, message, http_status, correlation_id,
                   occurred_at, received_at
            FROM supervision_events
            WHERE agent_id = ?
            ORDER BY occurred_at DESC, id DESC
            LIMIT 100
            """,
            (agent_id,),
        ).fetchall()
    ]
    return agent


def collector_state(
    connection: sqlite3.Connection, *, agent_id: int, collector_key: str
) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT * FROM supervision_collectors
        WHERE agent_id = ? AND collector_key = ?
        """,
        (agent_id, collector_key),
    ).fetchone()
    return dict(row) if row is not None else None


def is_suspended(
    connection: sqlite3.Connection, *, agent_id: int, collector_key: str, now: str
) -> bool:
    row = collector_state(
        connection, agent_id=agent_id, collector_key=collector_key
    )
    if row is None:
        return False
    if row["state"] != "blocked":
        return False
    until = _parse_time(row["suspended_until"])
    return until is not None and until > now
