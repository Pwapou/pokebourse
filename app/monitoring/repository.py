import json
import sqlite3
from typing import Any

from app.collectors.service import ensure_collection_source, utc_now
from app.monitoring.models import WatchInput, WatchAlreadyRunningError, WatchNotFoundError


def get_watch(connection: sqlite3.Connection, watch_id: int) -> dict[str, Any]:
    row = connection.execute(
        "SELECT * FROM listing_watches WHERE id = ?", (watch_id,)
    ).fetchone()
    if row is None:
        raise WatchNotFoundError(f"Veille introuvable : {watch_id}.")
    return dict(row)


def list_watches(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT
            w.id, w.name, w.platform, w.search_params, w.interval_seconds,
            w.is_active, w.created_at, w.updated_at, w.last_run_at,
            r.id AS last_run_id, r.started_at AS last_run_started_at,
            r.finished_at AS last_run_finished_at, r.status AS last_run_status,
            r.result_count AS last_result_count,
            r.created_count AS last_created_count,
            r.updated_count AS last_updated_count,
            r.invalid_count AS last_invalid_count,
            r.error_message AS last_error_message
        FROM listing_watches w
        LEFT JOIN listing_watch_runs r ON r.id = (
            SELECT r2.id
            FROM listing_watch_runs r2
            WHERE r2.watch_id = w.id
            ORDER BY r2.started_at DESC, r2.id DESC
            LIMIT 1
        )
        ORDER BY w.created_at DESC, w.id DESC
        """
    ).fetchall()


def create_watch(
    connection: sqlite3.Connection, watch: WatchInput, *, min_interval_seconds: int
) -> int:
    if watch.interval_seconds < min_interval_seconds:
        raise ValueError(
            f"L'intervalle minimum est de {min_interval_seconds} secondes."
        )
    with connection:
        cursor = connection.execute(
            """
            INSERT INTO listing_watches (
                name, platform, search_params, interval_seconds, is_active
            ) VALUES (?, ?, ?, ?, 1)
            """,
            (
                watch.name,
                watch.platform,
                json.dumps(watch.search_params(), ensure_ascii=False, sort_keys=True),
                watch.interval_seconds,
            ),
        )
    return int(cursor.lastrowid)


def update_watch(
    connection: sqlite3.Connection,
    watch_id: int,
    watch: WatchInput,
    *,
    min_interval_seconds: int,
) -> None:
    if watch.interval_seconds < min_interval_seconds:
        raise ValueError(
            f"L'intervalle minimum est de {min_interval_seconds} secondes."
        )
    get_watch(connection, watch_id)
    with connection:
        connection.execute(
            """
            UPDATE listing_watches SET
                name = ?, platform = ?, search_params = ?,
                interval_seconds = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE id = ?
            """,
            (
                watch.name,
                watch.platform,
                json.dumps(watch.search_params(), ensure_ascii=False, sort_keys=True),
                watch.interval_seconds,
                watch_id,
            ),
        )


def set_watch_active(connection: sqlite3.Connection, watch_id: int, active: bool) -> None:
    get_watch(connection, watch_id)
    with connection:
        connection.execute(
            """
            UPDATE listing_watches SET
                is_active = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE id = ?
            """,
            (1 if active else 0, watch_id),
        )


def delete_watch(connection: sqlite3.Connection, watch_id: int) -> None:
    get_watch(connection, watch_id)
    with connection:
        connection.execute("DELETE FROM listing_watches WHERE id = ?", (watch_id,))


def active_watches_due(
    connection: sqlite3.Connection, *, now: str, platform: str | None = None
) -> list[dict[str, Any]]:
    parameters: list[object] = [now]
    platform_filter = ""
    if platform is not None:
        platform_filter = "AND platform = ?"
        parameters.append(platform)
    rows = connection.execute(
        f"""
        SELECT * FROM listing_watches
        WHERE is_active = 1
          AND (last_run_at IS NULL OR last_run_at <= ?)
          {platform_filter}
        ORDER BY platform, id
        """,
        parameters,
    ).fetchall()
    return [dict(row) for row in rows]


def has_active_run(connection: sqlite3.Connection, watch_id: int) -> bool:
    return (
        connection.execute(
            """
            SELECT 1 FROM listing_watch_runs
            WHERE watch_id = ? AND finished_at IS NULL
            """,
            (watch_id,),
        ).fetchone()
        is not None
    )


def start_run(connection: sqlite3.Connection, watch: dict[str, Any]) -> int:
    """Ouvre une exécution et son lot dédié dans une seule transaction."""

    with connection:
        if has_active_run(connection, int(watch["id"])):
            raise WatchAlreadyRunningError(
                f"La veille {watch['id']} possède déjà une exécution active."
            )
        started_at = utc_now()
        cursor = connection.execute(
            """
            INSERT INTO listing_watch_runs (watch_id, started_at, status)
            VALUES (?, ?, 'running')
            """,
            (watch["id"], started_at),
        )
        run_id = int(cursor.lastrowid)
        source_id = ensure_collection_source(connection, watch["platform"])
        checksum = f"listing-watch:{watch['id']}:run:{run_id}:{started_at}"
        batch_cursor = connection.execute(
            """
            INSERT INTO import_batches (source_id, input_checksum, status)
            VALUES (?, ?, 'pending')
            """,
            (source_id, checksum),
        )
        connection.execute(
            "UPDATE listing_watch_runs SET import_batch_id = ? WHERE id = ?",
            (int(batch_cursor.lastrowid), run_id),
        )
        connection.execute(
            """
            UPDATE listing_watches SET
                last_run_at = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE id = ?
            """,
            (started_at, watch["id"]),
        )
    return run_id


def finish_run(
    connection: sqlite3.Connection,
    run_id: int,
    *,
    status: str,
    result_count: int,
    created_count: int,
    updated_count: int,
    invalid_count: int,
    error_message: str | None = None,
) -> None:
    finished_at = utc_now()
    with connection:
        row = connection.execute(
            "SELECT import_batch_id FROM listing_watch_runs WHERE id = ?", (run_id,)
        ).fetchone()
        connection.execute(
            """
            UPDATE listing_watch_runs SET
                finished_at = ?, status = ?, result_count = ?,
                created_count = ?, updated_count = ?, invalid_count = ?,
                error_message = ?
            WHERE id = ?
            """,
            (
                finished_at,
                status,
                result_count,
                created_count,
                updated_count,
                invalid_count,
                error_message[:1000] if error_message else None,
                run_id,
            ),
        )
        if row is not None and row["import_batch_id"] is not None:
            connection.execute(
                "UPDATE import_batches SET status = ? WHERE id = ?",
                ("completed" if status == "success" else "failed", row["import_batch_id"]),
            )


def recover_interrupted_runs(connection: sqlite3.Connection) -> int:
    """Clôture les exécutions laissées ouvertes par un arrêt du worker."""

    now = utc_now()
    with connection:
        cursor = connection.execute(
            """
            UPDATE listing_watch_runs SET
                status = 'failed', finished_at = ?,
                error_message = 'Arrêt du worker avant la fin de l’exécution.'
            WHERE status = 'running' AND finished_at IS NULL
            """,
            (now,),
        )
        failed_runs = connection.execute(
            """
            SELECT import_batch_id FROM listing_watch_runs
            WHERE status = 'failed' AND finished_at = ? AND import_batch_id IS NOT NULL
            """,
            (now,),
        ).fetchall()
        for row in failed_runs:
            connection.execute(
                "UPDATE import_batches SET status = 'failed' WHERE id = ?",
                (row["import_batch_id"],),
            )
    return int(cursor.rowcount)
