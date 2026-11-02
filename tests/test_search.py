import sqlite3
from pathlib import Path
from typing import Any
import pytest

from app.search.models import (
    CARD_SORTS,
    DEFAULT_CARD_SORT,
    DEFAULT_LISTING_SORT,
    LISTING_SORTS,
    SearchFilters,
)
from app.search.service import (
    build_search_csv,
    get_search_filter_options,
    search_all,
    search_catalog_listings,
    search_listings_export_rows,
    search_reference_cards,
)
from app.storage.database import connect
from app.storage.migration_runner import apply_migrations
from app.tcgdex.cache import TcgdexCache


@pytest.fixture
def memory_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    apply_migrations(conn)
    cache = TcgdexCache(conn)
    cache.seed_initial_if_empty()

    # Création d'une source pour les annonces de test
    conn.execute(
        "INSERT INTO sources (id, name, kind, enabled) VALUES (1, 'vinted', 'api', 1)"
    )
    conn.execute(
        "INSERT INTO sources (id, name, kind, enabled) VALUES (2, 'leboncoin', 'api', 1)"
    )
    conn.execute(
        "INSERT INTO sources (id, name, kind, enabled) VALUES (3, 'import-web', 'manual_jsonl', 1)"
    )
    conn.execute(
        "INSERT INTO import_batches (id, source_id, input_checksum, status) VALUES (1, 1, 'dummy', 'completed')"
    )

    # Récupération de l'ID d'une carte de référence existante (ex: Pikachu de base1)
    pikachu_row = conn.execute(
        "SELECT id FROM pokemon_reference_cards WHERE tcgdex_id = 'base1-58'"
    ).fetchone()
    pikachu_ref_id = pikachu_row["id"] if pikachu_row else 1

    # Insertion d'annonces de test
    # 1. Annonce identifiée Pikachu
    conn.execute(
        """
        INSERT INTO catalog_items (
            id, source_id, import_batch_id, external_id, name, set_name, card_number, language,
            condition, variant, edition, grading_company, grade, price_cents,
            currency, seller, identification_status, reference_card_id, is_lot
        ) VALUES (
            1, 1, 1, 'v-101', 'Pikachu 58/102', 'Set de Base', '58', 'fr',
            'Near Mint', 'Holo', '1ère édition', 'PSA', '9', 2500,
            'EUR', 'SellerPika', 'identified', ?, 0
        )
        """,
        (pikachu_ref_id,),
    )

    # 2. Annonce non identifiée (pas de reference_card_id, rareté et année inconnues)
    conn.execute(
        """
        INSERT INTO catalog_items (
            id, source_id, import_batch_id, external_id, name, set_name, card_number, language,
            condition, variant, edition, grading_company, grade, price_cents,
            currency, seller, identification_status, reference_card_id, is_lot
        ) VALUES (
            2, 2, 1, 'lbc-202', 'Carte Pikachu ancienne', 'Set Inconnu', NULL, 'fr',
            'Bon état', NULL, NULL, NULL, NULL, 1500,
            'EUR', 'SellerLbc', 'unidentified', NULL, 0
        )
        """
    )

    # 3. Lot de cartes (is_lot = 1, statut lot)
    conn.execute(
        """
        INSERT INTO catalog_items (
            id, source_id, import_batch_id, external_id, name, set_name, card_number, language,
            condition, variant, edition, grading_company, grade, price_cents,
            currency, seller, identification_status, reference_card_id, is_lot
        ) VALUES (
            3, 1, 1, 'v-303', 'Lot de 50 cartes Pokémon Set de Base', 'Set de Base', NULL, 'fr',
            'État moyen', NULL, NULL, NULL, NULL, 5000,
            'EUR', 'SellerLot', 'lot', NULL, 1
        )
        """
    )

    # 4. Annonce ambiguë
    conn.execute(
        """
        INSERT INTO catalog_items (
            id, source_id, import_batch_id, external_id, name, set_name, card_number, language,
            condition, variant, edition, grading_company, grade, price_cents,
            currency, seller, identification_status, reference_card_id, is_lot
        ) VALUES (
            4, 3, 1, 'man-404', 'Dracaufeu', 'Set Inconnu', '4', 'en',
            'Near Mint', NULL, NULL, 'PCA', '8', 12000,
            'EUR', 'SellerImport', 'ambiguous', NULL, 0
        )
        """
    )

    conn.commit()
    return conn


