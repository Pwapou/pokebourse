"""Tests du module Cardmarket — 100 % mockés, aucun appel réseau réel."""

import io
import json
import sqlite3
import urllib.error
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.cardmarket import aliases
from app.cardmarket import service
from app.cardmarket.client import (
    CardmarketClient,
    CardmarketNotConfiguredError,
    CardmarketNotFoundError,
    CardmarketRateLimitError,
    euros_to_cents,
)
from app.cardmarket.models import CardmarketPrice
from app.config import Settings
from app.storage.database import connect
from app.storage.migration_runner import apply_migrations
from app.web import app


def make_client(**overrides: Any) -> CardmarketClient:
    params = {
        "app_token": "app-token",
        "app_secret": "app-secret",
        "access_token": "access-token",
        "access_secret": "access-secret",
        "nonce_factory": lambda: "abc123",
        "clock": lambda: 1_700_000_000.0,
    }
    params.update(overrides)
    return CardmarketClient(**params)


class FakeResponse:
    def __init__(self, payload: Any) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def http_error(code: int, retry_after: str | None = None) -> urllib.error.HTTPError:
    headers: dict[str, str] = {}
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return urllib.error.HTTPError(
        "https://api.cardmarket.com/ws/v2.0/output.json/games",
        code,
        "error",
        headers,
        io.BytesIO(b""),
    )


# ---------------------------------------------------------------------------
# Conversion monétaire (centimes entiers, ROUND_HALF_UP)
# ---------------------------------------------------------------------------

def test_euros_to_cents_uses_round_half_up() -> None:
    assert euros_to_cents("12.34") == 1234
    assert euros_to_cents("0.005") == 1
    assert euros_to_cents(7) == 700
    assert euros_to_cents(None) is None
    assert euros_to_cents("") is None
    assert euros_to_cents("0.00") == 0


# ---------------------------------------------------------------------------
# Client OAuth et transport
# ---------------------------------------------------------------------------

def test_client_requires_all_credentials() -> None:
    with pytest.raises(CardmarketNotConfiguredError):
        CardmarketClient("token", "", "token", "secret")


def test_authorization_header_is_oauth_signed() -> None:
    client = make_client()
    header = client._authorization_header(
        "GET", "https://api.cardmarket.com/ws/v2.0/output.json/games"
    )
    assert header.startswith('OAuth realm="https%3A%2F%2Fapi.cardmarket.com')
    assert 'oauth_consumer_key="app-token"' in header
    assert 'oauth_token="access-token"' in header
    assert 'oauth_signature_method="HMAC-SHA1"' in header
    assert 'oauth_nonce="abc123"' in header
    assert 'oauth_timestamp="1700000000"' in header
    assert "oauth_signature=" in header


def test_signature_base_url_strips_output_json() -> None:
    client = make_client()
    assert (
        client._signature_base_url(
            "https://api.cardmarket.com/ws/v2.0/output.json/products/9/Pikachu"
        )
        == "https://api.cardmarket.com/ws/v2.0/products/9/Pikachu"
    )


def test_find_products_parses_json(monkeypatch: pytest.MonkeyPatch) -> None:
    client = make_client()
    captured: dict[str, Any] = {}

    def fake_urlopen(request: Any, timeout: float) -> FakeResponse:
        captured["url"] = request.full_url
        captured["authorization"] = request.headers["Authorization"]
        return FakeResponse({"products": [{"idProduct": 123, "name": "Pikachu"}]})

    monkeypatch.setattr(
        "app.cardmarket.client.urllib.request.urlopen", fake_urlopen
    )
    products = client.find_products("Pikachu")

    assert products == [{"idProduct": 123, "name": "Pikachu"}]
    assert "/output.json/products/6/Pikachu" in captured["url"]
    assert captured["authorization"].startswith("OAuth ")


def test_get_product_returns_product_entity(monkeypatch: pytest.MonkeyPatch) -> None:
    client = make_client()
    payload = {
        "product": {
            "idProduct": 123,
            "name": "Pikachu",
            "priceGuide": {"TREND": "12.34"},
        }
    }
    monkeypatch.setattr(
        "app.cardmarket.client.urllib.request.urlopen",
        lambda request, timeout: FakeResponse(payload),
    )
    assert client.get_product(123)["name"] == "Pikachu"


def test_404_raises_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    client = make_client()

    def failing(request: Any, timeout: float) -> Any:
        raise http_error(404)

    monkeypatch.setattr("app.cardmarket.client.urllib.request.urlopen", failing)
    with pytest.raises(CardmarketNotFoundError):
        client.get_games()


