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
            "0011_create_cardmarket_prices.sql",
            "0012_identification_research.sql",
            "0013_identification_reviews.sql",
            "0014_annotation_pilot.sql",
            "0015_cardmarket_name_aliases.sql",
            "0016_add_ebay_wallapop_platforms.sql",
            "0017_create_cardmarket_sync_state.sql",
            "0018_tcgdex_sync_jobs.sql",
            "0019_radar_observations.sql",
            "0020_search_indexes.sql",
            "0021_purchase_sale_price.sql",
            "0022_identification_observations.sql",
            "0023_visual_evidence.sql",
            "0024_reference_localizations.sql",
            "0025_reference_aliases.sql",
            "0026_tcgdex_sync_locale.sql",
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
            "cardmarket_prices",
            "listing_identity_evidence",
            "listing_identification_decisions",
            "identification_searches",
            "identification_search_listings",
            "listing_identification_snapshots",
            "listing_identification_reviews",
            "identification_catalog_versions",
            "annotation_pilots",
            "annotation_sampling_batches",
            "annotation_pilot_items",
            "card_name_aliases",
            "cardmarket_sync_state",
            "tcgdex_sync_jobs",
            "tcgdex_sync_cards",
            "tcgdex_sync_control",
            "listing_image_evidence",
            "listing_image_evidence_readings",
            "reference_aliases",
            "schema_migrations",
        } <= tables
        assert migration_count == 26
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
            "SELECT name, kind, enabled FROM sources WHERE name = 'demo'"
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


def test_invalid_table_rebuild_rolls_back_and_restores_foreign_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    with connect(tmp_path / "invalid-rebuild.db") as connection:
        connection.executescript("""
            CREATE TABLE schema_migrations(version TEXT PRIMARY KEY);
            CREATE TABLE parent(id INTEGER PRIMARY KEY);
            CREATE TABLE child(parent_id INTEGER REFERENCES parent(id) ON DELETE CASCADE);
            INSERT INTO parent VALUES (1);
            INSERT INTO child VALUES (1);
        """)
        script = """BEGIN IMMEDIATE;
            CREATE TABLE parent_new(id INTEGER PRIMARY KEY);
            DROP TABLE parent;
            ALTER TABLE parent_new RENAME TO parent;
            INSERT INTO schema_migrations VALUES ('9999_invalid.sql');
            COMMIT;
        """
        monkeypatch.setattr("app.storage.migration_runner.migration_files", lambda: [("9999_invalid.sql", script)])
        with pytest.raises(RuntimeError, match="9999_invalid.sql"):
            apply_migrations(connection)
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("SELECT id FROM parent").fetchone()[0] == 1
        assert connection.execute("SELECT parent_id FROM child").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM schema_migrations").fetchone()[0] == 0
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


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


def test_reviews_and_reference_cards_survive_t04_t05_rebuilds(tmp_path: Path) -> None:
    with connect(tmp_path / "upgrade-t04-t05.db") as connection:
        connection.execute(
            "CREATE TABLE schema_migrations ("
            "version TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        pending = ("0023_visual_evidence.sql", "0024_reference_localizations.sql",
                   "0025_reference_aliases.sql", "0026_tcgdex_sync_locale.sql")
        for version, script in migration_files():
            if version in pending:
                continue
            # Les reconstructions de tables sont exécutées par le runner en temps normal.
            if "DROP TABLE" in script:
                from app.storage.migration_runner import _apply_table_rebuild
                _apply_table_rebuild(connection, script)
            else:
                connection.executescript(script)

        # Une décision et une fiche référence existent à l'état 0022.
        connection.execute("INSERT INTO sources (name, kind) VALUES ('demo', 'demo')")
        connection.execute("INSERT INTO import_batches (source_id, input_checksum) VALUES (1, 'legacy-batch')")
        connection.execute(
            """INSERT INTO catalog_items (source_id, import_batch_id, external_id, name, original_title,
            set_name, price_cents, raw_data, identification_status)
            VALUES (1, 1, 'legacy-1', 'Dracaufeu 4/102', 'Dracaufeu 4/102', 'Set de Base', 100, '{}', 'ambiguous')"""
        )
        connection.execute("INSERT INTO identification_catalog_versions VALUES ('v-legacy', '[]', '2026-01-01T00:00:00.000Z')")
        connection.execute(
            """INSERT INTO listing_identification_snapshots
            (listing_id, input_hash, title, attributes_json, input_origin, source_kind, platform, group_key,
             normalization_version, captured_at)
            VALUES (1, 'hash-legacy', 'Dracaufeu 4/102', '{}', 'original_text', 'api', 'unknown', 'g-1', 'norm-v1', '2026-01-01T00:00:00.000Z')"""
        )
        connection.execute(
            """INSERT INTO listing_identification_reviews
            (snapshot_id, outcome, review_kind, validated_by, validated_at, evidence_basis, text_sufficient, catalog_version)
            VALUES (1, 'insufficient_evidence', 'decision', 'lecteur-legacy', '2026-01-01T00:00:01.000Z', 'text', 1, 'v-legacy')"""
        )
        connection.execute(
            "INSERT INTO pokemon_reference_sets (id, name) VALUES ('base1', 'Set de Base')"
        )
        connection.execute(
            """INSERT INTO pokemon_reference_cards
            (tcgdex_id, local_id, name, set_id, set_name, updated_at)
            VALUES ('base1-4', '4', 'Dracaufeu', 'base1', 'Set de Base', '2026-01-01T00:00:00.000Z')"""
        )
        connection.commit()

        assert apply_migrations(connection) == list(pending)

        review = connection.execute("SELECT * FROM listing_identification_reviews").fetchone()
        assert review["id"] == 1 and review["outcome"] == "insufficient_evidence"
        assert review["evidence_basis"] == "text" and review["validated_by"] == "lecteur-legacy"
        assert review["image_evidence_id"] is None
        card = connection.execute("SELECT * FROM pokemon_reference_cards WHERE tcgdex_id='base1-4'").fetchone()
        assert card["id"] == 1 and card["name"] == "Dracaufeu" and card["reference_language"] == "fr"
        # La nouvelle contrainte d'unicité par localisation est en vigueur.
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO pokemon_reference_cards (tcgdex_id, local_id, name, set_id, set_name) "
                "VALUES ('base1-4', '4', 'Doublon fr', 'base1', 'Set de Base')"
            )
        check_database(connection)
