"""Lecture des validations OCR conservées, sans modifier les annonces."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any

VALIDATION_ROOT = Path(__file__).resolve().parent.parent / "validation" / "ocr" / "marketplaces" / "runs"


def _summary(report: dict[str, Any]) -> dict[str, Any]:
    items = report.get("items", [])
    statuses = Counter(str((item.get("combined") or {}).get("status") or "unknown") for item in items)
    platforms = Counter(str(item.get("platform") or "unknown") for item in items)
    return {
        "id": str(report.get("id") or ""),
        "label": str(report.get("label") or report.get("id") or "Validation"),
        "created_at": str(report.get("created_at") or ""),
        "total": len(items),
        "identified": statuses["identified"],
        "ambiguous": statuses["ambiguous"],
        "lot": statuses["lot"],
        "unidentified": statuses["unidentified"],
        "vinted": platforms["vinted"],
        "ebay": platforms["ebay"],
        "images": sum(bool(item.get("image")) for item in items),
    }


def list_validation_runs() -> list[dict[str, Any]]:
    """Retourne les rapports valides, du plus récent au plus ancien."""
    runs = []
    for path in VALIDATION_ROOT.glob("*/resultats.json"):
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
            summary = _summary(report)
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
            continue
        if summary["id"] and summary["total"]:
            runs.append(summary)
    return sorted(runs, key=lambda run: (run["created_at"], run["id"]), reverse=True)


def get_validation_run(run_id: str) -> dict[str, Any] | None:
    """Charge un rapport par identifiant strictement local."""
    if not run_id or run_id != Path(run_id).name or run_id.startswith("."):
        return None
    path = VALIDATION_ROOT / run_id / "resultats.json"
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if report.get("id") != run_id or not isinstance(report.get("items"), list):
        return None
    report["summary"] = _summary(report)
    return report


def validation_image_path(run_id: str, filename: str) -> Path | None:
    """Restreint les vignettes aux images WebP du rapport demandé."""
    report = get_validation_run(run_id)
    if report is None or filename != Path(filename).name or Path(filename).suffix.lower() != ".webp":
        return None
    relative = f"images/{filename}"
    if not any(item.get("image") == relative for item in report["items"]):
        return None
    path = VALIDATION_ROOT / run_id / relative
    return path if path.is_file() else None
