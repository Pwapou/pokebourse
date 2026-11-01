"""Tests de la supervision : contrat, classification, backend et agent."""

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Iterator

import pytest

from app.collectors.models import CollectionResult
from app.monitoring.models import WatchInput
from app.storage.database import connect
from app.storage.migration_runner import apply_migrations
from app.supervision import repository
from app.supervision.agent import WatchSupervisor
from app.supervision.errors import (
    classify_error,
    contains_auth_wall,
    contains_challenge,
    extraction_failed_error,
    retry_after_seconds,
    validate_report_safety,
)
from app.supervision.models import (
    AGENT_STATES,
    ERROR_CODES,
    STATE_LABELS,
    StructuredError,
    SupervisionThresholds,
    new_correlation_id,
    transition_for,
    utc_now,
)
from app.supervision.service import SupervisionService
from app.monitoring.scheduler import WatchScheduler
from app.monitoring.service import WatchService


def iso(delta_seconds: float = 0.0) -> str:
    moment = datetime(2026, 11, 1, 12, 0, 0, tzinfo=UTC) + timedelta(
        seconds=delta_seconds
    )
    return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def real_iso(delta_seconds: float = 0.0) -> str:
    """Horodatage basé sur l'heure réelle, pour les comparaisons avec utc_now()."""

    moment = datetime.now(UTC) + timedelta(seconds=delta_seconds)
    return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")


class FakeResponse:
    def __init__(self, status_code: int | None = None, text: str = "", headers=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}


class FakeHttpError(RuntimeError):
    def __init__(self, response: FakeResponse):
        super().__init__("http error")
        self.response = response


@pytest.fixture
def connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    db_path = tmp_path / "supervision.db"
    with connect(db_path) as conn:
        apply_migrations(conn)
        yield conn


def make_service(
    tmp_path: Path, **threshold_overrides: object
) -> SupervisionService:
    thresholds = SupervisionThresholds(**threshold_overrides)
    return SupervisionService(
        tmp_path / "supervision.db",
        thresholds=thresholds,
        agent_key="agent-test",
        deployment_id="deploy-test",
    )


def registered(
    connection: sqlite3.Connection, service: SupervisionService
) -> int:
    agent_id = service.register(connection)
    service.mark_operational(connection)
    return agent_id


# ---------------------------------------------------------------------------
# Contrat (tâche 1)
# ---------------------------------------------------------------------------


def test_contract_states_and_codes_match_specification() -> None:
    assert AGENT_STATES == (
        "starting",
        "operational",
        "degraded",
        "blocked",
        "offline",
        "stopped",
    )
    assert "AGENT_HEARTBEAT_LOST" in ERROR_CODES
    assert "SCRAPE_CHALLENGE_REQUIRED" in ERROR_CODES
    assert all(state in STATE_LABELS for state in AGENT_STATES)


def test_structured_error_keeps_http_status_separate() -> None:
    error = StructuredError(
        code="SCRAPE_RATE_LIMITED",
        message="Trop de requêtes.",
        occurred_at=iso(),
        http_status=429,
        transient=True,
        correlation_id=new_correlation_id(),
    )
    assert error.http_status == 429
    assert error.code == "SCRAPE_RATE_LIMITED"


def test_structured_error_rejects_secret_in_message() -> None:
    with pytest.raises(ValueError):
        StructuredError(
            code="SCRAPE_UNKNOWN_ERROR",
            message="set-cookie reçu du serveur",
            occurred_at=iso(),
            transient=False,
            correlation_id=new_correlation_id(),
        )


def test_heartbeat_transition_exists_but_not_blocked_to_operational() -> None:
    assert transition_for("offline", "operational") is not None
    assert transition_for("degraded", "operational") is not None
    # Le retour d'un collecteur bloqué se fait par une collecte réussie,
    # jamais par un simple signal de vie ni une transition générique.
    assert transition_for("blocked", "operational") is None
    assert transition_for("stopped", "operational") is None


def test_thresholds_are_configurable_and_bounded() -> None:
    thresholds = SupervisionThresholds(
        heartbeat_interval_seconds=10,
        offline_after_seconds=30,
        degraded_after_consecutive_errors=2,
        blocked_after_consecutive_blocks=1,
        suspend_seconds=60,
    )
    assert thresholds.offline_after_seconds == 30
    with pytest.raises(ValueError):
        SupervisionThresholds(offline_after_seconds=0)


