"""Fixtures synthétiques du comparateur hors ligne, sans moteur ni réseau."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.evaluate_identification import (
    EvaluationError,
    compare_data,
    evaluate_data,
    main,
)


def prediction(
    status: str = "unidentified",
    tcg_id: str | None = None,
    candidates: list[str] | None = None,
    origin: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": status,
        "tcgdex_id": tcg_id,
        "candidates": [{"tcgdex_id": candidate} for candidate in (candidates or [])],
    }
    if origin is not None:
        result["decision_origin"] = origin
    return result


def report(items: list[dict[str, Any]], **metadata: Any) -> dict[str, Any]:
    return {
        "id": "synthetic-report",
        "decision_origin": "automatic",
        "catalog_version": "synthetic-catalog-v1",
        "data_version": "synthetic-data-v1",
        "pipeline_version": "synthetic-pipeline-v1",
        **metadata,
        "items": items,
    }


def item(
    listing_id: str,
    *,
    title: dict[str, Any] | None = None,
    ocr: dict[str, Any] | None = None,
    combined: dict[str, Any] | None = None,
    image_status: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "listing_id": listing_id,
        "title_only": title,
        "ocr_only": ocr,
        "combined": combined,
    }
    if image_status is not None:
        result["image_status"] = image_status
        result["ocr"] = None
    return result


def annotation(
    listing_id: str,
    *,
    status: str = "annotated",
    product_type: str = "single_card",
    determinable: bool | None = True,
    expected_id: str | None = None,
    catalog_presence: str = "present",
) -> dict[str, Any]:
    return {
        "listing_id": listing_id,
        "status": status,
        "product_type": product_type,
        "identity_determinable": determinable,
        "expected_tcgdex_id": expected_id,
        "catalog_presence": catalog_presence,
        "external_identity": None,
    }


def labels(*annotations: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "identification-labels-v1",
        "catalog_version": "synthetic-catalog-v1",
        "annotations": list(annotations),
    }


def combined_metrics(result: dict[str, Any]) -> dict[str, Any]:
    return result["variants"]["combined"]["metrics"]


def test_identity_precision_coverage_and_correct_overall() -> None:
    data = report(
        [
            item("correct", combined=prediction("identified", "card-a", ["card-a"])),
            item("incorrect", combined=prediction("identified", "card-x", ["card-b"])),
        ]
    )
    truth = labels(
        annotation("correct", expected_id="card-a"),
        annotation("incorrect", expected_id="card-b"),
    )

    metrics = combined_metrics(evaluate_data(data, truth))

    assert metrics["automatic_coverage"] == {"numerator": 2, "denominator": 2, "value": 1.0}
    assert metrics["automatic_precision"] == {"numerator": 1, "denominator": 2, "value": 0.5}
    assert metrics["correct_overall"] == {"numerator": 1, "denominator": 2, "value": 0.5}
    assert metrics["top3_recall"]["value"] == 1.0


def test_correct_card_only_in_top3_is_recall_not_accepted_identity() -> None:
    data = report(
        [item("top3", combined=prediction("ambiguous", candidates=["other-1", "other-2", "expected"]))]
    )
    truth = labels(annotation("top3", expected_id="expected"))

    metrics = combined_metrics(evaluate_data(data, truth))

    assert metrics["top3_recall"] == {"numerator": 1, "denominator": 1, "value": 1.0}
    assert metrics["automatic_precision"]["denominator"] == 0
    assert metrics["automatic_precision"]["value"] is None
    assert metrics["correct_overall"]["value"] == 0.0


def test_lot_false_acceptance_and_confusion_matrix() -> None:
    data = report(
        [
            item("lot-wrong", combined=prediction("identified", "card-x")),
            item("lot-right", combined=prediction("lot")),
            item("sealed", combined=prediction("lot")),
        ]
    )
    truth = labels(
        annotation("lot-wrong", product_type="lot", determinable=False, catalog_presence="unknown"),
        annotation("lot-right", product_type="lot", determinable=False, catalog_presence="unknown"),
        annotation("sealed", product_type="sealed", determinable=False, catalog_presence="unknown"),
    )

    variant = evaluate_data(data, truth)["variants"]["combined"]

    assert variant["metrics"]["lot_or_sealed_false_acceptance"] == {
        "numerator": 1,
        "denominator": 3,
        "value": 1 / 3,
    }
    assert variant["metrics"]["lot_precision"]["value"] == 0.5
    assert variant["metrics"]["lot_recall"]["value"] == 0.5
    assert variant["lot_confusion_matrix"]["lot"]["single_card"] == 1
    assert variant["lot_confusion_matrix"]["lot"]["lot"] == 1
    assert variant["lot_confusion_matrix"]["sealed"]["lot"] == 1


def test_out_of_catalog_is_distinct_from_absence_in_candidates() -> None:
    data = report(
        [
            item("absent", combined=prediction("identified", "fabricated")),
            item("not-in-top3", combined=prediction("ambiguous", candidates=["other"])),
        ]
    )
    truth = labels(
        annotation("absent", expected_id=None, catalog_presence="absent"),
        annotation("not-in-top3", expected_id="expected", catalog_presence="present"),
    )

    variant = evaluate_data(data, truth)["variants"]["combined"]

    assert variant["metrics"]["out_of_catalog_false_acceptance"]["value"] == 1.0
    assert variant["metrics"]["top3_recall"]["value"] == 0.0
    assert variant["counts"]["catalog_absent"] == 1
    assert variant["counts"]["top3_reference_absent_from_candidates"] == 1


def test_missing_unannotated_and_arbitration_are_not_correctness() -> None:
    data = report(
        [
            item("annotated", combined=prediction("unidentified")),
            item("absent-label", combined=prediction("identified", "card-x")),
            item("explicit-unannotated", combined=prediction("identified", "card-x")),
            item("arbitration", combined=prediction("identified", "card-x")),
        ]
    )
    truth = labels(
        annotation("annotated", expected_id="expected"),
        annotation("explicit-unannotated", status="unannotated", determinable=None, expected_id=None),
        annotation(
            "arbitration",
            status="needs_arbitration",
            product_type="unknown",
            determinable=None,
            expected_id=None,
            catalog_presence="unknown",
        ),
    )

    counts = evaluate_data(data, truth)["variants"]["combined"]["counts"]

    assert counts["total"] == 4
    assert counts["annotated"] == 1
    assert counts["unannotated"] == 2
    assert counts["excluded"] == 1
    assert counts["accepted_decisions"] == 0


def test_absent_ocr_variant_and_photo_not_analyzed_are_explicit() -> None:
    data = report(
        [
            item(
                "no-ocr",
                title=prediction("identified", "expected", ["expected"]),
                combined=prediction("identified", "expected", ["expected"]),
                image_status="non analysée : photo absente",
            )
        ]
    )
    truth = labels(annotation("no-ocr", expected_id="expected"))

    result = evaluate_data(data, truth)
    ocr_variant = result["variants"]["ocr_only"]

    assert ocr_variant["counts"]["variant_missing"] == 1
    assert ocr_variant["counts"]["photo_not_analyzed"] == 1
    assert ocr_variant["availability"]["photo_not_analyzed_ids"] == ["no-ocr"]
    assert ocr_variant["metrics"]["automatic_coverage"]["value"] == 0.0
    assert result["variants"]["title_only"]["metrics"]["automatic_precision"]["value"] == 1.0


def test_duplicate_report_identifier_is_rejected() -> None:
    data = report([item("duplicate"), item("duplicate")])

    with pytest.raises(EvaluationError, match="annonce dupliqué"):
        evaluate_data(data, labels())


def test_duplicate_annotation_identifier_is_rejected() -> None:
    data = report([item("duplicate")])
    truth = labels(
        annotation("duplicate", expected_id="card-a"),
        annotation("duplicate", expected_id="card-b"),
    )

    with pytest.raises(EvaluationError, match="annotation dupliqué"):
        evaluate_data(data, truth)


def test_incoherent_annotation_is_rejected() -> None:
    data = report([item("lot")])
    truth = labels(
        annotation("lot", product_type="lot", determinable=True, expected_id="card-a")
    )

    with pytest.raises(EvaluationError, match="non unitaire"):
        evaluate_data(data, truth)


def test_unattached_annotation_is_rejected() -> None:
    data = report([item("known")])
    truth = labels(annotation("unknown", expected_id="card-a"))

    with pytest.raises(EvaluationError, match="impossible à rattacher"):
        evaluate_data(data, truth)


def test_ambiguous_stable_identifiers_are_rejected() -> None:
    data = report(
        [{"listing_id": "internal-id", "url": "https://example.invalid/item", "combined": None}]
    )

    with pytest.raises(EvaluationError, match="association ambiguë"):
        evaluate_data(data, labels())


def test_comparison_is_paired_and_reports_regressions_and_missing_cases() -> None:
    before = report(
        [
            item("regression", combined=prediction("identified", "card-a", ["card-a"])),
            item("fixed", combined=prediction("identified", "card-x", ["card-b"])),
            item("abstained", combined=prediction("identified", "card-c", ["card-c"])),
            item("before-only", combined=prediction("identified", "card-d", ["card-d"])),
        ],
        id="before",
    )
    after = report(
        [
            item("regression", combined=prediction("identified", "card-x", ["card-a"])),
            item("fixed", combined=prediction("identified", "card-b", ["card-b"])),
            item("abstained", combined=prediction("ambiguous", candidates=["card-c"])),
            item("after-only", combined=prediction("identified", "card-e", ["card-e"])),
        ],
        id="after",
        pipeline_version="synthetic-pipeline-v2",
        data_version=None,
    )
    truth = labels(
        annotation("regression", expected_id="card-a"),
        annotation("fixed", expected_id="card-b"),
        annotation("abstained", expected_id="card-c"),
        annotation("before-only", expected_id="card-d"),
        annotation("after-only", expected_id="card-e"),
    )

    result = compare_data(before, after, truth)
    comparison = result["comparison"]
    combined = comparison["variants"]["combined"]

    assert comparison["intersection_size"] == 3
    assert comparison["missing_from_before_ids"] == ["after-only"]
    assert comparison["missing_from_after_ids"] == ["before-only"]
    assert combined["paired_count"] == 3
    assert combined["changes"]["errors_corrected"] == ["fixed"]
    assert combined["changes"]["new_errors"] == ["regression"]
    assert combined["changes"]["correct_to_incorrect"] == ["regression"]
    assert combined["changes"]["correct_to_abstained"] == ["abstained"]
    assert combined["changes"]["became_ambiguous"] == ["abstained"]
    assert combined["changes"]["identity_changes"] == ["fixed", "regression"]
    assert combined["paired_metrics"]["before"]["automatic_precision"]["value"] == 2 / 3
    assert combined["paired_metrics"]["after"]["automatic_precision"]["value"] == 0.5
    assert combined["paired_metrics"]["delta"]["correct_overall"]["delta"] == pytest.approx(-1 / 3)
    assert any("pipeline_version différent" in limit for limit in comparison["limitations"])
    assert any("data_version absent" in limit for limit in comparison["limitations"])


def test_zero_denominator_produces_unavailable_metrics() -> None:
    data = report([item("lot", combined=prediction("lot"))])
    truth = labels(
        annotation("lot", product_type="lot", determinable=False, catalog_presence="unknown")
    )

    metrics = combined_metrics(evaluate_data(data, truth))

    for name in ("automatic_coverage", "automatic_precision", "correct_overall", "top3_recall"):
        assert metrics[name]["denominator"] == 0
        assert metrics[name]["value"] is None


def test_human_decisions_are_excluded_and_unknown_origin_is_a_limit() -> None:
    data = report(
        [
            item("automatic", combined=prediction("identified", "card-a")),
            item("human", combined=prediction("identified", "card-b", origin="human")),
            item("unknown", combined=prediction("identified", "card-c", origin="unknown")),
        ]
    )
    truth = labels(
        annotation("automatic", expected_id="card-a"),
        annotation("human", expected_id="card-b"),
        annotation("unknown", expected_id="card-c"),
    )

    variant = evaluate_data(data, truth)["variants"]["combined"]

    assert variant["metrics"]["automatic_coverage"] == {"numerator": 2, "denominator": 3, "value": 2 / 3}
    assert variant["metrics"]["automatic_precision"]["value"] == 1.0
    assert variant["counts"]["human_decisions_excluded"] == 1
    assert variant["counts"]["unknown_origin_decisions"] == 1
    assert any("automatique n'est pas prouvé" in limit for limit in variant["limitations"])


def test_cli_writes_json_and_refuses_to_overwrite(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    report_path = tmp_path / "report.json"
    labels_path = tmp_path / "labels.json"
    output_path = tmp_path / "evaluation.json"
    report_path.write_text(
        json.dumps(report([item("one", combined=prediction("identified", "card-a", ["card-a"]))])),
        encoding="utf-8",
    )
    labels_path.write_text(json.dumps(labels(annotation("one", expected_id="card-a"))), encoding="utf-8")

    assert main(["--report", str(report_path), "--labels", str(labels_path), "--output", str(output_path)]) == 0
    exported = json.loads(output_path.read_text(encoding="utf-8"))
    assert exported["schema_version"] == "identification-evaluation-v1"
    assert exported["variants"]["combined"]["metrics"]["automatic_precision"]["value"] == 1.0

    with pytest.raises(SystemExit) as error:
        main(["--report", str(report_path), "--labels", str(labels_path), "--output", str(output_path)])
    assert error.value.code == 2
    assert "Refus d'écraser" in capsys.readouterr().err
    assert json.loads(output_path.read_text(encoding="utf-8")) == exported
