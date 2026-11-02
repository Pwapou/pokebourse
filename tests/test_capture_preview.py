"""Prévisualisation d'une annonce capturée par l'extension, sans écriture avant confirmation."""
from __future__ import annotations

import json
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from app.capture_preview import _provenance, router
from app.manual_listing import router as manual_router
from app.storage.database import connect
from app.storage.migration_runner import apply_migrations
from app.tcgdex.cache import TcgdexCache


def _capture(**overrides: str) -> dict[str, str]:
    """Une capture complète telle que transmise par le popup de l'extension."""
    data = {
        "platform": "vinted",
        "external_id": "vinted_12345",
        "url": "https://www.vinted.fr/items/12345-carte-pokemon",
        "title": "Carte Pokémon Dracaufeu 4/102 Set de Base",
        "description": "Dracaufeu 4/102 Set de Base, carte en très bon état",
        "name": "Carte Pokémon Dracaufeu 4/102 Set de Base",
        "set_name": "Set de Base",
        "card_number": "4/102",
        "language": "fr",
        "condition": "",
        "seller": "pseudo-vendeur",
        "price": "145,00",
        "shipping": "5,00",
        "currency": "EUR",
        "image_url": "https://images.vinted.net/photos/photo-1.jpg",
    }
    data.update(overrides)
    return data


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Base locale dédiée, réseau externe strictement interdit."""
    monkeypatch.setattr(
        socket.socket, "connect",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("réseau interdit")),
    )
    path = tmp_path / "capture.sqlite"
    with connect(path) as connection:
        apply_migrations(connection)
        TcgdexCache(connection).seed_initial_if_empty()
        # Une cote locale pour Dracaufeu afin d'exercer le calcul de rentabilité.
        from app.profitability import build_card_key
        key = build_card_key(
            name="Dracaufeu", set_name="Set de Base", card_number="",
            language="fr", condition="", currency="EUR",
        )
        connection.execute(
            """
            INSERT INTO market_references (
                card_key, name, set_name, card_number, language, condition,
                reference_price_cents, currency, source_name, reference_kind,
                observed_at, note
            ) VALUES (?, 'Dracaufeu', 'Set de Base', NULL, 'fr', NULL, ?, 'EUR',
                      'Cardmarket', 'estimation_manuelle', '2026-10-30', 'Cote de test locale')
            """,
            (key, 20000),
        )
        # Le profil « Standard » migre avec des frais vides : on les fixe pour
        # exercer le port de profil en repli et le calcul complet de rentabilité.
        connection.execute(
            """
            UPDATE fee_profiles SET buyer_shipping_cents = 450, platform_fee_bps = 500,
                   seller_fixed_fee_cents = 0, shipping_packaging_cents = 200
            WHERE is_active = 1
            """
        )
        connection.commit()
    app = FastAPI()
    app.state.settings = SimpleNamespace(database_path=path)
    app.mount("/static", StaticFiles(directory="app/static"), name="static")
    app.include_router(router)
    app.include_router(manual_router)
    return TestClient(app)


@pytest.mark.parametrize("first", ["manual", "capture", "direct"])
def test_same_listing_across_import_paths_preserves_original(client: TestClient, first: str) -> None:
    from app.catalog import import_listings_from_extension

    manual = {"url": "https://www.vinted.fr/items/12345-autre-titre?tracking=1", "name": "Dracaufeu corrigé", "set_name": "Base", "language": "fr", "price": "12", "shipping": "2", "currency": "EUR"}
    direct = json.dumps({"external_id": "vinted_12345", "name": "Autre titre", "set_name": "Base", "price_cents": 9999, "url": "https://www.vinted.fr/items/12345-carte-pokemon"}).encode()

    def run(kind: str) -> None:
        if kind == "direct":
            with connect(client.app.state.settings.database_path) as connection:
                import_listings_from_extension(connection, direct)
        elif kind == "manual":
            client.post("/ajouter-annonce/enregistrer", data=manual)
        else:
            client.post("/previsualiser-capture/confirmer", data=_capture())

    run(first)
    with connect(client.app.state.settings.database_path) as connection:
        before = tuple(connection.execute("SELECT * FROM catalog_items").fetchone())
    for other in {"manual", "capture", "direct"} - {first}:
        run(other)
    with connect(client.app.state.settings.database_path) as connection:
        rows = connection.execute("SELECT * FROM catalog_items").fetchall()
        assert len(rows) == 1
        assert tuple(rows[0]) == before


def test_url_identity_collision_and_atomic_batch(client: TestClient) -> None:
    from app.catalog import CatalogImportError, import_jsonl
    from app.listing_identity import listing_url_identity

    assert listing_url_identity("vinted", "https://www.vinted.fr.evil.example/items/12345-test") is None
    assert listing_url_identity("ebay", "https://www.vinted.fr/items/12345-test") is None
    assert listing_url_identity("ebay", "https://www.ebay.fr/itm/123456789") != listing_url_identity("vinted", "https://www.vinted.fr/items/12345-test")
    item = {"external_id": "a", "name": "Pikachu", "set_name": "Base", "price_cents": 100, "url": "https://www.vinted.fr/items/12345-test"}
    duplicate = {**item, "external_id": "b", "url": "https://www.vinted.fr/items/12345-autre"}
    batch = (json.dumps(item) + "\n" + json.dumps(duplicate)).encode()
    with connect(client.app.state.settings.database_path) as connection:
        with pytest.raises(CatalogImportError, match="existe déjà"):
            import_jsonl(connection, batch, "vinted")
        assert connection.execute("SELECT count(*) FROM catalog_items").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM import_batches").fetchone()[0] == 0


def test_extension_external_id_collision_does_not_overwrite(client: TestClient) -> None:
    from app.catalog import CatalogImportError, import_listings_from_extension

    item = {"external_id": "same", "name": "Pikachu", "set_name": "Base", "price_cents": 100, "url": "https://www.vinted.fr/items/12345-test"}
    with connect(client.app.state.settings.database_path) as connection:
        import_listings_from_extension(connection, json.dumps(item).encode())
        before = tuple(connection.execute("SELECT * FROM catalog_items").fetchone())
        item["url"] = "https://www.ebay.fr/itm/123456789"
        with pytest.raises(CatalogImportError, match="autre annonce"):
            import_listings_from_extension(connection, json.dumps(item).encode())
        assert tuple(connection.execute("SELECT * FROM catalog_items").fetchone()) == before


def _counts(db_path: Path) -> dict[str, int]:
    with connect(db_path) as connection:
        return {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("catalog_items", "import_batches", "listing_identification_reviews")
        }


def test_currency_is_explicit_and_retained(client: TestClient) -> None:
    """Une devise absente reste inconnue ; USD n'est jamais converti en EUR."""
    missing = _capture(currency="", price="145,00")
    response = client.post("/previsualiser-capture", data=missing)
    assert 'name="currency"' in response.text
    assert "Devise de l’annonce inconnue" in response.text
    invalid = client.post("/previsualiser-capture/confirmer", data=missing)
    assert "Indiquez la devise" in invalid.text
    assert _counts(Path(client.app.state.settings.database_path))["catalog_items"] == 0
    usd = _capture(currency="USD")
    assert client.post("/previsualiser-capture/confirmer", data=usd, follow_redirects=False).status_code == 303
    with connect(client.app.state.settings.database_path) as connection:
        row = connection.execute("SELECT price_cents, currency FROM catalog_items").fetchone()
        assert (row["price_cents"], row["currency"]) == (14500, "USD")


