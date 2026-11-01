import json
import sqlite3
from pathlib import Path

import pytest

from app.catalog import import_jsonl, import_listings_from_extension
from app.collectors.models import CollectedListing
from app.collectors.service import ensure_collection_source, ingest_collected_listings
from app.radar.repository import set_decision
from app.storage.database import connect
from app.storage.migration_runner import apply_migrations, migration_files


def test_collector_observations_decision_and_rollback(tmp_path: Path) -> None:
    with connect(tmp_path / "radar.db") as db:
        apply_migrations(db)
        source = ensure_collection_source(db, "vinted")
        batch = db.execute("INSERT INTO import_batches (source_id, input_checksum) VALUES (?, 'run')", (source,)).lastrowid
        db.commit()

        def ingest(price: int) -> None:
            listing = CollectedListing(source="vinted", external_id="1", title="Pikachu", price_cents=price,
                                       shipping_cents=100, url="https://www.vinted.fr/items/1", raw_data={"price": price})
            ingest_collected_listings(db, [listing], platform="vinted", import_batch_id=batch)

        ingest(1000)
        item = db.execute("SELECT * FROM catalog_items").fetchone()
        first_seen = item["first_seen_at"]
        with db:
            set_decision(db, item["id"], "ecartee", "déjà vue")
        ingest(1000)
        assert db.execute("SELECT count(*) FROM listing_observations").fetchone()[0] == 1
        ingest(800)
        assert [row[0] for row in db.execute("SELECT kind FROM listing_events ORDER BY id")] == ["creation", "baisse_prix"]
        assert db.execute("SELECT first_seen_at FROM catalog_items").fetchone()[0] == first_seen
        assert db.execute("SELECT state FROM listing_decisions").fetchone()[0] == "ecartee"
        db.execute("CREATE TRIGGER fail_event BEFORE INSERT ON listing_events BEGIN SELECT RAISE(ABORT, 'test'); END")
        db.commit()
        with pytest.raises(sqlite3.IntegrityError):
            ingest(700)
        assert db.execute("SELECT price_cents FROM catalog_items").fetchone()[0] == 800
        assert db.execute("SELECT count(*) FROM listing_observations").fetchone()[0] == 2


def test_import_and_extension_record_real_observations(tmp_path: Path) -> None:
    with connect(tmp_path / "imports.db") as db:
        apply_migrations(db)
        payload = {"external_id": "one", "name": "Pikachu", "set_name": "Base", "price_cents": 1000}
        import_jsonl(db, json.dumps(payload).encode(), source_name="manual")
        import_listings_from_extension(db, json.dumps(payload).encode())
        import_listings_from_extension(db, json.dumps(payload).encode())
        payload["price_cents"] = 900
        import_listings_from_extension(db, json.dumps(payload).encode())
        assert [tuple(row) for row in db.execute("SELECT origin, price_cents FROM listing_observations ORDER BY id")] == [
            ("import", 1000), ("extension", 1000), ("extension", 900)
        ]
        assert [row[0] for row in db.execute("SELECT kind FROM listing_events ORDER BY id")] == ["creation", "creation", "baisse_prix"]


def test_migration_labels_legacy_state_without_retroactive_event(tmp_path: Path) -> None:
    with connect(tmp_path / "legacy.db") as db:
        db.execute("CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        for version, sql in migration_files():
            if version == "0019_radar_observations.sql":
                break
            db.executescript(sql)
        import_payload = {"external_id": "one", "name": "Pikachu", "set_name": "Base", "price_cents": 1000}
        # Ancienne base : insertion directe avant que les nouvelles tables existent.
        db.execute("INSERT INTO sources (name, kind) VALUES ('legacy', 'manual_jsonl')")
        source = db.execute("SELECT id FROM sources WHERE name='legacy'").fetchone()[0]
        batch = db.execute("INSERT INTO import_batches (source_id, input_checksum) VALUES (?, 'old')", (source,)).lastrowid
        db.execute("INSERT INTO catalog_items (source_id, import_batch_id, external_id, name, set_name, price_cents) VALUES (?, ?, ?, ?, ?, ?)",
                   (source, batch, import_payload["external_id"], import_payload["name"], import_payload["set_name"], import_payload["price_cents"]))
        db.commit()
        apply_migrations(db)
        assert db.execute("SELECT origin FROM listing_observations").fetchone()[0] == "etat_migration"
        assert db.execute("SELECT count(*) FROM listing_events").fetchone()[0] == 0
