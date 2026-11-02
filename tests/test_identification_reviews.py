"""Régressions du premier lot ML, exclusivement sur données locales."""

import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.catalog import delete_import_batch, import_jsonl, import_listings_from_extension, reidentify_catalog_item
from app.cli import main
from app.collectors.models import CollectedListing
from app.collectors.service import ingest_collected_listings
from app.identification.dataset import build_dataset
from app.identification.detector import extract_features
from app.identification.resolution import IdentificationConflictError, confirm_card, reclassify_unit, resolve_listing, revoke_confirmation
from app.identification.reviews import ReviewInput, current_revision, review_context, save_review
from app.storage.database import connect
from app.storage.migration_runner import apply_migrations, migration_files
from app.tcgdex.cache import TcgdexCache
from app.web import app


@pytest.fixture
def connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    with connect(tmp_path / "reviews.db") as connection:
        apply_migrations(connection)
        TcgdexCache(connection).seed_initial_if_empty()
        import_jsonl(connection, json.dumps({
            "external_id": "pilot-1", "name": "Dracaufeu 4/102 Set de Base", "set_name": "Set de Base",
            "description": "Texte original VF", "price_cents": 1000,
        }).encode())
        yield connection


def matched(connection: sqlite3.Connection, **updates: object) -> ReviewInput:
    card = TcgdexCache(connection).get_card_by_tcgdex_id("base1-4")
    return ReviewInput.model_validate({
        "outcome": "matched", "validated_card_id": card.id, "text_sufficient": True, **updates,
    })


def save(connection: sqlite3.Connection, review: ReviewInput, item_id: int = 1, operator: str = "local") -> int:
    context = review_context(connection, item_id, blind=True)
    return save_review(connection, item_id, review, expected_hash=context["snapshot"]["input_hash"],
                       expected_revision=context["revision"], operator=operator)


def exported_reviews(connection: sqlite3.Connection) -> list[dict]:
    return [row for row in map(json.loads, build_dataset(connection).decode().splitlines()) if row["type"] == "review"]


def test_decision_survives_reidentification_without_changing_original(connection: sqlite3.Connection) -> None:
    before = review_context(connection, 1)["snapshot"]
    save(connection, matched(connection))
    reidentify_catalog_item(connection, 1)
    resolution = resolve_listing(connection, 1)
    assert resolution.decision_source == "human"
    assert resolution.result.matched_card.tcgdex_id == "base1-4"
    after = review_context(connection, 1)["snapshot"]
    assert before["input_hash"] == after["input_hash"]
    assert before["title"] == after["title"] == "Dracaufeu 4/102 Set de Base"


def test_independent_annotation_does_not_override_decision(connection: sqlite3.Connection) -> None:
    decision = save(connection, ReviewInput(outcome="no_catalog_match", text_sufficient=True))
    annotation = save(connection, matched(connection, review_kind="annotation"), operator="reader-2")
    assert annotation > decision
    assert current_revision(connection, 1) == decision
    assert resolve_listing(connection, 1).result.status == "unidentified"
    blind = review_context(connection, 1, blind=True)
    assert blind["history"] == blind["candidates"] == []
    assert blind["current"] is None
    assert "independent_annotation" in exported_reviews(connection)[-1]["exclusion_reasons"]


def test_adjudication_checks_annotation_snapshot(connection: sqlite3.Connection) -> None:
    annotation = save(connection, matched(connection, review_kind="annotation"), operator="reader-2")
    save(connection, matched(connection, review_kind="adjudication", reviewed_annotation_ids=[annotation]))
    assert resolve_listing(connection, 1).decision_source == "human"
    with pytest.raises(ValueError, match="même snapshot"):
        save(connection, matched(connection, review_kind="adjudication", reviewed_annotation_ids=[999]))


