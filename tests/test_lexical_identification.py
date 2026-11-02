"""Régressions de récupération lexicale et du diagnostic, sans appel réseau."""

import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.cli import main
from app.identification.annotation_pilot import sample_pilot
from app.identification.dataset import build_dataset
from app.identification.diagnostics import identification_diagnostics
from app.identification.lexical import LexicalNameIndex, bounded_edit_distance
from app.identification.matcher import CardMatcher
from app.identification.reference_search import search_references
from app.storage.database import connect
from app.storage.migration_runner import apply_migrations
from app.tcgdex.cache import TcgdexCache
from app.tcgdex.models import TcgdexCard, TcgdexSet
from app.web import app


@pytest.fixture
def connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    with connect(tmp_path / "lexical.db") as connection:
        apply_migrations(connection)
        TcgdexCache(connection).seed_initial_if_empty()
        connection.commit()
        yield connection


def add_listing(connection: sqlite3.Connection, title: str | None, *, description: str | None = None) -> int:
    """Représente une annonce restée non identifiée avant la nouvelle recherche."""
    with connection:
        connection.execute("INSERT OR IGNORE INTO sources(name, kind) VALUES ('lexical-test', 'manual_jsonl')")
        source_id = connection.execute("SELECT id FROM sources WHERE name='lexical-test'").fetchone()[0]
        cursor = connection.execute("INSERT INTO import_batches(source_id, input_checksum) VALUES (?, ?)",
                                    (source_id, f"lexical-{connection.total_changes}"))
        batch_id = cursor.lastrowid
        cursor = connection.execute(
            """INSERT INTO catalog_items(source_id, import_batch_id, external_id, name,
            original_title, set_name, price_cents, raw_data, identification_status)
            VALUES (?, ?, ?, 'Identité déjà recalculée', ?, 'Inconnue', 100, ?, 'unidentified')""",
            (source_id, batch_id, f"listing-{batch_id}", title, json.dumps({"description": description})),
        )
        return int(cursor.lastrowid)


@pytest.mark.parametrize(("left", "right", "expected"), [
    ("dracofeu", "dracaufeu", 2), ("dracafueu", "dracaufeu", 1),
    ("pikchu", "pikachu", 1), ("abc", "abc", 0), ("", "a", 1), ("ab", "ba", 1),
])
def test_bounded_distance_handles_typical_edits(left: str, right: str, expected: int) -> None:
    assert bounded_edit_distance(left, right, 2) == expected
    assert bounded_edit_distance(right, left, 2) == expected
    assert bounded_edit_distance("dracaufeu", "objet totalement différent", 2) == 3


@pytest.mark.parametrize(("title", "tcgdex_id"), [
    ("Dracofeu 4/102 Set de Base", "base1-4"),
    ("Dracafueu 4/102 Set de Base", "base1-4"),
    ("Pikchu 35/108 Évolutions", "xy12-35"),
])
def test_typo_returns_candidate_but_never_automatic_acceptance(connection: sqlite3.Connection, title: str, tcgdex_id: str) -> None:
    result = CardMatcher(TcgdexCache(connection)).identify(title)
    assert result.status == "ambiguous" and result.matched_card is None
    assert result.candidates[0].tcgdex_id == tcgdex_id
    assert result.candidates[0].name_match_kind == "fuzzy"
    assert result.confidence < 80 and "nom approché" in result.candidates[0].match_reason


def test_typo_can_be_found_in_description_without_rewriting_extracted_name(connection: sqlite3.Connection) -> None:
    result = CardMatcher(TcgdexCache(connection)).identify("Superbe carte ancienne", "Dracofeu 4/102 Set de Base VF")
    assert result.status == "ambiguous"
    assert any(candidate.tcgdex_id == "base1-4" for candidate in result.candidates)
    assert result.features.name != "Dracaufeu"


def test_short_names_numbers_suffixes_and_foreign_language_stay_protected(connection: sqlite3.Connection) -> None:
    index = LexicalNameIndex(("Mew", "Porygon2", "Dracaufeu EX", "Dracaufeu VMAX"))
    assert index.search("Mav") == []
    assert index.search("Porygon3") == []
    assert {item.name for item in index.search("Dracofeu EX")} == {"Dracaufeu EX"}
    matcher = CardMatcher(TcgdexCache(connection))
    assert matcher.identify("Lot de 50 cartes Dracofeu 4/102").status == "lot"
    foreign = matcher.identify("Dracofeu 4/102 version japonaise JAP")
    assert foreign.status == "unidentified" and foreign.candidates == []


@pytest.mark.parametrize("title", ["Dracofeu 14/102 Set de Base", "Dracofeu 4/999 Set de Base", "Dracaufeu 4/102 Évolutions"])
def test_contradictory_numbers_or_sets_are_not_accepted(connection: sqlite3.Connection, title: str) -> None:
    result = CardMatcher(TcgdexCache(connection)).identify(title)
    assert result.status != "identified" and result.matched_card is None
    assert result.candidates == []
    assert result.diagnostic_candidates and result.diagnostic_candidates[0].contradictions
    assert result.diagnostic_candidates[0].confidence <= 59


def test_global_candidate_scoring_does_not_drop_reference_after_200_rows(connection: sqlite3.Connection) -> None:
    cache = TcgdexCache(connection)
    with connection:
        for index in range(230):
            cache.upsert_card(TcgdexCard(id=f"noise-{index}", local_id="4", name=f"Créature {index}", set_id="base1", set_name="Set de Base"))
        cache.upsert_card(TcgdexCard(id="late-draco", local_id="4", name="Dracaufeu", set_id="base1", set_name="Set de Base"))
    result = CardMatcher(cache).identify("Dracofeu 4/102 Set de Base")
    assert "late-draco" in {candidate.tcgdex_id for candidate in result.candidates}
    assert result.status == "ambiguous"


