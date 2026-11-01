"""File pilote textuelle : tirages traçables, lectures indépendantes et suivi."""

import json
import random
import secrets
import sqlite3
from collections import Counter, defaultdict
from typing import Any

from app.identification.detector import extract_features
from app.identification.lexical import RETRIEVAL_VERSION
from app.identification.matcher import CardMatcher
from app.identification.reviews import ReviewInput, canonical_json, freeze_catalog
from app.tcgdex.cache import TcgdexCache

STRATEGY_VERSION = "pilot-status-platform-language-description-v1"
STATUS_WEIGHTS = {"ambiguous": 50, "unidentified": 25, "identified": 20, "lot": 5}
DIAGNOSES = {
    "correct": "Premier candidat correct",
    "candidate_missing": "Carte absente des candidats proposés",
    "ranking_error": "Mauvais classement des candidats",
    "catalog_missing": "Carte absente du catalogue",
    "insufficient_text": "Texte insuffisant",
    "business_rule": "Lot ou objet hors périmètre",
}


class AnnotationAccessError(ValueError):
    """Cette lecture requiert un autre opérateur ou une étape préalable."""


def _item_rows(connection: sqlite3.Connection, pilot_id: int) -> list[dict[str, Any]]:
    """Charge les tâches et leur applicabilité sans recalcul automatique."""
    rows = connection.execute(
        """SELECT i.*, s.listing_id, s.input_hash, s.title, s.platform, s.group_key,
        s.description, c.identification_snapshot_id AS current_snapshot_id,
        (SELECT max(r.id) FROM listing_identification_reviews r
         JOIN listing_identification_snapshots s2 ON s2.id=r.snapshot_id
         WHERE s2.listing_id=s.listing_id AND r.review_kind <> 'annotation') AS latest_decision_id,
        (SELECT max(d.id) FROM listing_identification_decisions d WHERE d.listing_id=s.listing_id) AS latest_legacy_id
        FROM annotation_pilot_items i
        JOIN listing_identification_snapshots s ON s.id=i.snapshot_id
        LEFT JOIN catalog_items c ON c.id=s.listing_id
        WHERE i.pilot_id=? ORDER BY i.id""", (pilot_id,)
    ).fetchall()
    return [dict(row) for row in rows]


def _is_current(item: dict[str, Any] | sqlite3.Row) -> bool:
    """Une suppression ou une nouvelle preuve retire la tâche de l'avancement."""
    return item["listing_id"] is not None and item["snapshot_id"] == item["current_snapshot_id"]


