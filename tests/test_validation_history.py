"""Historique local des campagnes OCR, sans appel réseau."""
from collections.abc import Iterator
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.web import app


def _result(status: str, tcg_id: str | None = None) -> dict[str, object]:
    return {
        "status": status, "tcgdex_id": tcg_id, "card_name": "Pikachu" if tcg_id else None,
        "set_name": "Set de Base" if tcg_id else None, "local_id": "58" if tcg_id else None,
        "detected_name": "Pikachu" if tcg_id else None, "detected_number": "58/102" if tcg_id else None,
        "confidence": 100 if tcg_id else 0, "reason": None, "candidates": [],
    }


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("POKEMON_DATABASE_PATH", str(tmp_path / "web.db"))
    root = tmp_path / "runs"
    report_dir = root / "campagne-test"
    images = report_dir / "images"
    images.mkdir(parents=True)
    (images / "01.webp").write_bytes(b"image-locale")
    report = {
        "id": "campagne-test", "label": "Jeu de contrôle", "created_at": "2026-11-02T12:00:00+00:00",
        "source": "Deux liens fictifs pour le test automatisé", "note": "Aucune vérité terrain.",
        "items": [
            {"index": 1, "platform": "vinted", "url": "https://www.vinted.fr/items/1", "title": "Pikachu 58/102",
             "image": "images/01.webp", "image_status": "analysée localement",
             "ocr": {"status": "ok", "recognized": {"names": ["Pikachu"], "numbers": ["15"]}},
             "title_only": _result("identified", "base1-58"), "ocr_only": _result("ambiguous"),
             "combined": _result("identified", "base1-58")},
            {"index": 2, "platform": "ebay", "url": "https://www.ebay.fr/itm/2", "title": "Lot de cartes",
             "image_status": "non fournie", "ocr": None, "ocr_only": None,
             "title_only": _result("lot"), "combined": _result("lot")},
        ],
    }
    (report_dir / "resultats.json").write_text(json.dumps(report), encoding="utf-8")
    monkeypatch.setattr("app.validation_history.VALIDATION_ROOT", root)
    with TestClient(app) as test_client:
        yield test_client


def test_history_and_combined_comparison(client: TestClient) -> None:
    index = client.get("/validations/ocr")
    detail = client.get("/validations/ocr/campagne-test")

    assert index.status_code == 200
    assert "Jeu de contrôle" in index.text
    assert "1 Vinted · 1 eBay · 1 photos" in index.text
    assert detail.status_code == 200
    assert "base1-58" in detail.text
    assert "Lot de cartes" in detail.text
    assert "TITRE SEUL" in detail.text
    assert "RÉSULTAT COMBINÉ" in detail.text


def test_only_referenced_images_are_served(client: TestClient) -> None:
    image = client.get("/validations/ocr/campagne-test/images/01.webp")
    missing = client.get("/validations/ocr/campagne-test/images/02.webp")
    unknown_run = client.get("/validations/ocr/inconnu")

    assert image.status_code == 200
    assert image.content == b"image-locale"
    assert image.headers["content-type"] == "image/webp"
    assert missing.status_code == 404
    assert unknown_run.status_code == 404
