import json
import re
from pathlib import Path
import struct

import pytest

from app.catalog import parse_jsonl
from app.storage.database import connect
from app.storage.migration_runner import apply_migrations


def test_manifest_v3_structure_and_files_exist() -> None:
    extension_dir = Path("extension")
    assert extension_dir.exists() and extension_dir.is_dir()

    manifest_path = extension_dir / "manifest.json"
    assert manifest_path.exists()

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    assert manifest["manifest_version"] == 3
    assert manifest["name"]
    assert manifest["version"]

    # Vérification des icônes
    icons = manifest.get("icons", {})
    for size, rel_path in icons.items():
        icon_file = extension_dir / rel_path
        assert icon_file.exists(), f"L'icône {rel_path} n'existe pas"
        with open(icon_file, "rb") as img:
            header = img.read(24)
            # Signature PNG
            assert header[:8] == b"\x89PNG\r\n\x1a\n"
            # Dimensions IHDR
            width, height = struct.unpack(">II", header[16:24])
            assert width == int(size)
            assert height == int(size)

    # Vérification du background service worker
    sw_rel_path = manifest["background"]["service_worker"]
    assert (extension_dir / sw_rel_path).exists()

    # Vérification du popup
    popup_rel_path = manifest["action"]["default_popup"]
    assert (extension_dir / popup_rel_path).exists()
    assert (extension_dir / "popup/popup.js").exists()
    assert (extension_dir / "popup/popup.css").exists()

    # Le popup expose un raccourci vers le guide de capture du tableau de bord.
    popup_html = (extension_dir / popup_rel_path).read_text(encoding="utf-8")
    assert "Guide de capture" in popup_html
    assert "http://localhost:8000/#capture" in popup_html

    # Le lien « Renseigner une cote » du popup pointe vers la page Réglages actuelle.
    popup_js = (extension_dir / "popup/popup.js").read_text(encoding="utf-8")
    assert "localhost:8000/reglages#cotes" in popup_js
    assert "localhost:8000/profitability#cotes" not in popup_js

    # Vérification des content scripts
    for cs in manifest["content_scripts"]:
        for js_rel in cs.get("js", []):
            assert (extension_dir / js_rel).exists()
        for css_rel in cs.get("css", []):
            assert (extension_dir / css_rel).exists()


def test_extension_has_no_inline_event_handlers() -> None:
    """La CSP Manifest V3 (script-src 'self') bloque tout gestionnaire en ligne.

    Les repli de vignette et interactions doivent être branchés via
    addEventListener ; un attribut on* en ligne serait silencieusement bloqué
    par Chrome avec « Executing inline event handler violates ... CSP ».
    """
    inline_handler_pattern = re.compile(
        r"""(?:on(?:error|click|load|change|submit|input|focus|blur)\s*=)|(?:javascript:)""",
        re.IGNORECASE,
    )
    checked_files = [
        "popup/popup.html",
        "popup/popup.js",
        "content/content.js",
        "background/service-worker.js",
    ]
    for rel_path in checked_files:
        content = (Path("extension") / rel_path).read_text(encoding="utf-8")
        match = inline_handler_pattern.search(content)
        assert match is None, (
            f"{rel_path} contient un gestionnaire d'événement en ligne "
            f"({match.group(0)!r}) interdit par la CSP Manifest V3 : "
            "utilisez addEventListener."
        )


def test_popup_broken_listing_image_falls_back_to_placeholder() -> None:
    """L'échec de chargement de la vignette bascule sur le pictogramme 🎴.

    Le repli est branché en JavaScript (addEventListener) car la CSP Manifest V3
    bloque les gestionnaires d'événement en ligne : sans ce test, un attribut
    onerror serait silencieusement ignoré par Chrome.
    """
    from playwright.sync_api import expect, sync_playwright

    popup_url = (Path("extension/popup/popup.html").resolve()).as_uri()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()
        page.add_init_script("""
            window.chrome = {runtime: {sendMessage(message, callback) {
                if (message.action === 'GET_STATUS') callback({autoCaptureEnabled:true});
                if (message.action === 'GET_LISTINGS') callback({listings:[{
                    external_id:'capture-thumb', name:'Dracaufeu 4/102', set_name:'Set de Base',
                    price_cents:1200, currency:'EUR',
                    url:'https://www.vinted.fr/items/1', source:'vinted',
                    image_url:'https://images.vinted.net/photos/inaccessible.jpg'
                }]});
            }}};
            window.fetch = () => Promise.resolve({ok: true, json: () => Promise.resolve({})});
        """)
        # Aucune requête réelle : seule l'image distante simulée est en échec,
        # les fichiers locaux du popup (file://) continuent normalement.
        def _abort_remote(route) -> None:
            if route.request.url.startswith("file://"):
                route.continue_()
            else:
                route.abort()

        page.route("**/*", _abort_remote)
        page.goto(popup_url)
        expect(page.locator(".listing-thumb-placeholder")).to_be_visible()
        assert page.locator(".listing-thumb").count() == 0
        browser.close()


