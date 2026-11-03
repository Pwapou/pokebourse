"""Vérité terrain textuelle : snapshots, lectures indépendantes et décisions.

Les images distantes ne sont pas des preuves durables. Ce premier pilote
accepte uniquement des lectures du texte ; aucune suggestion n'est un label.
"""

import hashlib
import json
import re
import sqlite3
from dataclasses import replace
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.identification.models import IdentificationResult
from app.tcgdex.cache import TcgdexCache

OUTCOMES = {
    "matched": "Carte reconnue",
    "lot": "Lot / coffret",
    "not_card": "Hors périmètre",
    "no_catalog_match": "Carte absente du catalogue",
    "insufficient_evidence": "Preuves insuffisantes",
    "withdrawn": "Validation retirée",
}


def canonical_json(value: Any) -> str:
    """Sérialise de façon stable pour les empreintes et les exports."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fingerprint(value: Any) -> str:
    """Identifie un contenu indépendamment de sa date d'écriture."""
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def redact_contacts(text: str | None) -> str | None:
    """Masque les contacts explicites dans les seules copies d'apprentissage."""
    if text is None:
        return None
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[contact masqué]", text)
    text = re.sub(r"https?://\S+", "[lien masqué]", text)
    return re.sub(r"(?<!\w)(?:\+33\s?|0)[1-9](?:[ .-]?\d{2}){4}(?!\d)", "[contact masqué]", text)


def text_observed_attributes(attributes_json: str, observations_json: str) -> dict[str, str]:
    """Ne présente pas des préremplissages/OCR comme preuves du pilote textuel."""
    attributes = json.loads(attributes_json)
    observations = json.loads(observations_json)
    if not observations:
        return attributes
    declared = {(item["field"], item["value"]) for item in observations if item["source"] not in {"ocr", "prefill"}}
    return {field: value for field, value in attributes.items() if (field, value) in declared}


class VerifiedAttribute(BaseModel):
    """Un attribut confirmé reste indépendant du rattachement d'identité."""

    model_config = ConfigDict(extra="forbid", strict=True)
    status: Literal["unknown", "verified"]
    value: str | None = Field(default=None, max_length=100)
    evidence_basis: Literal["text"] = "text"

    @model_validator(mode="after")
    def validate_value(self) -> "VerifiedAttribute":
        """Interdit une valeur supposée présentée comme vérifiée."""
        if self.status == "unknown" and self.value is not None:
            raise ValueError("Un attribut inconnu doit rester nul.")
        if self.status == "verified" and (not self.value or not self.value.strip()):
            raise ValueError("Un attribut vérifié exige une valeur et une preuve textuelle.")
        return self


class ReviewInput(BaseModel):
    """Contrat validé des écritures humaines, sans identité opérateur libre."""

    model_config = ConfigDict(extra="forbid", strict=True)
    outcome: Literal["matched", "lot", "not_card", "no_catalog_match", "insufficient_evidence", "withdrawn"]
    review_kind: Literal["annotation", "decision", "adjudication"] = "decision"
    validated_card_id: int | None = Field(default=None, gt=0)
    evidence_basis: Literal["text"] = "text"
    text_sufficient: bool
    reviewed_annotation_ids: list[int] = Field(default_factory=list)
    verified_attributes: dict[Literal["language", "variant", "edition", "condition"], VerifiedAttribute] = Field(default_factory=dict)
    sampling_probability: float | None = Field(default=None, gt=0, le=1)
    comment: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_review(self) -> "ReviewInput":
        """Vérifie le rôle et les références de la lecture."""
        if (self.outcome == "matched") != (self.validated_card_id is not None):
            raise ValueError("Une référence est requise uniquement pour une carte reconnue.")
        if self.outcome == "matched" and not self.text_sufficient:
            raise ValueError("Ce pilote exige un texte suffisant pour reconnaître une carte.")
        if self.outcome == "withdrawn" and self.review_kind == "annotation":
            raise ValueError("Une annotation indépendante ne retire pas une décision.")
        ids = self.reviewed_annotation_ids
        if len(set(ids)) != len(ids) or any(value <= 0 for value in ids):
            raise ValueError("Les identifiants d'annotations doivent être distincts et positifs.")
        if (self.review_kind == "adjudication") != bool(ids):
            raise ValueError("Seul un arbitrage référence des annotations, au moins une.")
        return self