# 1. Capture complète transmise à la prévisualisation.
def test_full_capture_renders_extracted_fields(client: TestClient) -> None:
    response = client.post("/previsualiser-capture", data=_capture())
    assert response.status_code == 200
    text = response.text
    assert "vinted" in text and "vinted_12345" in text
    assert "https://www.vinted.fr/items/12345-carte-pokemon" in text
    assert 'value="145,00"' in text and 'value="5,00"' in text
    assert "Extraite" in text
    assert "Indices concordants" in text
    assert "base1-4" in text
    assert "Confirmer et ajouter l’annonce" in text


# 2. Capture partielle : champs manquants clairement signalés, jamais inventés.
def test_partial_capture_marks_missing_fields(client: TestClient) -> None:
    response = client.post("/previsualiser-capture", data=_capture(
        description="", seller="", shipping="", image_url="", condition="", card_number="",
    ))
    assert response.status_code == 200
    text = response.text
    assert "Manquante" in text
    assert "Image principale manquante" in text


# 3. La description de l'annonce alimente l'identification.
def test_description_feeds_identification(client: TestClient) -> None:
    response = client.post("/previsualiser-capture", data=_capture(
        title="Carte à vendre",
        name="",
        set_name="",
        card_number="",
        description="Dracaufeu 4/102 Set de Base, carte française",
    ))
    assert response.status_code == 200
    assert "base1-4" in response.text