def test_popup_escapes_quotes_in_listing_name_inside_attributes() -> None:
    """Un titre d'annonce contenant des guillemets ne doit pas éclater les attributs.

    escapeHtml sert aussi dans title="…" et href="…" : une quote brute y créerait
    un attribut injecté (puis bloqué par la CSP avec une erreur en console).
    """
    from playwright.sync_api import expect, sync_playwright

    hostile_name = 'Dracaufeu " onmouseover="window.pwned=1" data-x="'
    popup_url = (Path("extension/popup/popup.html").resolve()).as_uri()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()
        init_script = """
            window.chrome = {runtime: {sendMessage(message, callback) {
                if (message.action === 'GET_STATUS') callback({autoCaptureEnabled:true});
                if (message.action === 'GET_LISTINGS') callback({listings:[{
                    external_id:'escape-check', name:__HOSTILE_NAME__,
                    set_name:'Set de Base', price_cents:1200, currency:'EUR',
                    url:'https://www.vinted.fr/items/1', source:'vinted'
                }]});
            }}};
        """.replace("__HOSTILE_NAME__", json.dumps(hostile_name))
        page.add_init_script(init_script)
        page.goto(popup_url)
        link = page.locator(".listing-title")
        expect(link).to_be_visible()
        # Le texte affiché reste le titre littéral, sans attribut injecté.
        assert link.inner_text() == hostile_name
        assert page.evaluate("window.pwned") is None
        for element in page.locator(".listing-card *").all():
            names = element.evaluate("el => Array.from(el.attributes).map(a => a.name)")
            assert not any(name.lower().startswith("on") for name in names), (
                f"Attribut de gestionnaire d'événement injecté : {names}"
            )
        browser.close()


def test_popup_ocr_requires_selection_and_keeps_proposals_unconfirmed() -> None:
    """La photo et le contexte local sont transmis explicitement sans confirmer la carte."""
    from playwright.sync_api import expect, sync_playwright

    popup_url = (Path("extension/popup/popup.html").resolve()).as_uri()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()
        page.add_init_script("""
            window.chrome = {runtime: {sendMessage(message, callback) {
                if (message.action === 'GET_STATUS') callback({autoCaptureEnabled:true});
                if (message.action === 'GET_LISTINGS') callback({listings:[{
                    external_id:'capture-1', name:'Pikachu', set_name:'151', price_cents:1200,
                    url:'https://example.com/item', raw_data:{title:'Pikachu 173/165'},
                    evaluation:{url_detail:'http://localhost:8000/catalog/42'}
                }]});
            }}};
            window.fetch = async (url, options) => {
                window.sentOcr = {url, listing_id:options.body.get('listing_id'),
                    title:options.body.get('title'), filename:options.body.get('file').name};
                return new Response(JSON.stringify({status:'candidates', message:'À vérifier',
                    recognized:{names:['Pikachu'],numbers:['173/165']},
                    candidates:[{name:'Pikachu',set_name:'151',local_id:'173'}]}),
                    {status:200,headers:{'Content-Type':'application/json'}});
            };
        """)
        page.goto(popup_url)
        page.locator(".ocr-panel summary").click()
        page.locator("#btn-ocr").click()
        assert "Choisissez d’abord une photo" in page.locator("#ocr-result").inner_text()
        page.locator("#ocr-image").set_input_files({"name": "photo.png", "mimeType": "image/png", "buffer": b"image-fictive"})
        page.locator("#btn-ocr").click()
        expect(page.locator("#ocr-result")).to_contain_text("Pikachu · 151 · N° 173 — à vérifier")
        assert page.locator("#ocr-result a").get_attribute("href") == "http://localhost:8000/catalog/42#ident-title"
        sent = page.evaluate("window.sentOcr")
        assert sent == {"url": "http://localhost:8000/ocr/suggestions", "listing_id": "42", "title": "Pikachu 173/165", "filename": "photo.png"}
        assert "confirm" not in sent["url"]
        page.locator(".item-checkbox").uncheck()
        page.locator("#btn-ocr").click()
        assert "exactement une annonce" in page.locator("#ocr-result").inner_text()
        browser.close()


