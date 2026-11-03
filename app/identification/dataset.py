"""Export reproductible de labels humains ; aucun entraînement implicite."""

import json
import sqlite3
from typing import Any

from app.identification.reviews import canonical_json, fingerprint, text_observed_attributes


def build_dataset(connection: sqlite3.Connection) -> bytes:
    """Exporte décisions actives, annotations, catalogues figés et manifeste.

    Les snapshots obsolètes, supprimés ou sans original fiable sont conservés
    dans l'audit mais exclus du futur train. Aucun vendeur ni JSON brut n'est
    exporté. Le group_key ne remplace pas le futur dédoublonnage interplateforme.
    """
    # La transaction de lecture garantit un instantané cohérent face au worker.
    with connection:
        if not connection.in_transaction:
            connection.execute("BEGIN")
        reviews = connection.execute(
            """SELECT r.*, s.listing_id, s.input_hash, s.title, s.description,
            s.attributes_json, s.input_origin, s.source_kind, s.platform, s.group_key,
            s.normalization_version, s.observations_json, s.pipeline_version,
            (SELECT max(d.id) FROM listing_identification_decisions d
             WHERE d.listing_id=s.listing_id) AS latest_legacy_id,
            (SELECT c.identification_snapshot_id FROM catalog_items c
             WHERE c.id=s.listing_id) AS latest_snapshot_id,
            (SELECT max(r2.id) FROM listing_identification_reviews r2
             JOIN listing_identification_snapshots s3 ON s3.id=r2.snapshot_id
             WHERE s3.listing_id=s.listing_id AND r2.review_kind <> 'annotation') AS latest_decision_id
            FROM listing_identification_reviews r
            JOIN listing_identification_snapshots s ON s.id=r.snapshot_id ORDER BY r.id"""
        ).fetchall()
        assignments = connection.execute("SELECT * FROM annotation_pilot_items ORDER BY id").fetchall()
        retrieval_metadata = {}
        for batch in connection.execute("SELECT id, frame_json FROM annotation_sampling_batches"):
            frame = json.loads(batch["frame_json"])
            metadata = frame[0] if frame else {}
            retrieval_metadata[batch["id"]] = {
                "retrieval_version": metadata.get("retrieval_version", "rules-v1"),
                "candidate_scope": f"up_to_{metadata.get('candidate_limit', 10)}_proposed_candidates",
                "pipeline_version": metadata.get("pipeline_version", "lexical-v1"),
            }
        by_review = {}
        for item in assignments:
            for role, column in (("first", "first_review_id"), ("second", "second_review_id"), ("final", "final_review_id")):
                if item[column] is not None:
                    by_review[item[column]] = {
                        "assignment_id": item["id"], "pilot_id": item["pilot_id"], "batch_id": item["batch_id"],
                        "role": role, "stratum": json.loads(item["stratum_key"]),
                        "selected_in_stratum": item["selected_in_stratum"],
                        "population_in_stratum": item["population_in_stratum"],
                        "requires_second": bool(item["requires_second"]),
                        "initial_status": item["initial_status"],
                        "automatic_top1_tcgdex_id": item["automatic_top1_tcgdex_id"],
                        "candidate_tcgdex_ids": json.loads(item["candidate_tcgdex_ids_json"]),
                        **retrieval_metadata[item["batch_id"]],
                    }
        records: list[dict[str, Any]] = []
        for row in reviews:
            reasons = []
            if row["listing_id"] is None:
                reasons.append("listing_deleted")
            if row["snapshot_id"] != row["latest_snapshot_id"]:
                reasons.append("stale_evidence")
            if row["input_origin"] == "legacy_unknown":
                reasons.append("unreliable_original")
            if row["review_kind"] == "annotation":
                reasons.append("independent_annotation")
            elif row["id"] != row["latest_decision_id"]:
                reasons.append("superseded")
            if (row["latest_legacy_id"] or 0) > row["legacy_revision"]:
                reasons.append("superseded_by_legacy_decision")
            if row["outcome"] == "withdrawn":
                reasons.append("withdrawn")
            if not row["text_sufficient"]:
                reasons.append("insufficient_text")
            records.append({
                "type": "review", "review_id": row["id"], "snapshot_id": row["snapshot_id"],
                "input_hash": row["input_hash"], "group_key": row["group_key"],
                "title": row["title"], "description": row["description"],
                "observed_attributes": text_observed_attributes(row["attributes_json"], row["observations_json"]),
                "input_origin": row["input_origin"], "source_kind": row["source_kind"],
                "platform": row["platform"],
                "normalization_version": row["normalization_version"],
                "observations": json.loads(row["observations_json"]),
                "pipeline_version": row["pipeline_version"],
                "outcome": row["outcome"], "review_kind": row["review_kind"],
                "validated_tcgdex_id": row["validated_tcgdex_id"],
                "validated_at": row["validated_at"], "catalog_version": row["catalog_version"],
                "reviewer_key": fingerprint(row["validated_by"]),
                "evidence_basis": row["evidence_basis"], "text_sufficient": bool(row["text_sufficient"]),
                "verified_attributes": json.loads(row["verified_attributes_json"]),
                "sampling_probability": row["sampling_probability"],
                "pilot_assignment": by_review.get(row["id"]),
                "supersedes_review_id": row["supersedes_review_id"],
                "reviewed_annotation_ids": json.loads(row["reviewed_annotation_ids_json"]),
                "eligible_for_text_training": not reasons,
                "exclusion_reasons": reasons,
            })
        versions = sorted({record["catalog_version"] for record in records})
        catalogs = [
            {"type": "catalog", "version": version, "cards": json.loads(connection.execute(
                "SELECT cards_json FROM identification_catalog_versions WHERE version=?", (version,)
            ).fetchone()[0])} for version in versions
        ]
        batches = [{
            "type": "sampling_batch", "batch_id": row["id"], "pilot_id": row["pilot_id"],
            "strategy_version": row["strategy_version"], "target_size": row["target_size"],
            "seed": row["seed"], "frame": json.loads(row["frame_json"]),
            "selected_count": row["selected_count"], "double_count": row["double_count"],
            "catalog_version": row["catalog_version"], "created_at": row["created_at"],
        } for row in connection.execute(
            """SELECT b.*, p.strategy_version, p.target_size FROM annotation_sampling_batches b
            JOIN annotation_pilots p ON p.id=b.pilot_id ORDER BY b.id"""
        )]
        # Un tirage sans lecture reste reproductible : conserver son catalogue aussi.
        for version in sorted({row["catalog_version"] for row in batches} - set(versions)):
            catalogs.append({"type": "catalog", "version": version, "cards": json.loads(connection.execute(
                "SELECT cards_json FROM identification_catalog_versions WHERE version=?", (version,)
            ).fetchone()[0])})
        versions = sorted(set(versions) | {row["catalog_version"] for row in batches})
    content = catalogs + batches + records
    manifest = {
        "type": "manifest", "schema_version": "identity-pilot-v2", "dataset_hash": fingerprint(content),
        "review_count": len(records),
        "eligible_count": sum(record["eligible_for_text_training"] for record in records),
        "catalog_versions": versions,
        "sampling_batch_count": len(batches),
        "scope": "text_only; no split; exact source groups only; no model trained",
    }
    return ("\n".join(canonical_json(row) for row in [manifest, *content]) + "\n").encode("utf-8")
