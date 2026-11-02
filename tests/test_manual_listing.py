"""Parcours de saisie d'une annonce par URL, sans accès réseau."""
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.staticfiles import StaticFiles

from app.manual_listing import parse_listing_url, router
from app.storage.database import connect
from app.storage.migration_runner import apply_migrations


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Initialise une base locale dédiée et bloque toute connexion externe."""
    import socket
    monkeypatch.setattr(socket.socket, "connect", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("réseau interdit")))
    path = tmp_path / "manual.sqlite"
    with connect(path) as connection:
        apply_migrations(connection)
    app = FastAPI()
    app.state.settings = SimpleNamespace(database_path=path)
    app.mount("/static", StaticFiles(directory="app/static"), name="static")
    app.include_router(router)
    return TestClient(app)


@pytest.mark.parametrize("url, source, identity", [
    ("https://www.ebay.fr/itm/pikachu-151/287597504111?tracking=1", "ebay", "287597504111"),
    ("https://www.vinted.fr/items/12345-carte-pokemon", "vinted", "12345"),
    ("https://www.leboncoin.fr/ad/collection/1234567", "leboncoin", "1234567"),
    ("https://fr.wallapop.com/item/carte-pokemon-12345", "wallapop", "carte-pokemon-12345"),
])
def test_url_is_parsed_without_network(url: str, source: str, identity: str) -> None:
    parsed = parse_listing_url(url)
    assert parsed["platform"] == source
    assert parsed["external_id"] == identity
    assert "?" not in parsed["url"]


@pytest.mark.parametrize("url", [
    "http://www.ebay.fr/itm/123456789012", "https://www.ebay.fr.evil.test/itm/123456789012",
    "https://www.ebay.fr@127.0.0.1/itm/123456789012", "https://127.0.0.1/itm/123456789012",
    "https://www.ebay.fr:8443/itm/123456789012", "https://www.ebay.fr/sch/i.html",
])
def test_rejects_unsupported_addresses(url: str) -> None:
    with pytest.raises(ValueError):
        parse_listing_url(url)


def test_review_then_import_with_shipping_and_correct_platform(client: TestClient) -> None:
    url = "https://www.ebay.fr/itm/pikachu-151/287597504111?tracking=1"
    review = client.post("/ajouter-annonce/preparer", data={"url": url})
    assert review.status_code == 200
    assert "ne sont pas extraits" in review.text
    assert "287597504111" in review.text
    assert "pikachu 151" in review.text
    payload = {
        "url": url, "name": "Pikachu", "set_name": "151", "card_number": "173/165",
        "language": "fr", "condition": "EX", "seller": "vendeur-public",
        "price": "83,25", "shipping": "5,00", "currency": "EUR",
    }
    result = client.post("/ajouter-annonce/enregistrer", data=payload, follow_redirects=False)
    assert result.status_code == 303
    assert result.headers["location"].startswith("/catalog/")
    with connect(client.app.state.settings.database_path) as connection:
        item = connection.execute("SELECT c.*, s.name source FROM catalog_items c JOIN sources s ON s.id=c.source_id").fetchone()
        assert (item["source"], item["external_id"], item["price_cents"], item["shipping_cents"]) == ("ebay", "287597504111", 8325, 500)
        seen = item["first_seen_at"]
    duplicate = client.post("/ajouter-annonce/enregistrer", data=payload)
    assert "annonce existe déjà" in duplicate.text
    with connect(client.app.state.settings.database_path) as connection:
        assert connection.execute("SELECT count(*) FROM catalog_items").fetchone()[0] == 1
        assert connection.execute("SELECT first_seen_at FROM catalog_items").fetchone()[0] == seen


def test_invalid_data_never_imported(client: TestClient) -> None:
    payload = {"url": "https://www.ebay.fr/itm/287597504111", "name": "Pikachu", "set_name": "151", "language": "fr", "price": "1.005", "seller": "vendeur"}
    assert "maximum deux décimales" in client.post("/ajouter-annonce/enregistrer", data=payload).text
    payload["price"] = "1.00"
    payload["seller"] = "personne@example.com"
    assert "pseudonyme public" in client.post("/ajouter-annonce/enregistrer", data=payload).text
    with connect(client.app.state.settings.database_path) as connection:
        assert connection.execute("SELECT count(*) FROM catalog_items").fetchone()[0] == 0


def test_preview_preserves_input_without_creating_listing(client: TestClient) -> None:
    payload = {"url": "https://www.ebay.fr/itm/287597504111", "title": "Lot de cartes Pokémon", "description": "Deux cartes", "name": "Pikachu", "set_name": "151", "language": "fr", "price": "83,25", "shipping": "5", "currency": "EUR"}
    response = client.post("/ajouter-annonce/analyser", data=payload)
    assert response.status_code == 200
    assert "Lot ou produit scellé" in response.text
    assert "Deux cartes" in response.text
    assert 'value="83,25"' in response.text
    with connect(client.app.state.settings.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM catalog_items").fetchone()[0] == 0


_FETCH_HTML = b'''<html><head>
<script type="application/ld+json">{"@type":"Product","name":"Annonce floue","description":"carte ancienne brillante","image":"https://i.ebayimg.com/photo.jpg","offers":{"price":"83.25","priceCurrency":"EUR","itemCondition":"https://schema.org/UsedCondition","shippingDetails":{"shippingRate":{"value":"4.50","currency":"EUR"}}}}</script>
</head><body></body></html>'''


@pytest.fixture
def fetch_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Parcours URL avec domaine explicitement autorisé et réponses simulées."""
    import socket
    monkeypatch.setattr(socket.socket, "connect", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("réseau interdit")))
    path = tmp_path / "fetch.sqlite"
    with connect(path) as connection:
        apply_migrations(connection)
        from app.tcgdex.cache import TcgdexCache
        from app.tcgdex.models import TcgdexCard, TcgdexSet
        cache = TcgdexCache(connection)
        cache.seed_initial_if_empty()
        cache.upsert_set(TcgdexSet(id="base1", name="Set de Base", card_count_official=102, card_count_total=102))
        cache.upsert_card(TcgdexCard(id="base1-4", local_id="4", name="Dracaufeu", set_id="base1", set_name="Set de Base"))
    import app.manual_listing as manual_listing
    from app.collectors.page_fetch import FetchedContent

    def _fake_page(url: str, *, allowed_hosts: tuple[str, ...], timeout: float = 10.0) -> FetchedContent:
        return FetchedContent(content=_FETCH_HTML, content_type="text/html", final_url=url)

    def _fake_image(url: str, *, allowed_hosts: tuple[str, ...], max_bytes: int = 8 * 1024 * 1024,
                    timeout: float = 10.0) -> FetchedContent:
        return FetchedContent(content=b"\x89PNG\r\n\x1a\nimage", content_type="image/jpeg", final_url=url)

    monkeypatch.setattr(manual_listing, "fetch_listing_page", _fake_page)
    monkeypatch.setattr(manual_listing, "fetch_listing_image", _fake_image)
    monkeypatch.setattr(
        "app.identification.ocr.analyze_image",
        lambda connection, content: {
            "status": "candidates",
            "recognized": {"names": ["Dracaufeu"], "numbers": ["4/102"]},
            "candidates": [{"card_id": 1, "tcgdex_id": "base1-4", "name": "Dracaufeu",
                            "set_name": "Set de Base", "local_id": "4", "image_url": None}],
            "message": "Suggestions à vérifier.",
        },
    )
    app = FastAPI()
    app.state.settings = SimpleNamespace(database_path=path, page_fetch_allowed_hosts=("www.ebay.fr", "ebayimg.com"))
    app.mount("/static", StaticFiles(directory="app/static"), name="static")
    app.include_router(router)
    return TestClient(app)


