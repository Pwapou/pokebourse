"""Tests pour l'annuaire vendeurs, le classement (fiabilité, pépites, achats) et le CRM."""

import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.catalog import catalog_item_detail
from app.collectors.models import CollectedListing
from app.collectors.service import ensure_collection_source, ingest_collected_listings
from app.config import Settings
from app.profitability import (
    FeeProfileUpdate,
    ReferenceInput,
    update_active_fee_profile,
    upsert_reference,
)
from app.purchases import purchases_page_data
from app.sellers import repository
from app.sellers.models import SellerProfile
from app.sellers.service import SellerService
from app.storage.database import connect
from app.storage.migration_runner import apply_migrations
from app.web import app


@pytest.fixture
def connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    with connect(tmp_path / "test_sellers_crm.db") as conn:
        apply_migrations(conn)
        yield conn


@pytest.fixture
def test_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Path, TestClient]]:
    db_path = tmp_path / "web_sellers.db"
    monkeypatch.setenv("POKEMON_DATABASE_PATH", str(db_path))
    with TestClient(app) as client:
        yield db_path, client


def make_profile(
    platform: str,
    seller_id: str,
    login: str,
    *,
    feedback_count: int = 10,
    positive_count: int = 10,
    negative_count: int = 0,
    reputation_bps: int = 10000,
    is_favorite: bool = False,
    user_notes: str | None = None,
) -> SellerProfile:
    return SellerProfile(
        platform=platform,  # type: ignore[arg-type]
        seller_external_id=seller_id,
        login=login,
        feedback_count=feedback_count,
        positive_count=positive_count,
        neutral_count=0,
        negative_count=negative_count,
        reputation_bps=reputation_bps,
        item_count=5,
        account_type="private",
        is_banned=False,
        is_favorite=is_favorite,
        user_notes=user_notes,
        fetched_at=datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
    )


def test_purchases_and_seller_stats(connection: sqlite3.Connection) -> None:
    # 1. Création d'un profil vendeur
    p = make_profile("vinted", "101", "PikaVendeur")
    pid = repository.upsert_profile(connection, p)

    # 2. Enregistrement de deux achats
    pur_id1 = repository.record_purchase(
        connection,
        seller_profile_id=pid,
        seller_name="PikaVendeur",
        card_name="Dracaufeu Holo",
        set_name="Set de Base",
        card_number="4/102",
        condition="NM",
        price_paid_cents=8000,
        shipping_paid_cents=500,
        platform="vinted",
        status="recu",
        notes="Superbe carte reçue rapidement.",
    )
    pur_id2 = repository.record_purchase(
        connection,
        seller_profile_id=pid,
        seller_name="PikaVendeur",
        card_name="Pikachu Illustrator Promo",
        price_paid_cents=12000,
        shipping_paid_cents=300,
        platform="vinted",
        status="commande",
    )

    assert pur_id1 > 0
    assert pur_id2 > 0

    # 3. Récupération des achats
    purchases = repository.list_purchases(connection, seller_profile_id=pid)
    assert len(purchases) == 2
    assert purchases[0]["price_paid_cents"] + purchases[0]["shipping_paid_cents"] == 12300

    # 4. Vérification de l'agrégation
    service = SellerService()
    summary = service.get_seller_summary(connection, pid)
    assert summary is not None
    assert summary["purchases_count"] == 2
    assert summary["total_spent_cents"] == (8000 + 500) + (12000 + 300)


def test_purchase_portfolio_counts_all_rows_and_separates_currencies(connection: sqlite3.Connection) -> None:
    connection.executemany(
        "INSERT INTO purchases (seller_name, card_name, price_paid_cents, shipping_paid_cents, currency, status) VALUES (?, ?, ?, ?, ?, ?)",
        [("vendeur", "carte", 100, 25, "EUR", "commande")] * 1001
        + [("vendeur", "carte", 200, 0, "USD", "vendu")],
    )
    result = purchases_page_data(connection, status="vendu")
    assert result["total_count"] == 1002
    assert result["ongoing_count"] == 1001
    assert result["totals_by_currency"] == {"EUR": 125125, "USD": 200}
    assert len(result["purchases"]) == 1