def test_429_retries_with_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    client = make_client()
    calls = {"count": 0}
    monkeypatch.setattr("app.cardmarket.client.time.sleep", lambda delay: None)

    def flaky(request: Any, timeout: float) -> FakeResponse:
        calls["count"] += 1
        if calls["count"] == 1:
            raise http_error(429, retry_after="1")
        return FakeResponse({"games": []})

    monkeypatch.setattr("app.cardmarket.client.urllib.request.urlopen", flaky)
    assert client.get_games() == []
    assert calls["count"] == 2


def test_503_exhaustion_raises_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = make_client(max_retries=2)
    monkeypatch.setattr("app.cardmarket.client.time.sleep", lambda delay: None)

    def failing(request: Any, timeout: float) -> Any:
        raise http_error(503)

    monkeypatch.setattr("app.cardmarket.client.urllib.request.urlopen", failing)
    with pytest.raises(CardmarketRateLimitError):
        client.get_games()


# ---------------------------------------------------------------------------
# Service : configuration, stockage, rafraîchissement
# ---------------------------------------------------------------------------

@pytest.fixture
def connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    with connect(tmp_path / "cardmarket.db") as conn:
        apply_migrations(conn)
        yield conn


def test_credentials_configured_and_client_factory() -> None:
    settings = Settings()
    assert not service.credentials_configured(settings)
    with pytest.raises(CardmarketNotConfiguredError):
        service.client_from_settings(settings)

    configured = Settings(
        cardmarket_app_token="a",
        cardmarket_app_secret="b",
        cardmarket_access_token="c",
        cardmarket_access_secret="d",
    )
    assert service.credentials_configured(configured)
    assert isinstance(service.client_from_settings(configured), CardmarketClient)


def test_upsert_price_then_lookup_by_item_name(connection: sqlite3.Connection) -> None:
    price = CardmarketPrice(
        product_id=123,
        card_name="Pikachu",
        expansion_name="Base Set",
        trend_price_cents=1234,
        avg1_price_cents=1200,
        avg7_price_cents=1220,
        avg30_price_cents=1190,
    )
    service.upsert_price(connection, price)

    item = {"name": "pikachu "}
    rows = service.prices_for_item(connection, item)
    assert len(rows) == 1
    assert rows[0]["trend_price_cents"] == 1234
    assert rows[0]["avg30_price_cents"] == 1190
    assert rows[0]["name_base"] == "pikachu"

    # Ré-écriture : mise à jour du même product_id, pas de doublon.
    service.upsert_price(connection, price.model_copy(update={"trend_price_cents": 1500}))
    count = connection.execute(
        "SELECT COUNT(*) AS n FROM cardmarket_prices"
    ).fetchone()
    assert count["n"] == 1
    assert service.prices_for_item(connection, {"name": "Pikachu"})[0]["trend_price_cents"] == 1500


def test_prices_for_item_returns_empty_when_unknown(connection: sqlite3.Connection) -> None:
    assert service.prices_for_item(connection, {"name": "Inconnu"}) == []
    assert service.prices_for_item(connection, {"name": ""}) == []


def test_parse_product_price_extracts_price_guide() -> None:
    price = service.parse_product_price(
        {
            "idProduct": 55,
            "name": "Dracaufeu",
            "expansion": {"enName": "Base Set"},
            "priceGuide": {
                "TREND": "12.34",
                "AVG1": None,
                "AVG7": "11.20",
                "AVG30": "10.99",
            },
        }
    )
    assert price is not None
    assert price.product_id == 55
    assert price.trend_price_cents == 1234
    assert price.avg1_price_cents is None
    assert price.avg7_price_cents == 1120
    assert price.avg30_price_cents == 1099
    assert price.expansion_name == "Base Set"
    assert price.best_known_price_cents == 1234


def test_parse_product_price_rejects_incomplete_product() -> None:
    assert service.parse_product_price({"name": "Sans id"}) is None
    assert service.parse_product_price({"idProduct": 1, "name": ""}) is None


class FakeClient:
    def find_products(self, name: str, game_id: int = 9) -> list[dict[str, Any]]:
        if "Dracaufeu" in name:
            return [{"idProduct": 999, "name": "Charizard"}]
        return [{"idProduct": 998, "name": name}]

    def get_product(self, product_id: int) -> dict[str, Any]:
        return {
            "idProduct": product_id,
            "name": "Pikachu",
            "expansionName": "Scarlet & Violet",
            "priceGuide": {"TREND": "0.45", "AVG1": "0.40", "AVG7": "0.42", "AVG30": "0.44"},
        }