def test_search_filters_validation_ranges() -> None:
    # Test années invalides
    with pytest.raises(ValueError, match="année minimale ne peut pas être supérieure"):
        SearchFilters(year_min=2024, year_max=2020)

    # Test prix invalides
    with pytest.raises(ValueError, match="prix minimal ne peut pas être supérieur"):
        SearchFilters(price_min_cents=5000, price_max_cents=1000)

    # Test valeurs valides
    filters = SearchFilters(year_min=1999, year_max=2024, price_min_cents=100, price_max_cents=5000)
    assert filters.year_min == 1999
    assert filters.year_max == 2024
    assert filters.price_min_cents == 100
    assert filters.price_max_cents == 5000


def test_search_filters_normalization() -> None:
    # Normalisation des chaînes et conversion des vides en None / defauts
    filters = SearchFilters(
        q="  Dracaufeu  ",
        scope="unknown_scope",
        year_min="2000",
        year_max="",
        price_min_cents="1000",
        price_max_cents=None,
        lot_filter="invalid_lot",
        source="invalid_source",
        ident_status="invalid_ident",
    )
    assert filters.q == "Dracaufeu"
    assert filters.scope == "all"
    assert filters.year_min == 2000
    assert filters.year_max is None
    assert filters.price_min_cents == 1000
    assert filters.price_max_cents is None
    assert filters.lot_filter == "all"
    assert filters.source == "all"
    assert filters.ident_status == "all"
    assert filters.sort == "relevance"


def test_search_filters_sort_whitelist() -> None:
    # Pour scope cards
    f_cards = SearchFilters(scope="cards", sort="invalid_sort")
    assert f_cards.sort == "name_asc"  # pas de q, donc name_asc

    f_cards_q = SearchFilters(scope="cards", q="Pikachu", sort="invalid_sort")
    assert f_cards_q.sort == DEFAULT_CARD_SORT

    # Pour scope listings
    f_list = SearchFilters(scope="listings", sort="invalid_sort")
    assert f_list.sort == "import_desc"

    f_list_q = SearchFilters(scope="listings", q="Pikachu", sort="invalid_sort")
    assert f_list_q.sort == DEFAULT_LISTING_SORT


def test_search_filters_to_query_params() -> None:
    filters = SearchFilters(
        q="Pikachu",
        scope="listings",
        set_name="Set de Base",
        year_min=1999,
        year_max=2000,
        rarity="Commune",
        condition="Near Mint",
        price_min_cents=500,
        price_max_cents=3000,
        ident_status="identified",
        lot_filter="exclude",
        sort="price_asc",
        page=2,
    )
    params = filters.to_query_params()
    assert params["q"] == "Pikachu"
    assert params["scope"] == "listings"
    assert params["set_name"] == "Set de Base"
    assert params["year_min"] == "1999"
    assert params["year_max"] == "2000"
    assert params["rarity"] == "Commune"
    assert params["condition"] == "Near Mint"
    assert params["price_min"] == "5.00"
    assert params["price_max"] == "30.00"
    assert params["ident_status"] == "identified"
    assert params["lot_filter"] == "exclude"
    assert params["sort"] == "price_asc"
    assert params["page"] == "2"