# 4. Photo absente ou disponible.
def test_image_rendered_or_reported_missing(client: TestClient) -> None:
    with_image = client.post("/previsualiser-capture", data=_capture())
    assert 'class="capture-preview-image"' in with_image.text
    assert "https://images.vinted.net/photos/photo-1.jpg" in with_image.text
    without = client.post("/previsualiser-capture", data=_capture(image_url=""))
    assert "Image principale manquante" in without.text
    assert "capture-preview-image" not in without.text


# 5. Carte aux indices concordants : identité proposée, score non probabiliste, rentabilité.
def test_concordant_card_shows_proposal_and_profitability(client: TestClient) -> None:
    response = client.post("/previsualiser-capture", data=_capture())
    text = response.text
    assert "Score" in text and "pas une probabilité" in text
    assert "Revente estimée : 200,00 €" in text
    assert "Cardmarket" in text and "Estimation manuelle" in text and "2026-10-30" in text
    assert "Gain net" in text and "ROI" in text
    assert "Proposée" in text
    assert "pas</strong> une confirmation humaine" in text


# 6. Identification ambiguë : reste ambiguë, aucune cote.
def test_ambiguous_capture_stays_ambiguous_without_cote(client: TestClient) -> None:
    response = client.post("/previsualiser-capture", data=_capture(
        title="Pikachu", name="Pikachu", set_name="", card_number="",
        description="carte pikachu française",
    ))
    text = response.text
    assert "Identification ambiguë" in text
    assert "Candidats pertinents" in text
    assert "Identité à vérifier" in text


# 7. Lot : aucune carte unitaire rattachée arbitrairement.
def test_lot_capture_never_gets_unit_card_identity(client: TestClient) -> None:
    response = client.post("/previsualiser-capture", data=_capture(
        title="Lot de 50 cartes Pokémon", name="Lot de 50 cartes Pokémon", description="",
    ))
    text = response.text
    assert "Lot ou produit scellé" in text
    assert "Aucune carte unitaire" in text
    assert "base1-4" not in text
    assert "Aucune cote exploitable" not in text  # un lot n'est pas coté unitairement


# 8. Absence de cote exploitable : identifiée mais sans prix de référence.
def test_identified_card_without_any_reference_has_no_price(client: TestClient) -> None:
    response = client.post("/previsualiser-capture", data=_capture(
        title="Tortank 15/102 Set de Base", name="Tortank 15/102 Set de Base",
        set_name="Set de Base", card_number="15/102",
        description="Tortank 15/102 Set de Base, carte française",
    ))
    text = response.text
    assert "Indices concordants" in text
    assert "Aucune cote exploitable" in text
    assert "Date : Inconnue" in text


# 9. Port de l'annonce prioritaire, y compris lorsqu'il vaut zéro.
def test_listing_shipping_zero_wins_over_profile(client: TestClient) -> None:
    response = client.post("/previsualiser-capture", data=_capture(shipping="0,00"))
    text = response.text
    assert "source : annonce" in text
    assert "Coût d’acquisition : 145,00 €" in text


# 10. Port du profil utilisé en repli lorsque celui de l'annonce est inconnu.
def test_profile_shipping_used_as_fallback(client: TestClient) -> None:
    response = client.post("/previsualiser-capture", data=_capture(shipping=""))
    assert "source : profil" in response.text
    assert "Manquante" in response.text  # le port capturé est absent, pas remplacé par zéro