def test_stale_revision_and_changed_proofs_rejected(connection: sqlite3.Connection) -> None:
    old = review_context(connection, 1)
    save(connection, matched(connection))
    with pytest.raises(IdentificationConflictError):
        save_review(connection, 1, matched(connection), expected_hash=old["snapshot"]["input_hash"], expected_revision=0)
    current = review_context(connection, 1)
    with connection:
        connection.execute("UPDATE catalog_items SET original_title='Pikachu' WHERE id=1")
    with pytest.raises(IdentificationConflictError):
        save_review(connection, 1, matched(connection), expected_hash=current["snapshot"]["input_hash"], expected_revision=current["revision"])
    assert resolve_listing(connection, 1).confirmation_review
    assert "stale_evidence" in exported_reviews(connection)[0]["exclusion_reasons"]


def test_explicit_description_clear_invalidates_label(connection: sqlite3.Connection) -> None:
    save(connection, matched(connection))
    with connection:
        connection.execute("UPDATE catalog_items SET raw_data=? WHERE id=1", (json.dumps({"description": ""}),))
    assert resolve_listing(connection, 1).confirmation_review
    assert review_context(connection, 1)["snapshot"]["description"] == ""


def test_recollection_price_only_preserves_decision_and_first_seen(connection: sqlite3.Connection) -> None:
    listing = CollectedListing(source="vinted", external_id="live-1", title="Dracaufeu 4/102 Set de Base",
                               price_cents=1000, url="https://www.vinted.fr/items/1", raw_data={"description": "VF"})
    ingest_collected_listings(connection, [listing], platform="vinted", import_batch_id=1)
    item_id = connection.execute("SELECT id FROM catalog_items WHERE external_id='live-1'").fetchone()[0]
    first = connection.execute("SELECT first_seen_at FROM catalog_items WHERE id=?", (item_id,)).fetchone()[0]
    save(connection, matched(connection), item_id)
    ingest_collected_listings(connection, [listing.model_copy(update={"price_cents": 2000})], platform="vinted", import_batch_id=1)
    assert resolve_listing(connection, item_id).decision_source == "human"
    assert connection.execute("SELECT first_seen_at FROM catalog_items WHERE id=?", (item_id,)).fetchone()[0] == first
    ingest_collected_listings(connection, [listing.model_copy(update={"title": "Dracaufeu"})], platform="vinted", import_batch_id=1)
    assert resolve_listing(connection, item_id).confirmation_review


def test_withdrawal_keeps_history_and_does_not_resurrect_old_confirmation(connection: sqlite3.Connection) -> None:
    resolution = resolve_listing(connection, 1)
    confirm_card(connection, 1, resolution.result.matched_card.id, resolution.evidence_hash, resolution.revision)
    connection.commit()
    save(connection, matched(connection))
    save(connection, ReviewInput(outcome="withdrawn", text_sufficient=False))
    assert resolve_listing(connection, 1).decision_source == "automatic"
    rows = exported_reviews(connection)
    assert len(rows) == 2
    assert not any(row["eligible_for_text_training"] for row in rows)


def test_existing_revoke_button_can_revoke_new_decision(connection: sqlite3.Connection) -> None:
    save(connection, matched(connection))
    resolution = resolve_listing(connection, 1)
    revoke_confirmation(connection, 1, resolution.evidence_hash, resolution.revision)
    assert resolve_listing(connection, 1).decision_source == "automatic"
    assert "superseded_by_legacy_decision" in exported_reviews(connection)[0]["exclusion_reasons"]


def test_lot_guard_and_human_lot_correction(connection: sqlite3.Connection) -> None:
    with connection:
        connection.execute("UPDATE catalog_items SET original_title='Lot de 50 cartes Dracaufeu' WHERE id=1")
    with pytest.raises(ValueError, match="lot"):
        save(connection, matched(connection))
    save(connection, ReviewInput(outcome="lot", text_sufficient=True))
    result = resolve_listing(connection, 1).result
    assert result.status == "lot" and result.matched_card is None


