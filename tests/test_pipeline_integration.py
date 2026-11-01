import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.catalog import catalog_data, catalog_item_detail, reidentify_catalog_item
from app.collectors.models import CollectedListing
from app.collectors.service import ensure_collection_source, ingest_collected_listings
from app.config import Settings
from app.profitability import (
    build_card_key,
    build_market_index,
    evaluate_listing,
    get_active_fee_profile,
    update_active_fee_profile,
    upsert_reference,
    FeeProfileUpdate,
    ReferenceInput,
)
from app.storage.database import connect
from app.storage.migration_runner import apply_migrations
from app.tcgdex.cache import TcgdexCache
from app.web import app


@pytest.fixture
def test_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "pipeline.db"
    with connect(db_path) as connection:
        apply_migrations(connection)
        cache = TcgdexCache(connection)
        cache.seed_initial_if_empty()
    return db_path


def make_listing(
    external_id: str,
    title: str,
    price_cents: int = 1500,
    source: str = "vinted",
) -> CollectedListing:
    return CollectedListing(
        source=source,  # type: ignore[arg-type]
        external_id=external_id,
        title=title,
        price_cents=price_cents,
        shipping_cents=250,
        url=f"https://www.vinted.fr/items/{external_id}",
        image_url=f"https://images.vinted.net/{external_id}.jpg",
        seller="Vendeur Test",
        raw_data={"title": title, "price": f"{price_cents / 100:.2f}"},
    )


def test_full_pipeline_clear_identification_and_profitability(test_db: Path) -> None:
    with connect(test_db) as conn:
        source_id = ensure_collection_source(conn, "vinted")
        with conn:
            batch_cursor = conn.execute(
                "INSERT INTO import_batches (source_id, input_checksum, status) VALUES (?, 'checksum-1', 'completed')",
                (source_id,),
            )
            batch_id = int(batch_cursor.lastrowid)

        # 1. Annonce claire : Dracaufeu 4/102 Set de Base
        listing = make_listing("vinted-dracaufeu-1", "Carte Pokémon Dracaufeu 4/102 Set de Base Holo", price_cents=5000)
        res = ingest_collected_listings(conn, [listing], platform="vinted", import_batch_id=batch_id)

        assert res.created_count == 1
        item_row = conn.execute("SELECT * FROM catalog_items WHERE external_id = 'vinted-dracaufeu-1'").fetchone()
        assert item_row["identification_status"] == "identified"
        assert item_row["name"] == "Dracaufeu"
        assert item_row["set_name"] == "Set de Base"
        assert item_row["card_number"] == "4"
        assert item_row["reference_card_id"] is not None

        # 2. Configuration des frais et ajout d'une cote de référence
        update_active_fee_profile(
            conn,
            FeeProfileUpdate(
                buyer_shipping_cents=0,
                platform_fee_bps=500,
                seller_fixed_fee_cents=0,
                shipping_packaging_cents=200,
                min_net_profit_cents=500,
                min_roi_bps=1500,
                min_catalog_samples=2,
            ),
        )
        ref = ReferenceInput(
            name="Dracaufeu",
            set_name="Set de Base",
            card_number="4",
            language="fr",
            variant="Holo",
            reference_price_cents=20000,  # 200 €
            currency="EUR",
            reference_kind="ventes_conclues",
            source_name="Cardmarket",
        )
        upsert_reference(conn, ref, source_kind="manual")

        # 3. Évaluation par le moteur de rentabilité
        fee_profile = get_active_fee_profile(conn)
        market_index = build_market_index(conn, fee_profile.min_catalog_samples)
        detail = catalog_item_detail(conn, item_row["id"])
        eval_res = evaluate_listing(detail, fee_profile, market_index)

        assert eval_res["verdict"] == "opportunite"
        assert eval_res["reference_price_cents"] == 20000
        assert eval_res["net_profit_cents"] is not None and eval_res["net_profit_cents"] > 10000


