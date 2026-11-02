"""Évalue hors ligne des rapports d'identification avec des labels humains.

Ce module ne lance aucun moteur d'identification et n'accède ni au réseau ni à
la base opérationnelle. Il lit uniquement des artefacts JSON déjà enregistrés.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Any, Iterable, Sequence

LABEL_SCHEMA_VERSION = "identification-labels-v1"
EVALUATION_SCHEMA_VERSION = "identification-evaluation-v1"
VARIANTS = ("title_only", "ocr_only", "combined")
ANNOTATION_STATUSES = {"unannotated", "annotated", "needs_arbitration"}
PRODUCT_TYPES = {"single_card", "lot", "sealed", "choice", "unknown"}
CATALOG_PRESENCES = {"present", "absent", "unknown"}
PREDICTION_STATUSES = {"identified", "ambiguous", "unidentified", "lot"}
DECISION_ORIGINS = {"automatic", "human", "mixed", "unknown"}
VERSION_FIELDS = ("catalog_version", "data_version", "pipeline_version")


class EvaluationError(ValueError):
    """Signale une entrée invalide ou une association non fiable."""


@dataclass(frozen=True)
class Annotation:
    """Vérité terrain humaine indépendante pour une annonce."""

    listing_id: str
    status: str
    product_type: str
    identity_determinable: bool | None
    expected_tcgdex_id: str | None
    catalog_presence: str
    external_identity: str | None


@dataclass(frozen=True)
class Prediction:
    """Projection minimale d'un résultat figé dans un rapport."""

    status: str
    tcgdex_id: str | None
    candidates: tuple[str, ...]
    decision_origin: str


@dataclass(frozen=True)
class Report:
    """Rapport validé, indexé par identifiant stable d'annonce."""

    report_id: str
    items: dict[str, dict[str, Any]]
    predictions: dict[str, dict[str, Prediction | None]]
    metadata: dict[str, Any]


def _read_json(path: str | Path) -> Any:
    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as error:
        raise EvaluationError(f"Impossible de lire {source} : {error.strerror or error}") from error
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise EvaluationError(
            f"JSON invalide dans {source}, ligne {error.lineno}, colonne {error.colno} : {error.msg}"
        ) from error


