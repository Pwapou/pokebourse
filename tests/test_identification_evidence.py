"""Contrat T03 et cohérence des parcours, uniquement sur SQLite temporaire."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from collections.abc import Iterator

import pytest

from app.catalog import CatalogImportError, import_jsonl, parse_jsonl
from app.collectors.models import CollectedListing
from app.collectors.service import ensure_collection_source, ingest_collected_listings
from app.identification.evidence import PIPELINE_VERSION, build_evidence
from app.identification.matcher import CardMatcher
from app.identification.resolution import apply_resolution, confirm_card, resolve_listing
from app.listing_preview import preview_listing
from app.storage.database import connect
from app.storage.migration_runner import apply_migrations
from app.tcgdex.cache import TcgdexCache


@pytest.fixture
def connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    """Catalogue embarqué figé, sans instance utilisateur ni accès distant."""
    with connect(tmp_path / "observations.db") as connection:
        apply_migrations(connection)
        TcgdexCache(connection).seed_initial_if_empty()
        connection.commit()
        yield connection


def _signature(result: object) -> tuple:
    """Compare les décisions publiques indépendamment des identifiants d'annonce."""
    data = asdict(result) if not isinstance(result, dict) else result
    return (data["status"], data["reason_code"], data["reason"], data["confidence"],
            [(item["tcgdex_id"], item["confidence"]) for item in data["candidates"]],
            [(item["tcgdex_id"], item["confidence"]) for item in data["diagnostic_candidates"]],
            data["pipeline_version"], data["normalization_version"])


@pytest.mark.parametrize("title, extra", [
    ("Dracaufeu 4/102 Set de Base", {}),
    ("Carte Pokémon", {"name": "Pikachu", "card_number": "58/102", "set_name": "Set de Base"}),
    ("Carte photographiée", {"identity_evidence": [
        {"field": "name", "value": "Pikachu", "source": "ocr"},
        {"field": "card_number", "value": "58/102", "source": "ocr"}]}),
    ("Pikachu 58/102", {"identity_evidence": [{"field": "card_number", "value": "15", "source": "ocr"}]}),
    ("Dracaufeu 4/102 + 3 cartes offertes", {}),
    ("Dracaufeu 4/102 langue : EN", {}),
])
def test_same_observations_give_same_preview_import_collection_and_replay(
    connection: sqlite3.Connection, title: str, extra: dict,
) -> None:
    """À preuves égales, toutes les façades réutilisent la proposition commune."""
    fields = {"name": title, "set_name": "Non identifiée", **extra}
    bundle = build_evidence(title, attributes=fields)
    fields["identity_evidence"] = bundle.transport()
    before = connection.total_changes
    preview = preview_listing(connection, {"title": title, **fields})["identification"]
    direct = CardMatcher(TcgdexCache(connection), seed_if_empty=False, repair_index=False).identify(title, raw_data=fields)
    assert connection.total_changes == before
    assert _signature(direct) == _signature(preview)

    payload = {"external_id": "json", "price_cents": 1200, "raw_data": {"title": title}, **fields}
    import_jsonl(connection, json.dumps(payload).encode(), source_name="manual")
    imported = connection.execute("SELECT id FROM catalog_items WHERE external_id='json'").fetchone()[0]
    first = resolve_listing(connection, imported)
    assert _signature(first.result) == _signature(direct)
    assert resolve_listing(connection, imported).evidence_hash == first.evidence_hash
    assert len({item["input_hash"] for item in connection.execute("SELECT input_hash FROM listing_identification_snapshots WHERE listing_id=?", (imported,))}) == 1

    source = ensure_collection_source(connection, "vinted")
    batch = connection.execute("INSERT INTO import_batches(source_id,input_checksum) VALUES (?, 'collection')", (source,)).lastrowid
    listing = CollectedListing(source="vinted", external_id="collected", title=title,
                               price_cents=1200, url="https://www.vinted.fr/items/123", raw_data=fields)
    ingest_collected_listings(connection, [listing], platform="vinted", import_batch_id=batch)
    collected = connection.execute("SELECT id FROM catalog_items WHERE external_id='collected'").fetchone()[0]
    assert _signature(resolve_listing(connection, collected).result) == _signature(direct)


