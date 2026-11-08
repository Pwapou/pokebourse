import sys
import types
from collections.abc import Iterator

import pytest

from app.collectors.ebay import build_ebay_search_params, collect_ebay_listings
from app.collectors.leboncoin import collect_leboncoin_listings
from app.collectors.models import CollectorError
from app.collectors.normalizer import normalize_ebay_item, normalize_wallapop_item
from app.collectors.retry import call_with_backoff
from app.collectors.vinted import collect_vinted_listings, build_vinted_search_params
from app.collectors.wallapop import build_wallapop_search_params, collect_wallapop_listings


class Response429:
    status_code = 429


class TemporaryError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("temporaire")
        self.response = Response429()


class Response403:
    status_code = 403


class ForbiddenError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("interdit")
        self.response = Response403()


def test_exponential_backoff_recovers_from_temporary_error() -> None:
    attempts = 0
    sleeps: list[float] = []

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise TemporaryError()
        return "ok"

    result = call_with_backoff(
        operation,
        operation_name="test réseau",
        attempts=3,
        base_delay_seconds=1,
        sleep=sleeps.append,
    )

    assert result == "ok"
    assert attempts == 3
    assert len(sleeps) == 2
    assert sleeps[1] > sleeps[0] * 0.8


def test_backoff_never_retries_forbidden_response() -> None:
    attempts = 0

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        raise ForbiddenError()

    with pytest.raises(CollectorError):
        call_with_backoff(
            operation,
            operation_name="test réseau",
            attempts=3,
            sleep=lambda _delay: None,
        )
    assert attempts == 1


def test_vinted_search_params_are_bounded_and_newest() -> None:
    params = build_vinted_search_params(
        search_text="Carte Pokémon Pikachu",
        price_from=1000,
        price_to=2500,
        per_page=500,
    )

    assert params == {
        "search_text": "Carte Pokémon Pikachu",
        "order": "newest",
        "page": 1,
        "per_page": 48,
        "price_from": "10.00",
        "price_to": "25.00",
    }


def test_vinted_connector_uses_specialized_library_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    class FakeScraper:
        def __init__(self, domain: str) -> None:
            assert domain == "https://www.vinted.fr"

        def search(self, params: dict[str, object]) -> list[object]:
            calls.append(params)
            return [
                {
                    "id": 101,
                    "title": "Carte Pokémon Pikachu",
                    "price": "10,00",
                    "url": "https://www.vinted.fr/items/101",
                    "user": {"login": "Vendeur Vinted"},
                }
            ]

    fake_module = types.SimpleNamespace(VintedScraper=FakeScraper)
    monkeypatch.setitem(sys.modules, "vinted_scraper", fake_module)

    result = collect_vinted_listings(search_text="Pikachu", per_page=10)

    assert calls[0]["order"] == "newest"
    assert calls[0]["page"] == 1
    assert len(result.listings) == 1
    assert result.listings[0].external_id == "101"
    assert result.listings[0].seller == "Vendeur Vinted"
    assert result.invalid_count == 0


def test_leboncoin_connector_uses_lbc_library_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []

    class FakeResult:
        ads = [
            {
                "id": 202,
                "subject": "Carte Pokémon Mew",
                "price": "8,50",
                "url": "https://www.leboncoin.fr/ad/202",
                "owner": {"name": "Vendeur LBC"},
            }
        ]

    class FakeClient:
        def search(self, **kwargs: object) -> FakeResult:
            calls.append(kwargs)
            return FakeResult()

    fake_module = types.SimpleNamespace(
        Client=FakeClient,
        Sort=types.SimpleNamespace(NEWEST="newest"),
        AdType=types.SimpleNamespace(OFFER="offer"),
        Category=types.SimpleNamespace(COLLECTIONS="collections"),
    )
    monkeypatch.setitem(sys.modules, "lbc", fake_module)

    result = collect_leboncoin_listings(
        text="Mew",
        price_from=500,
        price_to=1500,
        limit=500,
        category="COLLECTIONS",
    )

    assert calls == [
        {
            "text": "Mew",
            "page": 1,
            "limit": 100,
            "sort": "newest",
            "ad_type": "offer",
            "price": [500, 1500],
            "category": "collections",
        }
    ]
    assert len(result.listings) == 1
    assert result.listings[0].external_id == "202"
    assert result.listings[0].price_cents == 850