def _optional_string(value: Any, field: str, context: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise EvaluationError(f"{context} : {field} doit être une chaîne non vide ou null")
    return value.strip()


def _parse_annotations(data: Any, allowed_ids: set[str]) -> dict[str, Annotation]:
    if not isinstance(data, dict):
        raise EvaluationError("Le fichier d'annotations doit contenir un objet JSON")
    if data.get("schema_version") != LABEL_SCHEMA_VERSION:
        raise EvaluationError(f"schema_version d'annotation attendu : {LABEL_SCHEMA_VERSION}")
    raw_annotations = data.get("annotations")
    if not isinstance(raw_annotations, list):
        raise EvaluationError("Le fichier d'annotations doit contenir une liste annotations")

    annotations: dict[str, Annotation] = {}
    for position, raw in enumerate(raw_annotations, start=1):
        context = f"Annotation {position}"
        if not isinstance(raw, dict):
            raise EvaluationError(f"{context} : un objet JSON est requis")
        listing_id = _optional_string(raw.get("listing_id"), "listing_id", context)
        if listing_id is None:
            raise EvaluationError(f"{context} : listing_id est requis")
        if listing_id in annotations:
            raise EvaluationError(f"Identifiant d'annotation dupliqué : {listing_id}")
        if listing_id not in allowed_ids:
            raise EvaluationError(f"Annotation impossible à rattacher au rapport : {listing_id}")

        status = raw.get("status")
        if status not in ANNOTATION_STATUSES:
            raise EvaluationError(f"{context} ({listing_id}) : statut d'annotation inconnu {status!r}")
        product_type = raw.get("product_type", "unknown")
        if product_type not in PRODUCT_TYPES:
            raise EvaluationError(f"{context} ({listing_id}) : type de produit inconnu {product_type!r}")
        catalog_presence = raw.get("catalog_presence", "unknown")
        if catalog_presence not in CATALOG_PRESENCES:
            raise EvaluationError(
                f"{context} ({listing_id}) : présence catalogue inconnue {catalog_presence!r}"
            )
        expected_id = _optional_string(raw.get("expected_tcgdex_id"), "expected_tcgdex_id", context)
        external_identity = _optional_string(raw.get("external_identity"), "external_identity", context)
        determinable = raw.get("identity_determinable")
        if status == "annotated":
            if not isinstance(determinable, bool):
                raise EvaluationError(
                    f"{context} ({listing_id}) : identity_determinable doit être true ou false"
                )
            if product_type != "single_card" and (determinable or expected_id is not None):
                raise EvaluationError(
                    f"{context} ({listing_id}) : un produit non unitaire ne peut pas avoir d'identité unitaire attendue"
                )
            if not determinable and expected_id is not None:
                raise EvaluationError(
                    f"{context} ({listing_id}) : identité attendue incohérente avec identity_determinable=false"
                )
        else:
            determinable = determinable if isinstance(determinable, bool) else None

        annotations[listing_id] = Annotation(
            listing_id=listing_id,
            status=status,
            product_type=product_type,
            identity_determinable=determinable,
            expected_tcgdex_id=expected_id,
            catalog_presence=catalog_presence,
            external_identity=external_identity,
        )
    return annotations


def _parse_prediction(raw: Any, report_origin: str, context: str) -> Prediction:
    if not isinstance(raw, dict):
        raise EvaluationError(f"{context} : une variante doit être un objet JSON ou null")
    status = raw.get("status")
    if status not in PREDICTION_STATUSES:
        raise EvaluationError(f"{context} : statut de prédiction inconnu {status!r}")
    tcg_id = _optional_string(raw.get("tcgdex_id"), "tcgdex_id", context)
    if status == "identified" and tcg_id is None:
        raise EvaluationError(f"{context} : une décision identified exige tcgdex_id")
    if status != "identified" and tcg_id is not None:
        raise EvaluationError(f"{context} : tcgdex_id est réservé au statut identified")

    origin = raw.get("decision_origin", report_origin)
    if origin == "human_confirmed":
        origin = "human"
    if origin not in DECISION_ORIGINS:
        raise EvaluationError(f"{context} : origine de décision inconnue {origin!r}")

    raw_candidates = raw.get("candidates", [])
    if not isinstance(raw_candidates, list):
        raise EvaluationError(f"{context} : candidates doit être une liste")
    candidates: list[str] = []
    for candidate in raw_candidates:
        if isinstance(candidate, str):
            candidate_id = candidate.strip()
        elif isinstance(candidate, dict):
            candidate_id = candidate.get("tcgdex_id")
        else:
            candidate_id = None
        if not isinstance(candidate_id, str) or not candidate_id.strip():
            raise EvaluationError(f"{context} : chaque candidat doit porter tcgdex_id")
        candidate_id = candidate_id.strip()
        if candidate_id not in candidates:
            candidates.append(candidate_id)
    return Prediction(status, tcg_id, tuple(candidates), origin)


def _parse_report(data: Any) -> Report:
    if isinstance(data, list):
        raw_items = data
        raw_report: dict[str, Any] = {}
    elif isinstance(data, dict):
        raw_items = data.get("items")
        raw_report = data
    else:
        raise EvaluationError("Le rapport doit contenir un objet JSON avec une liste items")
    if not isinstance(raw_items, list):
        raise EvaluationError("Le rapport doit contenir une liste items")

    metadata_container = raw_report.get("metadata")
    if metadata_container is not None and not isinstance(metadata_container, dict):
        raise EvaluationError("metadata doit être un objet JSON")
    metadata = dict(metadata_container or {})
    for field in ("id", "label", "created_at", "decision_origin", *VERSION_FIELDS):
        if field in raw_report:
            metadata[field] = raw_report[field]
    report_origin = metadata.get("decision_origin", "unknown")
    if report_origin == "human_confirmed":
        report_origin = "human"
    if report_origin not in DECISION_ORIGINS:
        raise EvaluationError(f"Origine de décision du rapport inconnue : {report_origin!r}")

    items: dict[str, dict[str, Any]] = {}
    predictions: dict[str, dict[str, Prediction | None]] = {}
    for position, item in enumerate(raw_items, start=1):
        context = f"Annonce {position}"
        if not isinstance(item, dict):
            raise EvaluationError(f"{context} : un objet JSON est requis")
        identifiers = [
            (field, item[field].strip())
            for field in ("listing_id", "url")
            if isinstance(item.get(field), str) and item[field].strip()
        ]
        if len(identifiers) != 1:
            raise EvaluationError(
                f"{context} : association ambiguë ; fournir exactement un identifiant stable listing_id ou url"
            )
        listing_id = identifiers[0][1]
        if listing_id in items:
            raise EvaluationError(f"Identifiant d'annonce dupliqué : {listing_id}")
        items[listing_id] = item
        predictions[listing_id] = {}
        for variant in VARIANTS:
            raw_prediction = item.get(variant)
            if variant == "title_only" and raw_prediction is None and "title_identification" in item:
                raw_prediction = item.get("title_identification")
            predictions[listing_id][variant] = (
                None
                if raw_prediction is None
                else _parse_prediction(raw_prediction, report_origin, f"{context} ({listing_id}), {variant}")
            )

    report_id = str(metadata.get("id") or metadata.get("label") or "rapport sans identifiant")
    return Report(report_id=report_id, items=items, predictions=predictions, metadata=metadata)


def _metric(numerator: int, denominator: int) -> dict[str, Any]:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": numerator / denominator if denominator else None,
    }


