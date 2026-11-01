import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.catalog import import_jsonl
from app.collectors.models import CollectedListing
from app.collectors.service import ensure_collection_source, ingest_collected_listings
from app.storage.database import connect
from app.storage.migration_runner import apply_migrations


@pytest.fixture
def connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    with connect(tmp_path / "ingestion.db") as db_connection:
        apply_migrations(db_connection)
        yield db_connection


def collected(
    external_id: str,
    *,
    title: str = "Carte Pokémon Pikachu - Évolutions",
    price_cents: int = 1234,
) -> CollectedListing:
    return CollectedListing(
        source="vinted",
        external_id=external_id,
        title=title,
        price_cents=price_cents,
        shipping_cents=250,
        url=f"https://www.vinted.fr/items/{external_id}",
        image_url=f"https://images.vinted.net/{external_id}.jpg",
        seller="Vendeur test",
        raw_data={
            "id": external_id,
            "price": f"{price_cents // 100}.{price_cents % 100:02d}",
        },
    )


def create_batch(connection: sqlite3.Connection, platform: str = "vinted") -> int:
    source_id = ensure_collection_source(connection, platform)  # type: ignore[arg-type]
    with connection:
        cursor = connection.execute(
            "INSERT INTO import_batches (source_id, input_checksum, status) "
            "VALUES (?, ?, 'pending')",
            (source_id, f"test-batch-{connection.total_changes}"),
        )
    return int(cursor.lastrowid)


def test_insert_then_identical_second_pass_has_no_duplicate(connection: sqlite3.Connection) -> None:
    first_batch = create_batch(connection)
    listing = collected("abc-1")

    first = ingest_collected_listings(
        connection, [listing], platform="vinted", import_batch_id=first_batch
    )
    first_seen = connection.execute(
        "SELECT first_seen_at, last_seen_at FROM catalog_items WHERE external_id = 'abc-1'"
    ).fetchone()
    assert first_seen["first_seen_at"] == first_seen["last_seen_at"]

    second_batch = create_batch(connection)
    second = ingest_collected_listings(
        connection, [listing], platform="vinted", import_batch_id=second_batch
    )

    assert first.processed_count == 1
    assert first.created_count == 1
    assert first.updated_count == 0
    assert second.created_count == 0
    assert second.updated_count == 0
    assert connection.execute("SELECT COUNT(*) FROM catalog_items").fetchone()[0] == 1
    row = connection.execute(
        "SELECT external_id, original_title, first_seen_at, last_seen_at, raw_data "
        "FROM catalog_items"
    ).fetchone()
    assert row["external_id"] == "abc-1"
    assert row["original_title"] == listing.title
    assert row["first_seen_at"] == first_seen["first_seen_at"]
    assert row["last_seen_at"] >= first_seen["last_seen_at"]
    assert json.loads(row["raw_data"]) == {"id": "abc-1", "price": "12.34"}


def test_price_title_and_last_seen_update_preserves_first_seen(
    connection: sqlite3.Connection,
) -> None:
    batch_id = create_batch(connection)
    ingest_collected_listings(
        connection,
        [collected("abc-2", price_cents=1000, title="Carte Pokémon Pikachu")],
        platform="vinted",
        import_batch_id=batch_id,
    )
    with connection:
        connection.execute(
            """
            UPDATE catalog_items SET first_seen_at = '2026-10-01T10:00:00.000Z',
                   last_seen_at = '2026-10-01T10:00:00.000Z'
            WHERE external_id = 'abc-2'
            """
        )

    result = ingest_collected_listings(
        connection,
        [
            collected(
                "abc-2",
                price_cents=1250,
                title="Carte Pokémon Pikachu - Base Set",
            )
        ],
        platform="vinted",
        import_batch_id=batch_id,
    )

    assert result.created_count == 0
    assert result.updated_count == 1
    row = connection.execute(
        "SELECT price_cents, original_title, first_seen_at, last_seen_at "
        "FROM catalog_items WHERE external_id = 'abc-2'"
    ).fetchone()
    assert row["price_cents"] == 1250
    assert row["original_title"] == "Carte Pokémon Pikachu - Base Set"
    assert row["first_seen_at"] == "2026-10-01T10:00:00.000Z"
    assert row["last_seen_at"] > "2026-10-01T10:00:00.000Z"


def test_invalid_listing_is_isolated(connection: sqlite3.Connection) -> None:
    batch_id = create_batch(connection)
    invalid_platform = CollectedListing(
        source="leboncoin",
        external_id="wrong-platform",
        title="Carte Pokémon Mew",
        price_cents=500,
        url="https://www.leboncoin.fr/ad/wrong-platform",
    )

    result = ingest_collected_listings(
        connection,
        [collected("valid-1"), invalid_platform],
        platform="vinted",
        import_batch_id=batch_id,
    )

    assert result.processed_count == 1
    assert result.invalid_count == 1
    assert result.created_count == 1
    assert connection.execute(
        "SELECT COUNT(*) FROM catalog_items WHERE external_id = 'valid-1'"
    ).fetchone()[0] == 1


def test_manual_jsonl_import_survives_marketplace_ingestion(
    connection: sqlite3.Connection,
) -> None:
    content = (
        b'{"external_id":"manual-1","name":"Dracaufeu","set_name":"Base Set",'
        b'"price_cents":25000}'
    )
    imported = import_jsonl(connection, content, source_name="import-test")
    batch_id = create_batch(connection)
    marketplace = ingest_collected_listings(
        connection,
        [collected("market-1")],
        platform="vinted",
        import_batch_id=batch_id,
    )

    assert imported == 1
    assert marketplace.created_count == 1
    sources = connection.execute(
        "SELECT name, kind, enabled FROM sources WHERE name IN ('import-test', 'vinted') ORDER BY name"
    ).fetchall()
    assert {row["name"]: row["kind"] for row in sources} == {
        "import-test": "manual_jsonl",
        "vinted": "api",
    }
    assert all(row["enabled"] == 1 for row in sources)
    assert connection.execute("SELECT COUNT(*) FROM catalog_items").fetchone()[0] == 2
