"""Tests de la fiabilité vendeur : scoring, extraction en liste blanche, file d'enrichissement."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from app.collectors.models import CollectedListing
from app.collectors.service import ensure_collection_source, ingest_collected_listings
from app.sellers import repository
from app.sellers.collect import fetch_vinted_seller_profile
from app.sellers.models import (
    SellerProfile,
    profile_from_row,
    reliability_rating,
)
from app.sellers.service import SellerService
from app.storage.database import connect
from app.storage.migration_runner import apply_migrations
from app.supervision.models import utc_now


@pytest.fixture
def connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    with connect(tmp_path / "sellers.db") as conn:
        apply_migrations(conn)
        yield conn


def make_profile(**overrides: Any) -> SellerProfile:
    values: dict[str, Any] = {
        "platform": "vinted",
        "seller_external_id": "12345",
        "login": "vendeur-test",
        "feedback_count": 50,
        "positive_count": 48,
        "neutral_count": 1,
        "negative_count": 1,
        "reputation_bps": 9600,
        "item_count": 12,
        "account_type": "private",
        "is_banned": False,
        "fetched_at": utc_now(),
    }
    values.update(overrides)
    return SellerProfile.model_validate(values)


# ---------------------------------------------------------------------------
# Score de fiabilité
# ---------------------------------------------------------------------------


def test_rating_unknown_without_profile() -> None:
    rating = reliability_rating(None)
    assert rating.known is False
    assert rating.stars is None
    assert rating.stars_text() == "—"


def test_rating_insufficient_feedback() -> None:
    rating = reliability_rating(make_profile(feedback_count=2, reputation_bps=10_000))
    assert rating.known is False
    assert rating.label == "Données insuffisantes"


def test_rating_banned_account() -> None:
    rating = reliability_rating(make_profile(is_banned=True))
    assert rating.stars == 0
    assert rating.label == "Compte banni"


def test_rating_base_reputation_on_five_stars() -> None:
    rating = reliability_rating(make_profile(reputation_bps=8000))
    assert rating.stars == 4
    assert rating.label == "Fiable"
    assert rating.stars_text() == "★★★★☆"


def test_rating_low_feedback_caps_at_three_stars() -> None:
    rating = reliability_rating(
        make_profile(feedback_count=4, reputation_bps=10_000, negative_count=0)
    )
    assert rating.stars == 3
    assert any("plafonnée à 3" in note for note in rating.notes)


def test_rating_frequent_negative_feedback_caps_at_two() -> None:
    rating = reliability_rating(
        make_profile(feedback_count=40, negative_count=8, reputation_bps=9000)
    )
    assert rating.stars == 2
    assert rating.label == "À vérifier"
    assert any("20%" in note for note in rating.notes)


def test_profile_rejects_personal_data_fields() -> None:
    with pytest.raises(ValueError):
        SellerProfile.model_validate(
            {
                "platform": "vinted",
                "seller_external_id": "1",
                "email": "vendeur@exemple.fr",
                "real_name": "Jean Dupont",
                "fetched_at": utc_now(),
            }
        )


def test_profile_rejects_foreign_profile_url() -> None:
    with pytest.raises(ValueError):
        make_profile(profile_url="https://example.com/vendeur")


def test_profile_from_sqlite_row(connection: sqlite3.Connection) -> None:
    profile = make_profile(feedback_count=10, negative_count=1)
    repository.upsert_profile(connection, profile)
    row = connection.execute(
        """
        SELECT platform, seller_external_id, login, feedback_count,
               positive_count, neutral_count, negative_count, reputation_bps,
               item_count, response_rate_percent, account_type, is_banned,
               profile_url, fetched_at
        FROM seller_profiles
        WHERE platform = 'vinted' AND seller_external_id = '12345'
        """
    ).fetchone()
    rebuilt = profile_from_row(row)
    assert rebuilt is not None
    assert rebuilt.feedback_count == 10
    rating = reliability_rating(rebuilt)
    assert rating.known


# ---------------------------------------------------------------------------
# Extraction Vinted en liste blanche
# ---------------------------------------------------------------------------


class FakeVintedPayload:
    def __init__(self, json_data: dict[str, Any]):
        self.json_data = json_data


VINTED_RAW_WITH_PERSONAL_DATA = {
    "user": {
        "id": 38543837,
        "login": "alexndre.mrt",
        "email": "personnel@exemple.fr",
        "real_name": "Jean Dupont",
        "birthday": "1990-01-01",
        "city": "Lyon",
        "feedback_count": 264,
        "positive_feedback_count": 260,
        "neutral_feedback_count": 2,
        "negative_feedback_count": 2,
        "feedback_reputation": 1.0,
        "item_count": 39,
        "business": False,
        "is_account_banned": False,
        "account_status": "active",
        "profile_url": "https://www.vinted.fr/member/38543837",
        "default_address": {"street": "1 rue privée"},
    }
}


def test_vinted_extraction_keeps_only_whitelisted_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeScraper:
        def __init__(self, domain: str) -> None:
            pass

        def curl(self, endpoint: str) -> FakeVintedPayload:
            assert endpoint == "/api/v2/users/38543837"
            return FakeVintedPayload(VINTED_RAW_WITH_PERSONAL_DATA)

    monkeypatch.setattr("vinted_scraper.VintedScraper", FakeScraper)
    profile = fetch_vinted_seller_profile("38543837")
    assert profile.login == "alexndre.mrt"
    assert profile.feedback_count == 264
    assert profile.reputation_bps == 10_000
    assert profile.account_type == "private"
    serialized = profile.model_dump_json()
    for personal in ("personnel@exemple.fr", "Jean Dupont", "1990-01-01", "Lyon", "rue privée"):
        assert personal not in serialized


def test_vinted_extraction_rejects_invalid_id() -> None:
    with pytest.raises(Exception):
        fetch_vinted_seller_profile("abc")


# ---------------------------------------------------------------------------
# File d'enrichissement et service
# ---------------------------------------------------------------------------


def test_enqueue_is_idempotent(connection: sqlite3.Connection) -> None:
    assert repository.enqueue_seller(
        connection, platform="vinted", seller_external_id="42", login="v"
    )
    assert not repository.enqueue_seller(
        connection, platform="vinted", seller_external_id="42", login="v"
    )


def test_process_pending_enriches_and_relinks(
    connection: sqlite3.Connection,
) -> None:
    source_id = ensure_collection_source(connection, "vinted")
    with connection:
        connection.execute(
            """
            INSERT INTO import_batches (source_id, input_checksum, status)
            VALUES (?, 'test-sellers', 'pending')
            """,
            (source_id,),
        )
        batch_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
    listing = CollectedListing(
        source="vinted",
        external_id="item-1",
        title="Carte Pokémon Pikachu",
        price_cents=500,
        url="https://www.vinted.fr/items/item-1",
        seller="vendeur-1",
        seller_external_id="42",
    )
    ingestion = ingest_collected_listings(
        connection, [listing], platform="vinted", import_batch_id=batch_id
    )
    assert ingestion.created_count == 1

    item = connection.execute(
        "SELECT id, seller_external_id FROM catalog_items WHERE external_id = 'item-1'"
    ).fetchone()
    assert item["seller_external_id"] == "42"
    pending = repository.pending_sellers(connection, limit=10)
    assert [p["seller_external_id"] for p in pending] == ["42"]

    def fake_fetcher(seller_id: str) -> SellerProfile:
        assert seller_id == "42"
        return make_profile(seller_external_id="42", login="vendeur-1")

    service = SellerService(fetchers={"vinted": fake_fetcher}, per_tick=5)
    summary = service.process_pending(connection)
    assert summary == {"enriched": 1, "failed": 0}

    relinked = connection.execute(
        "SELECT seller_profile_id FROM catalog_items WHERE external_id = 'item-1'"
    ).fetchone()
    assert relinked["seller_profile_id"] is not None
    assert repository.pending_sellers(connection, limit=10) == []


def test_process_pending_failure_marks_and_reports(
    connection: sqlite3.Connection,
) -> None:
    repository.enqueue_seller(
        connection, platform="vinted", seller_external_id="99"
    )

    def failing_fetcher(seller_id: str) -> SellerProfile:
        raise RuntimeError("HTTP 500 simulé")

    reports: list[tuple[str, BaseException]] = []
    service = SellerService(
        fetchers={"vinted": failing_fetcher},
        per_tick=5,
    )
    summary = service.process_pending(
        connection, report_failure=lambda p, e: reports.append((p, e))
    )
    assert summary == {"enriched": 0, "failed": 1}
    assert reports and reports[0][0] == "vinted"
    row = connection.execute(
        "SELECT status, attempts, last_error FROM seller_enrichment_queue"
    ).fetchone()
    assert row["status"] == "failed"
    assert row["attempts"] == 1
    assert "HTTP 500" in row["last_error"]


def test_process_pending_is_bounded(connection: sqlite3.Connection) -> None:
    for seller_id in ("1", "2", "3", "4"):
        repository.enqueue_seller(
            connection, platform="leboncoin", seller_external_id=seller_id
        )
    service = SellerService(
        fetchers={"leboncoin": lambda seller_id: make_profile(
            platform="leboncoin", seller_external_id=seller_id
        )},
        per_tick=2,
    )
    summary = service.process_pending(connection)
    assert summary["enriched"] == 2
    assert len(repository.pending_sellers(connection, limit=10)) == 2


def test_stale_profile_is_requeued_on_read(
    connection: sqlite3.Connection,
) -> None:
    from datetime import UTC, datetime, timedelta

    stale_time = (datetime.now(UTC) - timedelta(days=7)).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")
    profile = make_profile(
        seller_external_id="7", fetched_at=stale_time, feedback_count=0
    )
    repository.upsert_profile(connection, profile)
    service = SellerService(cache_seconds=3600)
    row = service.profile_for_item(
        connection,
        platform="vinted",
        seller_profile_id=None,
        seller_external_id="7",
    )
    assert row is not None
    refreshed = connection.execute(
        """
        SELECT status FROM seller_enrichment_queue
        WHERE platform = 'vinted' AND seller_external_id = '7'
        """
    ).fetchone()
    assert refreshed is not None and refreshed["status"] == "pending"