def _quota_counts(size: int) -> dict[str, int]:
    """Répartit un effectif entier selon les quotas, sans flottants."""
    counts = {status: size * weight // 100 for status, weight in STATUS_WEIGHTS.items()}
    order = sorted(STATUS_WEIGHTS, key=lambda status: -(size * STATUS_WEIGHTS[status] % 100))
    for status in order[:size - sum(counts.values())]:
        counts[status] += 1
    return counts


def sample_pilot(connection: sqlite3.Connection, *, target_size: int = 300, seed: str | None = None) -> int:
    """Complète le dernier pilote sur des snapshots non encore annotés.

    Les allocations entre strates sont déterministes ; le tirage dans chaque
    strate est uniforme sans remise. La probabilité d'inclusion est donc n/N
    pour la population et la vague enregistrées, pas pour tout le marché.
    """
    from app.identification.resolution import capture_evidence, utc_now

    if type(target_size) is not int or not 1 <= target_size <= 5000:
        raise ValueError("La taille du pilote doit être comprise entre 1 et 5 000.")
    with connection:
        if not connection.in_transaction:
            connection.execute("BEGIN IMMEDIATE")
        pilot = connection.execute("SELECT * FROM annotation_pilots ORDER BY id DESC LIMIT 1").fetchone()
        if pilot is None:
            cursor = connection.execute(
                "INSERT INTO annotation_pilots(target_size, strategy_version, created_at) VALUES (?, ?, ?)",
                (target_size, STRATEGY_VERSION, utc_now()),
            )
            pilot = connection.execute("SELECT * FROM annotation_pilots WHERE id=?", (cursor.lastrowid,)).fetchone()
        pilot_id = int(pilot["id"])
        # Les annonces historiques n'ont pas nécessairement encore de snapshot.
        for row in connection.execute("SELECT id FROM catalog_items WHERE identification_snapshot_id IS NULL ORDER BY id").fetchall():
            capture_evidence(connection, row["id"])
        active = [item for item in _item_rows(connection, pilot_id) if _is_current(item)]
        remaining = max(0, pilot["target_size"] - len(active))
        if not remaining:
            return 0
        excluded_groups = {item["group_key"] for item in active}
        rows = connection.execute(
            """SELECT s.*, c.identification_status FROM listing_identification_snapshots s
            JOIN catalog_items c ON c.identification_snapshot_id=s.id
            WHERE s.input_origin <> 'legacy_unknown'
            AND NOT EXISTS (SELECT 1 FROM listing_identification_reviews r WHERE r.snapshot_id=s.id)
            AND NOT EXISTS (SELECT 1 FROM annotation_pilot_items i WHERE i.pilot_id=? AND i.snapshot_id=s.id)
            AND NOT EXISTS (SELECT 1 FROM listing_identification_decisions d
                WHERE d.listing_id=c.id AND d.evidence_hash=s.input_hash)
            ORDER BY s.id""", (pilot_id,)
        ).fetchall()
        strata: dict[str, list[sqlite3.Row]] = defaultdict(list)
        status_keys: dict[str, list[str]] = defaultdict(list)
        for row in rows:
            if row["group_key"] in excluded_groups:
                continue
            attributes = json.loads(row["attributes_json"])
            observed_language = attributes.get("language") or extract_features(row["title"], row["description"]).language
            # Une langue absente demeure inconnue, même si le stockage ancien avait un défaut « fr ».
            key = canonical_json([row["identification_status"], row["platform"],
                                  observed_language or "unknown", bool(row["description"])])
            strata[key].append(row)
        for key in sorted(strata):
            status_keys[json.loads(key)[0]].append(key)
        quotas = _quota_counts(pilot["target_size"])
        existing_counts = Counter(item["initial_status"] for item in active)
        available = {status: sum(len(strata[key]) for key in status_keys[status]) for status in STATUS_WEIGHTS}
        allocated = {status: min(available[status], max(0, quotas[status] - existing_counts[status])) for status in STATUS_WEIGHTS}
        # Des strates disparues peuvent déplacer le quota courant : toujours respecter le budget restant.
        while sum(allocated.values()) > remaining:
            for status in reversed(STATUS_WEIGHTS):
                if allocated[status] and sum(allocated.values()) > remaining:
                    allocated[status] -= 1
        while sum(allocated.values()) < min(remaining, sum(available.values())):
            for status in STATUS_WEIGHTS:
                if allocated[status] < available[status] and sum(allocated.values()) < remaining:
                    allocated[status] += 1
        seed = seed or secrets.token_hex(16)
        rng = random.Random(seed)
        chosen: list[tuple[sqlite3.Row, str, int, int]] = []
        frame = []
        for status in STATUS_WEIGHTS:
            keys = status_keys[status]
            counts = dict.fromkeys(keys, 0)
            for _ in range(allocated[status]):
                # Favorise la couverture des plateformes/langues et des descriptions manquantes.
                key = min((key for key in keys if counts[key] < len(strata[key])), key=lambda key: (counts[key], key))
                counts[key] += 1
            for key in keys:
                count, population = counts[key], len(strata[key])
                frame.append({"stratum": json.loads(key), "selected": count, "population": population,
                              "retrieval_version": RETRIEVAL_VERSION, "candidate_limit": 50,
                              "snapshot_ids": [row["id"] for row in strata[key]]})
                chosen.extend((row, key, count, population) for row in rng.sample(strata[key], count))
        if not chosen:
            return 0
        double_goal = (len(active) + len(chosen) + 4) // 5
        double_count = min(len(chosen), max(0, double_goal - sum(item["requires_second"] for item in active)))
        double_ids = {entry[0]["id"] for entry in rng.sample(chosen, double_count)}
        rng.shuffle(chosen)
        cache = TcgdexCache(connection)
        cache.seed_initial_if_empty()
        matcher = CardMatcher(cache)
        catalog_version = freeze_catalog(connection)
        cursor = connection.execute(
            """INSERT INTO annotation_sampling_batches
            (pilot_id, seed, frame_json, selected_count, double_count, catalog_version, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (pilot_id, seed, canonical_json(frame), len(chosen), double_count, catalog_version, utc_now()),
        )
        batch_id = int(cursor.lastrowid)
        for row, key, count, population in chosen:
            result = matcher.identify(row["title"], row["description"], raw_data=json.loads(row["attributes_json"]))
            candidates = [candidate.tcgdex_id for candidate in result.candidates]
            top1 = result.matched_card.tcgdex_id if result.matched_card else candidates[0] if candidates else None
            connection.execute(
                """INSERT INTO annotation_pilot_items
                (pilot_id, batch_id, snapshot_id, initial_status, stratum_key, selected_in_stratum,
                 population_in_stratum, requires_second, automatic_top1_tcgdex_id, candidate_tcgdex_ids_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (pilot_id, batch_id, row["id"], row["identification_status"], key, count, population,
                 int(row["id"] in double_ids), top1, canonical_json(candidates)),
            )
        return len(chosen)


def assignment(connection: sqlite3.Connection, item_id: int) -> dict[str, Any]:
    """Retourne une tâche identifiée de façon stable, jamais par son ordre d'affichage."""
    row = connection.execute("SELECT pilot_id FROM annotation_pilot_items WHERE id=?", (item_id,)).fetchone()
    if row is None:
        raise LookupError("Tâche d'annotation introuvable.")
    return next(item for item in _item_rows(connection, row["pilot_id"]) if item["id"] == item_id)


def assignment_stage(connection: sqlite3.Connection, item: dict[str, Any], operator: str) -> str:
    """Impose deux opérateurs distincts et masque la première lecture jusqu'à la seconde."""
    if not _is_current(item):
        raise AnnotationAccessError("Les preuves ont changé ou l'annonce a été supprimée. Complétez la file pour la remplacer.")
    if item["final_review_id"]:
        final = connection.execute(
            "SELECT legacy_revision, outcome FROM listing_identification_reviews WHERE id=?", (item["final_review_id"],)
        ).fetchone()
        if item["latest_decision_id"] == item["final_review_id"] and (item["latest_legacy_id"] or 0) <= final["legacy_revision"] and final["outcome"] != "withdrawn":
            return "done"
        return "adjudication"
    if item["first_review_id"] is None:
        stage = "first"
    elif item["requires_second"] and item["second_review_id"] is None:
        stage = "second"
    else:
        return "adjudication"
    seen = connection.execute(
        "SELECT 1 FROM listing_identification_reviews WHERE snapshot_id=? AND validated_by=?",
        (item["snapshot_id"], operator),
    ).fetchone()
    if seen:
        raise AnnotationAccessError("Une lecture indépendante par un autre opérateur est requise pour cette annonce.")
    return stage


def validate_assignment(
    connection: sqlite3.Connection, assignment_id: int, stage: str, snapshot_id: int,
    operator: str, review: ReviewInput,
) -> dict[str, Any]:
    """Valide l'étape dans la même transaction que l'enregistrement de la lecture."""
    from app.identification.resolution import IdentificationConflictError

    item = assignment(connection, assignment_id)
    if item["snapshot_id"] != snapshot_id or assignment_stage(connection, item, operator) != stage:
        raise IdentificationConflictError("La file a changé : rechargez la tâche d'annotation.")
    expected_ids = [item["first_review_id"]] + ([item["second_review_id"]] if item["second_review_id"] else [])
    if stage in ("first", "second"):
        if review.review_kind != "annotation":
            raise ValueError("Une lecture indépendante doit être enregistrée comme annotation.")
    elif stage == "adjudication":
        if review.review_kind != "adjudication" or set(review.reviewed_annotation_ids) != set(expected_ids):
            raise ValueError("La décision doit référencer exactement les lectures de cette tâche.")
    else:
        raise ValueError("Cette tâche est déjà terminée.")
    return item


def attach_review(connection: sqlite3.Connection, item: dict[str, Any], stage: str, review_id: int) -> None:
    """Relie atomiquement une lecture à son affectation après validation."""
    column = {"first": "first_review_id", "second": "second_review_id", "adjudication": "final_review_id"}[stage]
    connection.execute(f"UPDATE annotation_pilot_items SET {column}=? WHERE id=?", (review_id, item["id"]))


def _identity(review: sqlite3.Row) -> tuple[str, str | None]:
    """Compare les issues humaines et l'identité sans utiliser les scores automatiques."""
    return review["outcome"], review["validated_tcgdex_id"]


def pilot_dashboard(connection: sqlite3.Connection, operator: str) -> dict[str, Any]:
    """Calcule l'avancement et l'accord pré-arbitrage sur les preuves courantes."""
    pilot = connection.execute("SELECT * FROM annotation_pilots ORDER BY id DESC LIMIT 1").fetchone()
    if pilot is None:
        return {"pilot": None}
    items = _item_rows(connection, pilot["id"])
    reviews = {row["id"]: row for row in connection.execute(
        """SELECT r.* FROM listing_identification_reviews r JOIN annotation_pilot_items i
        ON r.id IN (i.first_review_id, i.second_review_id, i.final_review_id) WHERE i.pilot_id=?""", (pilot["id"],)
    )}
    active = [item for item in items if _is_current(item)]
    paired = [item for item in active if item["second_review_id"]]
    identity_agreement = sum(_identity(reviews[item["first_review_id"]]) == _identity(reviews[item["second_review_id"]]) for item in paired)
    text_agreement = sum(reviews[item["first_review_id"]]["text_sufficient"] == reviews[item["second_review_id"]]["text_sufficient"] for item in paired)
    diagnostics: Counter[str] = Counter()
    finalized = 0
    for item in items:
        item["current"] = _is_current(item)
        item["final_revised"] = False
        try:
            item["stage"] = assignment_stage(connection, item, operator)
            item["blocked"] = False
        except AnnotationAccessError:
            item["stage"] = "blocked"
            item["blocked"] = True
        if not item["current"] or not item["final_review_id"]:
            continue
        final = reviews[item["final_review_id"]]
        if item["latest_decision_id"] != final["id"] or (item["latest_legacy_id"] or 0) > final["legacy_revision"] or final["outcome"] == "withdrawn":
            item["final_revised"] = True
            continue
        finalized += 1
        if final["outcome"] == "matched":
            card = final["validated_tcgdex_id"]
            candidates = json.loads(item["candidate_tcgdex_ids_json"])
            diagnostic = "correct" if card == item["automatic_top1_tcgdex_id"] else "ranking_error" if card in candidates else "candidate_missing"
        else:
            diagnostic = {"no_catalog_match": "catalog_missing", "insufficient_evidence": "insufficient_text"}.get(final["outcome"], "business_rule")
        diagnostics[diagnostic] += 1
    return {
        "pilot": pilot, "items": items, "selected": len(active), "obsolete": len(items) - len(active),
        "first_count": sum(item["first_review_id"] is not None for item in active),
        "second_required": sum(item["requires_second"] for item in active),
        "second_count": len(paired), "double_target": (pilot["target_size"] + 4) // 5,
        "finalized": finalized, "identity_agreement": identity_agreement, "text_agreement": text_agreement,
        "disagreements": len(paired) - identity_agreement,
        "diagnostics": diagnostics, "diagnosis_labels": DIAGNOSES,
        "status_counts": Counter(item["initial_status"] for item in active),
        "batches": connection.execute("SELECT count(*) FROM annotation_sampling_batches WHERE pilot_id=?", (pilot["id"],)).fetchone()[0],
    }