def test_refresh_price_matches_exact_name_and_stores(
    connection: sqlite3.Connection,
) -> None:
    snapshot = service.refresh_price_for_item_with_client(
        connection, {"name": "Pikachu"}, FakeClient()
    )
    assert snapshot is not None
    assert snapshot.trend_price_cents == 45
    stored = service.prices_for_item(connection, {"name": "Pikachu"})
    assert len(stored) == 1
    assert stored[0]["product_id"] == 998


def test_refresh_price_rejects_ambiguous_foreign_name(
    connection: sqlite3.Connection,
) -> None:
    with pytest.raises(CardmarketNotFoundError):
        service.refresh_price_for_item_with_client(
            connection, {"name": "Dracaufeu"}, FakeClient()
        )


def test_best_known_price_falls_back_to_averages() -> None:
    price = CardmarketPrice(product_id=1, card_name="X", trend_price_cents=None, avg7_price_cents=700)
    assert price.best_known_price_cents == 700
    empty = CardmarketPrice(product_id=1, card_name="X")
    assert empty.best_known_price_cents is None


# ---------------------------------------------------------------------------
# Routes web
# ---------------------------------------------------------------------------

@pytest.fixture
def web_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("POKEMON_DATABASE_PATH", str(tmp_path / "web.db"))
    for key in ("CARDMARKET_APP_TOKEN", "CARDMARKET_APP_SECRET", "CARDMARKET_ACCESS_TOKEN", "CARDMARKET_ACCESS_SECRET"):
        monkeypatch.delenv(key, raising=False)
    with TestClient(app) as test_client:
        test_client.post(
            "/imports",
            files={
                "file": (
                    "annonces.jsonl",
                    b'{"external_id":"pika-1","name":"Pikachu",'
                    b'"set_name":"Base Set","price_cents":300}\n',
                    "application/x-ndjson",
                )
            },
        )
        yield test_client


def test_detail_page_shows_cardmarket_empty_state(web_client: TestClient) -> None:
    response = web_client.get("/catalog/1")
    assert response.status_code == 200
    assert "Valeur de marché Cardmarket" in response.text
    assert "Aucune cote Cardmarket en base" in response.text


def test_detail_page_empty_state_when_guide_synced_but_no_match(
    web_client: TestClient, tmp_path: Path
) -> None:
    with connect(tmp_path / "web.db") as connection:
        connection.execute(
            """
            INSERT INTO cardmarket_prices (product_id, card_name, trend_price_cents)
            VALUES (9001, 'Charizard ex', 12345)
            """
        )
        connection.commit()
    response = web_client.get("/catalog/1")
    assert response.status_code == 200
    assert "Aucun produit Cardmarket ne correspond" in response.text


def test_refresh_without_credentials_redirects_with_error(web_client: TestClient) -> None:
    response = web_client.post(
        "/catalog/1/cardmarket/refresh", follow_redirects=False
    )
    assert response.status_code == 303
    assert "error=" in response.headers["location"]

    followed = web_client.get(response.headers["location"])
    assert "API Cardmarket non configurée" in followed.text


def test_refresh_with_unproven_product_stores_but_does_not_display_price(
    web_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.cardmarket.service.client_from_settings", lambda settings: FakeClient()
    )
    response = web_client.post(
        "/catalog/1/cardmarket/refresh", follow_redirects=False
    )
    assert response.status_code == 303
    assert "notice=" in response.headers["location"]

    detail = web_client.get("/catalog/1")
    assert "Cote exacte Cardmarket non disponible" in detail.text
    assert "0,45 €" not in detail.text