@pytest.mark.parametrize("observations", [
    [{"field": "name", "value": "Pikachu", "source": "confirmed"}],
    [{"field": "name", "value": "Pikachu", "source": "manual", "verified": True}],
    [{"field": "title", "value": "Pikachu 58/102", "source": "ocr"}],
    [{"field": "name", "value": "Pikachu", "source": "ocr", "region": [3, 3, 1, 1]}],
    [{"field": "name", "value": "Pikachu", "source": "ocr"}] * 65,
])
def test_client_provenance_is_validated_before_import(connection: sqlite3.Connection, observations: list[dict]) -> None:
    """Une provenance reçue n'autorise ni rôle humain ni texte OCR substitué."""
    payload = {"external_id": "bad", "name": "Carte", "set_name": "Inconnue", "price_cents": 100,
               "identity_evidence": observations}
    with pytest.raises(CatalogImportError):
        import_jsonl(connection, json.dumps(payload).encode())
    assert connection.execute("SELECT count(*) FROM catalog_items").fetchone()[0] == 0
    assert connection.execute("SELECT count(*) FROM listing_identification_decisions").fetchone()[0] == 0


def test_ocr_proposal_survives_prefill_import_and_requires_separate_confirmation(connection: sqlite3.Connection) -> None:
    """Ajouter une annonce ne confirme pas les indices issus de sa photographie."""
    observations = [
        {"field": "name", "value": "Pikachu", "source": "prefill"},
        {"field": "card_number", "value": "58/102", "source": "ocr", "image_ref": "local-test-image", "region": [0, 0, 100, 200]},
        {"field": "set_name", "value": "Set de Base", "source": "prefill"},
    ]
    payload = {"external_id": "ocr", "name": "Pikachu", "set_name": "Set de Base", "card_number": "58/102",
               "price_cents": 100, "identity_evidence": observations}
    import_jsonl(connection, json.dumps(payload).encode())
    item_id = connection.execute("SELECT id FROM catalog_items").fetchone()[0]
    result = resolve_listing(connection, item_id)
    assert result.result.status == "ambiguous"
    assert result.result.reason_code == "indicative_evidence"
    assert result.result.matched_card is None
    assert result.decision_source == "automatic"
    assert connection.execute("SELECT count(*) FROM listing_identification_decisions").fetchone()[0] == 0
    snapshot = connection.execute("SELECT observations_json,pipeline_version FROM listing_identification_snapshots").fetchone()
    assert snapshot["pipeline_version"] == PIPELINE_VERSION
    stored = json.loads(snapshot["observations_json"])
    assert {observation["source"] for observation in stored} >= {"ocr", "prefill"}
    assert any(observation.get("region") == [0, 0, 100, 200] for observation in stored)
    confirm_card(connection, item_id, result.result.candidates[0].card_id, result.evidence_hash, result.revision)
    confirmed = resolve_listing(connection, item_id)
    assert confirmed.decision_source == "human"
    assert confirmed.result.reason_code == "human_confirmation"
    assert confirmed.result.matched_card.tcgdex_id == "base1-58"


def test_agreeing_ocr_does_not_remove_independent_text_acceptance(connection: sqlite3.Connection) -> None:
    """Le texte suffisant garde sa décision lorsqu'une lecture OCR concorde."""
    result = CardMatcher(TcgdexCache(connection)).identify("Pikachu 58/102 Set de Base", raw_data={
        "ocr_names": ["Pikachu"], "ocr_numbers": ["58"],
    })
    assert result.status == "identified"
    assert result.reason_code == "exact_match"
    assert result.matched_card.tcgdex_id == "base1-58"


def test_pipeline_evolution_preserves_existing_human_hash_and_audit(connection: sqlite3.Connection) -> None:
    """Changer de pipeline ne modifie pas l'empreinte des mêmes preuves historiques."""
    import_jsonl(connection, b'{"external_id":"old","name":"Pikachu 58/102 Set de Base","set_name":"Non identifiee","price_cents":100}')
    item_id = connection.execute("SELECT id FROM catalog_items").fetchone()[0]
    result = resolve_listing(connection, item_id)
    confirm_card(connection, item_id, result.result.matched_card.id, result.evidence_hash, result.revision)
    connection.execute("UPDATE listing_identity_evidence SET observations_json='[]', pipeline_version='lexical-v1'")
    connection.execute("UPDATE listing_identification_snapshots SET observations_json='[]', pipeline_version='lexical-v1'")
    updated = resolve_listing(connection, item_id)
    assert updated.evidence_hash == result.evidence_hash
    assert updated.decision_source == "human"
    assert updated.result.pipeline_version == PIPELINE_VERSION
    assert connection.execute("SELECT count(*) FROM listing_identification_decisions").fetchone()[0] == 1
    assert connection.execute("SELECT pipeline_version FROM listing_identification_snapshots").fetchone()[0] == "lexical-v1"