def capture_snapshot(connection: sqlite3.Connection, item_id: int, evidence: dict[str, Any]) -> sqlite3.Row:
    """Conserve les observations séparément des champs corrigés du catalogue."""
    from app.identification.resolution import NORMALIZATION_VERSION, utc_now

    item = connection.execute(
        "SELECT c.original_title, c.raw_data, c.source_id, c.external_id, s.kind, s.name AS source_name "
        "FROM catalog_items c JOIN sources s ON s.id=c.source_id WHERE c.id=?", (item_id,)
    ).fetchone()
    try:
        raw = json.loads(item["raw_data"] or "{}")
    except (json.JSONDecodeError, TypeError):
        raw = {}
    raw = raw if isinstance(raw, dict) else {}
    origin = raw.get("_identity_input_origin")
    if origin not in ("original_text", "structured_import"):
        origin = "original_text" if item["original_title"] else "legacy_unknown"
    platform = item["source_name"] if item["source_name"] in ("vinted", "leboncoin") else "manual" if item["kind"] == "manual_jsonl" else "unknown"
    connection.execute(
        """INSERT INTO listing_identification_snapshots
        (listing_id, input_hash, title, description, attributes_json, input_origin,
         source_kind, platform, group_key, normalization_version, captured_at, observations_json, pipeline_version)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(listing_id, input_hash) DO NOTHING""",
        (item_id, evidence["hash"], redact_contacts(evidence["title"]),
         redact_contacts(evidence["description"]), canonical_json({key: redact_contacts(value) for key, value in evidence["attributes"].items()}),
         origin, item["kind"], platform, fingerprint([item["source_id"], item["external_id"]]),
         NORMALIZATION_VERSION, utc_now(), canonical_json([
             {key: redact_contacts(value) if isinstance(value, str) else value for key, value in observation.items()}
             for observation in evidence.get("observations", [])]), evidence.get("pipeline_version", "lexical-v1")),
    )
    snapshot = connection.execute(
        "SELECT * FROM listing_identification_snapshots WHERE listing_id=? AND input_hash=?",
        (item_id, evidence["hash"]),
    ).fetchone()
    connection.execute(
        "UPDATE catalog_items SET identification_snapshot_id=? WHERE id=? AND "
        "(identification_snapshot_id IS NULL OR identification_snapshot_id <> ?)",
        (snapshot["id"], item_id, snapshot["id"]),
    )
    return snapshot


def latest_review(connection: sqlite3.Connection, item_id: int) -> sqlite3.Row | None:
    """La dernière décision, jamais une lecture indépendante, fait autorité."""
    return connection.execute(
        """SELECT r.*, s.input_hash FROM listing_identification_reviews r
        JOIN listing_identification_snapshots s ON s.id=r.snapshot_id
        WHERE s.listing_id=? AND r.review_kind <> 'annotation' ORDER BY r.id DESC LIMIT 1""",
        (item_id,),
    ).fetchone()


def current_revision(connection: sqlite3.Connection, item_id: int) -> int:
    """Combine les deux historiques pendant la transition des anciens boutons."""
    legacy = connection.execute(
        "SELECT max(id) FROM listing_identification_decisions WHERE listing_id=?", (item_id,)
    ).fetchone()[0] or 0
    review = latest_review(connection, item_id)
    return legacy + (review["id"] if review else 0)


def freeze_catalog(connection: sqlite3.Connection) -> str:
    """Fige les attributs de référence utilisés pour interpréter les labels."""
    from app.identification.resolution import utc_now

    rows = connection.execute(
        "SELECT tcgdex_id, name, local_id, set_id, set_name, rarity, reference_language "
        "FROM pokemon_reference_cards ORDER BY tcgdex_id"
    ).fetchall()
    cards = [dict(row) for row in rows]
    version = fingerprint(cards)
    connection.execute(
        "INSERT OR IGNORE INTO identification_catalog_versions VALUES (?, ?, ?)",
        (version, canonical_json(cards), utc_now()),
    )
    return version