def test_search_reference_cards_exact_and_filters(memory_db: sqlite3.Connection) -> None:
    # Recherche exacte de Pikachu
    filters = SearchFilters(q="Pikachu", scope="cards")
    res = search_reference_cards(memory_db, filters)
    assert res.total >= 1
    assert not res.is_approximate
    assert any("pikachu" in item.name.lower() for item in res.items)

    # Filtre par extension et rareté
    f_filtered = SearchFilters(set_name="Set de Base", rarity="Commune", scope="cards")
    res_filtered = search_reference_cards(memory_db, f_filtered)
    assert res_filtered.total >= 1
    for item in res_filtered.items:
        assert item.set_name == "Set de Base"
        assert item.rarity == "Commune"

    # Filtre par année (Set de Base sorti en 1999)
    f_year = SearchFilters(set_name="Set de Base", year_min=1998, year_max=2000, scope="cards")
    res_year = search_reference_cards(memory_db, f_year)
    assert res_year.total >= 1
    assert res_year.items[0].release_year == 1999

    # Année hors intervalle -> 0 résultat
    f_no_year = SearchFilters(set_name="Set de Base", year_min=2010, year_max=2020, scope="cards")
    res_no_year = search_reference_cards(memory_db, f_no_year)
    assert res_no_year.total == 0


def test_search_reference_cards_approximate(memory_db: sqlite3.Connection) -> None:
    # Recherche avec faute de frappe "Dracofeu" au lieu de "Dracaufeu"
    filters = SearchFilters(q="Dracofeu", scope="cards")
    res = search_reference_cards(memory_db, filters)
    assert res.is_approximate
    assert res.total >= 1
    assert any("dracaufeu" in item.name.lower() for item in res.items)


def test_search_reference_cards_unknown_attributes(memory_db: sqlite3.Connection) -> None:
    # Si une carte n'a pas de rareté ou de date, les champs sont bien None
    filters = SearchFilters(q="Pikachu", scope="cards")
    res = search_reference_cards(memory_db, filters)
    # Vérifie que les objets retournés ont bien des attributs sérialisables et non inventés
    for item in res.items:
        assert isinstance(item.name, str)
        assert item.release_year is None or isinstance(item.release_year, int)


def test_search_catalog_listings_text_and_ident(memory_db: sqlite3.Connection) -> None:
    # Recherche textuelle "Pikachu"
    filters = SearchFilters(q="Pikachu", scope="listings")
    res = search_catalog_listings(memory_db, filters)
    # Doit trouver l'annonce identifiée et l'annonce non identifiée
    ids = {item.id for item in res.items}
    assert 1 in ids
    assert 2 in ids

    # Filtre par statut d'identification "identified"
    f_ident = SearchFilters(q="Pikachu", ident_status="identified", scope="listings")
    res_ident = search_catalog_listings(memory_db, f_ident)
    assert res_ident.total == 1
    assert res_ident.items[0].id == 1


def test_search_catalog_listings_rarity_and_year_rule(memory_db: sqlite3.Connection) -> None:
    # RÈGLE D'OR : Rareté et Année ne s'appliquent qu'aux cartes identifiées via reference_card_id
    # L'annonce 2 (non identifiée) ne doit JAMAIS matcher un filtre de rareté, même si son titre contient Pikachu
    f_rarity = SearchFilters(rarity="Commune", scope="listings")
    res_rarity = search_catalog_listings(memory_db, f_rarity)
    found_ids = {item.id for item in res_rarity.items}
    assert 1 in found_ids  # Annonce identifiée rattachée à Pikachu (Commune)
    assert 2 not in found_ids  # Annonce non identifiée exclue du filtre rareté

    # Même règle pour l'année
    f_year = SearchFilters(year_min=1998, year_max=2000, scope="listings")
    res_year = search_catalog_listings(memory_db, f_year)
    year_ids = {item.id for item in res_year.items}
    assert 1 in year_ids
    assert 2 not in year_ids


def test_search_catalog_listings_lot_filter(memory_db: sqlite3.Connection) -> None:
    # 1. Exclure les lots
    f_exclude = SearchFilters(lot_filter="exclude", scope="listings")
    res_exclude = search_catalog_listings(memory_db, f_exclude)
    assert all(item.is_lot == 0 for item in res_exclude.items)
    assert 3 not in {item.id for item in res_exclude.items}

    # 2. Uniquement les lots
    f_only = SearchFilters(lot_filter="only", scope="listings")
    res_only = search_catalog_listings(memory_db, f_only)
    assert res_only.total == 1
    assert res_only.items[0].id == 3
    assert res_only.items[0].is_lot == 1

    # 3. Tous les lots inclus
    f_all = SearchFilters(lot_filter="all", scope="listings")
    res_all = search_catalog_listings(memory_db, f_all)
    all_ids = {item.id for item in res_all.items}
    assert 3 in all_ids


