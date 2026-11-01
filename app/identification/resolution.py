"""Preuves, décisions humaines et résolution commune aux chemins d'import."""

import hashlib
import json
import sqlite3
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from app.identification.matcher import CardMatcher
from app.identification.models import IdentificationResult
from app.tcgdex.cache import TcgdexCache

NORMALIZATION_VERSION = "identity-v2"


class IdentificationConflictError(ValueError):
    """Les preuves ou la révision ont changé pendant la saisie."""


@dataclass(frozen=True)
class Resolution:
    result: IdentificationResult
    evidence_hash: str
    revision: int
    decision_source: str
    confirmation_review: bool = False


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _raw_data(row: sqlite3.Row) -> dict[str, Any]:
    try:
        value = json.loads(row["raw_data"] or "{}")
        return value if isinstance(value, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def capture_evidence(connection: sqlite3.Connection, item_id: int) -> dict[str, Any]:
    """Capture les seules preuves d'identité, en fusionnant les captures partielles."""
    row = connection.execute(
        "SELECT id, original_title, name, card_number, set_name, language, image_url, raw_data "
        "FROM catalog_items WHERE id = ?", (item_id,)
    ).fetchone()
    if row is None:
        raise LookupError("Annonce introuvable")
    raw = _raw_data(row)
    previous = connection.execute(
        "SELECT e.title, e.description, e.attributes_json, e.image_evidence_ref, e.normalization_version "
        "FROM listing_identity_evidence e "
        "JOIN catalog_items c ON c.id=e.listing_id "
        "LEFT JOIN listing_identification_snapshots s ON s.id=c.identification_snapshot_id "
        "WHERE e.listing_id = ? ORDER BY COALESCE(e.evidence_hash=s.input_hash, 0) DESC, e.id DESC LIMIT 1", (item_id,)
    ).fetchone()
    previous_attributes = json.loads(previous["attributes_json"]) if previous and previous["normalization_version"] == NORMALIZATION_VERSION else {}
    observed = {
        "name": raw.get("name"),
        "card_number": raw.get("card_number"),
        "set_name": raw.get("set_name"),
        "language": raw.get("language"),
        "variant": raw.get("variant"),
        "condition": raw.get("condition"),
        "edition": raw.get("edition"),
    }
    attributes = dict(previous_attributes)
    for key, value in observed.items():
        if key in raw:
            attributes.pop(key, None)
        if isinstance(value, str) and value.strip():
            attributes[key] = value
    description = raw.get("description") if "description" in raw else raw.get("body")
    if not isinstance(description, (str, type(None))):
        description = None
    if description is None and "description" not in raw and "body" not in raw and previous:
        description = previous["description"]
    image = row["image_url"] or (previous["image_evidence_ref"] if previous else None)
    title = raw.get("_observed_title") or row["original_title"] or (previous["title"] if previous else row["name"])
    canonical = {
        "version": NORMALIZATION_VERSION,
        "title": title,
        "description": description,
        "attributes": {key: value for key, value in sorted(attributes.items()) if value is not None},
        "image": image or "",
    }
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    evidence = {
        "hash": digest, "title": title, "description": description,
        "attributes": attributes, "image": image,
        "incomplete": int(not description or not image),
    }
    connection.execute(
        """INSERT INTO listing_identity_evidence
        (listing_id, evidence_hash, normalization_version, title, description,
         attributes_json, image_evidence_ref, incomplete, captured_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(listing_id, evidence_hash) DO NOTHING""",
        (item_id, digest, NORMALIZATION_VERSION, title, description,
         json.dumps(attributes, ensure_ascii=False, sort_keys=True), image,
         evidence["incomplete"], utc_now()),
    )
    from app.identification.reviews import capture_snapshot
    capture_snapshot(connection, item_id, evidence)
    return evidence


def latest_decision(connection: sqlite3.Connection, item_id: int) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM listing_identification_decisions WHERE listing_id = ? ORDER BY id DESC LIMIT 1",
        (item_id,),
    ).fetchone()


def resolve_listing(connection: sqlite3.Connection, item_id: int) -> Resolution:
    from app.identification.reviews import current_revision, latest_review, reviewed_result
    evidence = capture_evidence(connection, item_id)
    decision = latest_decision(connection, item_id)
    revision = current_revision(connection, item_id)
    allow_unit = bool(decision and decision["action"] == "reclassify_unit" and decision["evidence_hash"] == evidence["hash"])
    result = CardMatcher(TcgdexCache(connection)).identify(
        evidence["title"], evidence["description"], raw_data=evidence["attributes"], allow_lot_override=allow_unit
    )
    automatic_result = result
    source = "automatic"
    review = False
    if decision and decision["evidence_hash"] == evidence["hash"]:
        if decision["action"] == "confirm" and result.status != "lot":
            card = TcgdexCache(connection).get_card_by_id(decision["reference_card_id"])
            if card:
                result = replace(result, status="identified", matched_card=card, confidence=None, reason="Confirmée manuellement. L'identité choisie ne certifie ni état, ni variante, ni authenticité, ni prix.")
                source = "human"
        elif decision["action"] == "reclassify_unit":
            source = "human_reclassification"
    elif decision and decision["action"] == "confirm":
        review = True
    human_review = latest_review(connection, item_id)
    if human_review and (not decision or decision["id"] <= human_review["legacy_revision"]):
        # Une nouvelle décision ou un retrait ne réactive jamais une confirmation ancienne.
        source = "automatic"
        result = automatic_result
        review = human_review["input_hash"] != evidence["hash"] and human_review["outcome"] != "withdrawn"
        if human_review["input_hash"] == evidence["hash"] and human_review["outcome"] != "withdrawn":
            result = reviewed_result(connection, human_review, result)
            source = "human"
    return Resolution(result, evidence["hash"], revision, source, review)


