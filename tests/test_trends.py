"""Tests du Lot 3 — Tendances de prix, activité des annonces et meilleures affaires.

100 % hermétiques : aucun appel réseau réel, données SQLite locales.
"""

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
import sqlite3
import pytest
from fastapi.testclient import TestClient

from app.profitability import (
    FeeProfileUpdate,
    ReferenceInput,
    evaluate_listing,
    get_active_fee_profile,
    update_active_fee_profile,
    upsert_reference,
)
from app.storage.database import connect
from app.storage.migration_runner import apply_migrations
from app.trends.models import TrendsFilters
from app.trends.opportunities import get_best_opportunities
from app.trends.service import (
    compute_price_variation,
    get_listing_activity,
    get_price_movements,
    get_trends_page_data,
)
from app.web import app


@pytest.fixture
def db_connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    """Crée une base de données de test avec toutes les migrations appliquées."""
    db_file = tmp_path / "trends_test.db"
    with connect(db_file) as connection:
        apply_migrations(connection)
        configure_fees(connection)
        yield connection


def configure_fees(connection: sqlite3.Connection, **overrides: int) -> None:
    values = {
        "buyer_shipping_cents": 0,
        "platform_fee_bps": 500,
        "seller_fixed_fee_cents": 0,
        "shipping_packaging_cents": 200,
        "min_net_profit_cents": 500,
        "min_roi_bps": 1500,
        "min_catalog_samples": 2,
        **overrides,
    }
    update_active_fee_profile(connection, FeeProfileUpdate(**values))


def insert_ref_card(
    connection: sqlite3.Connection,
    *,
    tcgdex_id: str,
    local_id: str,
    name: str,
    set_id: str,
    set_name: str,
    rarity: str = "Rare",
) -> int:
    connection.execute(
        "INSERT OR IGNORE INTO pokemon_reference_sets (id, name, release_date) VALUES (?, ?, '2023-01-01')",
        (set_id, set_name),
    )
    cursor = connection.execute(
        """
        INSERT INTO pokemon_reference_cards (tcgdex_id, local_id, name, set_id, set_name, rarity)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (tcgdex_id, local_id, name, set_id, set_name, rarity),
    )
    return cursor.lastrowid


def insert_catalog_listing(
    connection: sqlite3.Connection,
    *,
    external_id: str,
    name: str,
    set_name: str,
    card_number: str | None = None,
    price_cents: int = 1000,
    currency: str = "EUR",
    language: str = "fr",
    condition: str = "Near Mint",
    is_active: int = 1,
    is_lot: int = 0,
    identification_status: str = "identified",
    reference_card_id: int | None = None,
    first_seen_at: str | None = None,
    last_seen_at: str | None = None,
    source_name: str = "vinted",
) -> int:
    source_row = connection.execute(
        "SELECT id FROM sources WHERE name = ?", (source_name,)
    ).fetchone()
    if source_row:
        source_id = source_row[0]
    else:
        cursor = connection.execute(
            "INSERT INTO sources (name, kind) VALUES (?, 'manual_jsonl')", (source_name,)
        )
        source_id = cursor.lastrowid

    batch_row = connection.execute(
        "SELECT id FROM import_batches WHERE source_id = ?", (source_id,)
    ).fetchone()
    if batch_row:
        batch_id = batch_row[0]
    else:
        cursor = connection.execute(
            "INSERT INTO import_batches (source_id, input_checksum, status) VALUES (?, 'checksum-test', 'completed')",
            (source_id,),
        )
        batch_id = cursor.lastrowid

    now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    first_seen = first_seen_at or now_iso
    last_seen = last_seen_at or now_iso

    cursor = connection.execute(
        """
        INSERT INTO catalog_items (
            source_id, import_batch_id, external_id, name, set_name, card_number, price_cents,
            currency, language, condition, is_active, is_lot,
            identification_status, reference_card_id, first_seen_at, last_seen_at, imported_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source_id,
            batch_id,
            external_id,
            name,
            set_name,
            card_number,
            price_cents,
            currency,
            language,
            condition,
            is_active,
            is_lot,
            identification_status,
            reference_card_id,
            first_seen,
            last_seen,
            first_seen,
        ),
    )
    return cursor.lastrowid


# ==============================================================================
# T3.1 : Tests des variations de prix
# ==============================================================================

def test_compute_price_variation_positive_negative_zero() -> None:
    # Hausse (+20 %)
    pos = compute_price_variation(1200, 1000)
    assert pos == (200, 2000)

    # Baisse (-20 %)
    neg = compute_price_variation(800, 1000)
    assert neg == (-200, -2000)

    # Nulle (0 %)
    zero = compute_price_variation(1000, 1000)
    assert zero == (0, 0)


