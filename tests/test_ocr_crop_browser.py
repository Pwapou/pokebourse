"""Recette du cadrage manuel sur la fiche, sans accès externe."""
from __future__ import annotations

import io
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from PIL import Image
from playwright.sync_api import expect, sync_playwright


def test_manual_crop_and_photo_change(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Le rectangle affiché et les champs sont transmis à la lecture locale."""
    monkeypatch.setenv("POKEMON_DATABASE_PATH", str(tmp_path / "browser.sqlite"))
    from app.identification import ocr
    from app.web import app
    monkeypatch.setattr(ocr, "_run_tesseract", lambda *_args: "Pikachu 58/102")
    with socket.socket() as bound:
        bound.bind(("127.0.0.1", 0))
        port = bound.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.02)
        assert server.started
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": 1200, "height": 900})
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.route("**/*", lambda route: route.continue_() if route.request.url.startswith(f"http://127.0.0.1:{port}/") else route.abort())
            page.request.post(f"http://127.0.0.1:{port}/imports", multipart={"file": {"name": "test.jsonl", "mimeType": "application/x-ndjson", "buffer": b'{"external_id":"one","name":"Pikachu","set_name":"151","price_cents":1000}\n'}})
            page.goto(f"http://127.0.0.1:{port}/catalog/1")
            image = io.BytesIO()
            Image.new("RGB", (400, 300), "white").save(image, format="PNG")
            page.locator("#ocr-photo").set_input_files({"name": "carte.png", "mimeType": "image/png", "buffer": image.getvalue()})
            expect(page.locator("#ocr-crop")).to_be_visible()
            canvas = page.locator("#ocr-canvas")
            canvas.scroll_into_view_if_needed()
            box = canvas.bounding_box()
            assert box
            page.mouse.move(box["x"] + box["width"] * .25, box["y"] + box["height"] * .2)
            page.mouse.down()
            page.mouse.move(box["x"] + box["width"] * .75, box["y"] + box["height"] * .8)
            page.mouse.up()
            expect(page.locator('[name="crop_x"]')).to_have_value("100")
            expect(page.locator('[name="crop_width"]')).to_have_value("200")
            page.locator('[name="crop_height"]').fill("100")
            page.get_by_role("button", name="Analyser la photo").click()
            expect(page.locator("#ocr-status")).to_contain_text("Suggestions")
            page.locator("#ocr-photo").set_input_files({"name": "autre.png", "mimeType": "image/png", "buffer": image.getvalue()})
            expect(page.locator("#ocr-crop-enabled")).not_to_be_checked()
            expect(page.locator("#ocr-results")).to_be_empty()
            assert not errors
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