def _is_automatic(prediction: Prediction | None) -> bool:
    # Les rapports historiques ne portaient pas d'origine. Ils restent
    # descriptibles, mais l'origine inconnue est publiée comme une limite.
    return prediction is not None and prediction.decision_origin in {"automatic", "unknown"}


def _is_accepted(prediction: Prediction | None) -> bool:
    return _is_automatic(prediction) and prediction is not None and prediction.status == "identified"


def _is_evaluable(annotation: Annotation) -> bool:
    return (
        annotation.status == "annotated"
        and annotation.product_type == "single_card"
        and annotation.identity_determinable is True
        and annotation.expected_tcgdex_id is not None
    )


def _empty_confusion_matrix() -> dict[str, dict[str, int]]:
    columns = ("single_card", "lot", "abstained", "missing", "human_or_mixed")
    return {actual: {predicted: 0 for predicted in columns} for actual in sorted(PRODUCT_TYPES)}


def _calculate_variant(
    items: dict[str, dict[str, Any]],
    predictions: dict[str, dict[str, Prediction | None]],
    annotations: dict[str, Annotation],
    variant: str,
) -> dict[str, Any]:
    listing_ids = sorted(items)
    annotated_ids = [
        listing_id
        for listing_id in listing_ids
        if annotations.get(listing_id) is not None and annotations[listing_id].status == "annotated"
    ]
    excluded_ids = [
        listing_id
        for listing_id in listing_ids
        if annotations.get(listing_id) is not None
        and annotations[listing_id].status == "needs_arbitration"
    ]
    available_ids = [listing_id for listing_id in listing_ids if predictions[listing_id][variant] is not None]
    missing_ids = [listing_id for listing_id in listing_ids if predictions[listing_id][variant] is None]
    photo_not_analyzed_ids = []
    if variant == "ocr_only":
        for listing_id in missing_ids:
            item = items[listing_id]
            if ("ocr" in item and item.get("ocr") is None) or item.get("image_status"):
                photo_not_analyzed_ids.append(listing_id)

    evaluable_ids = [listing_id for listing_id in annotated_ids if _is_evaluable(annotations[listing_id])]
    accepted_ids: list[str] = []
    accepted_evaluable_ids: list[str] = []
    correct_ids: list[str] = []
    human_decisions: list[str] = []
    unknown_origin_decisions: list[str] = []
    origin_counts = {origin: 0 for origin in sorted(DECISION_ORIGINS)}
    confusion = _empty_confusion_matrix()

    top3_denominator_ids: list[str] = []
    top3_hit_ids: list[str] = []
    non_single_ids: list[str] = []
    non_single_false_accept_ids: list[str] = []
    out_of_catalog_ids: list[str] = []
    out_of_catalog_false_accept_ids: list[str] = []

    for listing_id in annotated_ids:
        annotation = annotations[listing_id]
        prediction = predictions[listing_id][variant]
        if prediction is not None:
            origin_counts[prediction.decision_origin] += 1
        accepted = _is_accepted(prediction)
        if accepted:
            accepted_ids.append(listing_id)
            if prediction is not None and prediction.decision_origin == "unknown":
                unknown_origin_decisions.append(listing_id)
        if (
            prediction is not None
            and prediction.status == "identified"
            and prediction.decision_origin in {"human", "mixed"}
        ):
            human_decisions.append(listing_id)

        if _is_evaluable(annotation):
            if accepted:
                accepted_evaluable_ids.append(listing_id)
                if prediction is not None and prediction.tcgdex_id == annotation.expected_tcgdex_id:
                    correct_ids.append(listing_id)

        if (
            annotation.product_type == "single_card"
            and annotation.identity_determinable is True
            and annotation.expected_tcgdex_id is not None
            and annotation.catalog_presence == "present"
        ):
            top3_denominator_ids.append(listing_id)
            if prediction is not None and annotation.expected_tcgdex_id in prediction.candidates[:3]:
                top3_hit_ids.append(listing_id)

        if annotation.product_type in {"lot", "sealed"}:
            non_single_ids.append(listing_id)
            if accepted:
                non_single_false_accept_ids.append(listing_id)
        if annotation.product_type == "single_card" and annotation.catalog_presence == "absent":
            out_of_catalog_ids.append(listing_id)
            if accepted:
                out_of_catalog_false_accept_ids.append(listing_id)

        if prediction is None:
            predicted_class = "missing"
        elif prediction.decision_origin in {"human", "mixed"}:
            predicted_class = "human_or_mixed"
        elif prediction.status == "identified":
            predicted_class = "single_card"
        elif prediction.status == "lot":
            predicted_class = "lot"
        else:
            predicted_class = "abstained"
        confusion[annotation.product_type][predicted_class] += 1

    predicted_lot = sum(confusion[actual]["lot"] for actual in PRODUCT_TYPES)
    actual_lot = len(
        [listing_id for listing_id in annotated_ids if annotations[listing_id].product_type == "lot"]
    )
    correct_lot = confusion["lot"]["lot"]
    counts = {
        "total": len(listing_ids),
        "annotated": len(annotated_ids),
        "unannotated": len(listing_ids) - len(annotated_ids) - len(excluded_ids),
        "excluded": len(excluded_ids),
        "variant_available": len(available_ids),
        "variant_missing": len(missing_ids),
        "photo_not_analyzed": len(photo_not_analyzed_ids),
        "identity_evaluable": len(evaluable_ids),
        "accepted_decisions": len(accepted_ids),
        "accepted_evaluable": len(accepted_evaluable_ids),
        "accepted_not_evaluable": len(accepted_ids) - len(accepted_evaluable_ids),
        "correct_identities": len(correct_ids),
        "human_decisions_excluded": len(human_decisions),
        "unknown_origin_decisions": len(unknown_origin_decisions),
        "top3_reference_absent_from_candidates": len(top3_denominator_ids) - len(top3_hit_ids),
        "catalog_absent": len(out_of_catalog_ids),
    }
    limitations: list[str] = []
    if unknown_origin_decisions:
        limitations.append(
            "L'origine de certaines décisions acceptées est absente ; leur caractère automatique n'est pas prouvé."
        )
    if human_decisions:
        limitations.append("Les décisions humaines ou mixtes sont exclues des métriques automatiques.")
    if missing_ids:
        limitations.append("Les variantes absentes ne sont pas converties en prédictions ou en annotations.")
    if photo_not_analyzed_ids:
        limitations.append("Certaines photos n'ont pas été analysées ; la variante OCR seule est indisponible.")
    if counts["accepted_not_evaluable"]:
        limitations.append("Certaines décisions acceptées n'ont pas de référence humaine exacte évaluable.")

    return {
        "counts": counts,
        "availability": {
            "available_ids": available_ids,
            "missing_ids": missing_ids,
            "photo_not_analyzed_ids": photo_not_analyzed_ids,
        },
        "metrics": {
            "automatic_coverage": _metric(len(accepted_evaluable_ids), len(evaluable_ids)),
            "automatic_precision": _metric(len(correct_ids), len(accepted_evaluable_ids)),
            "correct_overall": _metric(len(correct_ids), len(evaluable_ids)),
            "top3_recall": _metric(len(top3_hit_ids), len(top3_denominator_ids)),
            "lot_or_sealed_false_acceptance": _metric(
                len(non_single_false_accept_ids), len(non_single_ids)
            ),
            "out_of_catalog_false_acceptance": _metric(
                len(out_of_catalog_false_accept_ids), len(out_of_catalog_ids)
            ),
            "lot_precision": _metric(correct_lot, predicted_lot),
            "lot_recall": _metric(correct_lot, actual_lot),
        },
        "lot_confusion_matrix": confusion,
        "decision_origins": origin_counts,
        "limitations": limitations,
    }