def test_compute_price_variation_rounding_round_half_up() -> None:
    # 1 / 300 = 0.0033333... -> 33.33 bps -> 33 bps
    assert compute_price_variation(301, 300) == (1, 33)

    # 2 / 300 = 0.0066666... -> 66.67 bps -> 67 bps
    assert compute_price_variation(302, 300) == (2, 67)

    # 1 / 200 = 0.005 -> 50.0 bps -> 50 bps
    assert compute_price_variation(201, 200) == (1, 50)

    # Baisse arrondie : -1 / 300 -> -33.33 bps -> -33 bps
    assert compute_price_variation(299, 300) == (-1, -33)

    # Baisse arrondie : -2 / 300 -> -66.67 bps -> -67 bps
    assert compute_price_variation(298, 300) == (-2, -67)


def test_compute_price_variation_invalid_and_incompatible() -> None:
    # Prix absents
    assert compute_price_variation(None, 1000) is None
    assert compute_price_variation(1000, None) is None
    assert compute_price_variation(None, None) is None

    # Prix de référence nul ou négatif
    assert compute_price_variation(1000, 0) is None
    assert compute_price_variation(1000, -100) is None

    # Devises incompatibles
    assert compute_price_variation(1000, 800, currency="EUR", ref_currency="USD") is None


def test_get_price_movements_from_cardmarket_prices(db_connection: sqlite3.Connection) -> None:
    now_iso = "2026-11-01T10:00:00Z"
    # Produit 1 : Forte hausse 7/30 (avg7=1500, avg30=1000 -> +500 cents, +5000 bps)
    # Produit 2 : Baisse 7/30 (avg7=800, avg30=1000 -> -200 cents, -2000 bps)
    # Produit 3 : Prix de référence 0 (doit être exclu)
    # Produit 4 : Prix avg7 absent (doit être exclu)
    db_connection.executemany(
        """
        INSERT INTO cardmarket_prices (
            product_id, tcg_dex_id, card_name, expansion_name, language,
            trend_price_cents, avg1_price_cents, avg7_price_cents, avg30_price_cents,
            currency, fetched_at, name_base
        ) VALUES (?, ?, ?, ?, 'en', ?, ?, ?, ?, 'EUR', ?, ?)
        """,
        [
            (101, "sv03-125", "Charizard ex", "Obsidian Flames", 1400, 1600, 1500, 1000, now_iso, "charizard ex"),
            (102, None, "Pikachu", "151", 900, 750, 800, 1000, now_iso, "pikachu"),
            (103, None, "Mew", "151", 500, 500, 500, 0, now_iso, "mew"),
            (104, None, "Eevee", "151", 300, 300, None, 250, now_iso, "eevee"),
        ],
    )
    db_connection.commit()

    # Test période 7/30
    movements = get_price_movements(db_connection, period="7_30")
    hausses, baisses, total = movements.hausses, movements.baisses, movements.total_compared
    assert total == 2
    assert len(hausses) == 1
    assert len(baisses) == 1
    assert movements.hausses_total == 1
    assert movements.baisses_total == 1

    assert hausses[0].product_id == 101
    assert hausses[0].delta_cents == 500
    assert hausses[0].delta_bps == 5000
    assert hausses[0].match_status == "certifie"
    assert "sv03-125" in hausses[0].attachment_limits

    assert baisses[0].product_id == 102
    assert baisses[0].delta_cents == -200
    assert baisses[0].delta_bps == -2000
    assert baisses[0].match_status in ("partiel", "non_lie")

    # Test période 1/7 (produit 101: avg1=1600, avg7=1500 -> +100 cents, +667 bps)
    movements_1_7 = get_price_movements(db_connection, period="1_7")
    hausses_1_7 = movements_1_7.hausses
    total_1_7 = movements_1_7.total_compared
    assert total_1_7 == 2
    assert len(hausses_1_7) == 1
    assert hausses_1_7[0].product_id == 101
    assert hausses_1_7[0].delta_cents == 100
    assert hausses_1_7[0].delta_bps == 667


# ==============================================================================
# T3.2 : Tests de l'activité des annonces sur 30 jours
# ==============================================================================

