"""Bout en bout avec Chromium et l'extension chargée, sur une page simulée localement.

Trajet vérifié : capture de la page ouverte → bouton « Envoyer à Pokébourse » →
OCR local sur l'image principale → prévisualisation sans écriture → confirmation
explicite → fiche annonce enregistrée via le flux transactionnel existant.

Aucun appel réseau réel : la page annonce, son image et les réponses du serveur
local sont simulées ; toute autre destination est bloquée par interception.
Ce test ne valide pas le comportement sur une marketplace réelle.
"""
from __future__ import annotations

import io
import os
import socket
import threading
import time
from pathlib import Path

import pytest

LISTING_PAGE = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<title>Carte Pokémon Dracaufeu 4/102 Set de Base</title>
<meta property="og:image" content="https://images.vinted.net/photos/annonce-1.jpg">
</head><body>
<h1>Carte Pokémon Dracaufeu 4/102 Set de Base</h1>
<div data-testid="price">25,00 €</div>
<a href="/member/42">VendeurExemple</a>
</body></html>"""


def _ocr_image() -> bytes:
    """Photo locale simulée avec du texte lisible pour le moteur OCR."""
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (900, 300), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(
        "/usr/local/lib/python3.12/site-packages/matplotlib/mpl-data/fonts/ttf/DejaVuSans.ttf", 72
    )
    draw.text((40, 60), "Dracaufeu", font=font, fill="black")
    draw.text((40, 170), "4/102", font=font, fill="black")
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=92)
    return output.getvalue()


def _wait_port_free(port: int, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", port)) != 0:
                return
        time.sleep(0.1)
    pytest.skip("le port 8000 est déjà occupé : test e2e serveur impossible dans cet environnement")


def test_capture_to_listing_end_to_end(tmp_path: Path) -> None:
    """capture → Envoyer → OCR → prévisualisation → confirmation → fiche."""
    _wait_port_free(8000)
    os.environ["POKEMON_DATABASE_PATH"] = str(tmp_path / "e2e.sqlite")
    from app.web import app as web_app  # import après la variable d'environnement

    import uvicorn
    server = uvicorn.Server(uvicorn.Config(web_app, host="127.0.0.1", port=8000, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 20
    while not server.started and time.time() < deadline and not server.should_exit:
        time.sleep(0.05)
    assert server.started, "le serveur local n'a pas démarré"

    from playwright.sync_api import expect, sync_playwright

    import shutil
    import subprocess

    xvfb_bin = shutil.which("Xvfb")
    if xvfb_bin is None:
        pytest.skip("Xvfb indisponible : l'extension Chromium ne peut pas être chargée en mode headed")
    display = ":99"
    xvfb = subprocess.Popen([xvfb_bin, display, "-screen", "0", "1280x800x24"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.8)
    if xvfb.poll() is not None:
        pytest.skip("Xvfb n'a pas pu démarrer sur l'écran virtuel :99")

    extension_dir = Path("extension").resolve()
    listing_html = LISTING_PAGE
    photo = _ocr_image()
    popup_pages: list = []

    try:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(tmp_path / "chrome-profile"),
                headless=False,
                env={**os.environ, "DISPLAY": display},
                args=[
                    f"--disable-extensions-except={extension_dir}",
                    f"--load-extension={extension_dir}",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--remote-debugging-port=0",
                ],
            )
            context.on("page", lambda page: popup_pages.append(page))

            # Chrome n'expose pas à Playwright les onglets créés par les API chrome.tabs
            # d'une extension : une seconde connexion CDP liste tous les onglets réels.
            cdp_browser = None
            port_file = tmp_path / "chrome-profile" / "DevToolsActivePort"
            for _ in range(100):
                if port_file.exists():
                    break
                time.sleep(0.1)
            if port_file.exists():
                cdp_port = port_file.read_text(encoding="utf-8").splitlines()[0].strip()
                cdp_browser = playwright.chromium.connect_over_cdp(f"http://localhost:{cdp_port}")

            def _cdp_pages() -> list:
                if cdp_browser is None:
                    return []
                pages: list = []
                for cdp_context in cdp_browser.contexts:
                    pages.extend(cdp_context.pages)
                return pages

            def _route(route) -> None:
                url = route.request.url
                if url.startswith("chrome-extension://"):
                    route.continue_()  # les fichiers de l'extension elle-même
                elif url.startswith("http://localhost:8000"):
                    route.continue_()  # le vrai serveur local de test
                elif url.startswith("https://www.vinted.fr"):
                    route.fulfill(body=listing_html, content_type="text/html", status=200)
                elif url.startswith("https://images.vinted.net"):
                    route.fulfill(body=photo, content_type="image/jpeg", status=200)
                else:
                    route.abort()  # aucune autre destination : test strictement hermétique

            context.route("**/*", _route)

            # 1. L'utilisateur ouvre une annonce dans Chrome : la page simulée est capturée.
            page = context.pages[0] if context.pages else context.new_page()
            page.goto("https://www.vinted.fr/items/12345-carte-pokemon")
            page.wait_for_timeout(1500)  # le content script s'exécute à document_idle

            # Chrome bloque la navigation directe vers chrome-extension:// : l'onglet
            # de l'annonce est réutilisé pour afficher le popup, comme le ferait l'icône.
            service_worker = None
            deadline = time.time() + 20
            while time.time() < deadline:
                if context.service_workers:
                    service_worker = context.service_workers[0]
                    break
                time.sleep(0.1)
            assert service_worker is not None, "le service worker de l'extension ne s'est pas réveillé"
            captured = service_worker.evaluate("async () => (await chrome.storage.local.get('listings')).listings")
            assert len(captured) == 1
            assert captured[0]['name'] == ''
            assert captured[0]['language'] == 'und'
            assert captured[0]['raw_data']['title'] == 'Carte Pokémon Dracaufeu 4/102 Set de Base'

            service_worker.evaluate("""async () => {
                const [tab] = await chrome.tabs.query({ url: 'https://www.vinted.fr/*' });
                await chrome.tabs.update(tab.id, { url: chrome.runtime.getURL('popup/popup.html') });
                await new Promise(resolve => setTimeout(resolve, 2000)); // la navigation doit être validée
            }""")

            popup = None
            deadline = time.time() + 20
            while time.time() < deadline:
                for candidate in popup_pages + list(context.pages):
                    if "popup/popup.html" in candidate.url:
                        popup = candidate
                        break
                if popup is not None:
                    break
                time.sleep(0.1)
            assert popup is not None, "le popup de l'extension ne s'est pas ouvert"

            # 2. Le popup liste la capture ; « Envoyer » lance l'OCR puis ouvre la prévisualisation.
            expect(popup.locator("#listing-count")).to_have_text("1", timeout=15000)
            popup.locator("#btn-send-pokebourse").click()

            preview = None
            popup.wait_for_timeout(1000)  # laisser au navigateur le temps de créer l'onglet
            deadline = time.time() + 60
            while time.time() < deadline:
                for candidate in popup_pages + _cdp_pages():
                    if "/previsualiser-capture" in candidate.url or "/catalog/" in candidate.url:
                        preview = candidate
                        break
                if preview is not None:
                    break
                time.sleep(0.25)
            seen = sorted({p.url for p in popup_pages + _cdp_pages() + list(context.pages)})
            assert preview is not None, (
                "la prévisualisation ne s'est pas ouverte ; onglets vus : " + "; ".join(seen)
            )
            expect(preview.locator("body")).to_contain_text("Lecture automatique de l’image", timeout=30000)
            # Aucune écriture avant confirmation.
            from app.storage.database import connect
            with connect(tmp_path / "e2e.sqlite") as connection:
                assert connection.execute("SELECT COUNT(*) FROM catalog_items").fetchone()[0] == 0

            # 3. L'utilisateur choisit la langue puis confirme explicitement.
            preview.locator('select[name="language"]').select_option("fr")
            preview.get_by_role("button", name="Confirmer et ajouter l’annonce").click()
            expect(preview.locator("body")).to_contain_text("Annonce ajoutée", timeout=30000)
            expect(preview.locator("body")).to_contain_text("Dracaufeu")

            # 4. La fiche existe dans la base, enregistrée via le flux transactionnel.
            with connect(tmp_path / "e2e.sqlite") as connection:
                row = connection.execute(
                    "SELECT c.external_id, c.price_cents, c.currency, c.language, s.name AS source "
                    "FROM catalog_items c JOIN sources s ON s.id = c.source_id"
                ).fetchone()
            assert row is not None
            assert row["external_id"].startswith("vinted_")
            assert (row["price_cents"], row["currency"], row["language"], row["source"]) == (2500, "EUR", "fr", "vinted")
            context.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        xvfb.terminate()
        xvfb.wait(timeout=10)
        os.environ.pop("POKEMON_DATABASE_PATH", None)