def test_jsonl_generated_by_extension_is_compatible_with_pokebourse() -> None:
    # Exemple de données produites par extension/popup/popup.js
    sample_jsonl = (
        '{"external_id":"vinted_89234812","name":"Carte Pokémon Dracaufeu 4/102 Set de Base","set_name":"Set de Base","card_number":"4/102","price_cents":4500,"currency":"EUR","seller":"Collector92","url":"https://www.vinted.fr/items/89234812"}\n'
        '{"external_id":"lbc_98127391","name":"Pikachu Évolutions 35/108","set_name":"Évolutions","card_number":"35/108","price_cents":1200,"currency":"EUR","seller":"Marie","url":"https://www.leboncoin.fr/ad/98127391"}\n'
        '{"external_id":"web_123456","name":"Tortank Set de Base 15/102 Holo","set_name":"Set de Base","card_number":"15/102","price_cents":8000,"currency":"EUR","seller":"CardShop","url":"https://example.com/cards/tortank"}'
    )

    items = parse_jsonl(sample_jsonl.encode("utf-8"))
    assert len(items) == 3
    assert items[0].external_id == "vinted_89234812"
    assert items[0].name == "Carte Pokémon Dracaufeu 4/102 Set de Base"
    assert items[0].price_cents == 4500
    assert items[0].card_number == "4/102"
    assert str(items[0].url) == "https://www.vinted.fr/items/89234812"

    assert items[1].external_id == "lbc_98127391"
    assert items[1].price_cents == 1200
    assert str(items[1].url) == "https://www.leboncoin.fr/ad/98127391"

    assert items[2].price_cents == 8000


def test_import_extension_jsonl_into_catalog(tmp_path: Path) -> None:
    from app.catalog import import_jsonl

    db_path = tmp_path / "import_ext.db"
    with connect(db_path) as conn:
        apply_migrations(conn)

        sample_jsonl = (
            b'{"external_id":"ext_pika_1","name":"Pikachu","set_name":"Set de Base","card_number":"58/102","price_cents":1500,"currency":"EUR","seller":"Paul","url":"https://www.vinted.fr/items/111"}\n'
            b'{"external_id":"ext_mew_1","name":"Mewtwo","set_name":"Set de Base","card_number":"10/102","price_cents":3500,"currency":"EUR","seller":"Pierre","url":"https://www.leboncoin.fr/ad/222"}\n'
        )

        imported_count = import_jsonl(conn, sample_jsonl, source_name="extension-chrome")
        assert imported_count == 2

        count = conn.execute("SELECT COUNT(*) FROM catalog_items WHERE source_id IN (SELECT id FROM sources WHERE name = 'extension-chrome')").fetchone()[0]
        assert count == 2


