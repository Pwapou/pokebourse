"""Recette navigateur T03, serveur local et toutes les destinations distantes bloquées."""

from __future__ import annotations

import json
import os
import re
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import expect, sync_playwright

from app.storage.database import connect
from app.storage.migration_runner import apply_migrations
from app.tcgdex.cache import TcgdexCache


def test_ocr_prefill_is_indicative_after_reanalysis_and_save(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """capture → réanalyse → ajout : aucune confirmation d'identité implicite."""
    path = tmp_path / "browser.sqlite"
    monkeypatch.setenv("POKEMON_DATABASE_PATH", str(path))
    with connect(path) as connection:
        apply_migrations(connection)
        TcgdexCache(connection).seed_initial_if_empty()
    from app.web import app

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
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("console", lambda message: errors.append(message.text) if message.type in {"error", "warning"} else None)
            page.route("**/*", lambda route: route.continue_() if route.request.url.startswith(f"http://127.0.0.1:{port}/") else route.abort())
            page.goto(f"http://127.0.0.1:{port}/health")
            payload = {"platform": "vinted", "external_id": "browser-ocr", "url": "https://www.vinted.fr/items/555",
                       "title": "Carte photographiée", "description": "", "name": "", "set_name": "", "card_number": "",
                       "language": "", "price": "invalide", "currency": "",
                       "ocr_result": json.dumps({"recognized": {"names": ["Pikachu"], "numbers": ["58/102"]}, "raw_text": "texte OCR privé à ne pas archiver"})}
            page.evaluate("""payload => {
                const form = document.createElement('form'); form.method = 'POST'; form.action = '/previsualiser-capture';
                for (const [name,value] of Object.entries(payload)) { const input = document.createElement('input'); input.name=name; input.value=value; form.appendChild(input); }
                document.body.appendChild(form); form.submit();
            }""", payload)
            expect(page).to_have_url(f"http://127.0.0.1:{port}/previsualiser-capture")
            expect(page).to_have_title("Prévisualisation de capture · Pokébourse")
            expect(page.get_by_role("heading", name="Prévisualiser une annonce capturée")).to_be_visible()
            evidence_dir = os.environ.get("POKEBOURSE_QA_DIR")
            if evidence_dir:
                destination = Path(evidence_dir)
                destination.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(destination / "t08-initial-desktop.png"))
                page.locator('input[name="name"]').scroll_into_view_if_needed()
                page.screenshot(path=str(destination / "t08-fields-desktop.png"))
            expect(page.locator('input[name="name"]')).to_have_value("Pikachu")
            expect(page.locator('input[name="proposed_name"]')).to_have_value("Pikachu")
            expect(page.get_by_text("Identification ambiguë", exact=True)).to_be_visible()
            expect(page.locator('[data-financial-error="price"]')).to_be_visible()
            expect(page.locator('[data-financial-error="currency"]')).to_be_visible()
            expect(page.locator('select[name="language"]')).to_have_value("und")
            page.locator('input[name="price"]').fill("12,00")
            page.locator('input[name="currency"]').fill("EUR")
            page.locator('input[name="currency"]').press("Tab")
            expect(page.locator('input[name="shipping"]')).to_be_focused()
            page.get_by_role("button", name="Relancer l’analyse").click()
            expect(page.locator('[data-financial-error="price"]')).to_have_count(0)
            expect(page.locator('[data-financial-error="currency"]')).to_have_count(0)
            expect(page.locator('input[name="proposed_name"]')).to_have_value("Pikachu")
            expect(page.get_by_text("Identification ambiguë", exact=True)).to_be_visible()
            page.get_by_text("Indices et provenance", exact=True).click()
            expect(page.get_by_text("Lecture de l’image à vérifier", exact=False).first).to_be_visible()
            with connect(path) as connection:
                assert connection.execute("SELECT count(*) FROM catalog_items").fetchone()[0] == 0
            # Captures facultatives hors dépôt pour la recette interactive.
            evidence_dir = os.environ.get("POKEBOURSE_QA_DIR")
            if evidence_dir:
                destination = Path(evidence_dir)
                destination.mkdir(parents=True, exist_ok=True)
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                page.get_by_text("Identification ambiguë", exact=True).scroll_into_view_if_needed()
                page.screenshot(path=str(destination / "t03-desktop.png"))
                page.set_viewport_size({"width": 390, "height": 844})
                page.wait_for_function("document.getElementById('sidebar').getBoundingClientRect().right <= 1")
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                page.get_by_text("Identification ambiguë", exact=True).scroll_into_view_if_needed()
                page.screenshot(path=str(destination / "t03-mobile.png"))
                page.locator('input[name="name"]').scroll_into_view_if_needed()
                page.screenshot(path=str(destination / "t08-fields-mobile.png"))
            page.get_by_role("button", name="Confirmer et ajouter l’annonce").click()
            expect(page).to_have_url(re.compile(r"/catalog/\d+\?notice="))
            with connect(path) as connection:
                row = connection.execute("SELECT identification_status, reference_card_id, language FROM catalog_items").fetchone()
                assert tuple(row) == ("ambiguous", None, "und")
                assert connection.execute("SELECT count(*) FROM listing_identification_decisions").fetchone()[0] == 0
                assert "texte OCR privé" not in connection.execute("SELECT observations_json FROM listing_identity_evidence").fetchone()[0]
            # Même garde sur la soumission finale du formulaire URL : le prix
            # erroné ne masque pas l'identité ni ne perd le titre vendeur.
            page.evaluate("""payload => {
                const form = document.createElement('form'); form.method = 'POST'; form.action = '/ajouter-annonce/enregistrer';
                for (const [name,value] of Object.entries(payload)) { const input = document.createElement('input'); input.name=name; input.value=value; form.appendChild(input); }
                document.body.appendChild(form); form.submit();
            }""", {"url": "https://www.vinted.fr/items/999-browser-manual", "title": "Pikachu 58/102",
                   "captured_title": "Carte Pokémon Pikachu 58/102", "name": "Pikachu", "set_name": "Set de Base",
                   "card_number": "58/102", "language": "und", "price": "invalide", "currency": "EUR"})
            expect(page).to_have_url(f"http://127.0.0.1:{port}/ajouter-annonce/enregistrer")
            expect(page.get_by_role("heading", name="Ajouter une annonce par URL")).to_be_visible()
            expect(page.locator('[data-financial-error="price"]')).to_be_visible()
            expect(page.locator('input[name="name"]')).to_have_value("Pikachu")
            page.locator('input[name="price"]').fill("12,00")
            page.get_by_role("button", name="Analyser les informations saisies").click()
            expect(page.locator('[data-financial-error="price"]')).to_have_count(0)
            expect(page.locator('input[name="captured_title"]')).to_have_value("Carte Pokémon Pikachu 58/102")
            page.get_by_role("button", name="Confirmer et ajouter l’annonce").click()
            expect(page).to_have_url(re.compile(r"/catalog/\d+\?notice="))
            with connect(path) as connection:
                row = connection.execute("SELECT original_title, language FROM catalog_items WHERE external_id='999'").fetchone()
                assert tuple(row) == ("Carte Pokémon Pikachu 58/102", "und")
            assert not errors
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