def test_purchase_status_and_sale_price_update(connection: sqlite3.Connection) -> None:
    purchase_id = repository.record_purchase(connection, seller_name="vendeur", card_name="carte", price_paid_cents=500)
    assert repository.update_purchase_status(connection, purchase_id, status="vendu", sale_price_cents=1299)
    purchase = repository.list_purchases(connection)[0]
    assert purchase["status"] == "vendu"
    assert purchase["sale_price_cents"] == 1299
    assert not repository.update_purchase_status(connection, -1, status="recu", sale_price_cents=None)
    with pytest.raises(ValueError):
        repository.update_purchase_status(connection, purchase_id, status="invalide", sale_price_cents=0)


def test_seller_favorite_and_notes(connection: sqlite3.Connection) -> None:
    p = make_profile("leboncoin", "202", "MewSeller")
    pid = repository.upsert_profile(connection, p)

    repository.set_favorite(connection, pid, True)
    repository.set_user_notes(connection, pid, "Accepte 15% de rabais sur les lots")

    profile_data = repository.get_profile(connection, pid)
    assert profile_data is not None
    assert profile_data["is_favorite"] == 1
    assert profile_data["user_notes"] == "Accepte 15% de rabais sur les lots"

    repository.set_favorite(connection, pid, False)
    profile_data2 = repository.get_profile(connection, pid)
    assert profile_data2 is not None
    assert profile_data2["is_favorite"] == 0


