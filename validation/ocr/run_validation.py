"""Exécute l'OCR réel sur les trois cartes et conserve seulement les indices structurés."""
import json
from pathlib import Path

from app.config import Settings
from app.identification.ocr import analyze_image
from app.storage.database import connect

ROOT = Path(__file__).parent
results = []
with connect(Settings.from_env().database_path) as connection:
    for path in sorted(ROOT.glob("*.webp")):
        result = analyze_image(connection, path.read_bytes())
        results.append({
            "image": path.name,
            "status": result["status"],
            "recognized": result["recognized"],
            "candidates": [
                {
                    "tcgdex_id": candidate["tcgdex_id"],
                    "confidence": candidate["confidence"],
                    "match_reason": candidate["match_reason"],
                }
                for candidate in result["candidates"][:3]
            ],
        })
output = ROOT / "resultats.json"
output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(results, ensure_ascii=False, indent=2))
