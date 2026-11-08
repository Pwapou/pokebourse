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


@pytest.mark.parametrize("orientation,expected", [(1, (4, 3)), (3, (4, 3)), (6, (3, 4)), (8, (3, 4))])
def test_preview_and_crop_use_oriented_pixels(client: TestClient, orientation: int, expected: tuple[int, int], monkeypatch: pytest.MonkeyPatch) -> None:
    """La prévisualisation et l'OCR partagent le repère EXIF, puis la rotation."""
    source = Image.new("RGB", (4, 3), "red")
    exif = source.getexif()
    exif[274] = orientation
    output = io.BytesIO()
    source.save(output, format="JPEG", exif=exif)
    content = output.getvalue()
    response = client.post("/ocr/preview", files={"file": ("photo.jpg", content, "image/jpeg")})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert Image.open(io.BytesIO(response.content)).size == expected
    seen = []
    def read(image: bytes, _psm: int = 11) -> str:
        seen.append(Image.open(io.BytesIO(image)).size)
        return "Pikachu 58/102"
    monkeypatch.setattr(ocr, "_run_tesseract", read)
    data = {"crop_x": 0, "crop_y": 1, "crop_width": 2, "crop_height": 2, "image_width": expected[0], "image_height": expected[1], "crop_rotation": 90}
    result = client.post("/ocr/suggestions", files={"file": ("photo.jpg", content, "image/jpeg")}, data=data)
    assert result.status_code == 200
    assert seen[0] == (2, 2)


@pytest.mark.parametrize("changes", [{"crop_x": -1}, {"crop_width": 0}, {"crop_x": 99}, {"image_width": 99}, {"crop_rotation": 45}, {"crop_height": ""}])
def test_invalid_crop_is_rejected(client: TestClient, changes: dict[str, object]) -> None:
    """Une sélection partielle, hors image ou incohérente ne lance pas l'OCR."""
    data = {"crop_x": 0, "crop_y": 0, "crop_width": 10, "crop_height": 20, "image_width": 100, "image_height": 100, "crop_rotation": 0} | changes
    response = client.post("/ocr/suggestions", files={"file": ("photo.png", _image(), "image/png")}, data=data)
    assert response.status_code == 400


def test_crop_preserves_selected_pixels_and_rotates_clockwise() -> None:
    """La sélection et sa rotation portent sur les pixels attendus."""
    image = Image.new("RGB", (4, 3), "white")
    image.putpixel((1, 0), (255, 0, 0))
    image.putpixel((1, 1), (0, 0, 255))
    output = io.BytesIO()
    image.save(output, format="PNG")
    cropped = Image.open(io.BytesIO(ocr._crop_image(output.getvalue(), (1, 0, 2, 3, 4, 3, 90))))
    assert cropped.size == (3, 2)
    assert cropped.getpixel((2, 0)) == (255, 0, 0)
    assert cropped.getpixel((1, 0)) == (0, 0, 255)
