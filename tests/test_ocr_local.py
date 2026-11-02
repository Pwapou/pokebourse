"""OCR local : images bornées, aucune écriture et candidats à vérifier."""

import io
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app.catalog import import_jsonl
from app.identification import ocr
from app.storage.database import connect
from app.storage.migration_runner import apply_migrations
from app.tcgdex.cache import TcgdexCache


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Crée une base isolée et empêche toute connexion réseau."""
    import socket
    monkeypatch.setattr(socket.socket, "connect", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("réseau interdit")))
    path = tmp_path / "ocr.sqlite"
    with connect(path) as connection:
        apply_migrations(connection)
        TcgdexCache(connection).seed_initial_if_empty()
        import_jsonl(connection, b'{"external_id":"lot1","name":"Lot cartes Pokemon","set_name":"Lot","price_cents":1000}')
    app = FastAPI()
    app.state.settings = SimpleNamespace(database_path=path)
    app.include_router(ocr.router)
    return TestClient(app)


def _image() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (100, 100), "white").save(output, format="PNG")
    return output.getvalue()


def test_ocr_suggests_reference_without_recording_text_or_identity(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ocr, "_run_tesseract", lambda _image: "Pikachu\n58/102\ntexte personnel secret")
    response = client.post("/ocr/suggestions", files={"file": ("carte.png", _image(), "image/png")})
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "candidates"
    assert result["recognized"] == {"names": ["Pikachu"], "numbers": ["58/102"]}
    assert any(card["tcgdex_id"] == "base1-58" for card in result["candidates"])
    assert "secret" not in response.text
    with connect(client.app.state.settings.database_path) as connection:
        assert connection.execute("SELECT identification_status FROM catalog_items").fetchone()[0] == "lot"
        assert connection.execute("SELECT COUNT(*) FROM listing_identification_decisions").fetchone()[0] == 0


def test_lots_never_produce_individual_candidates(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ocr, "_run_tesseract", lambda _image: pytest.fail("OCR interdit pour un lot"))
    files = {"file": ("carte.png", _image(), "image/png")}
    for data in ({"listing_id": "1"}, {"title": "Lot de 20 cartes Pokémon"}):
        result = client.post("/ocr/suggestions", files=files, data=data).json()
        assert result["status"] == "lot"
        assert result["candidates"] == []


def test_invalid_images_and_unavailable_engine_are_reported(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    assert client.post("/ocr/suggestions", files={"file": ("carte.png", b"pas une image", "image/png")}).status_code == 400
    assert client.post("/ocr/suggestions", files={"file": ("carte.png", b"x" * (ocr.MAX_IMAGE_BYTES + 1), "image/png")}).status_code == 400
    monkeypatch.setattr(ocr, "MAX_PIXELS", 9_999)
    assert client.post("/ocr/suggestions", files={"file": ("carte.png", _image(), "image/png")}).status_code == 400
    monkeypatch.setattr(ocr, "MAX_PIXELS", 12_000_000)
    monkeypatch.setattr(ocr, "_run_tesseract", lambda _image: (_ for _ in ()).throw(RuntimeError("Moteur OCR indisponible.")))
    response = client.post("/ocr/suggestions", files={"file": ("carte.png", _image(), "image/png")})
    assert response.status_code == 503


def test_number_conflict_is_not_relaxed(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ocr, "_run_tesseract", lambda _image, _psm=11: "Pikachu 999/102")
    result = client.post("/ocr/suggestions", files={"file": ("carte.png", _image(), "image/png")}).json()
    assert result["recognized"]["numbers"] == ["999/102"]
    assert result["status"] == "no_match"
    assert not result["candidates"]