def test_listing_activity_exact_30_days_window(db_connection: sqlite3.Connection) -> None:
    now = datetime(2026, 11, 2, 12, 0, 0, tzinfo=UTC)
    card_id = insert_ref_card(
        db_connection,
        tcgdex_id="sv03-025",
        local_id="025",
        name="Pikachu",
        set_id="sv03",
        set_name="Flammes Obsidiennes",
        rarity="Commune",
    )

    # Annonce 1 : vue il y a 10 jours (dans la fenêtre, nouvelle)
    d10 = (now - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    insert_catalog_listing(
        db_connection,
        external_id="pika-10d",
        name="Pikachu",
        set_name="Flammes Obsidiennes",
        reference_card_id=card_id,
        first_seen_at=d10,
        last_seen_at=d10,
        price_cents=500,
    )

    # Annonce 2 : vue la première fois il y a 40 jours, mais observée il y a 5 jours (dans la fenêtre, connue avant)
    d40 = (now - timedelta(days=40)).strftime("%Y-%m-%dT%H:%M:%SZ")
    d5 = (now - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    insert_catalog_listing(
        db_connection,
        external_id="pika-known",
        name="Pikachu",
        set_name="Flammes Obsidiennes",
        reference_card_id=card_id,
        first_seen_at=d40,
        last_seen_at=d5,
        price_cents=700,
    )

    # Annonce 3 : dernière vue il y a 35 jours (hors de la fenêtre 30 jours)
    d35 = (now - timedelta(days=35)).strftime("%Y-%m-%dT%H:%M:%SZ")
    insert_catalog_listing(
        db_connection,
        external_id="pika-old",
        name="Pikachu",
        set_name="Flammes Obsidiennes",
        reference_card_id=card_id,
        first_seen_at=d40,
        last_seen_at=d35,
        price_cents=900,
    )

    db_connection.commit()

    activity = get_listing_activity(db_connection, now=now, window_days=30)
    assert len(activity.items) == 1
    pika_stat = activity.items[0]
    assert activity.total == 1
    assert pika_stat.reference_card_id == card_id
    assert pika_stat.card_name == "Pikachu"
    # 2 annonces observées dans les 30 jours (pika-10d et pika-known)
    assert pika_stat.distinct_listings_count == 2
    # 1 seule nouvelle annonce apparue dans les 30 jours (pika-10d)
    assert pika_stat.new_listings_count == 1
    assert pika_stat.min_price_cents == 500
    assert pika_stat.max_price_cents == 700


def test_listing_activity_reingestion_does_not_duplicate_distinct_count(
    db_connection: sqlite3.Connection,
) -> None:
    now = datetime(2026, 11, 2, 12, 0, 0, tzinfo=UTC)
    card_id = insert_ref_card(
        db_connection,
        tcgdex_id="sv03-006",
        local_id="006",
        name="Dracaufeu",
        set_id="sv03",
        set_name="Flammes Obsidiennes",
    )

    # Création initiale il y a 15 jours
    d15 = (now - timedelta(days=15)).strftime("%Y-%m-%dT%H:%M:%SZ")
    listing_id = insert_catalog_listing(
        db_connection,
        external_id="draco-unique",
        name="Dracaufeu",
        set_name="Flammes Obsidiennes",
        reference_card_id=card_id,
        first_seen_at=d15,
        last_seen_at=d15,
        price_cents=2500,
    )

    # Simulation de plusieurs observations ultérieures de la même annonce dans listing_observations
    d10 = (now - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    d2 = (now - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    db_connection.executemany(
        """
        INSERT INTO listing_observations (listing_id, price_cents, shipping_cents, currency, available, observed_at, origin)
        VALUES (?, ?, ?, 'EUR', 1, ?, 'collecteur')
        """,
        [
            (listing_id, 2400, 0, d10),
            (listing_id, 2300, 0, d2),
        ],
    )
    # Réingestion : actualise last_seen_at sans écraser first_seen_at
    db_connection.execute(
        "UPDATE catalog_items SET last_seen_at = ?, price_cents = 2300 WHERE id = ?",
        (d2, listing_id),
    )
    db_connection.commit()

    activity = get_listing_activity(db_connection, now=now, window_days=30)
    assert len(activity.items) == 1
    # Doit rester 1 seule annonce distincte
    assert activity.items[0].distinct_listings_count == 1
    assert activity.items[0].new_listings_count == 1


def test_listing_activity_excludes_lots_and_ambiguous(
    db_connection: sqlite3.Connection,
) -> None:
    now = datetime(2026, 11, 2, 12, 0, 0, tzinfo=UTC)
    card_id = insert_ref_card(
        db_connection,
        tcgdex_id="sv03-001",
        local_id="001",
        name="Bulbizarre",
        set_id="sv03",
        set_name="Flammes Obsidiennes",
    )
    d5 = (now - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Annonce 1 : lot (doit être exclue)
    insert_catalog_listing(
        db_connection,
        external_id="lot-bulbi",
        name="Bulbizarre",
        set_name="Flammes Obsidiennes",
        reference_card_id=card_id,
        is_lot=1,
        identification_status="lot",
        first_seen_at=d5,
        last_seen_at=d5,
    )
    # Annonce 2 : ambiguë (doit être exclue)
    insert_catalog_listing(
        db_connection,
        external_id="ambiguous-bulbi",
        name="Bulbizarre",
        set_name="Flammes Obsidiennes",
        reference_card_id=card_id,
        is_lot=0,
        identification_status="ambiguous",
        first_seen_at=d5,
        last_seen_at=d5,
    )
    # Annonce 3 : non identifiée (doit être exclue)
    insert_catalog_listing(
        db_connection,
        external_id="unidentified-bulbi",
        name="Bulbizarre",
        set_name="Flammes Obsidiennes",
        reference_card_id=None,
        is_lot=0,
        identification_status="unidentified",
        first_seen_at=d5,
        last_seen_at=d5,
    )

    db_connection.commit()

    activity = get_listing_activity(db_connection, now=now, window_days=30)
    assert len(activity.items) == 0
    assert activity.total == 0


def test_listing_activity_filters_and_threshold(db_connection: sqlite3.Connection) -> None:
    now = datetime(2026, 11, 2, 12, 0, 0, tzinfo=UTC)
    c1 = insert_ref_card(db_connection, tcgdex_id="c1", local_id="1", name="Tortank", set_id="sv1", set_name="Set A", rarity="Rare")
    c2 = insert_ref_card(db_connection, tcgdex_id="c2", local_id="2", name="Florizarre", set_id="sv2", set_name="Set B", rarity="Ultra Rare")

    d5 = (now - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    # Tortank : 2 annonces (français)
    insert_catalog_listing(db_connection, external_id="t1", name="Tortank", set_name="Set A", reference_card_id=c1, language="fr", first_seen_at=d5, last_seen_at=d5)
    insert_catalog_listing(db_connection, external_id="t2", name="Tortank", set_name="Set A", reference_card_id=c1, language="fr", first_seen_at=d5, last_seen_at=d5)
    # Florizarre : 1 annonce (japonais)
    insert_catalog_listing(db_connection, external_id="f1", name="Florizarre", set_name="Set B", reference_card_id=c2, language="ja", first_seen_at=d5, last_seen_at=d5)

    db_connection.commit()

    # Filtre seuil min_observations=2 -> seul Tortank retenu
    act_threshold = get_listing_activity(db_connection, now=now, min_observations=2)
    assert len(act_threshold.items) == 1
    assert act_threshold.items[0].card_name == "Tortank"
    assert act_threshold.total == 1

    # Filtre extension
    act_set = get_listing_activity(db_connection, now=now, set_name="Set B")
    assert len(act_set.items) == 1
    assert act_set.items[0].card_name == "Florizarre"

    # Filtre langue
    act_lang = get_listing_activity(db_connection, now=now, language="ja")
    assert len(act_lang.items) == 1
    assert act_lang.items[0].card_name == "Florizarre"


# ==============================================================================
# T3.3 : Tests des meilleures affaires
# ==============================================================================

def test_best_opportunities_aligned_with_evaluate_listing(db_connection: sqlite3.Connection) -> None:
    now = datetime(2026, 11, 2, 12, 0, 0, tzinfo=UTC)
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    card_id = insert_ref_card(
        db_connection,
        tcgdex_id="sv03-050",
        local_id="050",
        name="Mewtwo",
        set_id="sv03",
        set_name="Flammes Obsidiennes",
    )

    # Référence de marché : 30,00 € (3000 centimes), observée il y a 2 jours
    ref_date = (now - timedelta(days=2)).date()
    upsert_reference(
        db_connection,
        ReferenceInput(
            name="Mewtwo",
            set_name="Flammes Obsidiennes",
            card_number="050",
            language="fr",
            condition="Near Mint",
            reference_price_cents=3000,
            currency="EUR",
            reference_kind="ventes_conclues",
            source_name="Cardmarket Historique",
            observed_at=ref_date,
        ),
    )

    # Annonce active à 10,00 € (1000 centimes)
    listing_id = insert_catalog_listing(
        db_connection,
        external_id="mewtwo-opp",
        name="Mewtwo",
        set_name="Flammes Obsidiennes",
        card_number="050",
        price_cents=1000,
        condition="Near Mint",
        reference_card_id=card_id,
        first_seen_at=now_iso,
        last_seen_at=now_iso,
    )
    db_connection.commit()

    opportunities = get_best_opportunities(db_connection, now=now, max_quote_age_days=30)
    assert len(opportunities.items) == 1
    opp = opportunities.items[0]
    assert opportunities.total == 1

    assert opp.listing_id == listing_id
    assert opp.purchase_price_cents == 1000
    assert opp.estimated_resale_cents == 3000

    # Vérification stricte de l'alignement sur evaluate_listing
    profile = get_active_fee_profile(db_connection)
    from app.profitability import build_market_index
    market_index = build_market_index(db_connection, profile.min_catalog_samples)
    eval_direct = evaluate_listing(
        dict(db_connection.execute("SELECT * FROM catalog_items WHERE id = ?", (listing_id,)).fetchone()),
        profile,
        market_index,
    )
    assert opp.net_profit_cents == eval_direct["net_profit_cents"]
    assert opp.roi_bps == eval_direct["roi_bps"]
    assert opp.verdict == "opportunite"
    assert opp.quote_age_days == 2


def test_best_opportunities_requires_actual_observation_date(db_connection: sqlite3.Connection) -> None:
    """Une saisie récente ne rend pas une cote non datée ou ancienne fraîche."""
    now = datetime.now(UTC)
    card_id = insert_ref_card(
        db_connection, tcgdex_id="test-freshness-1", local_id="1", name="Mew",
        set_id="test-freshness", set_name="Test fraîcheur",
    )
    listing_id = insert_catalog_listing(
        db_connection, external_id="freshness-listing", name="Mew", set_name="Test fraîcheur",
        price_cents=1000, reference_card_id=card_id,
    )
    def save_reference(observed_at: date | None = None) -> None:
        upsert_reference(db_connection, ReferenceInput(
            name="Mew", set_name="Test fraîcheur", reference_price_cents=5000,
            observed_at=observed_at,
        ))

    save_reference()
    assert get_best_opportunities(db_connection, now=now).items == []
    save_reference((now - timedelta(days=45)).date())
    assert get_best_opportunities(db_connection, now=now).items == []
    save_reference((now - timedelta(days=2)).date())
    opportunities = get_best_opportunities(db_connection, now=now)
    assert len(opportunities.items) == 1
    assert opportunities.total == 1
    assert opportunities.items[0].listing_id == listing_id
    assert opportunities.items[0].quote_age_days == 2


def test_best_opportunities_excludes_ineligible_and_expired(db_connection: sqlite3.Connection) -> None:
    now = datetime(2026, 11, 2, 12, 0, 0, tzinfo=UTC)
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    card_id = insert_ref_card(
        db_connection,
        tcgdex_id="sv03-099",
        local_id="099",
        name="Lugia",
        set_id="sv03",
        set_name="Flammes Obsidiennes",
    )

    # Cote expirée : observée il y a 45 jours (> seuil 30 jours)
    old_date = (now - timedelta(days=45)).date()
    upsert_reference(
        db_connection,
        ReferenceInput(
            name="Lugia",
            set_name="Flammes Obsidiennes",
            reference_price_cents=5000,
            currency="EUR",
            reference_kind="ventes_conclues",
            source_name="Vente eBay",
            observed_at=old_date,
        ),
    )

    # 1. Annonce avec cote expirée -> exclue
    insert_catalog_listing(
        db_connection,
        external_id="lugia-expired",
        name="Lugia",
        set_name="Flammes Obsidiennes",
        price_cents=1000,
        reference_card_id=card_id,
        first_seen_at=now_iso,
        last_seen_at=now_iso,
    )

    # 2. Annonce inactive -> exclue
    insert_catalog_listing(
        db_connection,
        external_id="lugia-inactive",
        name="Lugia",
        set_name="Flammes Obsidiennes",
        price_cents=1000,
        is_active=0,
        reference_card_id=card_id,
        first_seen_at=now_iso,
        last_seen_at=now_iso,
    )

    # 3. Lot -> exclu
    insert_catalog_listing(
        db_connection,
        external_id="lugia-lot",
        name="Lugia",
        set_name="Flammes Obsidiennes",
        price_cents=1000,
        is_lot=1,
        identification_status="lot",
        reference_card_id=card_id,
        first_seen_at=now_iso,
        last_seen_at=now_iso,
    )

    # 4. Non identifiée -> exclue
    insert_catalog_listing(
        db_connection,
        external_id="lugia-unident",
        name="Lugia",
        set_name="Flammes Obsidiennes",
        price_cents=1000,
        identification_status="unidentified",
        reference_card_id=None,
        first_seen_at=now_iso,
        last_seen_at=now_iso,
    )

    db_connection.commit()

    opps = get_best_opportunities(db_connection, now=now, max_quote_age_days=30)
    assert len(opps.items) == 0
    assert opps.total == 0


def test_best_opportunities_ranking_and_tie_breaking(db_connection: sqlite3.Connection) -> None:
    now = datetime(2026, 11, 2, 12, 0, 0, tzinfo=UTC)
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    ref_date = now.date()

    c1 = insert_ref_card(db_connection, tcgdex_id="rk-1", local_id="1", name="Rayquaza", set_id="s1", set_name="Set")
    c2 = insert_ref_card(db_connection, tcgdex_id="rk-2", local_id="2", name="Gengar", set_id="s1", set_name="Set")

    upsert_reference(
        db_connection,
        ReferenceInput(name="Rayquaza", set_name="Set", reference_price_cents=10000, observed_at=ref_date),
    )
    upsert_reference(
        db_connection,
        ReferenceInput(name="Gengar", set_name="Set", reference_price_cents=5000, observed_at=ref_date),
    )

    # Rayquaza : Achat 20€ -> Revente 100€ (Gros gain net)
    id1 = insert_catalog_listing(db_connection, external_id="r1", name="Rayquaza", set_name="Set", price_cents=2000, reference_card_id=c1, first_seen_at=now_iso)
    # Gengar : Achat 10€ -> Revente 50€ (Gain net inférieur à Rayquaza)
    id2 = insert_catalog_listing(db_connection, external_id="g1", name="Gengar", set_name="Set", price_cents=1000, reference_card_id=c2, first_seen_at=now_iso)

    db_connection.commit()

    opps = get_best_opportunities(db_connection, now=now, max_quote_age_days=30)
    assert len(opps.items) == 2
    assert opps.total == 2
    # Tri 1 : gain net décroissant
    assert opps.items[0].listing_id == id1
    assert opps.items[1].listing_id == id2
    assert opps.items[0].net_profit_cents > opps.items[1].net_profit_cents


def test_best_opportunities_excludes_watch_verdict(db_connection: sqlite3.Connection) -> None:
    now = datetime(2026, 11, 2, 12, 0, 0, tzinfo=UTC)
    configure_fees(db_connection, min_net_profit_cents=5000)
    card_id = insert_ref_card(
        db_connection, tcgdex_id="watch-1", local_id="1", name="Mew",
        set_id="watch", set_name="Set Watch",
    )
    upsert_reference(
        db_connection,
        ReferenceInput(
            name="Mew", set_name="Set Watch", reference_price_cents=3000,
            observed_at=now.date(),
        ),
    )
    insert_catalog_listing(
        db_connection, external_id="watch-positive", name="Mew", set_name="Set Watch",
        price_cents=1000, reference_card_id=card_id,
        first_seen_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    db_connection.commit()

    assert get_best_opportunities(db_connection, now=now).items == []


def test_best_opportunities_uses_comparable_dates_for_catalog_median(
    db_connection: sqlite3.Connection,
) -> None:
    now = datetime(2026, 11, 2, 12, 0, 0, tzinfo=UTC)
    fresh = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    stale = (now - timedelta(days=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
    card_id = insert_ref_card(
        db_connection, tcgdex_id="median-1", local_id="1", name="Alakazam",
        set_id="median", set_name="Set Median",
    )
    insert_catalog_listing(
        db_connection, external_id="median-current", name="Alakazam", set_name="Set Median",
        price_cents=1000, reference_card_id=card_id, first_seen_at=fresh, last_seen_at=fresh,
    )
    for index in range(2):
        insert_catalog_listing(
            db_connection, external_id=f"median-old-{index}", name="Alakazam",
            set_name="Set Median", price_cents=3000, reference_card_id=card_id,
            first_seen_at=stale, last_seen_at=stale,
        )
    db_connection.commit()

    assert get_best_opportunities(db_connection, now=now, max_quote_age_days=30).items == []


# ==============================================================================
# Pagination des tendances : consultation au-delà du classement limité
# ==============================================================================

def test_price_movements_pagination_keeps_stable_order(
    db_connection: sqlite3.Connection,
) -> None:
    now_iso = "2026-11-01T10:00:00Z"
    # 5 hausses aux variations croissantes (avg30 constant à 1000) :
    # tri attendu par delta_bps décroissant -> produits 204, 203, 202, 201, 200.
    db_connection.executemany(
        """
        INSERT INTO cardmarket_prices (
            product_id, tcg_dex_id, card_name, expansion_name, language,
            trend_price_cents, avg1_price_cents, avg7_price_cents, avg30_price_cents,
            currency, fetched_at, name_base
        ) VALUES (?, NULL, ?, 'Set Pag', 'en', ?, ?, ?, 1000, 'EUR', ?, ?)
        """,
        [
            (200 + i, f"Pag {i}", 1000 + 100 * (i + 1), 1000 + 100 * (i + 1), 1000 + 100 * (i + 1), now_iso, f"pag {i}")
            for i in range(5)
        ],
    )
    db_connection.commit()

    full = get_price_movements(db_connection, limit=100)
    assert full.hausses_total == 5
    full_order = [item.product_id for item in full.hausses]
    assert full_order == [204, 203, 202, 201, 200]

    page_1 = get_price_movements(db_connection, limit=2, offset=0)
    page_2 = get_price_movements(db_connection, limit=2, offset=2)
    page_3 = get_price_movements(db_connection, limit=2, offset=4)

    assert page_1.hausses_total == 5
    assert [item.product_id for item in page_1.hausses] == [204, 203]
    assert [item.product_id for item in page_2.hausses] == [202, 201]
    assert [item.product_id for item in page_3.hausses] == [200]
    # Concaténation des pages = ordre complet, sans doublon ni écart.
    assert (
        [item.product_id for item in page_1.hausses + page_2.hausses + page_3.hausses]
        == full_order
    )


def test_listing_activity_pagination_and_total(
    db_connection: sqlite3.Connection,
) -> None:
    now = datetime(2026, 11, 2, 12, 0, 0, tzinfo=UTC)
    d5 = (now - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    cards = [
        insert_ref_card(
            db_connection,
            tcgdex_id=f"pag-{n}",
            local_id=str(n),
            name=f"Carte {n}",
            set_id="pag",
            set_name="Set Pag",
        )
        for n in range(3)
    ]
    # Carte 0 : 3 annonces, Carte 1 : 2, Carte 2 : 1.
    for card_index, count in enumerate((3, 2, 1)):
        for j in range(count):
            insert_catalog_listing(
                db_connection,
                external_id=f"pag-{card_index}-{j}",
                name=f"Carte {card_index}",
                set_name="Set Pag",
                reference_card_id=cards[card_index],
                first_seen_at=d5,
                last_seen_at=d5,
            )
    db_connection.commit()

    full = get_listing_activity(db_connection, now=now, limit=10)
    assert full.total == 3

    page_1 = get_listing_activity(db_connection, now=now, limit=2, offset=0)
    page_2 = get_listing_activity(db_connection, now=now, limit=2, offset=2)
    assert page_1.total == 3
    assert page_2.total == 3
    assert [item.reference_card_id for item in page_1.items] == [cards[0], cards[1]]
    assert [item.reference_card_id for item in page_2.items] == [cards[2]]
    assert (
        [item.reference_card_id for item in page_1.items + page_2.items]
        == [item.reference_card_id for item in full.items]
    )


def test_best_opportunities_pagination_and_total(
    db_connection: sqlite3.Connection,
) -> None:
    now = datetime(2026, 11, 2, 12, 0, 0, tzinfo=UTC)
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    ref_date = now.date()

    cards = [
        insert_ref_card(
            db_connection,
            tcgdex_id=f"opp-pag-{n}",
            local_id=str(n),
            name=f"Carte {n}",
            set_id="opp-pag",
            set_name="Set Pag",
        )
        for n in range(3)
    ]
    for n, ref_price in enumerate((3000, 5000, 4000)):
        upsert_reference(
            db_connection,
            ReferenceInput(
                name=f"Carte {n}",
                set_name="Set Pag",
                reference_price_cents=ref_price,
                observed_at=ref_date,
            ),
        )
    # Gains nets bruts décroissants : Carte 1 (5000-2000) > Carte 2 (4000-1500) > Carte 0 (3000-1000).
    listing_ids = []
    for n, buy_price in enumerate((1000, 2000, 1500)):
        listing_ids.append(
            insert_catalog_listing(
                db_connection,
                external_id=f"opp-pag-{n}",
                name=f"Carte {n}",
                set_name="Set Pag",
                price_cents=buy_price,
                reference_card_id=cards[n],
                first_seen_at=now_iso,
                last_seen_at=now_iso,
            )
        )
    db_connection.commit()

    full = get_best_opportunities(db_connection, now=now, limit=10)
    assert full.total == 3
    full_order = [item.listing_id for item in full.items]
    assert full_order == [listing_ids[1], listing_ids[2], listing_ids[0]]

    page_1 = get_best_opportunities(db_connection, now=now, limit=2, offset=0)
    page_2 = get_best_opportunities(db_connection, now=now, limit=2, offset=2)
    assert page_1.total == 3
    assert [item.listing_id for item in page_1.items] == [listing_ids[1], listing_ids[2]]
    assert [item.listing_id for item in page_2.items] == [listing_ids[0]]
    assert (
        [item.listing_id for item in page_1.items + page_2.items]
        == full_order
    )


# ==============================================================================
# T3.4 : Tests de l'interface /trends et des routes web
# ==============================================================================

@pytest.fixture
def test_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db_file = tmp_path / "web_trends.db"
    monkeypatch.setenv("POKEMON_DATABASE_PATH", str(db_file))
    with connect(db_file) as conn:
        apply_migrations(conn)
        configure_fees(conn)
    with TestClient(app) as client:
        yield client


def test_trends_page_empty_state(test_client: TestClient) -> None:
    response = test_client.get("/trends")
    assert response.status_code == 200
    assert "Tendances de prix &amp; activité" in response.text or "Tendances de prix & activité" in response.text
    assert "Aucune donnée de tendance disponible" in response.text
    # Lien de navigation "Tendances" présent et actif
    assert 'href="/trends"' in response.text
    assert "active" in response.text


def test_trends_page_with_data_and_filters(test_client: TestClient, tmp_path: Path) -> None:
    db_file = tmp_path / "web_trends.db"
    now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    with connect(db_file) as conn:
        # Donnée Cardmarket
        conn.execute(
            """
            INSERT INTO cardmarket_prices (
                product_id, card_name, expansion_name, language,
                avg1_price_cents, avg7_price_cents, avg30_price_cents, currency, fetched_at, name_base
            ) VALUES (555, 'Pikachu V', 'Voltage', 'en', 1200, 1000, 800, 'EUR', ?, 'pikachu v')
            """,
            (now_iso,),
        )
        # Carte et annonce
        cid = insert_ref_card(conn, tcgdex_id="swsh-025", local_id="025", name="Pikachu V", set_id="swsh4", set_name="Voltage")
        insert_catalog_listing(conn, external_id="pika-v-1", name="Pikachu V", set_name="Voltage", price_cents=400, reference_card_id=cid)
        # Cote de référence pour meilleure affaire
        upsert_reference(
            conn,
            ReferenceInput(name="Pikachu V", set_name="Voltage", reference_price_cents=1200, observed_at=datetime.now(UTC).date()),
        )
        conn.commit()

    # Appel de la page /trends
    resp = test_client.get("/trends")
    assert resp.status_code == 200
    assert "Plus fortes hausses de prix" in resp.text
    assert "Pikachu V" in resp.text
    assert "Activité des annonces" in resp.text
    assert "Meilleures affaires actuellement disponibles" in resp.text
    # Une synchronisation manuelle du guide renseigne fetched_at sans passer
    # par l'état de la synchronisation quotidienne complète.
    assert "Données Cardmarket récupérées" in resp.text
    assert "Cardmarket non synchronisé" not in resp.text
    # Vérification de l'absence de toute métrique inventée de vente
    assert "ventes conclues par pays" not in resp.text.casefold()
    assert "cartes vendues sur 30 jours" not in resp.text.casefold()

    # Test avec filtre d'extension
    resp_filtered = test_client.get("/trends", params={"set_name": "Voltage"})
    assert resp_filtered.status_code == 200
    assert "Pikachu V" in resp_filtered.text

    # Test avec filtre période 1/7
    resp_1_7 = test_client.get("/trends", params={"period": "1_7"})
    assert resp_1_7.status_code == 200


def test_trends_page_pagination_preserves_filters(
    test_client: TestClient, tmp_path: Path
) -> None:
    db_file = tmp_path / "web_trends.db"
    now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    with connect(db_file) as conn:
        # 3 hausses aux variations distinctes : tri attendu B (+3000 bps), A (+2000), C (+1000).
        conn.executemany(
            """
            INSERT INTO cardmarket_prices (
                product_id, card_name, expansion_name, language,
                avg1_price_cents, avg7_price_cents, avg30_price_cents, currency, fetched_at, name_base
            ) VALUES (?, ?, 'PagSet', 'en', ?, ?, 1000, 'EUR', ?, ?)
            """,
            [
                (1, "Pag A", 1200, 1200, now_iso, "pag a"),
                (2, "Pag B", 1300, 1300, now_iso, "pag b"),
                (3, "Pag C", 1100, 1100, now_iso, "pag c"),
            ],
        )
        conn.commit()

    # Page 1 : première hausse (Pag B) + navigation de pagination présente.
    resp = test_client.get("/trends", params={"limit": 1})
    assert resp.status_code == 200
    assert "Pag B" in resp.text
    assert 'aria-label="Pages des hausses de prix"' in resp.text
    assert "page=2" in resp.text

    # Page 2 : la hausse suivante dans l'ordre stable (Pag A), sans Pag B.
    resp_page_2 = test_client.get("/trends", params={"limit": 1, "page": 2})
    assert resp_page_2.status_code == 200
    assert "Pag A" in resp_page_2.text
    assert "Pag B" not in resp_page_2.text

    # Les liens de pagination conservent les filtres actifs.
    resp_filtered = test_client.get(
        "/trends", params={"limit": 1, "set_name": "PagSet"}
    )
    assert resp_filtered.status_code == 200
    assert "Pag B" in resp_filtered.text
    assert 'aria-label="Pages des hausses de prix"' in resp_filtered.text
    assert "set_name=PagSet" in resp_filtered.text
    assert "page=2" in resp_filtered.text
