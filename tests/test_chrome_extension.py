import json
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

    # Vérification des content scripts
    for cs in manifest["content_scripts"]:
        for js_rel in cs.get("js", []):
            assert (extension_dir / js_rel).exists()
        for css_rel in cs.get("css", []):
            assert (extension_dir / css_rel).exists()


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



