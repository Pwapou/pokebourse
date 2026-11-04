"""Rejeu local hermétique des campagnes d'identification (validation/ocr/marketplaces/replay_local.py)."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import socket
import sys

import pytest

from app.storage.database import connect
from app.storage.migration_runner import apply_migrations
from app.tcgdex.cache import TcgdexCache


def _load_replay_module(monkeypatch: pytest.MonkeyPatch, campaign_root: Path):
    """Charge replay_local.py en redirigeant ses constantes de chemins vers le dossier de campagne."""
    module_path = Path(__file__).parent.parent / "validation" / "ocr" / "marketplaces" / "replay_local.py"
    spec = importlib.util.spec_from_file_location("replay_local_under_test", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    # Après exécution : redirige les constantes de chemins vers le dossier de campagne.
    monkeypatch.setattr(module, "ROOT", campaign_root, raising=False)
    monkeypatch.setattr(module, "MANIFEST_PATH", campaign_root.parent / "evaluation" / "manifest.json", raising=False)
    return module


def _write_campaign(root: Path, with_photo: bool) -> None:
    run = root / "runs" / "campagne-test"
    (run / "images").mkdir(parents=True, exist_ok=True)
    items = []
    for index in range(1, 31):
        item = {"platform": "vinted", "url": f"https://www.vinted.fr/items/test-{index}", "title": f"Carte {index}"}
        if index == 1:
            item["image_url"] = "https://images.example.invalid/photo.webp"
        items.append(item)
    (root / "jeu-30-liens.json").write_text(__import__("json").dumps(items), encoding="utf-8")
    if with_photo:
        (run / "images" / "01.webp").write_bytes(b"photo-figee")


def _seed_backup(tmp_path: Path) -> Path:
    db_path = tmp_path / "backup.sqlite"
    with connect(db_path) as connection:
        apply_migrations(connection)
        TcgdexCache(connection).seed_initial_if_empty()
        connection.execute("PRAGMA journal_mode = DELETE")
    return db_path


def test_replay_refuses_missing_photo_without_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    campaign_root = tmp_path / "marketplaces"
    campaign_root.mkdir()
    _write_campaign(campaign_root, with_photo=False)
    backup = _seed_backup(tmp_path)
    module = _load_replay_module(monkeypatch, campaign_root)
    monkeypatch.setattr(sys, "argv", ["replay_local.py", "--run-id", "campagne-test", "--backup", str(backup)])

    exit_code = module.main()

    assert exit_code == 2
    assert "Photo manquante" in capsys.readouterr().err
    assert not (campaign_root / "runs" / "campagne-test-rejeu" / "resultats.json").exists()


def test_replay_runs_hermetically_on_frozen_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    campaign_root = tmp_path / "marketplaces"
    campaign_root.mkdir()
    _write_campaign(campaign_root, with_photo=True)
    backup = _seed_backup(tmp_path)
    module = _load_replay_module(monkeypatch, campaign_root)
    monkeypatch.setattr(sys, "argv", ["replay_local.py", "--run-id", "campagne-test", "--backup", str(backup)])

    def fake_analyze_image(connection, content: bytes):
        assert content == b"photo-figee"
        return {"status": "ok", "recognized": {"names": ["Pikachu"], "numbers": ["58/102"]}, "candidates": []}

    monkeypatch.setattr("app.identification.ocr.analyze_image", fake_analyze_image)

    def banned_network(*args, **kwargs):
        raise AssertionError("tentative de résolution DNS pendant le rejeu")

    monkeypatch.setattr(socket, "getaddrinfo", banned_network)

    exit_code = module.main()

    assert exit_code == 0
    report = __import__("json").loads(
        (campaign_root / "runs" / "campagne-test-rejeu" / "resultats.json").read_text(encoding="utf-8")
    )
    assert report["decision_origin"] == "automatic"
    assert report["pipeline_version"]
    assert len(report["items"]) == 30
    first, others = report["items"][0], report["items"][1:]
    assert first["ocr_only"] is not None and first["ocr"]["recognized"]["names"] == ["Pikachu"]
    assert all(item["ocr_only"] is None and item["ocr"] is None for item in others)
    assert all(item["combined"]["status"] for item in report["items"])
    # Le rejeu laisse la résolution DNS désactivée après exécution.
    with pytest.raises(RuntimeError, match="Accès réseau interdit"):
        socket.getaddrinfo("example.invalid", 443)