def test_directory_ranking_and_sourcing(connection: sqlite3.Connection) -> None:
    # Configuration des profils de frais et cotes pour faire naître une opportunité
    update_active_fee_profile(
        connection,
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
    upsert_reference(
        connection,
        ReferenceInput(
            name="Mewtwo GX",
            set_name="Légendes Brillantes",
            card_number="78/73",
            language="fr",
            reference_price_cents=10000,  # 100 €
            currency="EUR",
            reference_kind="ventes_conclues",
            source_name="Cardmarket",
        ),
    )

    # Vendeur 1 : Très fiable (5 étoiles, 50 avis positifs), 0 opportunité
    v1 = make_profile("vinted", "v1", "UltraFiable", feedback_count=50, positive_count=50, reputation_bps=10000)
    pid1 = repository.upsert_profile(connection, v1)

    # Vendeur 2 : Moins d'avis (3 étoiles), mais propose 1 opportunité rentable
    v2 = make_profile("vinted", "v2", "DénicheurDePépites", feedback_count=4, positive_count=3, reputation_bps=7500)
    pid2 = repository.upsert_profile(connection, v2)

    # Vendeur 3 : Acheteur assidu (3 achats pour 300 €)
    v3 = make_profile("leboncoin", "v3", "FournisseurFidèle", feedback_count=10, is_favorite=True)
    pid3 = repository.upsert_profile(connection, v3)
    repository.record_purchase(connection, seller_profile_id=pid3, seller_name="FournisseurFidèle", card_name="Carte A", price_paid_cents=30000)

    # Ingestion directe d'une annonce rentable pour Vendeur 2
    source_id = ensure_collection_source(connection, "vinted")
    with connection:
        batch_id = int(connection.execute(
            "INSERT INTO import_batches (source_id, input_checksum, status) VALUES (?, 'chk-crm', 'completed')",
            (source_id,),
        ).lastrowid)
        connection.execute(
            """
            INSERT INTO catalog_items (
                source_id, import_batch_id, external_id, name, set_name, card_number,
                language, price_cents, currency, seller, seller_profile_id
            ) VALUES (?, ?, 'ext-pepite-1', 'Mewtwo GX', 'Légendes Brillantes', '78/73', 'fr', 2000, 'EUR', 'DénicheurDePépites', ?)
            """,
            (source_id, batch_id, pid2),
        )

    service = SellerService()

    # 1. Tri par fiabilité (Les plus fiables)
    by_rep = service.list_sellers_directory(connection, sort="reputation")
    assert by_rep[0]["login"] == "UltraFiable"

    # 2. Tri par pépites (Ceux qui vendent les meilleures cartes)
    by_opp = service.list_sellers_directory(connection, sort="opportunities")
    assert by_opp[0]["login"] == "DénicheurDePépites"
    assert by_opp[0]["opportunities_count"] == 1

    # 3. Tri par volume d'achats (Ceux à qui j'ai le plus acheté)
    by_pur = service.list_sellers_directory(connection, sort="purchases")
    assert by_pur[0]["login"] == "FournisseurFidèle"
    assert by_pur[0]["purchases_count"] == 1
    assert by_pur[0]["total_spent_cents"] == 30000

    # 4. Filtre favoris
    favs = service.list_sellers_directory(connection, only_favorites=True)
    assert len(favs) == 1
    assert favs[0]["login"] == "FournisseurFidèle"


def test_web_routes_sellers_and_purchase_recording(test_env: tuple[Path, TestClient]) -> None:
    db_path, client = test_env

    # 1. Préparer un vendeur et une annonce en base
    with connect(db_path) as conn:
        p = make_profile("vinted", "v-web-1", "VendeurWeb")
        pid = repository.upsert_profile(conn, p)

        source_id = ensure_collection_source(conn, "vinted")
        with conn:
            batch_id = int(conn.execute(
                "INSERT INTO import_batches (source_id, input_checksum, status) VALUES (?, 'chk-web', 'completed')",
                (source_id,),
            ).lastrowid)
            item_id = int(conn.execute(
                """
                INSERT INTO catalog_items (
                    source_id, import_batch_id, external_id, name, set_name,
                    price_cents, currency, seller, seller_external_id, seller_profile_id
                ) VALUES (?, ?, 'ext-web-1', 'Gengar Holo', 'Fossile', 2500, 'EUR', 'VendeurWeb', 'v-web-1', ?)
                """,
                (source_id, batch_id, pid),
            ).lastrowid)

    # 2. Test GET /sellers (Annuaire)
    res_list = client.get("/sellers")
    assert res_list.status_code == 200
    assert "Vendeurs" in res_list.text
    assert "VendeurWeb" in res_list.text

    # 3. Test GET /sellers/{id} (Fiche vendeur)
    res_detail = client.get(f"/sellers/{pid}")
    assert res_detail.status_code == 200
    assert "VendeurWeb" in res_detail.text
    assert "Gengar Holo" in res_detail.text

    # 4. Test POST /sellers/{id}/favorite (Toggle favori)
    res_fav = client.post(f"/sellers/{pid}/favorite", data={"is_favorite": "1"}, follow_redirects=True)
    assert res_fav.status_code == 200
    assert "favoris" in res_fav.text

    # 5. Test POST /sellers/{id}/notes (Sauvegarde de notes)
    res_notes = client.post(f"/sellers/{pid}/notes", data={"notes": "Vendeur recommandé pour les holographiques"}, follow_redirects=True)
    assert res_notes.status_code == 200
    assert "Vendeur recommandé pour les holographiques" in res_notes.text

    # 6. Test POST /catalog/{item_id}/purchase (Enregistrement d'achat depuis l'annonce)
    res_buy = client.post(
        f"/catalog/{item_id}/purchase",
        data={
            "price_paid": "24.50",
            "shipping_paid": "2.90",
            "status": "recu",
            "notes": "Parfait état",
        },
        follow_redirects=True,
    )
    assert res_buy.status_code == 200
    assert "Achat enregistré" in res_buy.text

    # 7. Vérifier que la fiche vendeur reflète désormais l'achat conclu
    res_detail_updated = client.get(f"/sellers/{pid}")
    assert res_detail_updated.status_code == 200
    assert "Gengar Holo" in res_detail_updated.text
    assert "24,50" in res_detail_updated.text or "27,40" in res_detail_updated.text


def test_imported_purchase_never_invents_seller_platform(test_env: tuple[Path, TestClient]) -> None:
    """Un import eBay crée un vendeur eBay ; un domaine inconnu reste sans profil."""
    db_path, client = test_env
    content = (
        '{"external_id":"e1","name":"Pikachu","set_name":"151",'
        '"price_cents":8325,"seller":"vendeur-ebay","url":"https://www.ebay.fr/itm/123"}\n'
        '{"external_id":"e2","name":"Pikachu","set_name":"151",'
        '"price_cents":100,"seller":"autre","url":"https://ebay.fr.example.com/item"}\n'
    ).encode()
    assert client.post("/imports", files={"file": ("test.jsonl", content, "application/x-ndjson")}).status_code == 200
    for item_id in (1, 2):
        response = client.post(
            f"/catalog/{item_id}/purchase",
            data={"price_paid": "1.00", "shipping_paid": "0", "status": "commande"},
            follow_redirects=False,
        )
        assert response.status_code == 303
    with connect(db_path) as conn:
        rows = conn.execute("SELECT platform, seller_name, seller_profile_id FROM purchases ORDER BY id").fetchall()
        assert rows[0]["platform"] == "ebay"
        assert rows[0]["seller_profile_id"] is not None
        assert rows[1]["platform"] is None
        assert rows[1]["seller_profile_id"] is None
        assert conn.execute("SELECT platform FROM seller_profiles").fetchone()["platform"] == "ebay"
