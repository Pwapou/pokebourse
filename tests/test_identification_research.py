import json
import sqlite3
from pathlib import Path

import pytest

from app.identification.matcher import CardMatcher
from app.identification.normalization import canonical_local_id
from app.identification.research import claim_search, enqueue_search, process_claimed_search
from app.identification.resolution import IdentificationConflictError, apply_resolution, confirm_card, resolve_listing, revoke_confirmation
from app.storage.database import connect
from app.storage.migration_runner import apply_migrations
from app.tcgdex.cache import TcgdexCache


def make_item(connection: sqlite3.Connection, title: str = "Dracaufeu 004/102 Set de Base") -> int:
    connection.execute("INSERT OR IGNORE INTO sources(name, kind) VALUES ('test', 'manual_jsonl')")
    connection.execute("INSERT INTO import_batches(source_id, input_checksum) VALUES (1, ?)", (title,))
    cursor = connection.execute(
        "INSERT INTO catalog_items(source_id, import_batch_id, external_id, name, set_name, original_title, price_cents) VALUES (1, 1, ?, ?, 'Inconnue', ?, 1000)",
        (title, title, title),
    )
    return int(cursor.lastrowid)


def test_numbers_are_structural() -> None:
    assert canonical_local_id("004") == canonical_local_id("4")
    assert canonical_local_id("4") != canonical_local_id("14")
    assert canonical_local_id("4") != canonical_local_id("104")
    assert canonical_local_id("SWSH004") == canonical_local_id("swsh4")


def test_accents_and_dynamic_vocabulary(tmp_path: Path) -> None:
    with connect(tmp_path / "test.db") as connection:
        apply_migrations(connection)
        matcher = CardMatcher(TcgdexCache(connection))
        result = matcher.identify("Dracaufeu 4/102 Set de Base")
        assert result.status == "identified"
        assert result.matched_card.tcgdex_id == "base1-4"


def test_confirmation_survives_reidentification_and_revoke(tmp_path: Path) -> None:
    with connect(tmp_path / "test.db") as connection:
        apply_migrations(connection)
        cache = TcgdexCache(connection); cache.seed_initial_if_empty()
        item_id = make_item(connection)
        apply_resolution(connection, item_id, resolve_listing(connection, item_id))
        resolution = resolve_listing(connection, item_id)
        confirm_card(connection, item_id, resolution.result.matched_card.id, resolution.evidence_hash, resolution.revision)
        confirmed = resolve_listing(connection, item_id)
        assert confirmed.decision_source == "human"
        apply_resolution(connection, item_id, confirmed)
        revoke_confirmation(connection, item_id, confirmed.evidence_hash, confirmed.revision)
        assert resolve_listing(connection, item_id).decision_source == "automatic"
        assert connection.execute("SELECT COUNT(*) FROM listing_identification_decisions").fetchone()[0] == 2


def test_confirmation_conflict_and_lot_guard(tmp_path: Path) -> None:
    with connect(tmp_path / "test.db") as connection:
        apply_migrations(connection); TcgdexCache(connection).seed_initial_if_empty()
        item_id = make_item(connection)
        resolution = resolve_listing(connection, item_id)
        with pytest.raises(IdentificationConflictError):
            confirm_card(connection, item_id, 1, resolution.evidence_hash, 999)
        lot_id = make_item(connection, "Lot de 50 cartes Pokémon")
        lot = resolve_listing(connection, lot_id)
        with pytest.raises(ValueError, match="lot"):
            confirm_card(connection, lot_id, 1, lot.evidence_hash, lot.revision)


def test_persistent_remote_search_and_stale_lease(tmp_path: Path) -> None:
    class Client:
        def search_cards(self, **criteria):
            return [{"id": "new-004", "name": "Nouveau", "localId": "004", "set": {"id": "new", "name": "Nouvelle Extension"}}]
    with connect(tmp_path / "test.db") as connection:
        apply_migrations(connection); TcgdexCache(connection).seed_initial_if_empty()
        item_id = make_item(connection, "Nouveau #004 Nouvelle Extension")
        search_id = enqueue_search(connection, item_id, {"name": "Nouveau", "local_id": "4"})
        assert enqueue_search(connection, item_id, {"name": "Nouveau", "local_id": "004"}) == search_id
        connection.commit()
        claimed = claim_search(connection, "worker-test")
        assert claimed["id"] == search_id
        process_claimed_search(connection, claimed, Client())
        assert TcgdexCache(connection).get_card_by_tcgdex_id("new-004") is not None
        assert connection.execute("SELECT status FROM identification_searches WHERE id=?", (search_id,)).fetchone()[0] == "completed"


def test_summary_does_not_erase_details(tmp_path: Path) -> None:
    from app.tcgdex.models import TcgdexCard, TcgdexSet
    with connect(tmp_path / "test.db") as connection:
        apply_migrations(connection)
        cache = TcgdexCache(connection); cache.upsert_set(TcgdexSet(id="s", name="Set"))
        cache.upsert_card(TcgdexCard(id="s-1", local_id="1", name="Carte", set_id="s", set_name="Set", rarity="Rare", image_url="image"))
        cache.upsert_card(TcgdexCard(id="s-1", local_id="1", name="Carte", set_id="s", set_name="Set"))
        card = cache.get_card_by_tcgdex_id("s-1")
        assert card.rarity == "Rare"
        assert card.image_url == "image"