def test_allowed_page_is_extracted_prefilled_and_ocred(fetch_client: TestClient) -> None:
    """Parcours URL autorisé : JSON-LD complet → champs préremplis + OCR automatique."""
    response = fetch_client.post("/ajouter-annonce/preparer", data={"url": "https://www.ebay.fr/itm/123456789012"})
    assert response.status_code == 200
    text = response.text
    assert "Informations extraites de la page" in text
    assert "Identification proposée" in text
    assert "Trouvé" in text and "Proposé" in text and "Manquant" in text
    assert 'value="83,25"' in text          # prix prérempli
    assert 'value="4,50"' in text           # port proposé
    assert "Dracaufeu" in text and "4/102" in text   # indices OCR affichés
    assert 'name="ocr_names"' in text       # indices persistés pour l'analyse
    assert "extraits de la page" in text
    with connect(fetch_client.app.state.settings.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM catalog_items").fetchone()[0] == 0


def _form_payload(html: str) -> dict[str, str]:
    """Rejoue fidèlement les champs du formulaire, y compris les champs cachés."""
    import re
    form = re.search(r'<form method="post" action="/ajouter-annonce/enregistrer".*?</form>', html, re.S)
    assert form, "formulaire de vérification introuvable"
    block = form.group(0)
    payload = {}
    for tag in re.findall(r"<input\b[^>]*>", block):
        name = re.search(r'name="([^"]+)"', tag)
        if name:
            value = re.search(r'value="([^"]*)"', tag)
            payload[name.group(1)] = value.group(1) if value else ""
    payload.update({name: re.sub(r"<.*?>", "", text).strip()
                    for name, text in re.findall(r'<textarea[^>]*name="([^"]+)"[^>]*>(.*?)</textarea>', block, re.S)})
    payload.update({m.group(1): m.group(2)
                    for m in re.finditer(r'<select[^>]*name="([^"]+)"[^>]*>.*?<option value="([^"]+)" selected>', block, re.S)})
    return payload


def test_ocr_hints_feed_identification_of_vague_listing(fetch_client: TestClient) -> None:
    """Les indices OCR alimentent réellement l'identification d'un titre flou."""
    page = fetch_client.post("/ajouter-annonce/preparer", data={"url": "https://www.ebay.fr/itm/123456789012"})
    payload = _form_payload(page.text)
    payload.update({"language": "fr", "name": "", "set_name": ""})
    response = fetch_client.post("/ajouter-annonce/analyser", data=payload)
    assert response.status_code == 200
    assert "base1-4" in response.text  # l'identification tient compte des indices OCR


def test_human_correction_is_marked_and_never_overwritten(fetch_client: TestClient) -> None:
    """Une valeur corrigée reste en place et est signalée comme corrigée après analyse."""
    page = fetch_client.post("/ajouter-annonce/preparer", data={"url": "https://www.ebay.fr/itm/123456789012"})
    payload = _form_payload(page.text)
    payload.update({"name": "Dracaufeu", "set_name": "Set de Base", "language": "fr", "price": "90,00"})
    response = fetch_client.post("/ajouter-annonce/analyser", data=payload)
    assert 'value="90,00"' in response.text
    assert "corrigée" in response.text
    assert "Extrait : « 83,25 »" in response.text
    assert "Dracaufeu" in response.text


def test_refused_platform_proposes_extension_and_manual_entry(client: TestClient) -> None:
    """Domaine non autorisé : explication claire, jamais présenté comme extrait."""
    response = client.post("/ajouter-annonce/preparer", data={"url": "https://www.vinted.fr/items/12345-carte"})
    assert response.status_code == 200
    assert "pas autorisée" in response.text
    assert "extension" in response.text and "manuellement" in response.text
    assert "ne sont pas extraits" in response.text  # aucune extraction n'a eu lieu
    assert "Informations extraites" not in response.text


def test_fetch_failure_keeps_form_usable(fetch_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Échec de récupération : le motif est expliqué et le formulaire reste utilisable."""
    import app.manual_listing as manual_listing
    from app.collectors.page_fetch import PageFetchError

    def _broken(url: str, *, allowed_hosts: tuple[str, ...], timeout: float = 10.0):
        raise PageFetchError("La page exige une authentification ou bloque l’accès automatisé.")

    monkeypatch.setattr(manual_listing, "fetch_listing_page", _broken)
    response = fetch_client.post("/ajouter-annonce/preparer", data={"url": "https://www.ebay.fr/itm/123456789012"})
    assert response.status_code == 200
    assert "n’a pas pu être récupérée" in response.text
    assert "authentification" in response.text
    # Le formulaire reste entièrement disponible pour la saisie manuelle.
    assert 'name="price"' in response.text and 'name="name"' in response.text
    with connect(fetch_client.app.state.settings.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM catalog_items").fetchone()[0] == 0
