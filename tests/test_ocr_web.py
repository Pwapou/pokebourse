"""Affichage du parcours de lecture d’image sur une fiche annonce."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.web import app


def test_ocr_available_for_unit_but_not_a_lot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POKEMON_DATABASE_PATH", str(tmp_path / "ocr-web.sqlite"))
    with TestClient(app) as client:
        data = (
            '{"external_id":"one","name":"Pikachu","set_name":"151","price_cents":1000}\n'
            '{"external_id":"lot","name":"Lot cartes Pokémon","set_name":"151","price_cents":2000}\n'
        ).encode("utf-8")
        response = client.post("/imports", files={"file": ("test.jsonl", data, "application/x-ndjson")})
        assert response.status_code == 200
        unit = client.get("/catalog/1")
        assert unit.status_code == 200
        assert 'id="ocr-assist-form"' in unit.text
        assert 'action="/ocr/suggestions"' in unit.text
        assert 'name="file"' in unit.text
        assert "uniquement à proposer des candidats à vérifier" in unit.text
        assert 'data-evidence-hash=' in unit.text and 'data-revision=' in unit.text
        lot = client.get("/catalog/2")
        assert lot.status_code == 200
        assert 'id="ocr-assist-form"' not in lot.text
        assert "ne permet pas d’attribuer une carte unique à un lot" in lot.text