def test_name_index_refreshes_when_reference_vocabulary_changes(connection: sqlite3.Connection) -> None:
    cache = TcgdexCache(connection)
    matcher = CardMatcher(cache)
    with connection:
        cache.upsert_card(TcgdexCard(id="dynamic-12", local_id="12", name="Démolosse", set_id="base1", set_name="Set de Base"))
    result = matcher.identify("Demolose 12/102")
    assert result.status == "ambiguous"
    assert result.candidates[0].tcgdex_id == "dynamic-12"


def test_human_search_is_approximate_only_after_exact_results_are_exhausted(connection: sqlite3.Connection) -> None:
    cache = TcgdexCache(connection)
    search = search_references(cache, name="dracofeu", local_id="004", set_name="Set de Base")
    assert search.approximate and [card.tcgdex_id for card in search.cards] == ["base1-4"]
    assert [card.tcgdex_id for card in search_references(cache, name="dracofeu", set_name="base1").cards] == ["base1-4"]
    assert search_references(cache, name="Pikachu", offset=100).cards == []
    assert search_references(cache, tcgdex_id="base1-404").cards == []
    assert not search_references(cache, name="base1-4").approximate


def test_diagnostic_is_read_only_and_does_not_train_on_calculated_fields(connection: sqlite3.Connection) -> None:
    add_listing(connection, "Dracofeu 4/102 Set de Base", description="Contact secret@example.org 0612345678")
    add_listing(connection, "Dracaufeu 4/999 Set de Base")
    add_listing(connection, None)
    before = connection.total_changes
    rows_before = [dict(row) for row in connection.execute("SELECT * FROM catalog_items")]
    report = identification_diagnostics(connection, status="all")
    assert connection.total_changes == before
    assert [dict(row) for row in connection.execute("SELECT * FROM catalog_items")] == rows_before
    assert report["counts"] == {"fuzzy_name": 1, "contradiction": 1, "original_unavailable": 1}
    assert report["catalog"]["card_count"] >= 15
    serialized = json.dumps(report)
    assert "secret@example.org" not in serialized and "0612345678" not in serialized
    assert "Identité déjà recalculée" not in serialized


def test_empty_catalog_diagnostic_does_not_seed_or_repair(tmp_path: Path) -> None:
    with connect(tmp_path / "empty.db") as connection:
        apply_migrations(connection)
        add_listing(connection, "Dracofeu 4/102")
        before = connection.total_changes
        report = identification_diagnostics(connection)
        assert report["catalog"]["card_count"] == 0
        assert connection.total_changes == before
        assert connection.execute("SELECT count(*) FROM pokemon_reference_cards").fetchone()[0] == 0


def test_diagnostic_reports_language_conflict_instead_of_missing_reference(connection: sqlite3.Connection) -> None:
    """Une contradiction de langues ne prouve pas une lacune du catalogue local."""
    add_listing(connection, "Dracaufeu 4/102 VF", description="English")
    before = connection.total_changes
    report = identification_diagnostics(connection, status="all")
    assert report["counts"] == {"language_conflict": 1}
    assert report["items"][0]["proposed_status"] == "ambiguous"
    assert report["items"][0]["observed_languages"] == ["en", "fr"]
    assert connection.total_changes == before


def test_new_pilot_freezes_lexical_version_and_50_candidate_scope(connection: sqlite3.Connection) -> None:
    add_listing(connection, "Dracofeu 4/102")
    sample_pilot(connection, target_size=1, seed="lexical")
    rows = list(map(json.loads, build_dataset(connection).decode().splitlines()))
    batch = next(row for row in rows if row["type"] == "sampling_batch")
    assert batch["frame"][0]["retrieval_version"] == "lexical-v1"
    assert batch["frame"][0]["candidate_limit"] == 50


def test_diagnostic_web_download_and_manual_typo_search(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database = tmp_path / "web.db"
    monkeypatch.setenv("POKEMON_DATABASE_PATH", str(database))
    with TestClient(app) as client:
        with connect(database) as connection:
            TcgdexCache(connection).seed_initial_if_empty()
            connection.commit()
            add_listing(connection, "Dracofeu 4/102 Set de Base")
        response = client.get("/identification/diagnostics")
        assert response.status_code == 200 and "Nom approché à vérifier" in response.text
        assert "base1-4" in response.text
        download = client.get("/identification/diagnostics?download=true")
        assert download.status_code == 200 and download.json()["counts"] == {"fuzzy_name": 1}
        assert "attachment" in download.headers["content-disposition"]
        references = client.get("/catalog/1/identification?name=dracofeu&local_id=4")
        assert references.status_code == 200 and references.json()["approximate"]
        assert references.json()["items"][0]["tcgdex_id"] == "base1-4"
        review = client.get("/catalog/1/review?q=dracofeu")
        assert "Résultats approchés" in review.text
        assert client.get("/identification/diagnostics?limit=501").status_code == 422


def test_diagnostic_cli_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    database = tmp_path / "cli.db"
    with connect(database) as connection:
        apply_migrations(connection)
        TcgdexCache(connection).seed_initial_if_empty()
        connection.commit()
        add_listing(connection, "Dracofeu 4/102")
    assert main(["--database", str(database), "diagnose-identification", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["retrieval_version"] == "lexical-v1" and report["counts"]["fuzzy_name"] == 1