# 11. Corrections conservées et ancienne valeur présentée après une nouvelle analyse.
def test_reanalysis_keeps_user_corrections_and_shows_both_values(client: TestClient) -> None:
    corrected = _capture()
    corrected.update({
        "title": "Dracaufeu holographique 4/102",
        "captured_title": "Carte Pokémon Dracaufeu 4/102 Set de Base",
        "captured_description": corrected["description"],
        "captured_name": corrected["name"],
        "captured_set_name": corrected["set_name"],
        "captured_card_number": corrected["card_number"],
        "captured_language": corrected["language"],
        "captured_condition": "",
        "captured_seller": corrected["seller"],
        "captured_price": corrected["price"],
        "captured_shipping": corrected["shipping"],
        "captured_currency": corrected["currency"],
        "captured_image_url": corrected["image_url"],
    })
    response = client.post("/previsualiser-capture/analyser", data=corrected)
    text = response.text
    assert 'value="Dracaufeu holographique 4/102"' in text
    assert "Corrigée" in text
    assert "Capturé : « Carte Pokémon Dracaufeu 4/102 Set de Base »" in text
    assert "base1-4" in text  # l'identification tient compte de la correction


# 11b. Une correction du numéro contredisant la carte proposée rend l'identité ambiguë.
def test_corrected_conflicting_number_forces_ambiguity(client: TestClient) -> None:
    corrected = _capture(card_number="15/102", captured_card_number="4/102")
    response = client.post("/previsualiser-capture/analyser", data=corrected)
    text = response.text
    assert "contredisent la carte proposée" in text
    assert "Identification ambiguë" in text


# 12. Aucune écriture avant confirmation (prévisualisation et nouvelle analyse).
def test_preview_and_reanalysis_never_write(client: TestClient) -> None:
    db_path = Path(client.app.state.settings.database_path)
    client.post("/previsualiser-capture", data=_capture())
    corrected = _capture(title="Titre corrigé", captured_title="Titre capturé")
    client.post("/previsualiser-capture/analyser", data=corrected)
    assert _counts(db_path) == {"catalog_items": 0, "import_batches": 0, "listing_identification_reviews": 0}


# 13. Enregistrement confirmé : transfert fidèle des champs via le flux transactionnel.
def test_confirmed_capture_imports_faithfully(client: TestClient) -> None:
    db_path = Path(client.app.state.settings.database_path)
    response = client.post("/previsualiser-capture/confirmer", data=_capture(), follow_redirects=False)
    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith("/catalog/") and "notice=" in location
    with connect(db_path) as connection:
        row = connection.execute(
            "SELECT c.*, s.name AS source_name FROM catalog_items c "
            "JOIN sources s ON s.id = c.source_id"
        ).fetchone()
        assert row["source_name"] == "vinted"
        assert row["external_id"] == "vinted_12345"
        assert row["price_cents"] == 14500
        assert row["shipping_cents"] == 500
        assert row["currency"] == "EUR"
        assert row["seller"] == "pseudo-vendeur"
        assert row["language"] == "fr"
        assert row["image_url"] == "https://images.vinted.net/photos/photo-1.jpg"
        assert row["original_title"] == "Carte Pokémon Dracaufeu 4/102 Set de Base"
        # Le flux transactionnel existant conserve la description dans raw_data ;
        # le titre de l'annonce est conservé dans original_title.
        raw = json.loads(row["raw_data"])
        assert raw["description"].startswith("Dracaufeu 4/102")
        assert raw["_identity_input_origin"] == "original_text"