# ---------------------------------------------------------------------------
# Classification (tâche 2)
# ---------------------------------------------------------------------------


def test_classify_403_as_access_denied() -> None:
    error = classify_error(FakeHttpError(FakeResponse(status_code=403)))
    assert error.code == "SCRAPE_ACCESS_DENIED"
    assert error.http_status == 403
    assert error.transient is False


def test_classify_429_as_transient_rate_limit() -> None:
    error = classify_error(FakeHttpError(FakeResponse(status_code=429)))
    assert error.code == "SCRAPE_RATE_LIMITED"
    assert error.transient is True


def test_captcha_in_http_200_is_detected() -> None:
    body = "<html><title>Access denied</title><div id='captcha'>Datadome</div></html>"
    error = classify_error(
        FakeHttpError(FakeResponse(status_code=200, text=body))
    )
    assert error.code == "SCRAPE_CHALLENGE_REQUIRED"
    assert error.http_status == 200
    assert contains_challenge(body)
    assert not contains_challenge("<html>résultats normaux</html>")


def test_auth_wall_is_detected() -> None:
    assert contains_auth_wall("Veuillez se connecter pour continuer")
    error = classify_error(
        FakeHttpError(FakeResponse(status_code=200, text="Se connecter pour poursuivre"))
    )
    assert error.code == "SCRAPE_AUTH_REQUIRED"


def test_classify_timeout_and_network() -> None:
    assert classify_error(TimeoutError("délai")).code == "SCRAPE_TIMEOUT"
    assert classify_error(ConnectionError("dns")).code == "SCRAPE_NETWORK_ERROR"


def test_classify_unknown_fallback() -> None:
    error = classify_error(RuntimeError("boom"))
    assert error.code == "SCRAPE_UNKNOWN_ERROR"
    assert error.transient is False


def test_retry_after_is_extracted() -> None:
    error = FakeHttpError(
        FakeResponse(status_code=429, headers={"Retry-After": "12"})
    )
    assert retry_after_seconds(error) == 12.0
    assert retry_after_seconds(FakeHttpError(FakeResponse(status_code=429))) is None


def test_extraction_failed_error_is_transient() -> None:
    error = extraction_failed_error("champ prix absent")
    assert error.code == "SCRAPE_EXTRACTION_FAILED"
    assert error.transient is True


def test_report_safety_flags_secrets() -> None:
    assert validate_report_safety({"message": "ok"}) == []
    assert validate_report_safety({"headers": "Set-Cookie: x"}) != []


# ---------------------------------------------------------------------------
# Backend (tâche 3)
# ---------------------------------------------------------------------------