def test_create_import_endpoint_with_json_accept(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient
    from app.config import Settings
    from app.web import app

    db_path = tmp_path / "web_ext.db"
    with connect(db_path) as conn:
        apply_migrations(conn)

    app.state.settings = Settings(database_path=db_path)
    client = TestClient(app)

    sample_jsonl = (
        b'{"external_id":"chrome_1","name":"Pikachu","set_name":"Set de Base","card_number":"58/102","price_cents":1500,"currency":"EUR","seller":"Paul","url":"https://example.com/1"}\n'
    )

    response = client.post(
        "/imports",
        files={"file": ("capture.jsonl", sample_jsonl, "text/plain")},
        headers={"Accept": "application/json"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["imported"] == 1
    assert "evaluations" in data
    assert len(data["evaluations"]) == 1
    eval_item = data["evaluations"][0]
    assert eval_item["name"] == "Pikachu"
    assert eval_item["purchase_price_cents"] == 1500
    assert eval_item["purchase_price_formatted"] == "15,00 €"
    # Pikachu n'a pas encore de cote enregistrée
    assert eval_item["reference_price_cents"] is None
    assert eval_item["has_reference_price"] is False
    assert eval_item["reference_price_formatted"] == "Cote non renseignée dans Pokébourse"
    assert eval_item["verdict"] == "sans_cote"
    # Le raccourci « Renseigner une cote » pointe vers Réglages (page actuelle).
    assert eval_item["url_add_cote"] == "http://localhost:8000/reglages#cotes"


def test_import_with_known_resell_price_returns_full_profitability(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient
    from app.config import Settings
    from app.profitability import (
        FeeProfileUpdate,
        ReferenceInput,
        build_card_key,
        update_active_fee_profile,
        upsert_reference,
    )
    from app.tcgdex.cache import TcgdexCache
    from app.web import app

    db_path = tmp_path / "web_ext_profit.db"
    with connect(db_path) as conn:
        apply_migrations(conn)
        cache = TcgdexCache(conn)
        cache.seed_initial_if_empty()
        # Initialise le profil de frais
        update_active_fee_profile(
            conn,
            FeeProfileUpdate(
                buyer_shipping_cents=0,
                platform_fee_bps=500,
                seller_fixed_fee_cents=0,
                shipping_packaging_cents=200,
                min_net_profit_cents=500,
                min_roi_bps=1500,
                min_catalog_samples=2,
            ),
        )
        # Ajoute une cote de revente pour Dracaufeu Set de Base 4 à 85.00 € (8500 cents)
        upsert_reference(
            conn,
            ReferenceInput(
                name="Dracaufeu",
                set_name="Set de Base",
                card_number="4",
                language="fr",
                reference_price_cents=8500,
                currency="EUR",
                source_name="Cardmarket",
            ),
        )

    app.state.settings = Settings(database_path=db_path)
    client = TestClient(app)

    # L'utilisateur envoie une annonce Vinted d'un Dracaufeu à 25.00 € (2500 cents)
    sample_jsonl = (
        '{"external_id":"vinted_drac_1","name":"Carte Pokémon Dracaufeu 4/102 Set de Base","set_name":"Set de Base","card_number":"4/102","price_cents":2500,"currency":"EUR","seller":"Vendeur92","url":"https://www.vinted.fr/items/999"}\n'
    ).encode("utf-8")

    response = client.post(
        "/imports",
        files={"file": ("capture.jsonl", sample_jsonl, "text/plain")},
        headers={"Accept": "application/json"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["imported"] == 1
    ev = data["evaluations"][0]
    assert ev["name"] == "Dracaufeu"
    assert ev["purchase_price_cents"] == 2500
    assert ev["purchase_price_formatted"] == "25,00 €"
    assert ev["reference_price_cents"] == 8500
    assert ev["reference_price_formatted"] == "85,00 €"
    assert ev["has_reference_price"] is True
    assert ev["reference_source_name"] == "Cardmarket"
    assert ev["net_profit_cents"] is not None
    assert ev["net_profit_cents"] > 0
    assert ev["verdict"] == "opportunite"
    assert ev["verdict_label"] == "Opportunité"
    assert "http://localhost:8000/catalog/" in ev["url_detail"]


def test_import_with_vague_title_but_rich_description_identifies_tcgdex(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient
    from app.config import Settings
    from app.tcgdex.cache import TcgdexCache
    from app.web import app

    db_path = tmp_path / "web_ext_desc.db"
    with connect(db_path) as conn:
        apply_migrations(conn)
        cache = TcgdexCache(conn)
        cache.seed_initial_if_empty()

    app.state.settings = Settings(database_path=db_path)
    client = TestClient(app)

    # Titre vague typique sur Vinted/Leboncoin mais description contenant les vrais détails TCGdex
    sample_jsonl = (
        '{"external_id":"vinted_vague_1","name":"Superbe carte ancienne brillante","set_name":"Non identifiée","price_cents":3000,"currency":"EUR","description":"Magnifique Dracaufeu 4/102 Set de Base holo état neuf","url":"https://www.vinted.fr/items/888"}\n'
    ).encode("utf-8")

    response = client.post(
        "/imports",
        files={"file": ("capture.jsonl", sample_jsonl, "text/plain")},
        headers={"Accept": "application/json"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["imported"] == 1
    ev = data["evaluations"][0]
    # Doit avoir réconcilié la carte avec TCGdex grâce à la description
    assert ev["name"] == "Dracaufeu"
    assert ev["set_name"] == "Set de Base"
    assert ev["card_number"] == "4"
    assert ev["identification_status"] == "identified"


def _eval_extension_card_contexts(inputs: list[str]) -> list[dict[str, object]]:
    """Exécute les garde-fous réels du content script dans le Node livré avec Playwright."""
    import subprocess
    from playwright._impl._driver import compute_driver_executable

    driver = compute_driver_executable()
    node_path = driver[0] if isinstance(driver, tuple) else driver
    script = (
        "const { extractCardNumber, isLotContext } = require('./extension/content/content.js');"
        "const inputs = JSON.parse(process.argv[1]);"
        "process.stdout.write(JSON.stringify(inputs.map((t) => ({card_number: extractCardNumber(t), is_lot: isLotContext(t)}))));"
    )
    completed = subprocess.run(
        [str(node_path), "-e", script, json.dumps(inputs)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def _eval_extension_card_numbers(inputs: list[str]) -> list[str | None]:
    """Lit les numéros extraits pour la matrice historique de non-régression."""
    return [context["card_number"] for context in _eval_extension_card_contexts(inputs)]


def test_extension_lot_and_selection_guardrails_match_backend() -> None:
    """Le repli sur un numéro isolé exclut les cartes supplémentaires et ventes au choix."""
    from app.identification.detector import extract_features

    cases = [
        ("Carte Pokémon Évoli V vendu avec 3 cartes en plus", True, None),
        ("Évoli V vendue avec trois cartes supplémentaires", True, None),
        ("Évoli V + 3 cartes offertes", True, None),
        ("Mentali 175 vendu avec 3 cartes en plus", True, None),
        ("Mentali 175 + 3 cartes offertes", True, None),
        ("Mentali 175 avec une carte en plus", True, None),
        ("Mentali 175 carte avec protection", False, "175"),
        ("Mentali 175 carte avec 3 photos", False, "175"),
        ("Dracaufeu 4/102 carte Pokémon", False, "4/102"),
        ("Dracaufeu 4 / 102 carte Pokémon", False, "4/102"),
        ("Mentali 175 carte seule, pas un lot", False, "175"),
        ("Mentali 175 carte seule, pas un lot de cartes Pokémon", False, "175"),
        ("Mentali 175 carte seule, sans lot Pokémon", False, "175"),
        ("Mentali 175, 1 carte Pokémon avec boîtier", False, "175"),
        ("Mentali 175 carte au choix parmi 3", False, None),
        ("Mentali 175, 3 cartes Pokémon au choix, une seule vendue", False, None),
        ("Mentali 175 une carte à choisir parmi trois", False, None),
        ("Évoli V 0113/15 Gem Pack 2", False, "0113/15"),
        ("Mentali 175 Gem Pack 2", False, "175"),
        ("Carte Pokémon Gem Pack 2", False, None),
        ("Dracaufeu 4/102 numéro de série 102 carte Pokémon", False, "4/102"),
        ("Dracaufeu numéro de série 102 carte Pokémon", False, None),
        ("Dracaufeu serial number: 102 carte Pokémon", False, None),
        ("Dracaufeu 4/102 numéro de série 102/200 carte Pokémon", False, "4/102"),
        ("Dracaufeu 4/102, sans lot de trois cartes Pokémon", False, "4/102"),
        ("Pack Pokémon scellé", True, None),
        ("Pack de 3 boosters", True, None),
        ("Pack 151 scellé", True, None),
        ("2 packs Pokémon", True, None),
        ("Booster Gem Pack 2 scellé", True, None),
        ("Lot de trois cartes", True, None),
        ("Trois cartes Pokémon", True, None),
    ]
    contexts = _eval_extension_card_contexts([text for text, _, _ in cases])
    for (text, is_lot, number), actual in zip(cases, contexts, strict=True):
        assert extract_features(text).is_lot is is_lot, text
        assert actual["is_lot"] is is_lot, text
        assert actual["card_number"] == number, text


def test_extension_extract_card_number_parsing_and_guardrails() -> None:
    cases: list[tuple[str, str, str | None]] = [
        # Matrice 3.3 — formes acceptées
        ("mentali_ex_175_collectaura_9_5", "Mentali EX 175 CollectAura 9.5", "175"),
        ("mentali_ex_175_collectaura_lowercase", "mentali ex 175 collectaura 9.5", "175"),
        ("mentali_ex_psa10_glued", "Mentali ex PSA10", None),
        ("mentali_cgc_9_5", "Mentali CGC 9.5", None),
        ("mentali_ex_fraction_priority", "Mentali ex 175/198 Forces Temporelles", "175/198"),
        ("mentali_ex_hash_prefix", "Mentali ex #175", "175"),
        ("mentali_ex_numero_prefix", "Mentali ex n°175", "175"),
        ("dracaufeu_fraction_set_de_base", "Dracaufeu 4/102 set de base", "4/102"),
        ("carte_pokemon_mentali_ex_175_sleeve", "Carte pokemon Mentali ex 175 sous sleeve", "175"),
        # Matrice 3.4 et garde-fous 3.1 — formes rejetées
        ("reject_lot_50_cartes_mentali_4", "Lot de 50 cartes Pokémon dont Mentali 4", None),
        ("reject_lot_50_cartes_dracaufeu_4", "Lot de 50 cartes, Dracaufeu 4", None),
        ("reject_decimal_9_5", "Mentali ex 9.5", None),
        ("reject_single_digit_9", "Mentali ex 9", None),
        ("reject_year_2023", "Carte Pokémon édition 2023", None),
        ("reject_price_150_euro_glued", "Mentali 150€", None),
        ("reject_price_150_euro_spaced", "Mentali 150 €", None),
        ("reject_price_eur_and_percent", "Mentali 120 eur 100%", None),
        ("reject_quantity_x3", "Vends x3 Mentali ex", None),
        ("reject_psa_9", "Mentali PSA 9", None),
        ("reject_psa_10", "Mentali PSA 10", None),
        ("reject_collect_aura_10", "Mentali Collect'Aura 10", None),
        ("reject_over_300", "Mentali Réf 9999", None),
        ("reject_generic_no_name_no_set", "Cartes 125 disponibles", None),
    ]
    results = _eval_extension_card_numbers([title for _, title, _ in cases])
    for (case_id, title, expected), actual in zip(cases, results, strict=True):
        assert actual == expected, (
            f"[{case_id}] extractCardNumber({title!r}): attendu {expected!r}, obtenu {actual!r}"
        )


def test_extension_jsonl_with_isolated_number_is_valid_and_honest(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient
    from app.config import Settings
    from app.tcgdex.cache import TcgdexCache
    from app.tcgdex.models import TcgdexCard, TcgdexSet
    from app.web import app

    sample_jsonl = (
        '{"external_id":"vinted_mentali_175","name":"Mentali EX 175 CollectAura 9.5","set_name":"Non identifiée","card_number":"175","price_cents":9500,"currency":"EUR","seller":"AuraCollector","raw_data":{"title":"Mentali EX 175 CollectAura 9.5","description":""},"url":"https://www.vinted.fr/items/17595"}\n'
    ).encode("utf-8")

    items = parse_jsonl(sample_jsonl)
    assert len(items) == 1
    assert items[0].card_number == "175"

    db_path = tmp_path / "web_ext_isolated.db"
    with connect(db_path) as conn:
        apply_migrations(conn)
        cache = TcgdexCache(conn)
        cache.seed_initial_if_empty()
        cache.upsert_set(TcgdexSet(id="sv05", name="Forces Temporelles", card_count_official=162, card_count_total=218))
        cache.upsert_card(TcgdexCard(id="sv05-175", local_id="175", name="Mentali ex", set_id="sv05", set_name="Forces Temporelles"))

    app.state.settings = Settings(database_path=db_path)
    client = TestClient(app)

    response = client.post(
        "/imports",
        files={"file": ("capture.jsonl", sample_jsonl, "text/plain")},
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200
    ev = response.json()["evaluations"][0]
    assert ev["card_number"] == "175"
    # Un numéro isolé sans dénominateur propose les candidats (« ambiguous »), sans forcer « identified »
    assert ev["identification_status"] == "ambiguous"






def test_backend_rejects_incomplete_extension_payloads() -> None:
    """Champs obligatoires du contrat JSONL : external_id, name, set_name, price_cents."""
    from app.catalog import CatalogImportError

    # Prix manquant : rejet strict, aucune donnée inventée.
    with pytest.raises(CatalogImportError):
        parse_jsonl(
            b'{"external_id":"ext_1","name":"Pikachu","set_name":"Set de Base","url":"https://www.vinted.fr/items/1"}\n'
        )
    # Extension manquante.
    with pytest.raises(CatalogImportError):
        parse_jsonl(
            b'{"external_id":"ext_2","name":"Pikachu","price_cents":1500}\n'
        )
    # Nom vide.
    with pytest.raises(CatalogImportError):
        parse_jsonl(
            b'{"external_id":"ext_3","name":"   ","set_name":"Set de Base","price_cents":1500}\n'
        )
    # Prix en chaîne : rejeté (le backend exige un entier en centimes).
    with pytest.raises(CatalogImportError):
        parse_jsonl(
            b'{"external_id":"ext_4","name":"Pikachu","set_name":"Set de Base","price_cents":"15,00"}\n'
        )


def test_extension_price_parser_rejects_unreadable_prices() -> None:
    """Prix illisible → null → l'extracteur rejette l'annonce (rien d'inventé)."""
    import subprocess
    from playwright._impl._driver import compute_driver_executable

    driver = compute_driver_executable()
    node_path = driver[0] if isinstance(driver, tuple) else driver
    script = (
        "const { parsePriceToCents } = require('./extension/content/content.js');"
        "const inputs = JSON.parse(process.argv[1]);"
        "process.stdout.write(JSON.stringify(inputs.map((t) => parsePriceToCents(t))));"
    )
    inputs = ["15,00 €", "15.00€", "1 250,00 €", "", "   ", "Prix sur demande", "Négociable", None, "abc"]
    completed = subprocess.run(
        [str(node_path), "-e", script, json.dumps(inputs)],
        check=True,
        capture_output=True,
        text=True,
    )
    results = json.loads(completed.stdout)
    assert results[0] == 1500
    assert results[1] == 1500
    assert results[2] == 125000
    # Toutes les formes illisibles donnent null : l'annonce est rejetée, jamais estimée.
    assert results[3:] == [None, None, None, None, None, None]


def test_service_worker_accepts_partial_listings() -> None:
    """Une capture sans prix reste disponible, un prix invalide est refusé."""
    sw = Path("extension/background/service-worker.js").read_text(encoding="utf-8")
    assert "Number.isInteger(item.price_cents)" in sw
    assert "item.price_cents == null" in sw
    assert "item.price_cents >= 0" in sw
    assert "!item.set_name" in sw
    assert "!item.name.trim()" in sw


def test_content_extractors_require_title() -> None:
    """Chaque extracteur conserve une annonce sans prix mais exige un titre."""
    content = Path("extension/content/content.js").read_text(encoding="utf-8")
    assert "if (!title) return null;" in content
    assert "if (!title || priceCents === null) return null;" not in content


@pytest.mark.parametrize("offer,expected_price,expected_currency", [
    ({"price": "12.34", "priceCurrency": "USD"}, 1234, "USD"),
    ({"price": "12.34"}, 1234, None),
    ({}, None, None),
])
def test_generic_capture_preserves_currency_and_missing_price(offer, expected_price, expected_currency) -> None:
    from playwright.sync_api import sync_playwright

    product = {"@type": "Product", "name": "Carte Pokémon Pikachu", "offers": offer}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()
        page.set_content(f"<title>Carte Pokémon Pikachu</title><script type='application/ld+json'>{json.dumps(product)}</script>")
        page.evaluate("window.chrome = {runtime: {sendMessage(m, cb) { window.captured = m.payload[0]; cb({success:true, addedCount:0}); }}}")
        page.add_script_tag(path="extension/content/content.js")
        item = page.evaluate("window.captured")
        assert item["price_cents"] == expected_price
        assert item["currency"] == expected_currency
        assert item["seller"] is None
        browser.close()


def test_popup_partial_capture_previews_but_refuses_direct_exports() -> None:
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()
        page.add_init_script("""
            window.chrome = {runtime: {sendMessage(message, callback) {
                if (message.action === 'GET_STATUS') callback({autoCaptureEnabled:true});
                if (message.action === 'GET_LISTINGS') callback({listings:[{
                    external_id:'partial', name:'Pikachu', set_name:'151', price_cents:null,
                    currency:null, url:'https://www.vinted.fr/items/1', source:'vinted'
                }]});
            }}};
            window.fetch = async () => ({ok:true});
            HTMLFormElement.prototype.submit = function () { window.submitted = Object.fromEntries(new FormData(this)); };
        """)
        page.goto((Path("extension/popup/popup.html").resolve()).as_uri())
        expect(page.locator("#listings-list")).to_contain_text("Prix inconnu")
        for button in ("#btn-export-jsonl", "#btn-copy-jsonl"):
            page.locator(button).click()
            expect(page.locator("#status-message")).to_contain_text("Prix ou devise manquants")
        page.locator("#btn-send-pokebourse").click()
        expect(page.locator("#status-message")).to_contain_text("Analyse ouverte")
        sent = page.evaluate("window.submitted")
        assert "Image absente" in sent["ocr_result"]
        assert sent["price"] == ""
        assert sent["currency"] == ""
        browser.close()


def test_popup_preview_wiring_uses_local_preview_endpoint() -> None:
    """Le bouton Prévisualiser cible le parcours de prévisualisation, jamais l'import direct."""
    popup_html = Path("extension/popup/popup.html").read_text(encoding="utf-8")
    assert 'id="btn-preview-pokebourse"' in popup_html
    popup_js = Path("extension/popup/popup.js").read_text(encoding="utf-8")
    assert "http://localhost:8000/previsualiser-capture" in popup_js
    assert "http://localhost:8000/health" in popup_js
    manifest = json.loads(Path("extension/manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == 3
    assert "storage" in manifest["permissions"]


def test_popup_preview_when_pokebourse_unavailable_keeps_captures() -> None:
    """15. Application locale indisponible : les captures restent dans l'extension."""
    from playwright.sync_api import expect, sync_playwright

    popup_url = (Path("extension/popup/popup.html").resolve()).as_uri()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()
        page.add_init_script("""
            window.chrome = {runtime: {sendMessage(message, callback) {
                if (message.action === 'GET_STATUS') callback({autoCaptureEnabled:true});
                if (message.action === 'GET_LISTINGS') callback({listings:[{
                    external_id:'capture-1', name:'Dracaufeu 4/102', set_name:'Set de Base',
                    card_number:'4/102', price_cents:1200, currency:'EUR',
                    seller:'Collector92', url:'https://www.vinted.fr/items/1',
                    description:'Carte française', source:'vinted'
                }]});
            }}};
            window.fetch = () => Promise.reject(new Error('Connexion impossible'));
        """)
        page.goto(popup_url)
        page.locator("#btn-preview-pokebourse").click()
        expect(page.locator("#status-message")).to_contain_text("captures restent enregistrées")
        # La capture est toujours présente : rien n'est perdu ni envoyé.
        expect(page.locator("#listing-count")).to_have_text("1")
        browser.close()


def test_popup_preview_requires_exactly_one_listing() -> None:
    """17. Sélection multiple : comportement explicite, une prévisualisation à la fois."""
    from playwright.sync_api import expect, sync_playwright

    popup_url = (Path("extension/popup/popup.html").resolve()).as_uri()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()
        page.add_init_script("""
            window.chrome = {runtime: {sendMessage(message, callback) {
                if (message.action === 'GET_STATUS') callback({autoCaptureEnabled:true});
                if (message.action === 'GET_LISTINGS') callback({listings:[
                    {external_id:'capture-1', name:'Dracaufeu 4/102', set_name:'Set de Base',
                     price_cents:1200, currency:'EUR', seller:'Collector92',
                     url:'https://www.vinted.fr/items/1', raw_data:{title:'Dracaufeu 4/102'},
                     source:'vinted'},
                    {external_id:'capture-2', name:'Pikachu', set_name:'151',
                     price_cents:500, currency:'EUR',
                     url:'https://www.leboncoin.fr/ad/2', source:'leboncoin'}
                ]});
            }}};
            window.fetch = () => Promise.resolve({ok: true, json: () => Promise.resolve({})});
            window.__submitted = null;
            HTMLFormElement.prototype.submit = function () {
                window.__submitted = {
                    action: this.action, method: this.method, target: this.target,
                    fields: Object.fromEntries(new FormData(this).entries())
                };
            };
        """)
        page.goto(popup_url)
        # Deux annonces sélectionnées : aucune prévisualisation silencieuse.
        page.locator("#btn-preview-pokebourse").click()
        expect(page.locator("#status-message")).to_contain_text("exactement une annonce")
        assert page.evaluate("window.__submitted") is None
        # Une seule annonce : transmission des données capturées, sans enregistrement.
        page.locator("#card-capture-2 .item-checkbox").uncheck()
        page.locator("#btn-preview-pokebourse").click()
        expect(page.locator("#status-message")).to_contain_text("Prévisualisation ouverte")
        sent = page.evaluate("window.__submitted")
        assert sent is not None
        assert sent["action"] == "http://localhost:8000/previsualiser-capture"
        assert sent["method"] == "post"
        assert sent["target"] == "_blank"
        fields = sent["fields"]
        assert fields["platform"] == "vinted"
        assert fields["external_id"] == "capture-1"
        assert fields["title"] == "Dracaufeu 4/102"
        assert fields["price"] == "12,00"
        assert fields["shipping"] == ""
        assert fields["url"] == "https://www.vinted.fr/items/1"
        browser.close()


def test_send_triggers_automatic_ocr_before_preview() -> None:
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()
        page.add_init_script("""
            window.chrome = {runtime: {sendMessage(message, callback) {
                if (message.action === 'GET_STATUS') callback({autoCaptureEnabled:true});
                if (message.action === 'GET_LISTINGS') callback({listings:[{
                    external_id:'1', name:'Pikachu', price_cents:null, currency:null,
                    url:'https://www.vinted.fr/items/1', source:'vinted',
                    image_url:'https://images.vinted.net/photo.jpg'
                }]});
            }}};
            window.calls = [];
            window.fetch = async (url, options) => {
                window.calls.push(String(url));
                if (String(url).includes('images.vinted.net'))
                    return new Response(new Blob(['image'], {type:'image/jpeg'}), {headers:{'Content-Type':'image/jpeg'}});
                if (String(url).includes('/ocr/suggestions'))
                    return new Response(JSON.stringify({message:'À vérifier', recognized:{names:['Pikachu'], numbers:['58/102']}}), {status:200});
                return new Response('', {status:200});
            };
            HTMLFormElement.prototype.submit = function () { window.submitted = Object.fromEntries(new FormData(this)); };
        """)
        page.goto((Path("extension/popup/popup.html").resolve()).as_uri())
        page.locator("#btn-send-pokebourse").click()
        expect(page.locator("#status-message")).to_contain_text("Analyse ouverte")
        calls = page.evaluate("window.calls")
        assert any("/ocr/suggestions" in url for url in calls)
        sent = page.evaluate("window.submitted")
        assert json.loads(sent["ocr_result"])["recognized"]["numbers"] == ["58/102"]
        assert sent["price"] == "" and sent["currency"] == ""
        browser.close()


def test_vinted_product_jsonld_and_separate_prices() -> None:
    """Le prix de l'article ne doit pas être concaténé aux frais Vinted."""
    from playwright.sync_api import sync_playwright

    product = {"@type": "Product", "name": "Evoli GX Promo SM233", "description": "Evoli GX carte française", "image": "https://images1.vinted.net/photo.webp", "offers": {"price": 85, "priceCurrency": "EUR"}}
    html = f'''<html><head><title>Evoli GX</title><script type="application/ld+json">{json.dumps(product)}</script></head><body>
      <h1>Evoli GX Promo SM233</h1><div data-testid="item-sidebar-price-container"><span data-testid="item-price">85,00 €</span><span data-testid="total-combined-price">89,95 €</span></div>
      <span data-testid="profile-username">vendeur-public</span></body></html>'''
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()
        page.route("https://www.vinted.fr/items/123-evoli", lambda route: route.fulfill(status=200, content_type="text/html", body=html))
        page.add_init_script("window.chrome={runtime:{sendMessage(m,cb){window.captured=m.payload[0]; cb({success:true,addedCount:0});}}}")
        page.goto("https://www.vinted.fr/items/123-evoli")
        page.add_script_tag(path="extension/content/content.js")
        item = page.evaluate("window.captured")
        assert item["price_cents"] == 8500
        assert item["currency"] == "EUR"
        assert item["description"] == "Evoli GX carte française"
        assert item["image_url"] == "https://images1.vinted.net/photo.webp"
        assert item["seller"] == "vendeur-public"
        browser.close()
