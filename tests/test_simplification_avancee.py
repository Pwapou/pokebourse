"""Recette de la phase 3 : index de gestion avancée et harmonisation.

Aucun appel réseau réel : la base est locale (fichier temporaire) et les
états sont produits par les flux existants (imports, achats, références).
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

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
            '"card_number":"35/108","price_cents":1000}\n'
        ).encode()
        test_client.post(
            "/imports",
            files={"file": ("annonces.jsonl", content, "application/x-ndjson")},
        )
        yield test_client


def test_gestion_index_cards_links_and_empty_states(client: TestClient) -> None:
    page = client.get("/gestion")
    assert page.status_code == 200
    # Les sept cartes des modules avancés.
    for heading in (
        "Vendeurs",
        "Veilles",
        "Imports et erreurs",
        "TCGdex",
        "Annotations ML",
        "Agents et incidents",
        "Sauvegardes",
    ):
        assert heading in page.text
    # Les URL existantes sont conservées et pointent vers les écrans spécialisés.
    for url in (
        "/sellers",
        "/watches",
        "/#import",
        "/imports/failures/report",
        "/tcgdex",
        "/annotations",
        "/identification/diagnostics",
        "/agents",
        "/backups",
    ):
        assert f'href="{url}"' in page.text
    # États vides explicites (base neuve) : rien n'est inventé.
    assert "Aucun pilote lancé" in page.text
    assert "Aucune sauvegarde enregistrée" in page.text
    assert "Aucun incident actif" in page.text
    assert "Aucun échec répertorié" in page.text
    assert "Aucune synchronisation active" in page.text
    # Retour clair vers le parcours principal + entrée de navigation.
    assert 'href="/"' in page.text
    assert 'href="/catalog"' in page.text
    assert 'href="/gestion"' in page.text
    assert "Vue d’ensemble" in page.text
    # Avertissement espace ML.
    assert "ESPACE DE PRÉPARATION ML" in page.text


def test_gestion_reflects_real_import_states(client: TestClient) -> None:
    # 1 lot réussi (fixture) puis 1 import rejeté (ligne invalide → rapport d'erreurs).
    bad = (
        '{"external_id":"ok-1","name":"Salameche","set_name":"Base","price_cents":900}\n'
        '{"external_id":"bad-1","name":"Roucool"}\n'
    ).encode()
    client.post(
        "/imports",
        files={"file": ("mixte.jsonl", bad, "application/x-ndjson")},
    )
    page = client.get("/gestion")
    assert page.status_code == 200
    assert "1 lot importé" in page.text
    # L'échec réel est visible, sans dramatiser les lots réussis.
    assert "1 ligne rejetée" in page.text
    assert "Aucun échec répertorié" not in page.text


def test_vendeurs_et_veilles_liens_contextuels(client: TestClient) -> None:
    vendeurs = client.get("/sellers")
    assert vendeurs.status_code == 200
    # Vendeur ↔ achats ↔ annonces.
    assert 'href="/gestion"' in vendeurs.text
    assert 'href="/achats"' in vendeurs.text
    assert 'href="/catalog"' in vendeurs.text
    assert "Aucun vendeur" in vendeurs.text
    assert 'href="/#import"' in vendeurs.text

    veilles = client.get("/watches")
    assert veilles.status_code == 200
    # Veille ↔ agents ↔ catalogue.
    assert 'href="/gestion"' in veilles.text
    assert 'href="/agents"' in veilles.text
    assert 'href="/catalog"' in veilles.text
    assert "Aucune veille configurée" in veilles.text
    assert 'href="/watches#create-watch"' in veilles.text


def test_ecrans_avances_vue_ensemble_et_pilote_ml(client: TestClient) -> None:
    # T3.3 : TCGdex et diagnostic d'identification harmonisés avec retour commun.
    for url in ("/tcgdex", "/identification/diagnostics"):
        page = client.get(url)
        assert page.status_code == 200
        assert 'href="/gestion"' in page.text

    # T3.4 : le pilote ML est isolé et présenté comme espace de préparation.
    annotations = client.get("/annotations")
    assert annotations.status_code == 200
    assert "Espace de préparation ML" in annotations.text
    assert 'href="/gestion"' in annotations.text
    assert 'href="/catalog"' in annotations.text

    # T3.5 : agents et sauvegardes harmonisés.
    for url in ("/agents", "/backups"):
        page = client.get(url)
        assert page.status_code == 200
        assert 'href="/gestion"' in page.text

    # Un lot d'import expose aussi la vue d'ensemble et le rapport d'erreurs.
    detail = client.get("/imports/1")
    assert detail.status_code == 200
    assert 'href="/gestion"' in detail.text
    assert 'href="/imports/failures/report"' in detail.text