def test_register_creates_agent_and_collectors(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    service = make_service(tmp_path)
    agent_id = registered(connection, service)
    agents = repository.list_agents(connection)
    assert len(agents) == 1
    assert agents[0]["process_state"] == "operational"
    assert {c["collector_key"] for c in agents[0]["collectors"]} == {
        "vinted",
        "leboncoin",
    }
    detail = repository.agent_detail(connection, agent_id)
    assert detail is not None
    assert {c["site"] for c in detail["collectors"]} == {"Vinted", "Leboncoin"}


def test_heartbeat_does_not_unblock_collector(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    service = make_service(tmp_path, blocked_after_consecutive_blocks=1)
    agent_id = registered(connection, service)
    error = classify_error(FakeHttpError(FakeResponse(status_code=403)))
    state = service.report_error(
        connection, collector_key="vinted", error=error
    )
    assert state == "blocked"
    service.heartbeat(connection)
    row = repository.collector_state(
        connection, agent_id=agent_id, collector_key="vinted"
    )
    assert row is not None and row["state"] == "blocked"


def test_transient_errors_degrade_after_threshold(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    service = make_service(tmp_path, degraded_after_consecutive_errors=2)
    registered(connection, service)
    error = classify_error(TimeoutError("lent"))
    first = service.report_error(connection, collector_key="vinted", error=error)
    assert first == "operational"
    second = service.report_error(connection, collector_key="vinted", error=error)
    assert second == "degraded"


def test_confirmed_block_suspends_only_that_collector(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    service = make_service(
        tmp_path, blocked_after_consecutive_blocks=2, suspend_seconds=600
    )
    agent_id = registered(connection, service)
    error = classify_error(FakeHttpError(FakeResponse(status_code=403)))
    assert service.report_error(connection, collector_key="vinted", error=error) == "degraded"
    assert service.report_error(connection, collector_key="vinted", error=error) == "blocked"
    assert service.is_collector_suspended(
        connection, collector_key="vinted", now=real_iso()
    )
    assert not service.is_collector_suspended(
        connection, collector_key="vinted", now=real_iso(3600)
    )
    other = repository.collector_state(
        connection, agent_id=agent_id, collector_key="leboncoin"
    )
    assert other is not None and other["state"] == "operational"


def test_success_repairs_degraded_and_resolves_incidents(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    service = make_service(tmp_path, degraded_after_consecutive_errors=1)
    agent_id = registered(connection, service)
    error = classify_error(TimeoutError("lent"))
    service.report_error(connection, collector_key="vinted", error=error)
    service.report_success(connection, collector_key="vinted", result_count=3)
    row = repository.collector_state(
        connection, agent_id=agent_id, collector_key="vinted"
    )
    assert row is not None
    assert row["state"] == "operational"
    assert row["last_success_at"] is not None
    detail = repository.agent_detail(connection, agent_id)
    assert detail is not None and detail["active_incidents"] == []


def test_incidents_are_deduplicated_and_counted(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    service = make_service(tmp_path)
    agent_id = registered(connection, service)
    timeout = classify_error(TimeoutError("lent"))
    service.report_error(connection, collector_key="vinted", error=timeout)
    service.report_error(connection, collector_key="vinted", error=timeout)
    service.report_error(
        connection,
        collector_key="vinted",
        error=classify_error(FakeHttpError(FakeResponse(status_code=429))),
    )
    detail = repository.agent_detail(connection, agent_id)
    assert detail is not None
    incidents = detail["active_incidents"]
    assert len(incidents) == 2
    timeout_incident = next(i for i in incidents if i["error_code"] == "SCRAPE_TIMEOUT")
    assert timeout_incident["occurrence_count"] == 2


def test_stale_event_does_not_overwrite_newer_state(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    service = make_service(tmp_path, degraded_after_consecutive_errors=1)
    agent_id = registered(connection, service)
    recent = classify_error(TimeoutError("lent"))
    recent = recent.model_copy(update={"occurred_at": iso(100)})
    service.report_error(connection, collector_key="vinted", error=recent)
    old = classify_error(FakeHttpError(FakeResponse(status_code=403)))
    old = old.model_copy(update={"occurred_at": iso(0)})
    service.report_error(connection, collector_key="vinted", error=old)
    row = repository.collector_state(
        connection, agent_id=agent_id, collector_key="vinted"
    )
    assert row is not None
    assert row["last_error_at"] == iso(100)
    assert row["last_error_code"] == "SCRAPE_TIMEOUT"


def test_lost_heartbeat_marks_agent_offline_but_voluntary_stop_survives(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    service = make_service(tmp_path, offline_after_seconds=60)
    agent_id = registered(connection, service)
    repository.record_heartbeat(connection, agent_id=agent_id)
    # On vieillit manuellement le dernier signal reçu pour simuler la perte.
    with connection:
        connection.execute(
            """
            UPDATE supervision_agents SET last_heartbeat_received_at = ?
            WHERE id = ?
            """,
            (real_iso(-120), agent_id),
        )
    lost = service.check_offline_agents(connection, now=real_iso(0))
    assert lost == [agent_id]
    agents = repository.list_agents(connection)
    assert agents[0]["process_state"] == "offline"
    assert agents[0]["stop_reason"] == "lost"

    service2 = make_service(tmp_path, offline_after_seconds=60)
    service2.agent_id = agent_id
    service2.request_stop(connection)
    assert service.check_offline_agents(connection, now=real_iso(3600)) == []
    agents = repository.list_agents(connection)
    assert agents[0]["process_state"] == "stopped"
    assert agents[0]["stop_reason"] == "voluntary"


def test_deferred_reports_are_flushed_on_heartbeat(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    service = make_service(tmp_path)
    agent_id = registered(connection, service)
    service.defer(classify_error(TimeoutError("lent")))
    service.heartbeat(connection)
    detail = repository.agent_detail(connection, agent_id)
    assert detail is not None
    errors = [e for e in detail["history"] if e["event_type"] == "error"]
    assert len(errors) == 1


def test_resume_collector_after_block(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    service = make_service(tmp_path, blocked_after_consecutive_blocks=1)
    agent_id = registered(connection, service)
    error = classify_error(FakeHttpError(FakeResponse(status_code=403)))
    service.report_error(connection, collector_key="vinted", error=error)
    service.resume_collector(connection, collector_key="vinted")
    row = repository.collector_state(
        connection, agent_id=agent_id, collector_key="vinted"
    )
    assert row is not None and row["state"] == "operational"


def test_reports_with_secrets_are_rejected(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    service = make_service(tmp_path)
    registered(connection, service)
    error = classify_error(TimeoutError("lent"))
    tampered = error.model_copy(update={"message": "authorization: Bearer abc"})
    with pytest.raises(ValueError):
        service.report_error(connection, collector_key="vinted", error=tampered)


def test_history_keeps_event_and_received_dates(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    service = make_service(tmp_path)
    agent_id = registered(connection, service)
    service.heartbeat(connection)
    detail = repository.agent_detail(connection, agent_id)
    assert detail is not None
    heartbeats = [e for e in detail["history"] if e["event_type"] == "heartbeat"]
    assert heartbeats
    assert heartbeats[0]["occurred_at"]
    assert heartbeats[0]["received_at"]


# ---------------------------------------------------------------------------
# Intégration agent / planificateur
# ---------------------------------------------------------------------------


def _create_watch(connection: sqlite3.Connection, platform: str, name: str) -> int:
    from app.monitoring import repository as watch_repository

    return watch_repository.create_watch(
        connection,
        WatchInput(
            platform=platform,  # type: ignore[arg-type]
            name=name,
            search_text="Carte Pokémon Pikachu",
            interval_seconds=120,
        ),
        min_interval_seconds=1,
    )


def test_blocked_collector_does_not_stop_independent_collectors(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "scheduler-supervision.db"
    with connect(db_path) as connection:
        apply_migrations(connection)
        _create_watch(connection, "vinted", "veille vinted")
        _create_watch(connection, "leboncoin", "veille leboncoin")

    denied = FakeHttpError(FakeResponse(status_code=403))

    def failing_collection(**_params: object) -> CollectionResult:
        raise denied

    service = WatchService(
        min_interval_seconds=1,
        collectors={
            "vinted": lambda **_params: failing_collection(),
            "leboncoin": lambda **_params: CollectionResult(listings=[]),
        },
    )
    supervision_service = SupervisionService(
        db_path,
        thresholds=SupervisionThresholds(
            degraded_after_consecutive_errors=1,
            blocked_after_consecutive_blocks=1,
            suspend_seconds=3600,
        ),
        agent_key="agent-planificateur",
    )
    scheduler = WatchScheduler(
        db_path,
        settings=None,
        service=service,
        supervisor=WatchSupervisor(supervision_service),
    )
    scheduler.initialize()
    first = scheduler.tick()
    assert first["failed"] == 1
    assert first["executed"] == 1

    # Vinted est maintenant bloqué et suspendu. On remet la veille leboncoin
    # échéante : elle doit s'exécuter malgré le blocage de vinted.
    with connect(db_path) as connection:
        with connection:
            connection.execute(
                "UPDATE listing_watches SET last_run_at = NULL WHERE platform = 'leboncoin'"
            )
    second = scheduler.tick()
    assert second["suspended"] == 1
    assert second["executed"] == 1
    assert second["failed"] == 0

    with connect(db_path) as connection:
        agents = repository.list_agents(connection)
        states = {
            c["collector_key"]: c["state"] for c in agents[0]["collectors"]
        }
    assert states["vinted"] == "blocked"
    assert states["leboncoin"] == "operational"
