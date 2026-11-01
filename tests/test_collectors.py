import sys
import types
from collections.abc import Iterator

import pytest

from app.collectors.leboncoin import collect_leboncoin_listings
from app.collectors.models import CollectorError
from app.collectors.retry import call_with_backoff
from app.collectors.vinted import collect_vinted_listings, build_vinted_search_params


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

