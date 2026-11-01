"""Enrichissement TCGdex reprenable : données locales et réseau simulé seulement."""

import json
import sqlite3
import urllib.error
from collections import Counter
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.catalog import import_jsonl, reidentify_catalog_item
from app.cli import main
from app.config import Settings
from app.identification.resolution import confirm_card, resolve_listing
from app.monitoring.scheduler import WatchScheduler
from app.storage.database import connect
from app.storage.migration_runner import apply_migrations, migration_files
from app.tcgdex.cache import TcgdexCache
from app.tcgdex.client import TcgdexClient, TcgdexNetworkError, TcgdexRateLimitError, retry_after_seconds
from app.tcgdex.models import TcgdexCard, TcgdexSet
from app.tcgdex.sync import claim_sync, control_job, enqueue_sync, process_sync_step, sync_dashboard
from app.web import app

NOW = datetime(2026, 11, 1, 10, tzinfo=UTC)


@pytest.fixture
def connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    with connect(tmp_path / "sync.db") as connection:
        apply_migrations(connection)
        yield connection


class FakeClient:
    """API locale simulée ; chaque appel vérifie l'absence de transaction SQLite."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.calls: Counter[str] = Counter()
        self.fail_card: str | None = None
        self.rate_limited = False
        self.on_request = None
        self.manifest = {"id": "test", "name": "Extension Test", "cardCount": {"official": 2, "total": 3},
                         "cards": [{"id": "test-1", "localId": "1", "name": "Testmon"},
                                   {"id": "test-2", "localId": "2", "name": "Autremon"}]}

    def _request(self, key: str) -> None:
        assert not self.connection.in_transaction
        self.calls[key] += 1
        if self.on_request:
            self.on_request()

    def get_sets(self) -> list[dict]:
        self._request("directory")
        return [{"id": "test", "name": "Extension Test", "cardCount": {"total": 3}}]

    def get_set(self, set_id: str) -> dict:
        self._request("manifest")
        if self.rate_limited:
            raise TcgdexRateLimitError("Quota simulé", 120)
        return self.manifest

    def get_card(self, card_id: str) -> dict:
        self._request(card_id)
        if self.fail_card == card_id:
            raise TcgdexNetworkError("Réseau simulé indisponible")
        summary = next(card for card in self.manifest["cards"] if card["id"] == card_id)
        return {**summary, "set": {"id": "test", "name": "Extension Test"}, "rarity": "Rare",
                "category": "Pokemon", "hp": 80, "types": ["Feu"], "variants": {"holo": True}}


def job(connection: sqlite3.Connection, job_id: int = 1) -> sqlite3.Row:
    return connection.execute("SELECT * FROM tcgdex_sync_jobs WHERE id=?", (job_id,)).fetchone()


def test_progressive_sync_fetches_one_request_and_survives_reopening(connection: sqlite3.Connection) -> None:
    job_id = enqueue_sync(connection, "test", now=NOW)
    client = FakeClient(connection)
    assert process_sync_step(connection, client, now=NOW)
    assert job(connection, job_id)["stage"] == "details"
    assert job(connection)["summary_count"] == 2 and job(connection)["expected_count"] == 3
    assert connection.execute("SELECT count(*) FROM pokemon_reference_cards").fetchone()[0] == 2
    assert not process_sync_step(connection, client, now=NOW)
    assert process_sync_step(connection, client, now=NOW + timedelta(seconds=2))
    database = Path(connection.execute("PRAGMA database_list").fetchone()[2])
    with connect(database) as reopened:
        reopened_client = FakeClient(reopened)
        assert process_sync_step(reopened, reopened_client, now=NOW + timedelta(seconds=4))
        assert reopened_client.calls == {"test-2": 1}
        assert job(reopened)["status"] == "completed"
    assert sync_dashboard(connection)["jobs"][0]["detail_count"] == 2


def test_pause_and_resume_preserve_loaded_cards_and_skip_completed_requests(connection: sqlite3.Connection) -> None:
    enqueue_sync(connection, "test", now=NOW)
    client = FakeClient(connection)
    process_sync_step(connection, client, now=NOW)
    process_sync_step(connection, client, now=NOW + timedelta(seconds=2))
    control_job(connection, 1, "pause", now=NOW + timedelta(seconds=3))
    assert not process_sync_step(connection, client, now=NOW + timedelta(seconds=10))
    control_job(connection, 1, "resume", now=NOW + timedelta(seconds=11))
    assert process_sync_step(connection, client, now=NOW + timedelta(seconds=12))
    assert client.calls == {"manifest": 1, "test-1": 1, "test-2": 1}
    assert job(connection)["status"] == "completed"


def test_summary_cache_can_upgrade_to_details_without_loading_manifest_again(connection: sqlite3.Connection) -> None:
    enqueue_sync(connection, "test", include_details=False, now=NOW)
    client = FakeClient(connection)
    process_sync_step(connection, client, now=NOW)
    assert job(connection)["status"] == "completed"
    assert enqueue_sync(connection, "test", include_details=False, now=NOW + timedelta(seconds=10)) == 1
    assert not process_sync_step(connection, client, now=NOW + timedelta(seconds=11))
    enqueue_sync(connection, "test", include_details=True, now=NOW + timedelta(seconds=12))
    assert job(connection)["stage"] == "details"
    process_sync_step(connection, client, now=NOW + timedelta(seconds=12))
    process_sync_step(connection, client, now=NOW + timedelta(seconds=14))
    assert client.calls["manifest"] == 1 and job(connection)["status"] == "completed"


def test_expired_lease_is_recovered_and_pause_fences_an_inflight_reply(connection: sqlite3.Connection) -> None:
    enqueue_sync(connection, "test", now=NOW)
    original_claim = claim_sync(connection, now=NOW)
    assert original_claim
    client = FakeClient(connection)
    client.on_request = lambda: control_job(connection, 1, "pause", now=NOW + timedelta(seconds=62))
    assert process_sync_step(connection, client, now=NOW + timedelta(seconds=61))
    assert job(connection)["status"] == "paused"
    assert connection.execute("SELECT count(*) FROM pokemon_reference_cards").fetchone()[0] == 0
    assert connection.execute("SELECT count(*) FROM tcgdex_sync_cards").fetchone()[0] == 0


def test_global_gate_blocks_other_workers_and_respects_retry_after(connection: sqlite3.Connection) -> None:
    enqueue_sync(connection, "test", now=NOW)
    enqueue_sync(connection, "another", now=NOW)
    client = FakeClient(connection)
    client.rate_limited = True
    process_sync_step(connection, client, now=NOW)
    assert job(connection)["error_code"] == "rate_limited"
    assert not process_sync_step(connection, client, now=NOW + timedelta(seconds=119))
    assert client.calls == {"manifest": 1}
    control_job(connection, 1, "pause", now=NOW + timedelta(seconds=1))
    control_job(connection, 1, "resume", now=NOW + timedelta(seconds=2))
    assert not process_sync_step(connection, client, now=NOW + timedelta(seconds=100))
    database = Path(connection.execute("PRAGMA database_list").fetchone()[2])
    with connect(database) as other:
        assert claim_sync(other, now=NOW + timedelta(seconds=120))
        assert claim_sync(connection, now=NOW + timedelta(seconds=121)) is None


def test_failed_detail_retries_are_bounded_then_resume_at_the_failed_card(connection: sqlite3.Connection) -> None:
    enqueue_sync(connection, "test", now=NOW)
    client = FakeClient(connection)
    process_sync_step(connection, client, now=NOW)
    process_sync_step(connection, client, now=NOW + timedelta(seconds=2))
    client.fail_card = "test-2"
    for seconds in (4, 10, 21):
        process_sync_step(connection, client, now=NOW + timedelta(seconds=seconds))
    assert job(connection)["status"] == "failed"
    assert sync_dashboard(connection)["jobs"][0]["detail_count"] == 1
    control_job(connection, 1, "resume", now=NOW + timedelta(seconds=30))
    client.fail_card = None
    process_sync_step(connection, client, now=NOW + timedelta(seconds=30))
    assert job(connection)["status"] == "completed"
    assert client.calls["test-1"] == 1 and client.calls["test-2"] == 4


def test_extreme_server_delay_is_recorded_without_crashing_worker(connection: sqlite3.Connection) -> None:
    enqueue_sync(connection, "test", now=NOW)
    client = FakeClient(connection)
    def rate_limit() -> None:
        raise TcgdexRateLimitError("Délai serveur extrême", 1e300)
    client.on_request = rate_limit
    assert process_sync_step(connection, client, now=NOW)
    assert job(connection)["error_code"] == "rate_limited"
    assert not process_sync_step(connection, client, now=NOW + timedelta(days=365))


def test_bad_manifest_is_rejected_without_partially_importing_references(connection: sqlite3.Connection) -> None:
    enqueue_sync(connection, "test", now=NOW)
    client = FakeClient(connection)
    client.manifest["cards"][1]["name"] = None
    process_sync_step(connection, client, now=NOW)
    assert job(connection)["error_code"] == "invalid_response"
    assert connection.execute("SELECT count(*) FROM pokemon_reference_sets").fetchone()[0] == 0
    assert connection.execute("SELECT count(*) FROM pokemon_reference_cards").fetchone()[0] == 0


def test_upsert_set_is_atomic_and_directory_does_not_erase_details(connection: sqlite3.Connection) -> None:
    cache = TcgdexCache(connection)
    with pytest.raises(RuntimeError):
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            cache.upsert_set(TcgdexSet(id="rollback", name="Test"))
            raise RuntimeError("Annulation simulée")
    assert connection.execute("SELECT count(*) FROM pokemon_reference_sets").fetchone()[0] == 0
    cache.upsert_set(TcgdexSet(id="test", name="Extension Test", series="Série conservée", card_count_official=2, release_date="2026-01-01"))
    enqueue_sync(connection, now=NOW)
    process_sync_step(connection, FakeClient(connection), now=NOW)
    row = connection.execute("SELECT * FROM pokemon_reference_sets WHERE id='test'").fetchone()
    assert row["series"] == "Série conservée" and row["release_date"] == "2026-01-01"
    assert row["card_count_official"] == 2 and job(connection)["summary_count"] == 1


def test_sync_preserves_reference_ids_human_decisions_and_raw_details(connection: sqlite3.Connection) -> None:
    cache = TcgdexCache(connection)
    cache.upsert_set(TcgdexSet(id="test", name="Extension Test", card_count_total=3))
    card_id = cache.upsert_card(TcgdexCard(id="test-1", name="Testmon", local_id="1", set_id="test", set_name="Extension Test",
                                       rarity="Rare initiale", raw_data={"variants": {"holo": True}}))
    import_jsonl(connection, json.dumps({"external_id": "human", "name": "Testmon 1/3 Extension Test", "set_name": "Extension Test", "price_cents": 100}).encode())
    with connection:
        resolution = resolve_listing(connection, 1)
        confirm_card(connection, 1, card_id, resolution.evidence_hash, resolution.revision)
    before = dict(connection.execute("SELECT * FROM catalog_items WHERE id=1").fetchone())
    enqueue_sync(connection, "test", include_details=False, now=NOW)
    process_sync_step(connection, FakeClient(connection), now=NOW)
    assert dict(connection.execute("SELECT * FROM catalog_items WHERE id=1").fetchone()) == before
    reidentify_catalog_item(connection, 1)
    assert resolve_listing(connection, 1).decision_source == "human"
    card = cache.get_card_by_tcgdex_id("test-1")
    assert card.id == card_id and card.rarity == "Rare initiale" and card.raw_data["variants"]["holo"]


def test_network_step_does_not_hold_a_write_lock(connection: sqlite3.Connection) -> None:
    enqueue_sync(connection, "test", include_details=False, now=NOW)
    database = Path(connection.execute("PRAGMA database_list").fetchone()[2])
    def concurrent_write() -> None:
        with connect(database) as other:
            with other:
                other.execute("INSERT INTO sources(name,kind) VALUES ('concurrent','demo')")
    client = FakeClient(connection)
    client.on_request = concurrent_write
    assert process_sync_step(connection, client, now=NOW)
    assert connection.execute("SELECT name FROM sources WHERE name='concurrent'").fetchone()


def test_retry_after_accepts_seconds_http_dates_and_invalid_headers() -> None:
    assert retry_after_seconds("90") == 90
    assert retry_after_seconds("NaN") == retry_after_seconds("invalid") == 60
    date = (datetime.now(UTC) + timedelta(seconds=120)).strftime("%a, %d %b %Y %H:%M:%S GMT")
    error = urllib.error.HTTPError("https://api.tcgdex.net/v2/fr/sets/test", 429, "Quota", {"Retry-After": date}, None)
    with patch("urllib.request.urlopen", side_effect=error):
        with pytest.raises(TcgdexRateLimitError) as result:
            TcgdexClient(max_retries=1).get_set("test")
    assert 115 <= result.value.retry_after <= 121


def test_scheduler_advances_only_a_queued_sync_step(connection: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch) -> None:
    database = Path(connection.execute("PRAGMA database_list").fetchone()[2])
    scheduler = WatchScheduler(database, settings=Settings(database_path=database))
    assert not scheduler.process_tcgdex_sync()
    enqueue_sync(connection, "test", include_details=False)
    calls = []
    def manifest(_client: TcgdexClient, set_id: str) -> dict:
        calls.append(set_id)
        return FakeClient(connection).manifest
    monkeypatch.setattr(TcgdexClient, "get_set", manifest)
    assert scheduler.process_tcgdex_sync()
    assert calls == ["test"]


def test_web_queues_without_network_and_controls_follow_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database = tmp_path / "web.db"
    monkeypatch.setenv("POKEMON_DATABASE_PATH", str(database))
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Aucun réseau depuis les routes web")
    monkeypatch.setattr(TcgdexClient, "_request", forbidden)
    with TestClient(app) as client:
        assert client.get("/tcgdex").status_code == 200
        response = client.post("/tcgdex/sync", data={"manual_set_id": "test", "include_details": "true"})
        assert response.status_code == 200 and 'http-equiv="refresh"' in response.text
        assert client.post("/tcgdex/jobs/1/pause").status_code == 200
        assert 'http-equiv="refresh"' not in client.get("/tcgdex?follow=1").text
        assert client.post("/tcgdex/jobs/1/resume").status_code == 200
        assert client.post("/tcgdex/jobs/999/pause").status_code == 404
        invalid = client.post("/tcgdex/sync", data={"set_ids": ["valid", "../invalid"]})
        assert invalid.status_code == 200 and "invalide" in invalid.text
        with connect(database) as connection:
            assert connection.execute("SELECT count(*) FROM tcgdex_sync_jobs").fetchone()[0] == 1


def test_cli_queue_and_status_are_offline(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    database = tmp_path / "cli.db"
    assert main(["--database", str(database), "migrate"]) == 0
    capsys.readouterr()
    assert main(["--database", str(database), "sync-tcgdex", "test", "--summaries-only"]) == 0
    capsys.readouterr()
    assert main(["--database", str(database), "sync-tcgdex", "--status"]) == 0
    jobs = json.loads(capsys.readouterr().out)
    assert jobs[0]["set_id"] == "test" and jobs[0]["include_details"] == 0
    assert main(["--database", str(database), "sync-tcgdex", "../bad"]) == 1


def test_migration_0018_upgrades_existing_catalog_without_touching_it(tmp_path: Path) -> None:
    with connect(tmp_path / "upgrade.db") as connection:
        connection.execute("CREATE TABLE schema_migrations(version TEXT PRIMARY KEY)")
        for version, script in migration_files():
            if version < "0018":
                # Les migrations de reconstruction sont exécutées par le runner en temps normal.
                if "DROP TABLE" in script:
                    from app.storage.migration_runner import _apply_table_rebuild
                    _apply_table_rebuild(connection, script)
                else:
                    connection.executescript(script)
        TcgdexCache(connection).seed_initial_if_empty()
        before = connection.execute("SELECT count(*) FROM pokemon_reference_cards").fetchone()[0]
        assert apply_migrations(connection) == ["0018_tcgdex_sync_jobs.sql", "0019_radar_observations.sql"]
        assert connection.execute("SELECT count(*) FROM pokemon_reference_cards").fetchone()[0] == before
        assert apply_migrations(connection) == []
