import sqlite3
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.collectors.models import CollectionResult, CollectorError
from app.config import Settings
from app.monitoring.models import (
    WatchAlreadyRunningError,
    WatchInput,
    WatchNotFoundError,
    WatchValidationError,
)
from app.monitoring.repository import start_run
from app.monitoring.scheduler import WatchScheduler
from app.monitoring.service import WatchService
from app.storage.database import connect
from app.storage.migration_runner import apply_migrations


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "watches.db"
    with connect(path) as connection:
        apply_migrations(connection)
    return path


@pytest.fixture
def connection(database_path: Path) -> Iterator[sqlite3.Connection]:
    with connect(database_path) as db_connection:
        yield db_connection


def watch_input(
    platform: str = "vinted",
    *,
    name: str = "Pikachu Vinted",
    interval_seconds: int = 120,
    search_text: str = "Carte Pokémon Pikachu",
) -> WatchInput:
    return WatchInput(
        platform=platform,  # type: ignore[arg-type]
        name=name,
        search_text=search_text,
        interval_seconds=interval_seconds,
    )


def fake_listing(external_id: str = "watch-1") -> CollectionResult:
    from app.collectors.models import CollectedListing

    return CollectionResult(
        listings=[
            CollectedListing(
                source="vinted",
                external_id=external_id,
                title="Carte Pokémon Pikachu - Évolutions",
                price_cents=1500,
                url=f"https://www.vinted.fr/items/{external_id}",
                seller="Vendeur veille",
            )
        ]
    )


def test_watch_validation_pause_resume_and_unknown_identifier(
    connection: sqlite3.Connection,
) -> None:
    service = WatchService(min_interval_seconds=120)
    watch_id = service.create_watch(connection, watch_input())

    with pytest.raises(WatchValidationError, match="intervalle minimum"):
        service.create_watch(connection, watch_input(interval_seconds=60))
    with pytest.raises(ValidationError):
        service.create_watch(
            connection, watch_input(platform="inconnue")  # type: ignore[arg-type]
        )

    service.pause_watch(connection, watch_id)
    assert connection.execute(
        "SELECT is_active FROM listing_watches WHERE id = ?", (watch_id,)
    ).fetchone()[0] == 0
    service.resume_watch(connection, watch_id)
    assert connection.execute(
        "SELECT is_active FROM listing_watches WHERE id = ?", (watch_id,)
    ).fetchone()[0] == 1
    with pytest.raises(WatchNotFoundError):
        service.pause_watch(connection, 9999)


def test_manual_execution_ingests_and_records_success(
    connection: sqlite3.Connection,
) -> None:
    calls: list[dict[str, object]] = []

    def collector(**params: object) -> CollectionResult:
        calls.append(params)
        return fake_listing()

    service = WatchService(
        min_interval_seconds=120,
        collectors={"vinted": collector},
    )
    watch_id = service.create_watch(connection, watch_input(interval_seconds=600))

    summary = service.run_watch_once(connection, watch_id)

    assert calls == [{"search_text": "Carte Pokémon Pikachu"}]
    assert summary["status"] == "success"
    assert summary["result_count"] == 1
    assert summary["created_count"] == 1
    assert summary["updated_count"] == 0
    run = connection.execute(
        "SELECT status, result_count, import_batch_id FROM listing_watch_runs"
    ).fetchone()
    assert run["status"] == "success"
    assert run["result_count"] == 1
    assert connection.execute(
        "SELECT status FROM import_batches WHERE id = ?", (run["import_batch_id"],)
    ).fetchone()[0] == "completed"
    assert connection.execute(
        "SELECT COUNT(*) FROM catalog_items WHERE external_id = 'watch-1'"
    ).fetchone()[0] == 1

    second = service.run_watch_once(connection, watch_id)
    assert second["created_count"] == 0
    assert connection.execute("SELECT COUNT(*) FROM catalog_items").fetchone()[0] == 1


def test_failed_execution_is_persisted_and_can_recover(
    connection: sqlite3.Connection,
) -> None:
    attempts = 0

    def flaky(**_params: object) -> CollectionResult:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise CollectorError("erreur temporaire", retryable=True)
        return fake_listing(external_id="watch-recovery")

    service = WatchService(
        min_interval_seconds=1,
        collectors={"vinted": flaky},
    )
    watch_id = service.create_watch(connection, watch_input(interval_seconds=1))

    with pytest.raises(CollectorError, match="erreur temporaire"):
        service.run_watch_once(connection, watch_id)
    failed = connection.execute(
        "SELECT status, error_message FROM listing_watch_runs WHERE watch_id = ?",
        (watch_id,),
    ).fetchone()
    assert failed["status"] == "failed"
    assert "erreur temporaire" in failed["error_message"]

    with connection:
        connection.execute(
            "UPDATE listing_watches SET last_run_at = '2026-01-01T00:00:00.000Z' "
            "WHERE id = ?",
            (watch_id,),
        )
    summary = service.run_watch_once(connection, watch_id)
    assert summary["status"] == "success"
    assert attempts == 2
    assert connection.execute(
        "SELECT COUNT(*) FROM catalog_items WHERE external_id = 'watch-recovery'"
    ).fetchone()[0] == 1


def test_only_one_active_execution_per_watch(connection: sqlite3.Connection) -> None:
    service = WatchService(min_interval_seconds=1)
    watch_id = service.create_watch(connection, watch_input(interval_seconds=1))
    watch = dict(
        connection.execute(
            "SELECT * FROM listing_watches WHERE id = ?", (watch_id,)
        ).fetchone()
    )

    start_run(connection, watch)
    with pytest.raises(WatchAlreadyRunningError):
        start_run(connection, watch)


def test_scheduler_isolates_failed_watch_and_continues_others(
    database_path: Path,
) -> None:
    def failing_vinted(**_params: object) -> CollectionResult:
        raise CollectorError("Vinted temporairement indisponible")

    def successful_leboncoin(**_params: object) -> CollectionResult:
        from app.collectors.models import CollectedListing

        return CollectionResult(
            listings=[
                CollectedListing(
                    source="leboncoin",
                    external_id="lbc-1",
                    title="Carte Pokémon Mew",
                    price_cents=900,
                    url="https://www.leboncoin.fr/ad/lbc-1",
                )
            ]
        )

    service = WatchService(
        min_interval_seconds=1,
        collectors={"vinted": failing_vinted, "leboncoin": successful_leboncoin},
    )
    scheduler = WatchScheduler(
        database_path,
        settings=Settings(
            database_path=database_path,
            min_watch_interval_seconds=1,
            watch_poll_seconds=0.5,
        ),
        service=service,
    )
    with connect(database_path) as connection:
        scheduler.service.create_watch(
            connection,
            watch_input("vinted", name="Veille en échec", interval_seconds=1),
        )
        scheduler.service.create_watch(
            connection,
            watch_input(
                "leboncoin",
                name="Veille valide",
                interval_seconds=1,
                search_text="Carte Pokémon Mew",
            ),
        )

    summary = scheduler.tick()

    assert summary["executed"] == 1
    assert summary["failed"] == 1
    with connect(database_path) as connection:
        statuses = dict(
            connection.execute(
                """
                SELECT w.platform, r.status
                FROM listing_watches w
                JOIN listing_watch_runs r ON r.watch_id = w.id
                ORDER BY w.id
                """
            ).fetchall()
        )
        assert statuses == {"vinted": "failed", "leboncoin": "success"}
        assert connection.execute(
            "SELECT COUNT(*) FROM catalog_items WHERE external_id = 'lbc-1'"
        ).fetchone()[0] == 1