def _evaluate_prepared(report: Report, annotations: dict[str, Annotation]) -> dict[str, Any]:
    limitations = [
        "Résultats descriptifs sur les cas annotés ; aucune qualification statistique n'est déduite de petits échantillons."
    ]
    if any(annotation.status == "needs_arbitration" for annotation in annotations.values()):
        limitations.append("Les annotations à arbitrer sont exclues des métriques.")
    return {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "report": report.metadata | {"id": report.report_id},
        "variants": {
            variant: _calculate_variant(report.items, report.predictions, annotations, variant)
            for variant in VARIANTS
        },
        "limitations": limitations,
    }


def evaluate_data(report_data: Any, labels_data: Any) -> dict[str, Any]:
    """Évalue des objets JSON déjà chargés, sans accès externe."""
    report = _parse_report(report_data)
    annotations = _parse_annotations(labels_data, set(report.items))
    return _evaluate_prepared(report, annotations)


def evaluate_report(report_path: str | Path, labels_path: str | Path) -> dict[str, Any]:
    """Lit un rapport et ses annotations puis calcule les métriques."""
    return evaluate_data(_read_json(report_path), _read_json(labels_path))


def _metadata_limitations(before: Report, after: Report) -> list[str]:
    limitations: list[str] = []
    for field in VERSION_FIELDS:
        before_value = before.metadata.get(field)
        after_value = after.metadata.get(field)
        if before_value is None or after_value is None:
            limitations.append(f"{field} absent dans au moins un rapport : comparabilité limitée.")
        elif before_value != after_value:
            limitations.append(
                f"{field} différent ({before_value!r} puis {after_value!r}) : comparabilité limitée."
            )
    return limitations