def test_vinted_empty_collection(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeScraper:
        def __init__(self, domain: str) -> None:
            pass

        def search(self, params: dict[str, object]) -> list[object]:
            return []

    fake_module = types.SimpleNamespace(VintedScraper=FakeScraper)
    monkeypatch.setitem(sys.modules, "vinted_scraper", fake_module)

    result = collect_vinted_listings(search_text="Introuvable 999999")
    assert result.listings == []
    assert result.invalid_count == 0


def test_leboncoin_empty_collection(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeClient:
        def search(self, **kwargs: object) -> list[object]:
            return []

    fake_module = types.SimpleNamespace(
        Client=FakeClient,
        Sort=types.SimpleNamespace(NEWEST="newest"),
        AdType=types.SimpleNamespace(OFFER="offer"),
    )
    monkeypatch.setitem(sys.modules, "lbc", fake_module)

    result = collect_leboncoin_listings(text="Introuvable 999999")
    assert result.listings == []
    assert result.invalid_count == 0


def test_leboncoin_datadome_anti_bot_blocks_without_bypass(monkeypatch: pytest.MonkeyPatch) -> None:
    class DataDomeError(Exception):
        pass

    class FakeClient:
        def search(self, **kwargs: object) -> object:
            raise DataDomeError("Blocked by DataDome protection")

    fake_module = types.SimpleNamespace(
        Client=FakeClient,
        Sort=types.SimpleNamespace(NEWEST="newest"),
        AdType=types.SimpleNamespace(OFFER="offer"),
    )
    monkeypatch.setitem(sys.modules, "lbc", fake_module)

    with pytest.raises(CollectorError, match="DataDome"):
        collect_leboncoin_listings(text="Pikachu")


@pytest.mark.parametrize(
    "price_from,price_to,expected_from,expected_to",
    [
        (0, 0, "0.00", "0.00"),
        (1, 105, "0.01", "1.05"),
        (5, 499, "0.05", "4.99"),
        (10_000_000, 999_999_999, "100000.00", "9999999.99"),
    ],
)
def test_price_filter_conversion_is_exact_and_rounded(
    price_from: int,
    price_to: int,
    expected_from: str,
    expected_to: str,
) -> None:
    vinted_params = build_vinted_search_params(
        search_text="Pikachu", price_from=price_from, price_to=price_to
    )
    ebay_params = build_ebay_search_params(
        search_text="Pikachu", price_from=price_from, price_to=price_to
    )

    assert vinted_params["price_from"] == expected_from
    assert vinted_params["price_to"] == expected_to
    assert ebay_params["_udlo"] == expected_from
    assert ebay_params["_udhi"] == expected_to


def test_ebay_search_params_and_collection() -> None:
    params = build_ebay_search_params(
        search_text="Dracaufeu Holo",
        price_from=1500,
        price_to=5000,
        per_page=25,
    )
    assert params["_nkw"] == "Dracaufeu Holo"
    assert params["_udlo"] == "15.00"
    assert params["_udhi"] == "50.00"
    assert params["_ipg"] == 25

    fake_items = [
        {
            "id": "11223344",
            "title": "Carte Pokémon Dracaufeu Holo",
            "price": "35,00",
            "shipping": "4,50",
            "url": "https://www.ebay.fr/itm/11223344",
            "image": "https://i.ebayimg.com/images/g/xyz/s-l1600.jpg",
            "seller": "PokeSellerEbay",
        }
    ]

    result = collect_ebay_listings(
        search_text="Dracaufeu",
        search_func=lambda _p: fake_items,
    )
    assert len(result.listings) == 1
    listing = result.listings[0]
    assert listing.source == "ebay"
    assert listing.external_id == "11223344"
    assert listing.price_cents == 3500
    assert listing.shipping_cents == 450
    assert listing.seller == "PokeSellerEbay"
    assert str(listing.url) == "https://www.ebay.fr/itm/11223344"


def test_wallapop_search_params_and_collection() -> None:
    params = build_wallapop_search_params(
        search_text="Mewtwo GX",
        price_from=1000,
        price_to=3000,
    )
    assert params["keywords"] == "Mewtwo GX"
    assert params["min_sale_price"] == 10
    assert params["max_sale_price"] == 30

    fake_items = [
        {
            "id": "w-998877",
            "title": "Carte Pokémon Mewtwo GX",
            "price": "20.00",
            "web_slug": "carte-pokemon-mewtwo-gx-998877",
            "images": [{"original": "https://cdn.wallapop.com/images/10420/item.jpg"}],
            "user": {"micro_name": "PokeSellerWalla"},
        }
    ]

    result = collect_wallapop_listings(
        search_text="Mewtwo",
        search_func=lambda _p: fake_items,
    )
    assert len(result.listings) == 1
    listing = result.listings[0]
    assert listing.source == "wallapop"
    assert listing.external_id == "w-998877"
    assert listing.price_cents == 2000
    assert listing.seller == "PokeSellerWalla"
    assert str(listing.url) == "https://fr.wallapop.com/item/carte-pokemon-mewtwo-gx-998877"

