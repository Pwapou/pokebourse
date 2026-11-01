"""Diagnostic local en lecture seule ; les causes métier restent à valider humainement."""

import json
import sqlite3
from collections import Counter
from dataclasses import asdict
from time import perf_counter_ns
from typing import Any

from app.identification.lexical import RETRIEVAL_VERSION
from app.identification.matcher import CardMatcher
from app.identification.models import IdentificationResult
from app.identification.reviews import redact_contacts
from app.tcgdex.cache import TcgdexCache

DIAGNOSTIC_LABELS = {
    "original_unavailable": "Original indisponible ou non fiable",
    "lot": "Lot ou produit scellé",
    "foreign_language": "Langue hors du référentiel français",
    "no_evidence": "Indices textuels insuffisants",
    "no_candidate": "Aucun candidat local",
    "contradiction": "Numéro ou extension contradictoire",
    "fuzzy_name": "Nom approché à vérifier",
    "ambiguous": "Plusieurs cartes plausibles",
    "weak_evidence": "Correspondance partielle",
    "exact_available": "Correspondance exacte disponible",
}


def _observations(row: sqlite3.Row) -> tuple[str | None, str | None, dict[str, Any]]:
    """Lit les preuves originales sans utiliser les champs d'identité corrigés."""
    try:
        raw = json.loads(row["raw_data"] or "{}")
    except (json.JSONDecodeError, TypeError):
        raw = {}
    raw = raw if isinstance(raw, dict) else {}
    title = row["original_title"] or raw.get("title")
    if not isinstance(title, str) or not title.strip() or row["input_origin"] == "legacy_unknown":
        title = None
    description = raw.get("description") if "description" in raw else raw.get("body")
    if "description" not in raw and "body" not in raw:
        description = row["snapshot_description"]
    return title, description if isinstance(description, str) else None, raw


def _diagnosis(result: IdentificationResult) -> str:
    """Décrit ce que le moteur constate, sans inventer une absence dans TCGdex."""
    if result.status == "lot":
        return "lot"
    if result.features.language and result.features.language != "fr":
        return "foreign_language"
    if result.status == "identified":
        return "exact_available"
    if result.candidates:
        best = result.candidates[0]
        if best.contradictions:
            return "contradiction"
        if best.name_match_kind == "fuzzy":
            return "fuzzy_name"
        if len(result.candidates) > 1 and best.confidence == result.candidates[1].confidence:
            return "ambiguous"
        return "weak_evidence"
    return "no_evidence" if not result.features.local_id and not result.features.name else "no_candidate"


def identification_diagnostics(connection: sqlite3.Connection, *, limit: int = 100, status: str = "unidentified") -> dict[str, Any]:
    """Inventorie le catalogue et analyse les annonces récentes sans aucune écriture.

    Le diagnostic ne synchronise pas le catalogue, ne crée ni seed ni snapshot,
    ne publie pas d'identification et ne remplace pas une décision humaine.
    """
    if type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError("Le diagnostic accepte entre 1 et 500 annonces.")
    if status not in ("unidentified", "ambiguous", "all"):
        raise ValueError("Statut de diagnostic inconnu.")
    own_transaction = not connection.in_transaction
    if own_transaction:
        connection.execute("BEGIN")
    try:
        matcher = CardMatcher(TcgdexCache(connection), seed_if_empty=False, repair_index=False)
        statuses = dict(connection.execute("SELECT identification_status, count(*) FROM catalog_items GROUP BY identification_status").fetchall())
        reference_languages = dict(connection.execute("SELECT reference_language, count(*) FROM pokemon_reference_cards GROUP BY reference_language").fetchall())
        sets = [dict(row) for row in connection.execute(
            """SELECT s.id, s.name, s.card_count_total AS expected_total,
            s.card_count_official AS expected_official, count(c.id) AS cached_cards
            FROM pokemon_reference_sets s LEFT JOIN pokemon_reference_cards c ON c.set_id=s.id
            GROUP BY s.id ORDER BY s.name, s.id"""
        )]
        selected_statuses = ("unidentified", "ambiguous") if status == "all" else (status,)
        placeholders = ",".join("?" for _ in selected_statuses)
        population = sum(statuses.get(value, 0) for value in selected_statuses)
        rows = connection.execute(
            f"""SELECT c.id, c.original_title, c.raw_data, c.image_url, c.identification_status,
            s.description AS snapshot_description, s.input_origin
            FROM catalog_items c LEFT JOIN listing_identification_snapshots s ON s.id=c.identification_snapshot_id
            WHERE c.identification_status IN ({placeholders}) ORDER BY c.id DESC LIMIT ?""",
            (*selected_statuses, limit),
        ).fetchall()
        items = []
        counts: Counter[str] = Counter()
        durations = []
        for row in rows:
            title, description, raw = _observations(row)
            start = perf_counter_ns()
            result = matcher.identify(title, description, raw_data={}) if title else None
            elapsed_us = (perf_counter_ns() - start + 500) // 1000
            durations.append(elapsed_us)
            code = _diagnosis(result) if result else "original_unavailable"
            counts[code] += 1
            candidates = []
            for candidate in result.candidates[:5] if result else []:
                payload = asdict(candidate)
                payload["match_reason"] = redact_contacts(candidate.match_reason)
                candidates.append(payload)
            items.append({
                "id": row["id"], "title": redact_contacts(title) or "Original non fiable",
                "stored_status": row["identification_status"], "diagnostic": code,
                "diagnostic_label": DIAGNOSTIC_LABELS[code], "proposed_status": result.status if result else None,
                "reason": redact_contacts(result.reason) if result else "Récupérer un original fiable avant l'analyse textuelle.",
                "has_description": bool(description), "has_image_url": bool(row["image_url"]),
                "observed_language": result.features.language if result else None,
                "input_origin": row["input_origin"] or ("original_text" if title else "legacy_unknown"),
                "candidates": candidates, "candidate_count": len(result.candidates) if result else 0,
                "elapsed_us": elapsed_us,
                "structured_hints_present": [key for key in ("card_number", "set_name") if raw.get(key)],
            })
        return {
            "schema_version": "identification-diagnostics-v1", "retrieval_version": RETRIEVAL_VERSION,
            "status": status, "limit": limit, "population": population, "analyzed_count": len(items),
            "with_candidates": sum(bool(item["candidates"]) for item in items),
            "counts": dict(counts), "labels": DIAGNOSTIC_LABELS, "items": items,
            "catalog": {"card_count": sum(row["cached_cards"] for row in sets), "set_count": len(sets),
                        "sets": sets, "reference_languages": reference_languages},
            "p95_us": sorted(durations)[max(0, (len(durations) * 95 + 99) // 100 - 1)] if durations else None,
            "scope": "recent_unresolved_listings; descriptive_only; no_accuracy_estimate; no_writes; text_only",
        }
    finally:
        if own_transaction:
            connection.rollback()
