"""Validation manuelle sur 30 annonces réelles ; ne fait pas partie de pytest."""
from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any
import urllib.request

from app.config import Settings
from app.identification.ocr import analyze_image
from app.listing_preview import preview_listing
from app.storage.database import connect

ROOT = Path(__file__).parent
RUN_ID = "2026-11-02-30-liens"
OUTPUT = ROOT / "runs" / RUN_ID


def identity(connection: Any, title: str, ocr: dict[str, list[str]] | None = None) -> dict[str, Any]:
    fields: dict[str, Any] = {"title": title}
    if ocr:
        fields.update(ocr_names=ocr.get("names", []), ocr_numbers=ocr.get("numbers", []))
    result = preview_listing(connection, fields)["identification"]
    card = result.get("matched_card") or {}
    features = result.get("features") or {}
    return {
        "status": result["status"],
        "tcgdex_id": card.get("tcgdex_id"),
        "card_name": card.get("name"),
        "set_name": card.get("set_name"),
        "local_id": card.get("local_id"),
        "detected_name": features.get("name"),
        "detected_number": features.get("card_number") or features.get("local_id"),
        "confidence": result.get("confidence"),
        "reason": result.get("reason"),
        "candidates": [
            {
                "tcgdex_id": candidate.get("tcgdex_id"),
                "name": candidate.get("name"),
                "set_name": candidate.get("set_name"),
                "local_id": candidate.get("local_id"),
            }
            for candidate in (result.get("candidates") or [])[:3]
        ],
    }


def download_image(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=15) as response:
        content = response.read(8_000_001)
    if len(content) > 8_000_000:
        raise ValueError("Image supérieure à 8 Mo")
    destination.write_bytes(content)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    images = OUTPUT / "images"
    images.mkdir(exist_ok=True)
    dataset = json.loads((ROOT / "jeu-30-liens.json").read_text(encoding="utf-8"))
    if len(dataset) != 30 or len({item["url"] for item in dataset}) != 30:
        raise ValueError("Le jeu doit contenir exactement 30 liens distincts")
    results = []
    with connect(Settings.from_env().database_path) as connection:
        for index, item in enumerate(dataset, start=1):
            result = dict(item)
            result["index"] = index
            result["image_status"] = "non fournie ; titre public seul testé"
            result["ocr"] = None
            result["ocr_only"] = None
            if item.get("image_url"):
                image_path = images / f"{index:02d}.webp"
                try:
                    download_image(item["image_url"], image_path)
                    result["image"] = f"images/{image_path.name}"
                    result["image_status"] = "analysée localement"
                    ocr_result = analyze_image(connection, image_path.read_bytes())
                    result["ocr"] = {
                        "status": ocr_result["status"],
                        "recognized": ocr_result["recognized"],
                    }
                    result["ocr_only"] = identity(connection, "", ocr_result["recognized"])
                except Exception as error:
                    result["image_status"] = f"non analysée : {type(error).__name__}"
            result["title_only"] = identity(connection, item["title"])
            recognized = (result.get("ocr") or {}).get("recognized")
            result["combined"] = identity(connection, item["title"], recognized)
            results.append(result)
            print(f"{index:02d}/30 {item['platform']} {result['combined']['status']} {result['combined']['tcgdex_id']}", flush=True)
    report = {
        "id": RUN_ID,
        "label": "30 annonces Vinted et eBay",
        "created_at": datetime.now(UTC).isoformat(),
        "source": "15 annonces Vinted récentes et 15 titres publics eBay ; aucune annonce importée dans le catalogue",
        "note": "Résultats indicatifs sans vérité terrain confirmée. Les photos eBay ne sont pas testées. L’OCR complète le texte sans le remplacer.",
        "items": results,
    }
    (OUTPUT / "resultats.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
