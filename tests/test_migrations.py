import sqlite3
from pathlib import Path

import pytest

from app.storage.database import connect
from app.storage.migration_runner import apply_migrations, check_database, migration_files


def test_migrations_create_registry_and_are_idempotent(tmp_path: Path) -> None:
    database_path = tmp_path / "arbitrage.db"
    with connect(database_path) as connection:
        first_applied = apply_migrations(connection)
        second_applied = apply_migrations(connection)

        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        migration_count = connection.execute(
            "SELECT COUNT(*) FROM schema_migrations"
        ).fetchone()[0]

        assert first_applied == [
            "0001_create_import_registry.sql",
            "0002_create_catalog.sql",
            "0003_create_profitability.sql",
            "0004_create_import_failures.sql",
            "0005_profitability_v11.sql",
            "0006_create_listing_watches.sql",
            "0007_create_supervision.sql",
            "0008_create_pokemon_reference_catalog.sql",
            "0009_create_seller_profiles.sql",
            "0010_create_purchases_and_seller_stats.sql",
        ]
        assert second_applied == []
        assert {
            "sources",
            "import_batches",
            "catalog_items",
            "fee_profiles",
            "market_references",
            "import_failures",
            "listing_watches",
            "listing_watch_runs",
            "supervision_agents",
            "supervision_collectors",
            "supervision_incidents",
            "supervision_events",
            "pokemon_reference_sets",
            "pokemon_reference_cards",
            "seller_profiles",
            "seller_enrichment_queue",
            "purchases",
            "schema_migrations",
        } <= tables
        assert migration_count == 10
        check_database(connection)


def test_data_survives_reopening_database(tmp_path: Path) -> None:
    database_path = tmp_path / "arbitrage.db"
    with connect(database_path) as connection:
        apply_migrations(connection)
        connection.execute(
            "INSERT INTO sources (name, kind) VALUES ('demo', 'demo')"
        )
        connection.commit()

    with connect(database_path) as connection:
        source = connection.execute(
            "SELECT name, kind, enabled FROM sources"
        ).fetchone()
        assert dict(source) == {"name": "demo", "kind": "demo", "enabled": 0}
        check_database(connection)


def test_foreign_keys_are_enforced(tmp_path: Path) -> None:
    database_path = tmp_path / "arbitrage.db"
    with connect(database_path) as connection:
        apply_migrations(connection)

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO import_batches (source_id, input_checksum) VALUES (999, 'abc')"
            )


def test_check_rejects_uninitialized_database(tmp_path: Path) -> None:
    with connect(tmp_path / "arbitrage.db") as connection:
        with pytest.raises(RuntimeError, match="Base non initialisée"):
            check_database(connection)


def test_v11_migration_marks_legacy_fees_for_confirmation(tmp_path: Path) -> None:
    with connect(tmp_path / "upgrade.db") as connection:
        connection.execute(
            "CREATE TABLE schema_migrations ("
            "version TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        for version, script in migration_files():
            if version != "0005_profitability_v11.sql":
                connection.executescript(script)
        connection.execute(
            "INSERT INTO market_references (card_key, name, set_name, reference_price_cents) "
            "VALUES ('legacy-key', 'Mew', '151', 1000)"
        )

        assert apply_migrations(connection) == ["0005_profitability_v11.sql"]
        fees = connection.execute(
            "SELECT buyer_shipping_cents, platform_fee_bps, "
            "seller_fixed_fee_cents, shipping_packaging_cents FROM fee_profiles"
        ).fetchone()
        assert tuple(fees) == (None, None, None, None)
        legacy_fees = connection.execute(
            "SELECT buyer_shipping_cents, platform_fee_bps, "
            "seller_fixed_fee_cents, shipping_packaging_cents "
            "FROM fee_profile_legacy_assumptions"
        ).fetchone()
        assert tuple(legacy_fees) == (0, 500, 0, 200)
        assert connection.execute(
            "SELECT reference_price_cents FROM market_references WHERE card_key = 'legacy-key'"
        ).fetchone()[0] == 1000
        reference_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(market_references)")
        }
        assert {
            "variant",
            "edition",
            "grading_company",
            "grade",
            "source_name",
            "reference_kind",
            "observed_at",
            "source_url",
            "sample_size",
        } <= reference_columns
        check_database(connection)