def save_review(
    connection: sqlite3.Connection, item_id: int, review: ReviewInput, *,
    expected_hash: str, expected_revision: int, operator: str = "local",
    assignment_id: int | None = None, assignment_stage: str | None = None,
) -> int:
    """Ajoute une lecture et publie sa décision sous verrou SQLite optimiste."""
    from app.identification.resolution import (
        IdentificationConflictError, apply_resolution, capture_evidence, resolve_listing, utc_now,
    )

    if not operator.strip() or len(operator) > 100:
        raise ValueError("Identifiant opérateur local invalide.")
    with connection:
        if not connection.in_transaction:
            connection.execute("BEGIN IMMEDIATE")
        evidence = capture_evidence(connection, item_id)
        previous = latest_review(connection, item_id)
        revision = current_revision(connection, item_id)
        if evidence["hash"] != expected_hash or revision != expected_revision:
            raise IdentificationConflictError("Les preuves ou la décision ont changé : rechargez la fiche.")
        snapshot = capture_snapshot(connection, item_id, evidence)
        pilot_item = None
        if assignment_id is not None:
            from app.identification.annotation_pilot import validate_assignment
            pilot_item = validate_assignment(connection, assignment_id, assignment_stage or "", snapshot["id"], operator, review)
            review = review.model_copy(update={
                "sampling_probability": pilot_item["selected_in_stratum"] / pilot_item["population_in_stratum"],
            })
        elif assignment_stage is not None:
            raise ValueError("Une étape de file exige une tâche d'annotation.")
        card = TcgdexCache(connection).get_card_by_id(review.validated_card_id) if review.validated_card_id else None
        if review.validated_card_id and card is None:
            raise ValueError("Référence TCGdex locale introuvable.")
        if card and resolve_listing(connection, item_id).result.status == "lot":
            raise ValueError("Un lot détecté ne peut pas recevoir une carte unitaire.")
        if review.outcome == "withdrawn" and previous is None:
            raise ValueError("Aucune décision à retirer.")
        for annotation_id in review.reviewed_annotation_ids:
            annotation = connection.execute(
                "SELECT snapshot_id, review_kind FROM listing_identification_reviews WHERE id=?", (annotation_id,)
            ).fetchone()
            if not annotation or annotation["snapshot_id"] != snapshot["id"] or annotation["review_kind"] != "annotation":
                raise ValueError("L'arbitrage doit référencer des annotations du même snapshot.")
        catalog_version = freeze_catalog(connection)
        legacy_revision = connection.execute(
            "SELECT max(id) FROM listing_identification_decisions WHERE listing_id=?", (item_id,)
        ).fetchone()[0] or 0
        cursor = connection.execute(
            """INSERT INTO listing_identification_reviews
            (snapshot_id, outcome, validated_card_id, validated_tcgdex_id, review_kind,
             supersedes_review_id, legacy_revision, reviewed_annotation_ids_json, verified_attributes_json,
             validated_by, validated_at, evidence_basis, text_sufficient, catalog_version,
             sampling_probability, comment)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (snapshot["id"], review.outcome, card.id if card else None, card.tcgdex_id if card else None,
             review.review_kind, previous["id"] if previous and review.review_kind != "annotation" else None,
             legacy_revision,
             canonical_json(review.reviewed_annotation_ids),
             canonical_json({key: value.model_dump() for key, value in review.verified_attributes.items()}),
             operator, utc_now(), review.evidence_basis, int(review.text_sufficient), catalog_version,
             review.sampling_probability, redact_contacts(review.comment)),
        )
        review_id = int(cursor.lastrowid)
        if pilot_item is not None:
            from app.identification.annotation_pilot import attach_review
            attach_review(connection, pilot_item, assignment_stage or "", review_id)
        if review.review_kind != "annotation":
            apply_resolution(connection, item_id, resolve_listing(connection, item_id))
        return review_id


def reviewed_result(connection: sqlite3.Connection, review: sqlite3.Row, result: IdentificationResult) -> IdentificationResult:
    """Applique un résultat humain sans inventer de confiance probabiliste."""
    card = TcgdexCache(connection).get_card_by_id(review["validated_card_id"]) if review["validated_card_id"] else None
    status = "identified" if card else "lot" if review["outcome"] == "lot" else "unidentified"
    if review["outcome"] == "insufficient_evidence" and result.candidates:
        status = "ambiguous"
    # La barrière lots reste absolue, même après une modification du détecteur.
    if result.status == "lot" and card:
        return replace(result, status="lot", matched_card=None, confidence=0,
                       reason="Lot détecté : validation unitaire à réexaminer.")
    return replace(result, status=status, matched_card=card, confidence=None,
                   reason_code="human_confirmation" if card else "lot" if status == "lot" else "human_abstention", decision_source="human",
                   reason=f"Validation humaine : {OUTCOMES[review['outcome']]}. État, variante, authenticité et prix restent distincts.")


def review_context(connection: sqlite3.Connection, item_id: int, query: str = "", offset: int = 0, *, blind: bool = False) -> dict[str, Any]:
    """Prépare une correction ou une lecture sans suggestion ni premier avis."""
    from app.identification.resolution import capture_evidence, resolve_listing

    evidence = capture_evidence(connection, item_id)
    current = latest_review(connection, item_id)
    snapshot = capture_snapshot(connection, item_id, evidence)
    cache = TcgdexCache(connection)
    # La recherche porte sur tout le catalogue, avec pagination, jamais sur le top-K.
    from app.identification.reference_search import ReferenceSearchResult, search_references
    search = search_references(cache, name=query.strip(), limit=26, offset=offset) if query.strip() else ReferenceSearchResult([])
    cards = search.cards
    history = [] if blind else connection.execute(
        """SELECT r.id, r.outcome, r.review_kind, r.validated_tcgdex_id, r.validated_at,
        s.input_hash FROM listing_identification_reviews r
        JOIN listing_identification_snapshots s ON s.id=r.snapshot_id
        WHERE s.listing_id=? ORDER BY r.id DESC LIMIT 20""", (item_id,)
    ).fetchall()
    return {
        "snapshot": snapshot, "revision": current_revision(connection, item_id),
        "observed_attributes": text_observed_attributes(snapshot["attributes_json"], snapshot["observations_json"]),
        "current": None if blind else current,
        "needs_review": bool(current and current["outcome"] != "withdrawn" and current["input_hash"] != evidence["hash"]),
        "history": history, "cards": cards[:25], "has_more": len(cards) > 25,
        "search_approximate": search.approximate,
        "candidates": [] if blind else resolve_listing(connection, item_id).result.candidates[:5],
    }