def _delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_value = before["value"]
    after_value = after["value"]
    return {
        "before": before_value,
        "after": after_value,
        "delta": after_value - before_value if before_value is not None and after_value is not None else None,
    }


def _compare_variant(
    before: Report,
    after: Report,
    annotations: dict[str, Annotation],
    common_ids: set[str],
    variant: str,
) -> dict[str, Any]:
    missing_before = sorted(
        listing_id for listing_id in common_ids if before.predictions[listing_id][variant] is None
    )
    missing_after = sorted(
        listing_id for listing_id in common_ids if after.predictions[listing_id][variant] is None
    )
    paired_ids = sorted(
        listing_id
        for listing_id in common_ids
        if before.predictions[listing_id][variant] is not None
        and after.predictions[listing_id][variant] is not None
    )
    paired_set = set(paired_ids)
    before_items = {key: value for key, value in before.items.items() if key in paired_set}
    after_items = {key: value for key, value in after.items.items() if key in paired_set}
    before_predictions = {key: value for key, value in before.predictions.items() if key in paired_set}
    after_predictions = {key: value for key, value in after.predictions.items() if key in paired_set}
    before_metrics = _calculate_variant(before_items, before_predictions, annotations, variant)
    after_metrics = _calculate_variant(after_items, after_predictions, annotations, variant)

    categories: dict[str, list[str]] = {
        name: []
        for name in (
            "errors_corrected",
            "new_errors",
            "correct_to_incorrect",
            "correct_to_abstained",
            "wrong_to_abstained",
            "became_ambiguous",
            "became_unidentified",
            "identity_changes",
            "status_changes",
        )
    }
    for listing_id in paired_ids:
        annotation = annotations.get(listing_id)
        if annotation is None or annotation.status != "annotated":
            continue
        before_prediction = before.predictions[listing_id][variant]
        after_prediction = after.predictions[listing_id][variant]
        assert before_prediction is not None and after_prediction is not None
        if before_prediction.status != after_prediction.status:
            categories["status_changes"].append(listing_id)
        if (
            before_prediction.status == "identified"
            and after_prediction.status == "identified"
            and before_prediction.tcgdex_id != after_prediction.tcgdex_id
        ):
            categories["identity_changes"].append(listing_id)
        if after_prediction.status == "ambiguous" and before_prediction.status != "ambiguous":
            categories["became_ambiguous"].append(listing_id)
        if after_prediction.status == "unidentified" and before_prediction.status != "unidentified":
            categories["became_unidentified"].append(listing_id)
        if not _is_evaluable(annotation):
            continue

        before_accepted = _is_accepted(before_prediction)
        after_accepted = _is_accepted(after_prediction)
        before_correct = before_accepted and before_prediction.tcgdex_id == annotation.expected_tcgdex_id
        after_correct = after_accepted and after_prediction.tcgdex_id == annotation.expected_tcgdex_id
        before_wrong = before_accepted and before_prediction.tcgdex_id != annotation.expected_tcgdex_id
        after_wrong = after_accepted and after_prediction.tcgdex_id != annotation.expected_tcgdex_id
        if before_wrong and after_correct:
            categories["errors_corrected"].append(listing_id)
        if after_wrong and not before_wrong:
            categories["new_errors"].append(listing_id)
        if before_correct and after_wrong:
            categories["correct_to_incorrect"].append(listing_id)
        if before_correct and not after_accepted:
            categories["correct_to_abstained"].append(listing_id)
        if before_wrong and not after_accepted:
            categories["wrong_to_abstained"].append(listing_id)

    return {
        "paired_count": len(paired_ids),
        "missing_before_ids": missing_before,
        "missing_after_ids": missing_after,
        "changes": categories,
        "change_counts": {name: len(ids) for name, ids in categories.items()},
        "paired_metrics": {
            "before": before_metrics["metrics"],
            "after": after_metrics["metrics"],
            "delta": {
                name: _delta(before_metrics["metrics"][name], after_metrics["metrics"][name])
                for name in before_metrics["metrics"]
            },
        },
    }


