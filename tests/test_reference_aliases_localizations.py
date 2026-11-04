"""Localisations du référentiel, alias contrôlés et recherche alias (T05).

Aucun réseau réel : la synchronisation locale simulée reprend le style du
client factice de test_tcgdex_sync. Aucun alias n'est jamais fabriqué
automatiquement : « gempack 2 » reste non résolu et aucune écriture n'apparaît.
"""

import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.identification.aliases import (
    ALIAS_VERSION,
    register_alias,
    resolve_alias,
    set_alias_status,
    suggest_aliases,
)
from app.identification.diagnostics import identification_diagnostics
from app.identification.reference_search import search_references
from app.storage.database import connect
from app.storage.migration_runner import apply_migrations
from app.tcgdex.cache import TcgdexCache
from app.tcgdex.models import TcgdexCard, TcgdexSet
from app.tcgdex.sync import enqueue_sync, process_sync_step

NOW = datetime(2026, 11, 1, 10, tzinfo=UTC)


@pytest.fixture
def database(tmp_path: Path) -> Iterator[tuple[sqlite3.Connection, Path]]:
    path = tmp_path / "aliases.db"
    with connect(path) as connection:
        apply_migrations(connection)
        cache = TcgdexCache(connection)
        cache.seed_initial_if_empty()
        connection.commit()
        yield connection, path


def seed_two_cards(connection: sqlite3.Connection) -> tuple[int, int]:
    cache = TcgdexCache(connection)
    cache.upsert_set(TcgdexSet(id="base1", name="Set de Base", card_count_total=102))
    first = cache.upsert_card(TcgdexCard(id="base1-4", local_id="4", name="Dracaufeu", set_id="base1", set_name="Set de Base"))
    second = cache.upsert_card(TcgdexCard(id="base1-5", local_id="5", name="Tortank", set_id="base1", set_name="Set de Base"))
    return first, second