def test_full_pipeline_lot_does_not_forge_profitability(test_db: Path) -> None:
    with connect(test_db) as conn:
        source_id = ensure_collection_source(conn, "vinted")
        with conn:
            batch_cursor = conn.execute(
                "INSERT INTO import_batches (source_id, input_checksum, status) VALUES (?, 'checksum-lot', 'completed')",
                (source_id,),
            )
            batch_id = int(batch_cursor.lastrowid)

        lot_listing = make_listing("vinted-lot-1", "Lot de 50 cartes Pokémon rares et communes", price_cents=1500)
        res = ingest_collected_listings(conn, [lot_listing], platform="vinted", import_batch_id=batch_id)

        assert res.created_count == 1
        item_row = conn.execute("SELECT * FROM catalog_items WHERE external_id = 'vinted-lot-1'").fetchone()
        assert item_row["identification_status"] == "lot"
        assert item_row["is_lot"] == 1
        assert item_row["reference_card_id"] is None

        # Évaluation rentabilité : doit rester sans cote / données insuffisantes
        update_active_fee_profile(
            conn,
            FeeProfileUpdate(
                buyer_shipping_cents=0,
                platform_fee_bps=500,
                seller_fixed_fee_cents=0,
                shipping_packaging_cents=200,
                min_net_profit_cents=500,
                min_roi_bps=1500,
                min_catalog_samples=2,
            ),
        )
        fee_profile = get_active_fee_profile(conn)
        market_index = build_market_index(conn, fee_profile.min_catalog_samples)
        detail = catalog_item_detail(conn, item_row["id"])
        eval_res = evaluate_listing(detail, fee_profile, market_index)
        assert eval_res["verdict"] == "sans_cote"


def test_reimport_preserves_first_seen_and_updates_price(test_db: Path) -> None:
    with connect(test_db) as conn:
        source_id = ensure_collection_source(conn, "vinted")
        with conn:
            batch_id = int(conn.execute(
                "INSERT INTO import_batches (source_id, input_checksum, status) VALUES (?, 'b1', 'completed')",
                (source_id,),
            ).lastrowid)

        listing1 = make_listing("vinted-pika-1", "Pikachu 58/102 Set de Base", price_cents=2000)
        ingest_collected_listings(conn, [listing1], platform="vinted", import_batch_id=batch_id)
        row1 = conn.execute("SELECT first_seen_at, last_seen_at, price_cents FROM catalog_items WHERE external_id = 'vinted-pika-1'").fetchone()

        # Deuxième passage avec baisse de prix
        listing2 = make_listing("vinted-pika-1", "Pikachu 58/102 Set de Base", price_cents=1500)
        ingest_collected_listings(conn, [listing2], platform="vinted", import_batch_id=batch_id)
        row2 = conn.execute("SELECT first_seen_at, last_seen_at, price_cents FROM catalog_items WHERE external_id = 'vinted-pika-1'").fetchone()

        assert row2["first_seen_at"] == row1["first_seen_at"]
        assert row2["price_cents"] == 1500
        # Pas de doublon
        assert conn.execute("SELECT COUNT(*) FROM catalog_items WHERE external_id = 'vinted-pika-1'").fetchone()[0] == 1


def test_web_routes_and_reidentification(test_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POKEMON_DATABASE_PATH", str(test_db))

    with connect(test_db) as conn:
        source_id = ensure_collection_source(conn, "vinted")
        with conn:
            batch_id = int(conn.execute(
                "INSERT INTO import_batches (source_id, input_checksum, status) VALUES (?, 'bweb', 'completed')",
                (source_id,),
            ).lastrowid)
        listing = make_listing("vinted-web-1", "Dracaufeu 4/102 Set de Base", price_cents=3000)
        ingest_collected_listings(conn, [listing], platform="vinted", import_batch_id=batch_id)
        item_id = conn.execute("SELECT id FROM catalog_items WHERE external_id = 'vinted-web-1'").fetchone()[0]

    with TestClient(app) as client:
        # Test route /catalog avec filtre d'identification
        response = client.get("/catalog?ident=identified")
        assert response.status_code == 200
        assert "Dracaufeu" in response.text
        assert "Identifiée" in response.text

        # Test route détail /catalog/{id}
        detail_res = client.get(f"/catalog/{item_id}")
        assert detail_res.status_code == 200
        assert "Identification &amp; Justification" in detail_res.text or "Identification & Justification" in detail_res.text
        assert "Set de Base" in detail_res.text

        # Test réidentification POST /catalog/{id}/reidentify
        post_res = client.post(f"/catalog/{item_id}/reidentify", follow_redirects=True)
        assert post_res.status_code == 200
        assert "Identification r" in post_res.text  # notice "Identification réexaminée"