def compare_data(before_data: Any, after_data: Any, labels_data: Any) -> dict[str, Any]:
    """Compare deux rapports sur leurs annonces et variantes communes."""
    before = _parse_report(before_data)
    after = _parse_report(after_data)
    annotations = _parse_annotations(labels_data, set(before.items) | set(after.items))
    common_ids = set(before.items) & set(after.items)
    return {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "mode": "comparison",
        "before": _evaluate_prepared(before, annotations),
        "after": _evaluate_prepared(after, annotations),
        "comparison": {
            "intersection_size": len(common_ids),
            "missing_from_before_ids": sorted(set(after.items) - set(before.items)),
            "missing_from_after_ids": sorted(set(before.items) - set(after.items)),
            "variants": {
                variant: _compare_variant(before, after, annotations, common_ids, variant)
                for variant in VARIANTS
            },
            "limitations": _metadata_limitations(before, after),
        },
    }


def compare_reports(
    before_path: str | Path,
    after_path: str | Path,
    labels_path: str | Path,
) -> dict[str, Any]:
    """Lit et compare deux rapports avec un même fichier d'annotations."""
    return compare_data(_read_json(before_path), _read_json(after_path), _read_json(labels_path))


def _format_metric(metric: dict[str, Any]) -> str:
    value = metric["value"]
    percentage = "indisponible" if value is None else f"{value:.1%}"
    return f"{metric['numerator']}/{metric['denominator']} ({percentage})"