def test_search_catalog_listings_price_and_condition_filters(memory_db: sqlite3.Connection) -> None:
    # Filtre prix : 1000 à 2000 cents (10 à 20 €) -> Annonce 2 (1500 cents)
    f_price = SearchFilters(price_min_cents=1000, price_max_cents=2000, scope="listings")
    res_price = search_catalog_listings(memory_db, f_price)
    assert res_price.total == 1
    assert res_price.items[0].id == 2

    # Filtre condition et langue
    f_cond = SearchFilters(condition="Near Mint", language="fr", scope="listings")
    res_cond = search_catalog_listings(memory_db, f_cond)
    assert res_cond.total == 1
    assert res_cond.items[0].id == 1

    # Filtre gradation
    f_grade = SearchFilters(grading_company="PSA", grade="9", scope="listings")
    res_grade = search_catalog_listings(memory_db, f_grade)
    assert res_grade.total == 1
    assert res_grade.items[0].id == 1


def test_search_catalog_listings_sources(memory_db: sqlite3.Connection) -> None:
    # Source Vinted
    f_vinted = SearchFilters(source="vinted", scope="listings")
    res_vinted = search_catalog_listings(memory_db, f_vinted)
    assert all(item.source_name == "vinted" for item in res_vinted.items)

    # Source manuelle
    f_manual = SearchFilters(source="manual", scope="listings")
    res_manual = search_catalog_listings(memory_db, f_manual)
    assert res_manual.total == 1
    assert res_manual.items[0].id == 4


def test_search_all_combined(memory_db: sqlite3.Connection) -> None:
    filters = SearchFilters(q="Pikachu", scope="all")
    res = search_all(memory_db, filters)
    assert res.cards is not None
    assert res.listings is not None
    assert res.cards.total >= 1
    assert res.listings.total >= 2


def test_search_export_csv(memory_db: sqlite3.Connection) -> None:
    filters = SearchFilters(q="Pikachu", scope="listings")
    rows = search_listings_export_rows(memory_db, filters)
    assert len(rows) == 2

    csv_bytes = build_search_csv(rows)
    # Vérification BOM UTF-8
    assert csv_bytes.startswith(b"\xef\xbb\xbf")
    csv_text = csv_bytes.decode("utf-8-sig")

    # Vérification des colonnes
    assert "Identifiant interne" in csv_text
    assert "Statut d'identification" in csv_text
    assert "Lot (1=oui, 0=non)" in csv_text
    assert "ID TCGdex officiel" in csv_text
    assert "Pikachu" in csv_text
    assert "SellerPika" in csv_text

    # Vérification RGPD : aucune mention d'email ou tel
    assert "@" not in csv_text or csv_text.count("@") == 0


def test_search_filter_options(memory_db: sqlite3.Connection) -> None:
    options = get_search_filter_options(memory_db)
    assert "Set de Base" in options["sets"]
    assert "Commune" in options["rarities"]
    assert "Near Mint" in options["conditions"]
    assert "fr" in options["languages"]
    assert "PSA" in options["grading_companies"]