def test_explicit_false_lot_reclassification_allows_review(connection: sqlite3.Connection) -> None:
    with connection:
        connection.execute("UPDATE catalog_items SET original_title='Lot Dracaufeu 4/102 Set de Base' WHERE id=1")
        resolution = resolve_listing(connection, 1)
        reclassify_unit(connection, 1, resolution.evidence_hash, resolution.revision, "Le mot lot est une erreur de titre, une seule carte vérifiée dans le texte.")
    save(connection, matched(connection))
    assert resolve_listing(connection, 1).result.status == "identified"


def test_human_can_choose_reference_outside_candidates(connection: sqlite3.Connection) -> None:
    with connection:
        connection.execute("UPDATE catalog_items SET original_title='Carte inconnue', raw_data=? WHERE id=1",
                           (json.dumps({"name": None, "set_name": None, "card_number": None, "description": None}),))
    assert resolve_listing(connection, 1).result.candidates == []
    save(connection, matched(connection))
    assert resolve_listing(connection, 1).result.matched_card.tcgdex_id == "base1-4"


def test_unknown_language_never_becomes_training_evidence(connection: sqlite3.Connection) -> None:
    assert extract_features("Dracaufeu 4/102").language is None
    attrs = json.loads(review_context(connection, 1)["snapshot"]["attributes_json"])
    assert "language" not in attrs  # Le défaut historique de stockage « fr » n'est pas une preuve.


def test_concurrent_connections_cannot_replace_an_unseen_decision(connection: sqlite3.Connection) -> None:
    old = review_context(connection, 1)
    connection.commit()
    database = Path(connection.execute("PRAGMA database_list").fetchone()[2])
    with connect(database) as other:
        save(other, matched(other))
    with pytest.raises(IdentificationConflictError):
        save_review(connection, 1, matched(connection), expected_hash=old["snapshot"]["input_hash"], expected_revision=old["revision"])
    assert len(exported_reviews(connection)) == 1


def test_revisited_snapshot_is_current_even_with_an_older_id(connection: sqlite3.Connection) -> None:
    save(connection, matched(connection))
    with connection:
        connection.execute("UPDATE catalog_items SET original_title='Pikachu' WHERE id=1")
        resolve_listing(connection, 1)
        connection.execute("UPDATE catalog_items SET original_title='Dracaufeu 4/102 Set de Base' WHERE id=1")
        resolve_listing(connection, 1)
    assert exported_reviews(connection)[0]["eligible_for_text_training"]


def test_legacy_without_original_is_excluded(connection: sqlite3.Connection) -> None:
    with connection:
        connection.execute("INSERT INTO catalog_items(source_id, import_batch_id, external_id, name, set_name, price_cents) VALUES (1, 1, 'legacy', 'Nom déjà corrigé', 'Inconnue', 100)")
    item_id = connection.execute("SELECT id FROM catalog_items WHERE external_id='legacy'").fetchone()[0]
    save(connection, matched(connection), item_id)
    row = exported_reviews(connection)[0]
    assert row["input_origin"] == "legacy_unknown"
    assert "unreliable_original" in row["exclusion_reasons"]


@pytest.mark.parametrize("updates", [
    {"evidence_basis": "image"}, {"text_sufficient": False},
    {"verified_attributes": {"seller": {"status": "verified", "value": "X"}}},
    {"verified_attributes": {"language": {"status": "unknown", "value": "fr"}}},
    {"verified_attributes": {"language": {"status": "verified"}}},
    {"review_kind": "adjudication", "reviewed_annotation_ids": [1, 1]},
])
def test_invalid_provenance_and_attributes_rejected(connection: sqlite3.Connection, updates: dict) -> None:
    with pytest.raises(ValidationError):
        matched(connection, **updates)


def test_dataset_is_deterministic_private_and_catalog_is_frozen(connection: sqlite3.Connection) -> None:
    with connection:
        connection.execute("UPDATE catalog_items SET seller='SecretSeller', raw_data=? WHERE id=1", (
            json.dumps({"description": "VF contact a@example.org 0612345678", "seller": {"email": "private@hidden.fr"}}),))
    save(connection, matched(connection, verified_attributes={"language": {"status": "verified", "value": "fr"}}))
    first = build_dataset(connection)
    assert first == build_dataset(connection)
    text = first.decode()
    assert all(value not in text for value in ("SecretSeller", "a@example.org", "0612345678", "private@hidden.fr"))
    assert exported_reviews(connection)[0]["verified_attributes"]["language"]["status"] == "verified"
    with connection:
        connection.execute("UPDATE pokemon_reference_cards SET name='Nom modifié' WHERE tcgdex_id='base1-4'")
    assert build_dataset(connection) == first