def _summary_lines(result: dict[str, Any]) -> Iterable[str]:
    if result.get("mode") == "comparison":
        comparison = result["comparison"]
        yield f"Comparaison : {result['before']['report']['id']} → {result['after']['report']['id']}"
        yield f"Intersection : {comparison['intersection_size']} annonces"
        yield f"Absentes de l'avant : {len(comparison['missing_from_before_ids'])}"
        yield f"Absentes de l'après : {len(comparison['missing_from_after_ids'])}"
        for variant, values in comparison["variants"].items():
            changes = values["change_counts"]
            yield f"\n[{variant}] — {values['paired_count']} cas appariés"
            yield f"  Erreurs corrigées : {changes['errors_corrected']}"
            yield f"  Nouvelles erreurs : {changes['new_errors']}"
            yield f"  Devenues ambiguës : {changes['became_ambiguous']}"
            yield f"  Devenues non identifiées : {changes['became_unidentified']}"
            for metric_name in ("automatic_coverage", "automatic_precision", "correct_overall"):
                delta = values["paired_metrics"]["delta"][metric_name]
                before = "n/d" if delta["before"] is None else f"{delta['before']:.1%}"
                after = "n/d" if delta["after"] is None else f"{delta['after']:.1%}"
                yield f"  {metric_name} : {before} → {after}"
        for limitation in comparison["limitations"]:
            yield f"  Limite : {limitation}"
        return

    counts = result["variants"]["combined"]["counts"]
    yield f"Rapport : {result['report']['id']}"
    yield (
        f"Annonces : {counts['total']} ; annotées : {counts['annotated']} ; "
        f"non annotées : {counts['unannotated']} ; exclues : {counts['excluded']}"
    )
    for variant, values in result["variants"].items():
        yield f"\n[{variant}]"
        yield (
            f"  Disponibilité : {values['counts']['variant_available']}/{values['counts']['total']} ; "
            f"photos non analysées : {values['counts']['photo_not_analyzed']}"
        )
        for name, metric in values["metrics"].items():
            yield f"  {name} : {_format_metric(metric)}"
        for limitation in values["limitations"]:
            yield f"  Limite : {limitation}"
    for limitation in result["limitations"]:
        yield f"Limite : {limitation}"


def _write_json(path: str | Path, result: dict[str, Any]) -> None:
    destination = Path(path)
    if destination.exists():
        raise EvaluationError(f"Refus d'écraser le fichier de sortie existant : {destination}")
    try:
        with destination.open("x", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    except FileExistsError as error:
        raise EvaluationError(f"Refus d'écraser le fichier de sortie existant : {destination}") from error
    except OSError as error:
        raise EvaluationError(f"Impossible d'écrire {destination} : {error.strerror or error}") from error


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Évalue hors ligne des prédictions enregistrées avec des annotations humaines indépendantes. "
            "Aucun OCR, matcher, accès SQLite ou téléchargement n'est exécuté."
        )
    )
    parser.add_argument("--report", required=True, help="Rapport JSON de prédictions à évaluer")
    parser.add_argument("--labels", required=True, help=f"Annotations JSON au format {LABEL_SCHEMA_VERSION}")
    parser.add_argument(
        "--compare-with",
        metavar="APRES_JSON",
        help="Second rapport ; --report est alors la version avant",
    )
    parser.add_argument("--output", help="Export JSON optionnel ; un fichier existant n'est jamais écrasé")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Point d'entrée de la CLI en lecture seule."""
    parser = _argument_parser()
    args = parser.parse_args(argv)
    try:
        if args.compare_with:
            result = compare_reports(args.report, args.compare_with, args.labels)
        else:
            result = evaluate_report(args.report, args.labels)
        for line in _summary_lines(result):
            print(line)
        if args.output:
            _write_json(args.output, result)
            print(f"\nExport JSON : {args.output}")
    except EvaluationError as error:
        parser.exit(2, f"Erreur : {error}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
