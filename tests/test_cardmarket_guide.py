"""Tests du synchroniseur de price guide Cardmarket — aucun appel réseau réel."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.cardmarket import guide
from app.storage.database import connect
from app.storage.migration_runner import apply_migrations
from app.web import app

GUIDE_PAYLOAD: dict[str, Any] = {
    "version": 1,
    "createdAt": "2026-11-01T02:47:16+0100",
    "priceGuides": [
        {
            "idProduct": 1001,
            "idCategory": 51,
            "avg": 1.5,
            "low": 1.0,
            "trend": 2.05,
            "avg1": None,
            "avg7": 2.0,
            "avg30": 1.95,
            "trend-holo": 5.0,
        },
        {
            "idProduct": 1002,
            "idCategory": 51,
            "avg": 150,
            "low": 100,
            "trend": 174.5,
            "avg1": None,
            "avg7": None,
            "avg30": None,
        },
        {
            "idProduct": 9999,
            "idCategory": 51,
            "trend": 3.0,
        },
    ],
}

CATALOGUE_PAYLOAD: dict[str, Any] = {
    "version": 1,
    "createdAt": "2026-11-01T11:49:19+0100",
    "products": [
        {"idProduct": 1001, "name": "Pikachu", "idExpansion": 10},
        {"idProduct": 1002, "name": "Charizard", "idExpansion": 11},
        # 9999 est volontairement absent du catalogue.
    ],
}


def fake_fetcher(url: str) -> dict[str, Any]:
    if "priceGuide" in url:
        return GUIDE_PAYLOAD
    if "products_singles" in url:
        return CATALOGUE_PAYLOAD
    raise ValueError(f"URL inattendue : {url}")


def test_parse_price_entries_converts_to_cents() -> None:
    prices = guide.parse_price_entries(GUIDE_PAYLOAD["priceGuides"])
    assert prices[1001] == {
        "trend": 205,
        "avg1": None,
        "avg7": 200,
        "avg30": 195,
    }
    assert prices[1002]["trend"] == 17450
    assert prices[1002]["avg1"] is None


def test_parse_price_entries_skips_invalid_rows() -> None:
    prices = guide.parse_price_entries([{}, {"idProduct": "x"}, {"idProduct": 7}])
    assert prices == {7: {"trend": None, "avg1": None, "avg7": None, "avg30": None}}


def test_parse_product_entries() -> None:
    products = guide.parse_product_entries(
        [
            {"idProduct": 1, "name": "Mew "},
            {"idProduct": 2, "name": ""},
            {"idProduct": 3},
            {"idProduct": "4", "name": "Mewtwo"},
        ]
    )
    assert products == {1: "Mew", 4: "Mewtwo"}


def test_to_utc_iso_converts_cardmarket_timezone() -> None:
    assert guide.to_utc_iso("2026-11-01T02:47:16+0100") == "2026-11-01T01:47:16Z"
    assert guide.to_utc_iso(None).endswith("Z")
    assert guide.to_utc_iso("pas-une-date").endswith("Z")


@pytest.fixture
def connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    with connect(tmp_path / "guide.db") as conn:
        apply_migrations(conn)
        yield conn


def test_sync_price_guide_stores_joined_prices(
    connection: sqlite3.Connection,
) -> None:
    result = guide.sync_price_guide(connection, fetcher=fake_fetcher)

    assert result["guide_products"] == 3
    assert result["synced"] == 2
    assert result["skipped"] == 1
    assert result["created_at"] == "2026-11-01T01:47:16Z"

    rows = connection.execute(
        "SELECT product_id, card_name, trend_price_cents, avg7_price_cents, "
        "avg30_price_cents, currency, fetched_at, name_base FROM cardmarket_prices "
        "ORDER BY product_id"
    ).fetchall()
    assert len(rows) == 2
    assert rows[0]["product_id"] == 1001
    assert rows[0]["card_name"] == "Pikachu"
    assert rows[0]["trend_price_cents"] == 205
    assert rows[0]["avg7_price_cents"] == 200
    assert rows[0]["currency"] == "EUR"
    assert rows[0]["fetched_at"] == "2026-11-01T01:47:16Z"
    assert rows[0]["name_base"] == "pikachu"
    assert rows[1]["card_name"] == "Charizard"
    assert rows[1]["trend_price_cents"] == 17450
    assert rows[1]["name_base"] == "charizard"


def test_sync_price_guide_is_idempotent(connection: sqlite3.Connection) -> None:
    guide.sync_price_guide(connection, fetcher=fake_fetcher)
    guide.sync_price_guide(connection, fetcher=fake_fetcher)
    count = connection.execute(
        "SELECT COUNT(*) AS n FROM cardmarket_prices"
    ).fetchone()["n"]
    assert count == 2


def test_sync_price_guide_updates_existing_product(
    connection: sqlite3.Connection,
) -> None:
    guide.sync_price_guide(connection, fetcher=fake_fetcher)
    updated = {
        **GUIDE_PAYLOAD,
        "priceGuides": [
            {**GUIDE_PAYLOAD["priceGuides"][0], "trend": 3.10},
        ],
    }

    def fetcher(url: str) -> dict[str, Any]:
        return updated if "priceGuide" in url else CATALOGUE_PAYLOAD

    guide.sync_price_guide(connection, fetcher=fetcher)
    row = connection.execute(
        "SELECT trend_price_cents FROM cardmarket_prices WHERE product_id = 1001"
    ).fetchone()
    assert row["trend_price_cents"] == 310


# ---------------------------------------------------------------------------
# Route web
# ---------------------------------------------------------------------------

@pytest.fixture
def web_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("POKEMON_DATABASE_PATH", str(tmp_path / "web.db"))
    with TestClient(app) as test_client:
        yield test_client


def test_sync_route_success_redirects_with_notice(
    web_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.cardmarket.guide.sync_price_guide",
        lambda connection: {
            "created_at": "2026-11-01T01:47:16Z",
            "guide_products": 3,
            "synced": 2,
            "skipped": 1,
        },
    )
    response = web_client.post("/cardmarket/sync", follow_redirects=False)
    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith("/reglages?notice=")
    assert "1%20produits%20sans%20nom" in location

    page = web_client.get(location)
    assert "Cotes Cardmarket synchronisées" in page.text


def test_sync_route_failure_redirects_with_error(
    web_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing(connection: Any) -> dict[str, Any]:
        raise RuntimeError("Cardmarket indisponible")

    monkeypatch.setattr("app.cardmarket.guide.sync_price_guide", failing)
    response = web_client.post("/cardmarket/sync", follow_redirects=False)
    assert response.status_code == 303
    assert "error=" in response.headers["location"]
    page = web_client.get(response.headers["location"])
    assert "Synchronisation Cardmarket impossible" in page.text