def test_import_deletion_preserves_audit_but_excludes_training(connection: sqlite3.Connection) -> None:
    save(connection, matched(connection))
    assert delete_import_batch(connection, 1)
    rows = exported_reviews(connection)
    assert len(rows) == 1 and "listing_deleted" in rows[0]["exclusion_reasons"]
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_extension_preserves_original_and_validation(connection: sqlite3.Connection) -> None:
    payload = {"external_id": "ext-1", "name": "Dracaufeu 4/102 Set de Base", "set_name": "Inconnue", "price_cents": 1000}
    import_listings_from_extension(connection, json.dumps(payload).encode())
    item_id = connection.execute("SELECT id FROM catalog_items WHERE external_id='ext-1'").fetchone()[0]
    save(connection, matched(connection), item_id)
    payload["price_cents"] = 2000
    import_listings_from_extension(connection, json.dumps(payload).encode())
    assert resolve_listing(connection, item_id).decision_source == "human"
    assert review_context(connection, item_id)["snapshot"]["title"] == payload["name"]


def test_migration_upgrade_keeps_existing_data(tmp_path: Path) -> None:
    with connect(tmp_path / "upgrade.db") as connection:
        connection.execute("CREATE TABLE schema_migrations(version TEXT PRIMARY KEY)")
        for version, script in migration_files():
            if version < "0013":
                connection.executescript(script)
        connection.execute("INSERT INTO sources(name, kind) VALUES ('legacy', 'manual_jsonl')")
        connection.commit()
        assert apply_migrations(connection) == [version for version, _ in migration_files() if version >= "0013"]
        assert connection.execute("SELECT name FROM sources WHERE name='legacy'").fetchone()[0] == "legacy"
        assert apply_migrations(connection) == []


def test_cli_export_does_not_overwrite_existing_file(tmp_path: Path) -> None:
    database = tmp_path / "cli.db"
    output = tmp_path / "labels.jsonl"
    assert main(["--database", str(database), "migrate"]) == 0
    assert main(["--database", str(database), "export-labels", "--output", str(output)]) == 0
    assert json.loads(output.read_text())["review_count"] == 0
    first = output.read_bytes()
    assert main(["--database", str(database), "export-labels", "--output", str(output)]) == 1
    assert output.read_bytes() == first


def test_web_review_search_conflict_and_export(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database = tmp_path / "web.db"
    monkeypatch.setenv("POKEMON_DATABASE_PATH", str(database))
    with TestClient(app) as client:
        client.post("/imports", files={"file": ("pilot.jsonl", json.dumps({
            "external_id": "web-1", "name": "Dracaufeu 4/102 Set de Base", "set_name": "Set de Base", "price_cents": 1000,
        }).encode())})
        page = client.get("/catalog/1/review?q=base1-4")
        assert page.status_code == 200
        assert "suggestions et avis précédents masqués" in page.text
        assert "base1-4" in page.text
        with connect(database) as connection:
            context = review_context(connection, 1)
            card = TcgdexCache(connection).get_card_by_tcgdex_id("base1-4")
            connection.commit()
        data = {"evidence_hash": context["snapshot"]["input_hash"], "revision": context["revision"],
                "outcome": "matched", "review_kind": "decision", "reference_card_id": card.id, "text_sufficient": "true"}
        assert client.post("/catalog/1/review", data=data).status_code == 200
        assert client.post("/catalog/1/review", data=data).status_code == 409
        export = client.get("/catalog/labels.jsonl")
        assert export.status_code == 200
        assert json.loads(export.text.splitlines()[0])["eligible_count"] == 1
        assert client.get("/catalog/999/review").status_code == 404