def apply_resolution(connection: sqlite3.Connection, item_id: int, resolution: Resolution) -> None:
    """Publie une identification sans jamais modifier les preuves originales."""
    result = resolution.result
    current = connection.execute("SELECT name, set_name, card_number FROM catalog_items WHERE id=?", (item_id,)).fetchone()
    name, set_name, number = current["name"], current["set_name"], current["card_number"]
    if result.matched_card:
        name, set_name, number = result.matched_card.name, result.matched_card.set_name, result.matched_card.local_id
    if result.status == "lot":
        name, set_name, number = current["name"], "Lot / Coffret", None
    connection.execute(
        """UPDATE catalog_items SET name=?, set_name=?, card_number=?,
        identification_status=?, reference_card_id=?, identification_confidence=?,
        identification_reason=?, is_lot=? WHERE id=?""",
        (name, set_name, number, result.status,
         result.matched_card.id if result.matched_card else None,
         result.confidence, ("Confirmation à revoir. " if resolution.confirmation_review else "") + result.reason,
         int(result.status == "lot"), item_id),
    )


def confirm_card(connection: sqlite3.Connection, item_id: int, reference_card_id: int, evidence_hash: str, expected_revision: int, reason: str | None = None) -> int:
    from app.identification.reviews import current_revision
    current = capture_evidence(connection, item_id)
    decision = latest_decision(connection, item_id)
    revision = current_revision(connection, item_id)
    item = connection.execute("SELECT is_lot FROM catalog_items WHERE id=?", (item_id,)).fetchone()
    card = TcgdexCache(connection).get_card_by_id(reference_card_id)
    if current["hash"] != evidence_hash or revision != expected_revision:
        raise IdentificationConflictError("Les preuves ou la décision ont changé : rechargez la fiche.")
    if item is None or item["is_lot"] or resolve_listing(connection, item_id).result.status == "lot":
        raise ValueError("Un lot actif ne peut pas être rattaché à une carte unitaire.")
    if card is None:
        raise ValueError("La référence TCGdex doit d'abord être enregistrée localement.")
    cursor = connection.execute(
        """INSERT INTO listing_identification_decisions
        (listing_id, evidence_hash, action, reference_card_id, tcgdex_id,
         expected_revision, previous_decision_id, operator, reason, created_at)
        VALUES (?, ?, 'confirm', ?, ?, ?, ?, 'local', ?, ?)""",
        (item_id, evidence_hash, reference_card_id, card.tcgdex_id, expected_revision,
         decision["id"] if decision else None, reason, utc_now()),
    )
    apply_resolution(connection, item_id, resolve_listing(connection, item_id))
    return int(cursor.lastrowid)


def revoke_confirmation(connection: sqlite3.Connection, item_id: int, evidence_hash: str, expected_revision: int, reason: str | None = None) -> None:
    _append_simple_decision(connection, item_id, "revoke", evidence_hash, expected_revision, reason)


def reclassify_unit(connection: sqlite3.Connection, item_id: int, evidence_hash: str, expected_revision: int, reason: str) -> None:
    if not reason.strip():
        raise ValueError("Un motif explicite est requis pour corriger le classement lot.")
    _append_simple_decision(connection, item_id, "reclassify_unit", evidence_hash, expected_revision, reason)


def _append_simple_decision(connection: sqlite3.Connection, item_id: int, action: str, evidence_hash: str, expected_revision: int, reason: str | None) -> None:
    from app.identification.reviews import current_revision
    current = capture_evidence(connection, item_id)
    decision = latest_decision(connection, item_id)
    revision = current_revision(connection, item_id)
    if current["hash"] != evidence_hash or revision != expected_revision:
        raise IdentificationConflictError("Les preuves ou la décision ont changé : rechargez la fiche.")
    connection.execute(
        """INSERT INTO listing_identification_decisions
        (listing_id, evidence_hash, action, expected_revision, previous_decision_id,
         operator, reason, created_at) VALUES (?, ?, ?, ?, ?, 'local', ?, ?)""",
        (item_id, evidence_hash, action, expected_revision,
         decision["id"] if decision else None, reason, utc_now()),
    )
    apply_resolution(connection, item_id, resolve_listing(connection, item_id))