def test_refresh_not_found_redirects_with_error(
    web_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class EmptyClient(FakeClient):
        def find_products(self, name: str, game_id: int = 9) -> list[dict[str, Any]]:
            return []

    monkeypatch.setattr(
        "app.cardmarket.service.client_from_settings", lambda settings: EmptyClient()
    )
    response = web_client.post(
        "/catalog/1/cardmarket/refresh", follow_redirects=False
    )
    assert response.status_code == 303
    followed = web_client.get(response.headers["location"])
    assert "Aucun produit Cardmarket" in followed.text


# ---------------------------------------------------------------------------
# Pont multilingue FR · EN · KO · JA · ZH (TCGdex → Cardmarket)
# ---------------------------------------------------------------------------

LOCALE_DATA: dict[str, list[dict[str, Any]]] = {
    "fr": [{"id": "sv03-125", "name": "Dracaufeu-ex"}],
    "en": [{"id": "sv03-125", "name": "Charizard ex"}],
    "ko": [{"id": "sv03-125", "name": "리자몽 ex"}],
    "ja": [{"id": "sv03-125", "name": "リザードンex"}],
    "zh-tw": [{"id": "sv03-125", "name": "噴火龍 ex"}],
}


def locale_fetcher(locale: str) -> list[dict[str, Any]]:
    return LOCALE_DATA[locale]


def seed_reference_card(connection: sqlite3.Connection) -> None:
    connection.execute(
        "INSERT INTO pokemon_reference_sets (id, name) VALUES ('sv03', 'Flammes Obsidiennes')"
    )
    connection.execute(
        "INSERT INTO pokemon_reference_cards (tcgdex_id, local_id, name, set_id, set_name) "
        "VALUES ('sv03-125', '125', 'Dracaufeu-ex', 'sv03', 'Flammes Obsidiennes')"
    )
    connection.commit()


def seed_charizard_prices(connection: sqlite3.Connection) -> None:
    service.upsert_price(
        connection,
        CardmarketPrice(product_id=501, card_name="Charizard ex [Fire Spin]", trend_price_cents=1000),
    )
    service.upsert_price(
        connection,
        CardmarketPrice(product_id=502, card_name="Charizard ex", trend_price_cents=500),
    )


def test_base_card_name_normalizes_suffixes() -> None:
    assert aliases.base_card_name("Charizard [Fire Spin | Wing Attack]") == "charizard"
    assert aliases.base_card_name("Charizard ex") == "charizard ex"
    assert aliases.base_card_name("  Dracaufeu-ex  ") == "dracaufeu-ex"
    assert aliases.base_card_name("Pikachu [Scream]") == "pikachu"
    assert aliases.base_card_name(None) == ""
    assert aliases.base_card_name("") == ""


def test_sync_name_aliases_builds_all_locales(connection: sqlite3.Connection) -> None:
    seed_reference_card(connection)
    result = aliases.sync_name_aliases(connection, fetcher=locale_fetcher)

    assert result["skipped"] == []
    assert result["per_locale"] == {
        "fr": 1,
        "en": 1,
        "ko": 1,
        "ja": 1,
        "zh-tw": 1,
    }
    rows = connection.execute("SELECT locale, name FROM card_name_aliases ORDER BY locale").fetchall()
    assert {(row["locale"], row["name"]) for row in rows} == {
        ("fr", "Dracaufeu-ex"),
        ("en", "Charizard ex"),
        ("ko", "리자몽 ex"),
        ("ja", "リザードンex"),
        ("zh-tw", "噴火龍 ex"),
    }


def test_sync_name_aliases_skips_failing_locale(connection: sqlite3.Connection) -> None:
    seed_reference_card(connection)

    def flaky(locale: str) -> list[dict[str, Any]]:
        if locale == "ja":
            raise RuntimeError("503 Service Unavailable")
        return LOCALE_DATA[locale]

    result = aliases.sync_name_aliases(connection, fetcher=flaky)
    assert result["skipped"] == ["ja"]
    assert result["per_locale"]["en"] == 1


def test_sync_name_aliases_ignores_unknown_cards(connection: sqlite3.Connection) -> None:
    # Aucune carte dans pokemon_reference_cards : rien ne doit être inséré.
    result = aliases.sync_name_aliases(connection, fetcher=locale_fetcher)
    assert all(count == 0 for count in result["per_locale"].values())


def test_french_listing_matches_english_cardmarket_via_alias(
    connection: sqlite3.Connection,
) -> None:
    seed_reference_card(connection)
    aliases.sync_name_aliases(connection, fetcher=locale_fetcher)
    seed_charizard_prices(connection)

    rows = service.prices_for_item(connection, {"name": "Dracaufeu-ex"})
    assert len(rows) == 2  # deux produits partagent le nom de base
    assert {row["product_id"] for row in rows} == {501, 502}


def test_japanese_and_korean_names_match_via_alias(
    connection: sqlite3.Connection,
) -> None:
    seed_reference_card(connection)
    aliases.sync_name_aliases(connection, fetcher=locale_fetcher)
    seed_charizard_prices(connection)

    for name in ("リザードンex", "리자몽 ex", "噴火龍 ex"):
        rows = service.prices_for_item(connection, {"name": name})
        assert len(rows) == 2, f"échec pour {name}"


def test_identified_item_matches_via_ref_tcgdex_id(
    connection: sqlite3.Connection,
) -> None:
    seed_reference_card(connection)
    aliases.sync_name_aliases(connection, fetcher=locale_fetcher)
    seed_charizard_prices(connection)

    item = {"name": "Annonce mal titrée", "ref_tcgdex_id": "sv03-125"}
    rows = service.prices_for_item(connection, item)
    assert len(rows) == 2


def test_english_listing_matches_directly_without_alias(
    connection: sqlite3.Connection,
) -> None:
    seed_charizard_prices(connection)
    rows = service.prices_for_item(connection, {"name": "Charizard ex [anything]"})
    assert len(rows) == 2


def test_unknown_name_returns_no_prices(connection: sqlite3.Connection) -> None:
    seed_reference_card(connection)
    aliases.sync_name_aliases(connection, fetcher=locale_fetcher)
    seed_charizard_prices(connection)
    assert service.prices_for_item(connection, {"name": "Méga-Unknown"}) == []


def test_cardmarket_view_helper_builds_range() -> None:
    import app.web as web_module

    class FakeRow(dict):
        pass

    rows = [
        FakeRow(trend_price_cents=500, currency="EUR"),
        FakeRow(trend_price_cents=1000, currency="EUR"),
    ]
    view = web_module._cardmarket_view(rows)
    assert view is not None
    assert view["count"] == 2
    assert view["single"] is None
    assert view["trend_min"] == 500
    assert view["trend_max"] == 1000

    single = web_module._cardmarket_view([rows[0]])
    assert single["single"] is not None
    assert web_module._cardmarket_view([]) is None


def test_detail_page_rejects_unproven_cardmarket_price_range(
    web_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = service.prices_for_item

    def fake_prices(connection: Any, item: Any) -> list[Any]:
        service.upsert_price(
            connection,
            CardmarketPrice(product_id=601, card_name="Pikachu [A]", trend_price_cents=300),
        )
        service.upsert_price(
            connection,
            CardmarketPrice(product_id=602, card_name="Pikachu [B]", trend_price_cents=900),
        )
        return original(connection, item)

    monkeypatch.setattr("app.cardmarket.service.prices_for_item", fake_prices)
    detail = web_client.get("/catalog/1")
    assert "Cote exacte Cardmarket non disponible" in detail.text
    assert "2 produits trouvés" in detail.text
    assert "9,00 €" not in detail.text


def test_detail_page_displays_only_explicitly_linked_product(web_client: TestClient, tmp_path: Path) -> None:
    with connect(tmp_path / "web.db") as connection:
        with connection:
            connection.execute("INSERT INTO pokemon_reference_sets (id, name) VALUES ('test-set', 'Test')")
            connection.execute("INSERT INTO pokemon_reference_cards (tcgdex_id, local_id, name, set_id, set_name) VALUES ('test-173', '173', 'Pikachu', 'test-set', 'Test')")
            card_id = connection.execute("SELECT id FROM pokemon_reference_cards WHERE tcgdex_id = 'test-173'").fetchone()[0]
            connection.execute("UPDATE catalog_items SET identification_status = 'identified', reference_card_id = ? WHERE id = 1", (card_id,))
        service.upsert_price(connection, CardmarketPrice(product_id=601, card_name="Pikachu [A]", tcg_dex_id="test-173", trend_price_cents=3500))
    detail = web_client.get("/catalog/1")
    assert "PRIX TENDANCE CARDMARKET" in detail.text
    assert "35,00 €" in detail.text
    assert "prix agrégé sans langue ni état confirmés" in detail.text
    with connect(tmp_path / "web.db") as connection:
        with connection:
            connection.execute("UPDATE cardmarket_prices SET trend_price_cents = 0 WHERE product_id = 601")
    detail = web_client.get("/catalog/1")
    assert "Cote exacte Cardmarket non disponible" in detail.text


def test_aliases_sync_route_success(
    web_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.cardmarket.aliases.sync_name_aliases",
        lambda connection: {
            "per_locale": {"fr": 100, "en": 100, "ko": 99, "ja": 0, "zh-tw": 100},
            "skipped": ["ja"],
        },
    )
    response = web_client.post("/cardmarket/aliases/sync", follow_redirects=False)
    assert response.status_code == 303
    assert "notice=" in response.headers["location"]
    page = web_client.get(response.headers["location"])
    assert "Noms multilingues synchronisés" in page.text
    assert "JA" in page.text