def test_service_unavailable_is_explicit_without_blocking_an_independent_title(connection: sqlite3.Connection) -> None:
    """Une panne OCR explique l'abstention, mais n'efface pas des preuves textuelles."""
    matcher = CardMatcher(TcgdexCache(connection))
    assert matcher.identify("Carte Pokémon", raw_data={"ocr_status": "unavailable"}).reason_code == "service_unavailable"
    assert matcher.identify("Pikachu 58/102", raw_data={"ocr_status": "unavailable"}).status == "identified"


def test_partial_reingestion_keeps_traced_proof_and_human_confirmation(connection: sqlite3.Connection) -> None:
    """Prix seul : mêmes preuves ; nouveaux indices : confirmation à réexaminer."""
    source = ensure_collection_source(connection, "vinted")
    batch = connection.execute("INSERT INTO import_batches(source_id,input_checksum) VALUES (?, 'partial')", (source,)).lastrowid
    observations = [{"field": "name", "value": "Pikachu", "source": "ocr"},
                    {"field": "card_number", "value": "58/102", "source": "ocr"}]
    listing = CollectedListing(source="vinted", external_id="partial", title="Carte photographiée", price_cents=1200,
                               url="https://www.vinted.fr/items/321", raw_data={"identity_evidence": observations})
    ingest_collected_listings(connection, [listing], platform="vinted", import_batch_id=batch)
    item_id = connection.execute("SELECT id FROM catalog_items").fetchone()[0]
    first_seen = connection.execute("SELECT first_seen_at FROM catalog_items").fetchone()[0]
    current = resolve_listing(connection, item_id)
    confirm_card(connection, item_id, current.result.candidates[0].card_id, current.evidence_hash, current.revision)
    partial = listing.model_copy(update={"price_cents": 800, "raw_data": {}})
    ingest_collected_listings(connection, [partial], platform="vinted", import_batch_id=batch)
    retained = resolve_listing(connection, item_id)
    assert retained.evidence_hash == current.evidence_hash
    assert retained.decision_source == "human"
    assert retained.result.matched_card.tcgdex_id == "base1-58"
    assert any(item.source == "ocr" for item in retained.result.observations)
    assert connection.execute("SELECT first_seen_at FROM catalog_items").fetchone()[0] == first_seen
    changed = listing.model_copy(update={"raw_data": {"identity_evidence": [
        {"field": "name", "value": "Dracaufeu", "source": "ocr"},
        {"field": "card_number", "value": "4/102", "source": "ocr"}]}})
    ingest_collected_listings(connection, [changed], platform="vinted", import_batch_id=batch)
    revision = resolve_listing(connection, item_id)
    assert revision.evidence_hash != current.evidence_hash
    assert revision.confirmation_review
    assert revision.decision_source == "automatic"
    assert revision.result.matched_card is None
    assert connection.execute("SELECT count(*) FROM listing_identification_decisions").fetchone()[0] == 1


def test_client_manual_origin_is_a_declaration_and_never_a_human_decision(connection: sqlite3.Connection) -> None:
    """Un champ saisi peut étayer une proposition automatique sans devenir un label."""
    payload = {"external_id": "entered", "name": "Pikachu", "set_name": "Set de Base", "card_number": "58/102",
               "price_cents": 100, "identity_evidence": [
                   {"field": "name", "value": "Pikachu", "source": "manual"},
                   {"field": "card_number", "value": "58/102", "source": "manual"}]}
    import_jsonl(connection, json.dumps(payload).encode())
    resolution = resolve_listing(connection, connection.execute("SELECT id FROM catalog_items").fetchone()[0])
    assert resolution.result.status == "identified"
    assert resolution.decision_source == "automatic"
    assert resolution.result.decision_source == "automatic"
    assert connection.execute("SELECT count(*) FROM listing_identification_reviews").fetchone()[0] == 0
    assert connection.execute("SELECT count(*) FROM listing_identification_decisions").fetchone()[0] == 0


def test_missing_title_does_not_turn_a_compound_prefill_into_text(connection: sqlite3.Connection) -> None:
    """Le nom prérempli ne doit pas être recyclé comme titre réputé extrait."""
    result = preview_listing(connection, {"title": "", "name": "Pikachu 58/102", "proposed_name": "Pikachu 58/102"})
    assert result["identification"]["status"] == "ambiguous"
    assert result["identification"]["matched_card"] is None
