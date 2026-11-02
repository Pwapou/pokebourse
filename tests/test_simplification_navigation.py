"""Recette de la phase 1 : navigation cible, catalogue unifié et compatibilité.

Aucun appel réseau réel : la base est locale (fichier temporaire) et les
cotes sont enregistrées via les formulaires existants.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.storage.database import connect
from app.web import app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("POKEMON_DATABASE_PATH", str(tmp_path / "web.db"))
    with TestClient(app) as test_client:
        test_client.post(
            "/profitability/settings",
            data={
                "buyer_shipping_euros": "0",
                "platform_fee_percent": "5",
                "seller_fixed_fee_euros": "0",
                "shipping_packaging_euros": "2",
                "min_net_profit_euros": "5",
                "min_roi_percent": "15",
                "min_catalog_samples": "2",
            },
        )
        content = (
            '{"external_id":"pika-1","name":"Pikachu","set_name":"Evolutions",'
            '"card_number":"35/108","condition":"NM","price_cents":1000}\n'
            '{"external_id":"draco-1","name":"Dracaufeu","set_name":"Base Set",'
            '"card_number":"4/102","condition":"NM","price_cents":34000}\n'
            '{"external_id":"no-ref","name":"Mélofée","set_name":"Jungle",'
            '"price_cents":500}'
        ).encode()
        test_client.post(
            "/imports",
            files={"file": ("annonces.jsonl", content, "application/x-ndjson")},
        )
        # Cotes : Pikachu 25,00 € (opportunité), Dracaufeu 300,00 € (perte).
        test_client.post(
            "/profitability/references",
            data={
                "name": "Pikachu",
                "set_name": "Evolutions",
                "card_number": "35/108",
                "language": "fr",
                "condition": "NM",
                "reference_price_euros": "25,00",
                "currency": "EUR",
                "reference_kind": "ventes_conclues",
                "observed_at": "2026-10-31",
            },
        )
        test_client.post(
            "/profitability/references",
            data={
                "name": "Dracaufeu",
                "set_name": "Base Set",
                "card_number": "4/102",
                "language": "fr",
                "condition": "NM",
                "reference_price_euros": "300,00",
                "currency": "EUR",
            },
        )
        yield test_client


def test_navigation_cible_affiche_les_cinq_entrees(client: TestClient) -> None:
    page = client.get("/catalog")
    assert page.status_code == 200
    for label in ("Accueil", "Opportunités", "Mes achats", "Réglages", "Gestion avancée"):
        assert label in page.text
    # Les pages avancées restent accessibles par de vrais liens.
    for url in ("/sellers", "/watches", "/tcgdex", "/annotations", "/agents", "/backups"):
        assert f'href="{url}"' in page.text
    assert 'href="/identification/diagnostics"' in page.text
    assert 'href="/#import"' in page.text
    # Menu global d'ajout.
    assert "Ajouter des annonces" in page.text
    assert 'href="/watches"' in page.text


def test_catalog_verdict_filter_exact_counts(client: TestClient) -> None:
    all_page = client.get("/catalog")
    assert "3" in all_page.text

    opportunities = client.get("/catalog", params={"verdict": "opportunite"})
    assert opportunities.status_code == 200
    assert "1–1 sur 1" in opportunities.text
    assert "Pikachu" in opportunities.text
    assert "Dracaufeu" not in opportunities.text
    assert "Mélofée" not in opportunities.text

    losses = client.get("/catalog", params={"verdict": "non_rentable"})
    assert "1–1 sur 1" in losses.text
    assert "Dracaufeu" in losses.text

    missing = client.get("/catalog", params={"verdict": "sans_cote"})
    assert "Mélofée" in missing.text

    # Verdict inconnu : retombe sur « all » sans erreur.
    fallback = client.get("/catalog", params={"verdict": "injection"})
    assert fallback.status_code == 200
    assert "1–3 sur 3" in fallback.text


def test_catalog_profit_sorts_rank_by_gain_and_roi(client: TestClient) -> None:
    by_profit = client.get("/catalog", params={"sort": "profit_desc"})
    assert by_profit.status_code == 200
    profit_pos = by_profit.text.index("+11,75 €")
    loss_pos = by_profit.text.index("Dracaufeu")
    assert profit_pos < loss_pos

    by_roi = client.get("/catalog", params={"sort": "roi_desc"})
    assert by_roi.status_code == 200
    assert by_roi.text.index("Pikachu") < by_roi.text.index("Dracaufeu")

    # Tri de rentabilité combinable avec un filtre catalogue.
    combined = client.get(
        "/catalog", params={"sort": "roi_desc", "ident": "unidentified"}
    )
    assert combined.status_code == 200
    assert "Mélofée" in combined.text
    assert "Pikachu" not in combined.text


def test_profitability_analysis_links_redirect_to_catalog(client: TestClient) -> None:
    response = client.get(
        "/profitability",
        params={"q": "Pikachu", "set_name": "Evolutions", "sort": "roi_desc"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith("/catalog?")
    assert "q=Pikachu" in location
    assert "set_name=Evolutions" in location
    assert "sort=roi_desc" in location

    followed = client.get(location)
    assert followed.status_code == 200
    assert "Pikachu" in followed.text


def test_profitability_prefill_links_redirect_to_reglages(client: TestClient) -> None:
    response = client.get(
        "/profitability",
        params={"prefill_name": "Pikachu", "prefill_set": "Evolutions"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith("/reglages?")
    assert "prefill_name=Pikachu" in location
    assert location.endswith("#cotes")


def test_profitability_without_params_shows_compat_page(client: TestClient) -> None:
    response = client.get("/profitability")
    assert response.status_code == 200
    # Ancres #parametres / #cotes conservées (formulaires inchangés).
    assert 'id="parametres"' in response.text
    assert 'id="cotes"' in response.text
    assert 'id="marche"' in response.text
    assert "déménagé" in response.text
    # Le formulaire de frais reste fonctionnel (POST vers l'endpoint existant).
    assert 'action="/profitability/settings"' in response.text
    assert 'action="/profitability/references"' in response.text


def test_reglages_page_groups_three_sections(client: TestClient) -> None:
    response = client.get("/reglages")
    assert response.status_code == 200
    assert 'id="parametres"' in response.text
    assert 'id="cotes"' in response.text
    assert 'id="marche"' in response.text
    assert 'action="/cardmarket/sync-all"' in response.text
    assert 'action="/cardmarket/sync"' in response.text
    assert 'action="/cardmarket/aliases/sync"' in response.text


def test_post_settings_redirects_to_reglages_with_notice(client: TestClient) -> None:
    response = client.post(
        "/profitability/settings",
        data={
            "buyer_shipping_euros": "0",
            "platform_fee_percent": "6",
            "seller_fixed_fee_euros": "0",
            "shipping_packaging_euros": "2",
            "min_net_profit_euros": "5",
            "min_roi_percent": "15",
            "min_catalog_samples": "2",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].startswith("/reglages?notice=")
    followed = client.get(response.headers["location"].split("#")[0])
    assert "Paramètres de rentabilité enregistrés." in followed.text


def test_dashboard_headline_indicators(client: TestClient) -> None:
    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert "OPPORTUNITÉS" in dashboard.text
    assert "DONNÉES INSUFFISANTES" in dashboard.text
    assert "ACHATS EN COURS" in dashboard.text
    assert "Meilleures opportunités estimées" in dashboard.text
    assert "+11,75 €" in dashboard.text
    assert 'id="capture"' in dashboard.text
    assert 'id="import"' in dashboard.text


def test_manual_cardmarket_guide_status_is_not_reported_as_unsynchronized(client: TestClient) -> None:
    """La récupération du guide et la synchronisation complète ont des états distincts."""
    with connect(client.app.state.settings.database_path) as conn, conn:
        conn.execute(
            "INSERT INTO cardmarket_prices (product_id, card_name, currency, fetched_at) VALUES (1, 'Pikachu', 'EUR', '2026-11-02T10:00:00.000Z')"
        )
    page = client.get("/reglages")
    assert "Guide de prix récupéré le" in page.text
    assert "Aucune synchronisation complète enregistrée" in page.text
    assert "Aucune synchronisation Cardmarket enregistrée" not in page.text


def test_achats_empty_state_then_records_purchase(client: TestClient) -> None:
    # État initial : aucun achat enregistré.
    empty = client.get("/achats")
    assert empty.status_code == 200
    assert "Aucun achat enregistré" in empty.text

    # Enregistrement depuis la fiche annonce existante (annonce « pika-1 »).
    bought = client.post(
        "/catalog/1/purchase",
        data={
            "price_paid": "12.00",
            "shipping_paid": "1.50",
            "status": "recu",
            "notes": "Lot reçu conforme",
        },
        follow_redirects=True,
    )
    assert bought.status_code == 200
    assert "Achat enregistré" in bought.text

    page = client.get("/achats")
    assert page.status_code == 200
    assert "Aucun achat enregistré" not in page.text
    # Compteurs et coût total exacts (1200 + 150 = 1350 centimes).
    assert "13,50 €" in page.text
    assert "Lot reçu conforme" in page.text
    # Lien vers la carte d'origine préservé.
    assert 'href="/catalog/1"' in page.text


def test_achats_status_filters(client: TestClient) -> None:
    client.post(
        "/catalog/1/purchase",
        data={"price_paid": "12.00", "shipping_paid": "1.50", "status": "recu"},
    )
    client.post(
        "/catalog/2/purchase",
        data={"price_paid": "300.00", "shipping_paid": "0", "status": "commande"},
    )

    all_page = client.get("/achats")
    assert "2" in all_page.text

    received = client.get("/achats", params={"status": "recu"})
    assert received.status_code == 200
    assert "12,00 €" in received.text
    assert "300,00 €" not in received.text

    ordered = client.get("/achats", params={"status": "commande"})
    assert "300,00 €" in ordered.text
    assert "12,00 €" not in ordered.text

    sold = client.get("/achats", params={"status": "vendu"})
    assert "Aucun achat avec ce statut" in sold.text

    # Statut invalide : retombe sur « all » sans erreur.
    fallback = client.get("/achats", params={"status": "injection"})
    assert fallback.status_code == 200
    assert "300,00 €" in fallback.text


def test_purchase_lifecycle_and_exact_amount_validation(client: TestClient) -> None:
    """Un achat peut évoluer sans arrondir silencieusement des fractions de centime."""
    item = client.get("/catalog/1")
    assert 'Choisir un statut' in item.text
    assert '0 si gratuit' in item.text
    invalid = client.post(
        "/catalog/1/purchase",
        data={"price_paid": "1.005", "shipping_paid": "0", "status": "commande"},
        follow_redirects=True,
    )
    assert "maximum deux décimales" in invalid.text
    assert "Aucun achat enregistré" in client.get("/achats").text
    bought = client.post(
        "/catalog/1/purchase",
        data={"price_paid": "12.34", "shipping_paid": "1.50", "status": "commande"},
        follow_redirects=False,
    )
    assert bought.status_code == 303
    updated = client.post("/achats/1/update", data={"status": "vendu", "sale_price": "25.99"}, follow_redirects=True)
    assert "Achat mis à jour" in updated.text
    assert 'value="25.99"' in updated.text
    assert "12,34 €" in client.get("/achats?status=vendu").text
    rejected = client.post("/achats/1/update", data={"status": "vendu", "sale_price": "25.999"}, follow_redirects=True)
    assert "maximum deux décimales" in rejected.text
    assert 'value="25.99"' in rejected.text
    assert client.post("/achats/999/update", data={"status": "vendu", "sale_price": ""}).status_code == 404


def test_reglages_guide_reflects_real_state(client: TestClient) -> None:
    """Les 4 étapes du guide affichent l'état réel (frais, cotes, catalogue)."""
    response = client.get("/reglages")
    assert response.status_code == 200
    assert 'id="guide"' in response.text
    assert "Configuration guidée" in response.text
    for step in ("Définir les frais", "Ajouter des références de prix",
                 "Importer ou capturer des annonces", "Consulter les opportunités"):
        assert step in response.text
    # Frais complets (le fixture les enregistre tous) → étape 1 complétée.
    assert "Complété" in response.text
    # 2 références et 3 annonces réellement en base → indicateurs exacts.
    assert "2 références enregistrées" in response.text
    assert "3 annonces en catalogue" in response.text
    # Liens d'action présents.
    assert 'href="/reglages#parametres"' in response.text
    assert 'href="/#import"' in response.text
    assert 'href="/catalog?verdict=opportunite&sort=profit_desc"' in response.text


def test_reglages_guide_flags_missing_fees(tmp_path, monkeypatch) -> None:
    """Sans frais enregistrés, le guide signale explicitement les frais inconnus."""
    monkeypatch.setenv("POKEMON_DATABASE_PATH", str(tmp_path / "guide.db"))
    with TestClient(app) as test_client:
        response = test_client.get("/reglages")
    assert response.status_code == 200
    assert "À compléter" in response.text
    assert "Commission plateforme" in response.text
    assert "Aucune référence" in response.text
    assert "Catalogue vide" in response.text