def test_web_search_initial_page(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient
    from app.web import app

    db_path = tmp_path / "test_search_web.db"
    monkeypatch.setenv("POKEMON_DATABASE_PATH", str(db_path))

    with TestClient(app) as client:
        # Page initiale sans requête
        response = client.get("/search")
        assert response.status_code == 200
        assert "Recherche" in response.text
        assert "Recherche multi-critères" in response.text
        # Vérification du lien de navigation
        assert 'href="/search"' in response.text
        assert "Recherche" in response.text


def test_web_search_with_query_and_results(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient
    from app.web import app

    db_path = tmp_path / "test_search_web.db"
    monkeypatch.setenv("POKEMON_DATABASE_PATH", str(db_path))

    with TestClient(app) as client:
        # Import d'une annonce
        client.post(
            "/imports",
            files={
                "file": (
                    "test.jsonl",
                    b'{"external_id":"s-01","name":"Pikachu","set_name":"Set de Base","price_cents":1000,"currency":"EUR"}\n',
                    "text/plain",
                )
            },
        )

        response = client.get("/search?q=Pikachu&scope=all")
        assert response.status_code == 200
        assert "Pikachu" in response.text
        assert "Cartes du référentiel officiel" in response.text
        assert "Annonces observées" in response.text
        assert "Exporter les annonces (CSV)" in response.text

        # Un formulaire HTML transmet aussi les champs facultatifs vides.
        form_response = client.get(
            "/search", params={"q": "Pikachu", "scope": "all", "year_min": "", "year_max": ""}
        )
        assert form_response.status_code == 200
        assert "Cartes du référentiel officiel" in form_response.text
        assert "Annonces observées" in form_response.text

        export = client.get(
            "/search/export.csv", params={"q": "Pikachu", "year_min": "", "year_max": ""}
        )
        assert export.status_code == 200
        assert "Pikachu" in export.text


def test_web_search_validation_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient
    from app.web import app

    db_path = tmp_path / "test_search_web.db"
    monkeypatch.setenv("POKEMON_DATABASE_PATH", str(db_path))

    with TestClient(app) as client:
        # Test prix min > prix max
        res_price = client.get("/search?price_min=50&price_max=10")
        assert res_price.status_code == 200
        assert "Critères invalides" in res_price.text
        assert "prix minimal ne peut pas être supérieur" in res_price.text

        # Test années min > max
        res_year = client.get("/search?year_min=2024&year_max=2020")
        assert res_year.status_code == 200
        assert "Critères invalides" in res_year.text
        assert "année minimale ne peut pas être supérieure" in res_year.text


def test_web_search_html_escaping(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient
    from app.web import app

    db_path = tmp_path / "test_search_web.db"
    monkeypatch.setenv("POKEMON_DATABASE_PATH", str(db_path))

    with TestClient(app) as client:
        # Injection XSS dans q
        xss = '<script>alert("xss")</script>'
        res = client.get(f"/search?q={xss}")
        assert res.status_code == 200
        # Vérification qu'il est bien échappé en entités HTML
        assert "<script>" not in res.text
        assert "&lt;script&gt;alert" in res.text or "&#34;xss&#34;" in res.text or "&quot;xss&quot;" in res.text


def test_web_search_export_csv_endpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient
    from app.web import app

    db_path = tmp_path / "test_search_web.db"
    monkeypatch.setenv("POKEMON_DATABASE_PATH", str(db_path))

    with TestClient(app) as client:
        # Import d'une annonce
        client.post(
            "/imports",
            files={
                "file": (
                    "test.jsonl",
                    b'{"external_id":"s-02","name":"Mewtwo","set_name":"Set de Base","price_cents":4500,"currency":"EUR","seller":"SellerMew"}\n',
                    "text/plain",
                )
            },
        )

        res = client.get("/search/export.csv?q=Mewtwo")
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/csv")
        assert "pokebourse-recherche.csv" in res.headers["content-disposition"]
        content = res.content.decode("utf-8-sig")
        assert "Mewtwo" in content
        assert "SellerMew" in content
        assert "Statut d'identification" in content


def test_search_page_beyond_last_returns_last_page_items(memory_db: sqlite3.Connection) -> None:
    cards = search_reference_cards(memory_db, SearchFilters(scope="cards", page=999, per_page=1))
    assert cards.total > 0
    assert cards.page == cards.total_pages
    assert len(cards.items) == 1

    listings = search_catalog_listings(
        memory_db, SearchFilters(scope="listings", page=999, per_page=1)
    )
    assert listings.total > 0
    assert listings.page == listings.total_pages
    assert len(listings.items) == 1


def test_web_search_export_preserves_price_filters_and_rejects_invalid_ranges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient
    from app.web import app

    db_path = tmp_path / "test_search_export_filters.db"
    monkeypatch.setenv("POKEMON_DATABASE_PATH", str(db_path))

    with TestClient(app) as client:
        client.post(
            "/imports",
            files={
                "file": (
                    "test.jsonl",
                    b'{"external_id":"cheap","name":"Bon prix","set_name":"Set de Base","price_cents":1000,"currency":"EUR"}\n'
                    b'{"external_id":"expensive","name":"Hors prix","set_name":"Set de Base","price_cents":9000,"currency":"EUR"}\n',
                    "text/plain",
                )
            },
        )

        exported = client.get("/search/export.csv?price_min=20.00&price_max=100.00")
        assert exported.status_code == 200
        content = exported.content.decode("utf-8-sig")
        assert "Hors prix" in content
        assert "Bon prix" not in content

        invalid = client.get("/search/export.csv?price_min=50&price_max=10")
        assert invalid.status_code == 400
        assert "Critères d’export invalides" in invalid.text


# ==============================================================================
# TESTS DU LOT 2 — RECHERCHE EXTERNE CONTRÔLÉE
# ==============================================================================

def test_external_search_triggered_only_on_explicit_action(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient
    from app.web import app

    db_path = tmp_path / "test_external_explicit.db"
    monkeypatch.setenv("POKEMON_DATABASE_PATH", str(db_path))

    with TestClient(app) as client:
        # 1. GET /search ordinaire : aucun appel externe
        resp_local = client.get("/search?q=Pikachu")
        assert resp_local.status_code == 200
        assert "Rechercher aussi à l’extérieur" in resp_local.text
        # La section des résultats externes n'est pas affichée
        assert "Recherche externe contrôlée</h2>" not in resp_local.text
        # Suivre le lien affiché reproduit l'action réelle de l'utilisateur.
        import html
        import re
        link = re.search(r'href="([^"]+)">Rechercher aussi à l’extérieur', resp_local.text)
        assert link is not None
        external_url = html.unescape(link.group(1))
        assert "external=1" in external_url

        # 2. Action explicite external=1 : la recherche externe est activée
        # Mock d'eBay pour éviter tout appel réseau réel
        def mock_ebay(params: dict) -> list:
            return [{
                "title": "Pikachu Promo Holo",
                "price": 15.00,
                "url": "https://www.ebay.fr/itm/123456",
                "item_id": "ebay-pika-1",
                "seller": "EbaySeller1",
            }]

        with monkeypatch.context() as m:
            m.setattr("app.search.external.collect_ebay_listings", lambda **kw: type("Res", (), {
                "listings": [type("List", (), {
                    "source": "ebay", "external_id": "ebay-pika-1",
                    "title": "Pikachu Promo Holo", "price_cents": 1500, "currency": "EUR",
                    "shipping_cents": 250, "seller": "EbaySeller1", "seller_external_id": "s1",
                    "url": "https://www.ebay.fr/itm/123456", "image_url": None, "raw_data": {}
                })],
                "invalid_count": 0
            })())
            resp_ext = client.get(external_url)
            assert resp_ext.status_code == 200
            assert "Recherche externe contrôlée</h2>" in resp_ext.text
            assert "Pikachu Promo Holo" in resp_ext.text
            assert "EbaySeller1" in resp_ext.text
            assert "Importer" in resp_ext.text
            assert "Actualiser les résultats externes" in resp_ext.text


def test_external_search_local_resilience_when_external_fails(
    memory_db: sqlite3.Connection,
) -> None:
    from app.search.external import execute_external_search

    # Simulation d'un échec réseau eBay
    def failing_ebay(params: dict) -> list:
        from app.collectors.models import CollectorError
        raise CollectorError("Réseau eBay inaccessible (429 Rate Limited)")

    filters = SearchFilters(q="Pikachu")
    summary = execute_external_search(memory_db, filters, ebay_search_func=failing_ebay)

    # Vérification que l'erreur est isolée sur la source eBay
    ebay_report = summary.sources["ebay"]
    assert ebay_report.status == "error"
    assert "inaccessible" in (ebay_report.error_message or "")

    # Vérification que la recherche locale continue de fonctionner parfaitement
    local_res = search_reference_cards(memory_db, filters)
    assert local_res.total >= 1
    assert any("pikachu" in item.name.lower() for item in local_res.items)


def test_external_search_tcgdex_deduplication_and_worker_completion(
    memory_db: sqlite3.Connection,
) -> None:
    from app.identification.research import claim_search, process_claimed_search
    from app.search.external import execute_external_search
    from app.tcgdex.cache import TcgdexCache

    filters = SearchFilters(q="Pikachu", set_name="Set de Base")

    # 1. Première demande externe
    summary1 = execute_external_search(
        memory_db, filters, ebay_search_func=lambda params: []
    )
    tcgdex1 = summary1.sources["tcgdex"]
    assert tcgdex1.task_id is not None
    assert tcgdex1.status in ("queued", "completed")

    # 2. Deuxième demande identique : déduplication stricte (même task_id)
    summary2 = execute_external_search(
        memory_db, filters, ebay_search_func=lambda params: []
    )
    tcgdex2 = summary2.sources["tcgdex"]
    assert tcgdex2.task_id == tcgdex1.task_id

    # 3. Traitement par le worker via TcgdexClient simulé
    class MockTcgdexClient:
        def search_cards(self, **criteria: Any) -> list:
            return [{
                "id": "base1-58",
                "localId": "58",
                "name": "Pikachu",
                "set": {"id": "base1", "name": "Set de Base"},
                "rarity": "Commune",
                "category": "Pokemon",
            }]

    claimed = claim_search(memory_db)
    if claimed:
        process_claimed_search(memory_db, claimed, MockTcgdexClient())

    # 4. Après exécution du worker, la carte est disponible dans le référentiel
    cache = TcgdexCache(memory_db)
    card = cache.get_card_by_tcgdex_id("base1-58")
    assert card is not None
    assert card.name == "Pikachu"


def test_external_search_unauthorized_sources_displayed_as_unavailable(
    memory_db: sqlite3.Connection,
) -> None:
    from app.search.external import execute_external_search

    filters = SearchFilters(q="Dracaufeu")
    summary = execute_external_search(
        memory_db, filters, ebay_search_func=lambda params: []
    )

    # Vinted et Leboncoin doivent être signalées non disponibles
    vinted_report = summary.sources["vinted"]
    assert not vinted_report.is_available
    assert vinted_report.status == "unavailable"
    assert "CGU Vinted" in (vinted_report.info_message or "")
    assert len(vinted_report.items) == 0

    lbc_report = summary.sources["leboncoin"]
    assert not lbc_report.is_available
    assert lbc_report.status == "unavailable"
    assert "DataDome" in (lbc_report.info_message or "")
    assert len(lbc_report.items) == 0


def test_external_import_new_and_reimport_preserves_first_seen_at(
    memory_db: sqlite3.Connection,
) -> None:
    from app.search.external import ExternalSearchItem, import_external_listing

    item = ExternalSearchItem(
        source="ebay",
        external_id="ebay-ext-999",
        title="Pikachu 58/102 Set de Base",
        price_cents=2000,
        currency="EUR",
        shipping_cents=300,
        seller="TopSeller",
        seller_external_id="ts-99",
        url="https://ebay.fr/itm/999",
        raw_data={"title": "Pikachu 58/102 Set de Base"},
    )

    # 1. Premier import
    listing_id = import_external_listing(memory_db, item)
    row_first = memory_db.execute(
        "SELECT * FROM catalog_items WHERE id = ?", (listing_id,)
    ).fetchone()
    first_seen_at = row_first["first_seen_at"]
    assert first_seen_at is not None
    assert row_first["price_cents"] == 2000
    assert row_first["seller"] == "TopSeller"

    # Vérification de l'observation initiale de prix
    obs_count = memory_db.execute(
        "SELECT COUNT(*) FROM listing_observations WHERE listing_id = ?", (listing_id,)
    ).fetchone()[0]
    assert obs_count == 1

    # 2. Ré-ingestion avec baisse de prix à 1800 cents
    item_updated = ExternalSearchItem(
        source="ebay",
        external_id="ebay-ext-999",
        title="Pikachu 58/102 Set de Base",
        price_cents=1800,
        currency="EUR",
        shipping_cents=300,
        seller="TopSeller",
        seller_external_id="ts-99",
        url="https://ebay.fr/itm/999",
        raw_data={"title": "Pikachu 58/102 Set de Base", "price": 18},
    )
    reimport_id = import_external_listing(memory_db, item_updated)
    assert reimport_id == listing_id

    row_second = memory_db.execute(
        "SELECT * FROM catalog_items WHERE id = ?", (listing_id,)
    ).fetchone()

    # RÈGLE D'OR 5 : first_seen_at NE DOIT JAMAIS ÊTRE ÉCRASÉ
    assert row_second["first_seen_at"] == first_seen_at
    assert row_second["price_cents"] == 1800

    # Une deuxième observation a été enregistrée
    obs_count_after = memory_db.execute(
        "SELECT COUNT(*) FROM listing_observations WHERE listing_id = ?", (listing_id,)
    ).fetchone()[0]
    assert obs_count_after == 2


def test_external_import_rgpd_and_lots(
    memory_db: sqlite3.Connection,
) -> None:
    from app.search.external import ExternalSearchItem, import_external_listing

    # Annonce de lot de cartes
    lot_item = ExternalSearchItem(
        source="ebay",
        external_id="ebay-lot-777",
        title="Lot de 100 cartes Pokémon anciennes",
        price_cents=6500,
        currency="EUR",
        seller="SellerPseudoOnly",
        seller_external_id="seller_777",
        raw_data={"title": "Lot de 100 cartes Pokémon anciennes"},
    )

    listing_id = import_external_listing(memory_db, lot_item)
    row = memory_db.execute(
        "SELECT * FROM catalog_items WHERE id = ?", (listing_id,)
    ).fetchone()

    # RÈGLE D'OR 4 : Règle absolue des lots (is_lot=1 et aucun rattachement unitaire)
    assert row["is_lot"] == 1
    assert row["identification_status"] == "lot"
    assert row["reference_card_id"] is None

    # RÈGLE D'OR 6 : RGPD - seul le pseudo public est conservé, aucune donnée interdite
    assert row["seller"] == "SellerPseudoOnly"
    seller_queue = memory_db.execute(
        "SELECT * FROM seller_enrichment_queue WHERE seller_external_id = 'seller_777'"
    ).fetchone()
    assert seller_queue is not None
    assert seller_queue["platform"] == "ebay"


def test_web_external_import_endpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient
    from app.web import app

    db_path = tmp_path / "test_web_ext_import.db"
    monkeypatch.setenv("POKEMON_DATABASE_PATH", str(db_path))

    with TestClient(app) as client:
        # Import d'une annonce via le endpoint POST
        response = client.post(
            "/search/external/import",
            data={
                "source": "ebay",
                "external_id": "ebay-web-101",
                "title": "Ectoplasma Holo",
                "price_cents": "3500",
                "currency": "EUR",
                "seller": "GhostSeller",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"].startswith("/catalog/")

        # Vérification que l'annonce est accessible dans le catalogue
        catalog_detail = client.get(response.headers["location"])
        assert catalog_detail.status_code == 200
        assert "Ectoplasma" in catalog_detail.text
        assert "GhostSeller" in catalog_detail.text


def test_external_import_rejects_unknown_source(memory_db: sqlite3.Connection) -> None:
    from app.search.external import ExternalSearchItem, import_external_listing

    item = ExternalSearchItem(
        source="tcgdex",
        external_id="base1-58",
        title="Pikachu",
        price_cents=0,
    )
    with pytest.raises(ValueError, match="Seules les annonces eBay"):
        import_external_listing(memory_db, item)


def test_web_external_import_error_is_visible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient
    from app.web import app

    db_path = tmp_path / "test_web_ext_import_error.db"
    monkeypatch.setenv("POKEMON_DATABASE_PATH", str(db_path))

    with TestClient(app) as client:
        response = client.post(
            "/search/external/import",
            data={
                "source": "tcgdex",
                "external_id": "base1-58",
                "title": "Pikachu",
                "price_cents": "0",
            },
        )
        assert response.status_code == 200
        assert "Échec de l’import externe" in response.text
        assert "Seules les annonces eBay" in response.text


