import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch
import urllib.error

import pytest

from app.storage.database import connect
from app.storage.migration_runner import apply_migrations
from app.tcgdex.cache import TcgdexCache
from app.tcgdex.client import (
    TcgdexClient,
    TcgdexError,
    TcgdexNetworkError,
    TcgdexNotFoundError,
    TcgdexRateLimitError,
)
from app.tcgdex.models import TcgdexCard, TcgdexSet


@pytest.fixture
def connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    db_path = tmp_path / "tcgdex_test.db"
    with connect(db_path) as conn:
        apply_migrations(conn)
        yield conn


def test_tcgdex_cache_seed_initial_and_offline_lookup(connection: sqlite3.Connection) -> None:
    cache = TcgdexCache(connection)
    assert cache.is_empty() is True

    inserted = cache.seed_initial_if_empty()
    assert inserted > 0
    assert cache.is_empty() is False

    # Deuxième appel idempotent
    assert cache.seed_initial_if_empty() == 0

    # Recherche hors-ligne sans aucun appel réseau
    cards = cache.find_cards(name="Dracaufeu")
    assert len(cards) >= 3

    # Recherche avec numéro local
    cards_base = cache.find_cards(name="Dracaufeu", local_id="4")
    assert len(cards_base) == 1
    assert cards_base[0].set_id == "base1"
    assert cards_base[0].tcgdex_id == "base1-4"
    assert cards_base[0].rarity == "Rare Holo"

    # Vérification par identifiant TCGdex
    card = cache.get_card_by_tcgdex_id("swsh3-136")
    assert card is not None
    assert card.name == "Galvagon V"
    assert card.set_name == "Ténèbres Embrasées"

    # Liste des extensions en cache
    sets = cache.list_sets()
    assert len(sets) >= 4
    set_ids = {s["id"] for s in sets}
    assert "base1" in set_ids
    assert "swsh3" in set_ids
    assert "sv03.5" in set_ids


def test_tcgdex_cache_upsert_custom_card_and_set(connection: sqlite3.Connection) -> None:
    cache = TcgdexCache(connection)
    test_set = TcgdexSet(
        id="test-set-1",
        name="Extension Test",
        series="Série Test",
        card_count_total=50,
        card_count_official=50,
        release_date="2024-01-01",
    )
    cache.upsert_set(test_set)

    test_card = TcgdexCard(
        id="test-set-1-001",
        local_id="001",
        name="Pikachu Test",
        set_id="test-set-1",
        set_name="Extension Test",
        rarity="Rare",
        category="Pokemon",
        types=["Électrique"],
        hp=70,
    )
    card_id = cache.upsert_card(test_card)
    assert card_id > 0

    retrieved = cache.get_card_by_id(card_id)
    assert retrieved is not None
    assert retrieved.tcgdex_id == "test-set-1-001"
    assert retrieved.name == "Pikachu Test"
    assert retrieved.local_id == "001"


def test_tcgdex_client_get_sets_mocked() -> None:
    client = TcgdexClient()
    mock_response = [
        {"id": "base1", "name": "Set de Base"},
        {"id": "swsh3", "name": "Ténèbres Embrasées"},
    ]
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_cm = MagicMock()
        mock_cm.read.return_value = json.dumps(mock_response).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_cm

        sets = client.get_sets()
        assert len(sets) == 2
        assert sets[0]["id"] == "base1"


def test_tcgdex_client_handles_404_not_found() -> None:
    client = TcgdexClient()
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://api.tcgdex.net/v2/fr/cards/unknown",
            code=404,
            msg="Not Found",
            hdrs={},
            fp=None,
        )
        with pytest.raises(TcgdexNotFoundError):
            client.get_card("unknown")


def test_tcgdex_client_handles_429_rate_limit() -> None:
    client = TcgdexClient(max_retries=1)
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://api.tcgdex.net/v2/fr/cards/rate-limit",
            code=429,
            msg="Too Many Requests",
            hdrs={},
            fp=None,
        )
        with pytest.raises(TcgdexRateLimitError):
            client.get_card("rate-limit")


def test_tcgdex_client_handles_network_error_without_crashing() -> None:
    client = TcgdexClient(max_retries=1)
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = urllib.error.URLError("DNS resolution failed")
        with pytest.raises(TcgdexNetworkError):
            client.get_sets()