@pytest.mark.parametrize("image_url", [
    "http://example.com/photo.jpg",
    "https://127.0.0.1/photo.jpg",
    "https://user:pass@example.com/photo.jpg",
    "https://service.local/photo.jpg",
    "javascript:alert(1)",
])
def test_unsafe_image_is_neither_previewed_nor_imported(client: TestClient, image_url: str) -> None:
    """Les images invalides ne déclenchent pas de chargement dans le navigateur."""
    payload = _capture(image_url=image_url)
    preview = client.post("/previsualiser-capture", data=payload)
    assert 'class="capture-preview-image"' not in preview.text
    assert "Adresse de l’image invalide" in preview.text
    confirmed = client.post("/previsualiser-capture/confirmer", data=payload)
    assert "Adresse de l’image invalide" in confirmed.text
    with connect(client.app.state.settings.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM catalog_items").fetchone()[0] == 0


# 14. Doublon : message clair, aucun écrasement de first_seen_at.
def test_duplicate_confirmation_preserves_first_seen_at(client: TestClient) -> None:
    db_path = Path(client.app.state.settings.database_path)
    payload = _capture()
    client.post("/previsualiser-capture/confirmer", data=payload)
    with connect(db_path) as connection:
        before = connection.execute("SELECT first_seen_at FROM catalog_items").fetchone()[0]
    duplicate = client.post("/previsualiser-capture/confirmer", data=payload)
    assert "existe déjà" in duplicate.text
    with connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM catalog_items").fetchone()[0] == 1
        after = connection.execute("SELECT first_seen_at FROM catalog_items").fetchone()[0]
    assert after == before  # le doublon n'écrase ni les métadonnées ni les prix


# 16. Confirmations humaines protégées et vendeur limité à la liste blanche.
def test_no_human_confirmation_created_and_seller_whitelist_enforced(client: TestClient) -> None:
    db_path = Path(client.app.state.settings.database_path)
    client.post("/previsualiser-capture", data=_capture())
    client.post("/previsualiser-capture/confirmer", data=_capture())
    with connect(db_path) as connection:
        human = connection.execute(
            "SELECT COUNT(*) FROM listing_identification_reviews WHERE review_kind IN ('decision','adjudication')"
        ).fetchone()[0]
    assert human == 0  # le moteur ne crée jamais une validation humaine à la place de l'utilisateur
    rejected = client.post("/previsualiser-capture/confirmer", data=_capture(
        external_id="vinted_99999", seller="personne@example.com",
    ))
    assert "pseudonyme public" in rejected.text
    rejected_phone = client.post("/previsualiser-capture/confirmer", data=_capture(
        external_id="vinted_99998", seller="06 12 34 56 78",
    ))
    assert "pseudonyme public" in rejected_phone.text
    with connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM catalog_items").fetchone()[0] == 1


def test_provenance_rules() -> None:
    assert _provenance("", "") == "manquante"
    assert _provenance("", "valeur") == "saisie"
    assert _provenance("ancienne", "nouvelle") == "corrigée"
    assert _provenance("identique", "identique") == "extraite"


def test_capture_ocr_hints_are_visible_and_do_not_replace_capture(client: TestClient) -> None:
    payload = _capture(price="", currency="", name="Carte photographiée", card_number="")
    payload["ocr_result"] = json.dumps({"message": "Suggestions à vérifier", "recognized": {"names": ["Pikachu"], "numbers": ["58/102"]}})
    response = client.post("/previsualiser-capture", data=payload)
    assert response.status_code == 200
    assert "Lecture automatique de l’image" in response.text
    assert "Pikachu" in response.text and "58/102" in response.text
    assert 'value="Carte photographiée"' in response.text
    assert _counts(Path(client.app.state.settings.database_path))["catalog_items"] == 0


def test_capture_reanalysis_preserves_ocr_hints_and_prefills_empty_fields(client: TestClient) -> None:
    payload = _capture(
        title="Carte photographiée", description="", name="", set_name="", card_number="",
    )
    payload["ocr_result"] = json.dumps({
        "message": "Suggestions à vérifier",
        "recognized": {"names": ["Pikachu"], "numbers": ["58/102"]},
        "raw_text": "texte privé qui ne doit pas être conservé",
    })
    first = client.post("/previsualiser-capture", data=payload)
    assert "base1-58" in first.text
    assert 'name="name" maxlength="200" value="Pikachu"' in first.text
    assert 'name="card_number" maxlength="50" value="58/102"' in first.text
    assert "texte privé" not in first.text

    reanalysis = dict(payload)
    reanalysis.pop("ocr_result")
    reanalysis.update({"name": "Pikachu", "set_name": "Set de Base", "card_number": "58/102"})
    reanalysis.update({"ocr_names": ["Pikachu"], "ocr_numbers": ["58/102"]})
    second = client.post("/previsualiser-capture/analyser", data=reanalysis)
    assert second.status_code == 200
    assert "base1-58" in second.text
    assert "Indices conservés depuis la première lecture" in second.text
    assert "texte privé" not in second.text
    assert _counts(Path(client.app.state.settings.database_path))["catalog_items"] == 0