class FakeLocaleClient:
    """API locale simulée ; chaque appel vérifie l'absence de transaction SQLite."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.base_url: str | None = None
        self.manifest = {"id": "test", "name": "Test Set", "cardCount": {"official": 1, "total": 1},
                         "cards": [{"id": "test-1", "localId": "1", "name": "Testmon"}]}

    def get_set(self, set_id: str) -> dict:
        assert not self.connection.in_transaction
        return self.manifest

    def get_card(self, card_id: str) -> dict:
        assert not self.connection.in_transaction
        summary = next(card for card in self.manifest["cards"] if card["id"] == card_id)
        return {**summary, "set": {"id": "test", "name": "Test Set"}, "category": "Pokemon"}


def test_localizations_coexist_without_overwriting_internal_ids(database: tuple[sqlite3.Connection, Path]) -> None:
    connection, _ = database
    cache = TcgdexCache(connection)
    cache.upsert_set(TcgdexSet(id="base1", name="Set de Base", card_count_total=102))
    french_id = cache.upsert_card(TcgdexCard(id="base1-4", local_id="4", name="Dracaufeu", set_id="base1", set_name="Set de Base"))
    english_id = cache.upsert_card(TcgdexCard(id="base1-4", local_id="4", name="Charizard", set_id="base1", set_name="Base Set", reference_language="en"))

    assert french_id != english_id
    rows = connection.execute("SELECT reference_language, name FROM pokemon_reference_cards WHERE tcgdex_id='base1-4' ORDER BY reference_language").fetchall()
    assert [(row["reference_language"], row["name"]) for row in rows] == [("en", "Charizard"), ("fr", "Dracaufeu")]

    # La réécriture d'une localisation conserve son identifiant interne.
    rewritten = cache.upsert_card(TcgdexCard(id="base1-4", local_id="4", name="Dracaufeu EX", set_id="base1", set_name="Set de Base"))
    assert rewritten == french_id
    assert cache.get_card_by_id(french_id).name == "Dracaufeu EX"

    # « fr » reste la localisation de référence par défaut.
    assert cache.get_card_by_tcgdex_id("base1-4").reference_language == "fr"
    assert cache.get_card_by_tcgdex_id("base1-4", locale="en").reference_language == "en"
    localizations = cache.get_card_localizations("base1-4")
    assert [record.reference_language for record in localizations] == ["fr", "en"]
    assert cache.get_card_by_tcgdex_id("absent-1") is None


def test_register_alias_validates_target_and_degrades_collisions(database: tuple[sqlite3.Connection, Path]) -> None:
    connection, _ = database
    first, second = seed_two_cards(connection)
    registered = register_alias(connection, "Dracaufeu Holo 1re édition", first, provenance="manual", operator="op-1")
    assert registered["status"] == "active" and registered["version"] == ALIAS_VERSION
    assert registered["raw_alias"] == "Dracaufeu Holo 1re édition"

    # Une collision dégrade l'ancien alias en suggestion, sans l'effacer.
    colliding = register_alias(connection, "dracaufeu holo 1re edition", second, provenance="import", operator="op-2")
    assert colliding["status"] == "suggestion"
    statuses = dict(connection.execute("SELECT target_card_id, status FROM reference_aliases WHERE alias='dracaufeu holo 1re edition'").fetchall())
    assert statuses == {first: "suggestion", second: "suggestion"}

    with pytest.raises(LookupError):
        register_alias(connection, "cible absente", 9999)
    with pytest.raises(ValueError, match="Périmètre"):
        register_alias(connection, "mauvais périmètre", first, scope="imprime")
    with pytest.raises(ValueError, match="provenance"):
        register_alias(connection, "mauvaise provenance", first, provenance="robot")

    alias_id = colliding["id"]
    set_alias_status(connection, alias_id, "active", operator="op-3")
    assert connection.execute("SELECT status FROM reference_aliases WHERE id=?", (alias_id,)).fetchone()[0] == "active"
    with pytest.raises(ValueError, match="Statut"):
        set_alias_status(connection, alias_id, "imprime")
    with pytest.raises(LookupError):
        set_alias_status(connection, 9999, "active")


def test_resolve_alias_exact_collision_suggestion_and_unresolved(database: tuple[sqlite3.Connection, Path]) -> None:
    connection, _ = database
    first, second = seed_two_cards(connection)
    register_alias(connection, "Le Lézard Flamboyant", first)
    exact = resolve_alias(connection, "le lézard flamboyant")
    assert exact.status == "exact" and not exact.approximate
    assert [match["target_card_id"] for match in exact.matches] == [first]

    register_alias(connection, "Le Lézard Flamboyant", second)
    collision = resolve_alias(connection, "Le Lézard Flamboyant")
    assert collision.approximate and len(collision.matches) == 2

    register_alias(connection, "Tortank Bizarre", second, locale="en")
    localized = resolve_alias(connection, "Tortank Bizarre", locale="fr")
    assert localized.status == "none"  # un alias anglais ne répond pas pour le français

    # Cas non vérifié : aucune écriture, aucune résolution.
    unresolved = resolve_alias(connection, "gempack 2")
    assert unresolved.status == "none" and unresolved.matches == ()
    assert suggest_aliases(connection, "gempack 2") == []
    assert connection.execute("SELECT count(*) FROM reference_aliases").fetchone()[0] == 3
    assert resolve_alias(connection, "   ").status == "none"


def test_suggest_aliases_is_fuzzy_and_never_writes(database: tuple[sqlite3.Connection, Path]) -> None:
    connection, _ = database
    first, _ = seed_two_cards(connection)
    register_alias(connection, "Dracaufeu Soleil et Lune", first)
    before = connection.execute("SELECT count(*) FROM reference_aliases").fetchone()[0]

    exact_hit = suggest_aliases(connection, "Dracaufeu Soleil et Lune")
    assert len(exact_hit) == 1 and exact_hit[0]["status"] == "suggestion" and exact_hit[0]["distance"] == 0
    fuzzy = suggest_aliases(connection, "Dracaufeu Soleil et Lun")
    assert fuzzy and fuzzy[0]["distance"] == 1 and fuzzy[0]["target_card_id"] == first
    assert all(item["status"] == "suggestion" for item in fuzzy)
    assert suggest_aliases(connection, "xyzzy inconnu au bataillon") == []
    assert connection.execute("SELECT count(*) FROM reference_aliases").fetchone()[0] == before


def test_search_references_redirects_exact_alias_and_marks_approximate(database: tuple[sqlite3.Connection, Path]) -> None:
    connection, _ = database
    first, second = seed_two_cards(connection)
    cache = TcgdexCache(connection)
    register_alias(connection, "Le Lézard", first)

    redirected = search_references(cache, name="Le Lézard")
    assert redirected.approximate is False
    assert [card.id for card in redirected.cards] == [first]

    register_alias(connection, "Le Lézard", second)
    ambiguous = search_references(cache, name="Le Lézard")
    assert ambiguous.approximate is True and len(ambiguous.cards) == 2

    fuzzy = search_references(cache, name="Le Lézards")
    assert fuzzy.approximate is True and fuzzy.cards

    plain = search_references(cache, name="Dracaufeu")
    assert any(card.id == first for card in plain.cards)


def test_search_references_alias_does_not_override_explicit_filters(database: tuple[sqlite3.Connection, Path]) -> None:
    connection, _ = database
    first, second = seed_two_cards(connection)
    cache = TcgdexCache(connection)
    # L'alias porte le nom réel d'une autre carte : seul le garde-fou filtre
    # empêche la redirection de court-circuiter la recherche exacte.
    register_alias(connection, "Tortank", first)

    redirected = search_references(cache, name="Tortank")
    assert [card.id for card in redirected.cards] == [first]

    # Avec un filtre numéro, l'alias ne redirige plus : la recherche exacte
    # classique s'applique et retourne la carte correspondant au critère.
    filtered = search_references(cache, name="Tortank", local_id="5")
    assert [card.id for card in filtered.cards] == [second]
    assert filtered.approximate is False

    by_set = search_references(cache, name="Tortank", set_name="Set de Base")
    assert second in {card.id for card in by_set.cards}, "la recherche classique reste possible avec un filtre extension"
    assert by_set.approximate is False


def test_sync_job_carries_locale_and_stores_localized_cards(database: tuple[sqlite3.Connection, Path]) -> None:
    connection, _ = database
    job_id = enqueue_sync(connection, "test", locale="en", now=NOW)
    job = connection.execute("SELECT * FROM tcgdex_sync_jobs WHERE id=?", (job_id,)).fetchone()
    assert job["locale"] == "en" and job["resource_key"] == "set:test:en"
    client = FakeLocaleClient(connection)
    for step in range(6):
        process_sync_step(connection, client, now=NOW + timedelta(seconds=2 * step))
    rows = connection.execute("SELECT reference_language, name FROM pokemon_reference_cards WHERE tcgdex_id='test-1'").fetchall()
    assert [(row["reference_language"], row["name"]) for row in rows] == [("en", "Testmon")]
    assert connection.execute("SELECT status FROM tcgdex_sync_jobs WHERE id=?", (job_id,)).fetchone()[0] == "completed"

    # La locale « fr » conserve la clé historique et n'écrase pas l'anglais.
    french_id = enqueue_sync(connection, "test", locale="fr", now=NOW)
    assert connection.execute("SELECT resource_key FROM tcgdex_sync_jobs WHERE id=?", (french_id,)).fetchone()[0] == "set:test"
    for step in range(6):
        process_sync_step(connection, client, now=NOW + timedelta(seconds=20 + 2 * step))
    languages = [row[0] for row in connection.execute("SELECT reference_language FROM pokemon_reference_cards WHERE tcgdex_id='test-1'").fetchall()]
    assert sorted(languages) == ["en", "fr"]

    with pytest.raises(ValueError, match="Locale"):
        enqueue_sync(connection, "test", locale="FR", now=NOW)
    with pytest.raises(ValueError, match="Locale"):
        enqueue_sync(connection, "test", locale="e", now=NOW)


def test_diagnostics_reports_localization_coverage(database: tuple[sqlite3.Connection, Path]) -> None:
    connection, _ = database
    cache = TcgdexCache(connection)
    cache.upsert_set(TcgdexSet(id="base1", name="Set de Base", card_count_total=102))
    cache.upsert_card(TcgdexCard(id="base1-4", local_id="4", name="Dracaufeu", set_id="base1", set_name="Set de Base", image_url="https://img.example/4.png", rarity="Rare"))
    cache.upsert_card(TcgdexCard(id="base1-4", local_id="4", name="Charizard", set_id="base1", set_name="Base Set", reference_language="en", rarity="Rare"))
    cache.upsert_card(TcgdexCard(id="base1-5", local_id="5", name="Tortank", set_id="base1", set_name="Set de Base", rarity="Common"))
    register_alias(connection, "Le Lézard", connection.execute("SELECT id FROM pokemon_reference_cards WHERE tcgdex_id='base1-4' AND reference_language='fr'").fetchone()[0])
    connection.commit()

    report = identification_diagnostics(connection, status="all", limit=10)
    localization = report["catalog"]["localization"]
    assert localization["covered_locales"] == ["en", "fr"]
    assert localization["multi_locale_identities"] == 1
    assert localization["cards_missing_image_url"] == 2  # fiche en sans image + Tortank
    assert localization["cards_missing_details"] == 0
    assert localization["aliases_active"] == 1 and localization["aliases_suggestions"] == 0
    assert "n'active aucune identification" in localization["note"]
