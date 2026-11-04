"""Harness/fixture tests only: these do not validate future T06/T07 recognition."""
from __future__ import annotations

import copy
import importlib.util
import io
import json
from pathlib import Path
import socket
import sqlite3
import types
from typing import Any

from PIL import Image
import pytest

ROOT = Path(__file__).resolve().parents[1]
PREP = ROOT / "validation/ocr/benchmarks/t06_preparation"


def load(name: str, path: Path) -> Any:
    """Import the separate preparation tools without running their CLI."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bench = load("ocr_preparation", PREP / "benchmark.py")
fixtures = load("ocr_fixture_construction", PREP / "fixtures.py")


@pytest.fixture(autouse=True)
def no_network() -> Any:
    """Protect every test, including accidental direct IP connections."""
    with bench.offline():
        yield


@pytest.fixture
def backup(tmp_path: Path) -> Path:
    """Small synthetic standalone catalogue; no migrations, no application seed."""
    path = tmp_path / "backup.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE pokemon_reference_cards (id INTEGER PRIMARY KEY)")
        connection.execute("CREATE TABLE pokemon_reference_sets (id TEXT)")
        connection.execute("INSERT INTO pokemon_reference_cards VALUES (1)")
    return path


def test_guard_blocks_dns_direct_ip_and_udp() -> None:
    with pytest.raises(RuntimeError, match="network_forbidden"):
        socket.getaddrinfo("example.invalid", 443)
    with socket.socket() as stream:
        with pytest.raises(RuntimeError, match="network_forbidden"):
            stream.connect(("127.0.0.1", 443))
        with pytest.raises(RuntimeError, match="network_forbidden"):
            stream.connect_ex(("127.0.0.1", 443))
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as stream:
        with pytest.raises(RuntimeError, match="network_forbidden"):
            stream.sendto(b"test", ("127.0.0.1", 53))


def test_artifact_missing_mismatch_and_path_escape(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="artifact_missing"):
        bench.checked(tmp_path, "absent.png", "a" * 64)
    (tmp_path / "photo.png").write_bytes(b"synthetic")
    with pytest.raises(ValueError, match="hash_mismatch"):
        bench.checked(tmp_path, "photo.png", "a" * 64)
    with pytest.raises(ValueError, match="path_escape"):
        bench.checked(tmp_path, "../escape", "a" * 64)


def test_refuses_overwrite_even_symlink(tmp_path: Path) -> None:
    path = tmp_path / "result.json"
    bench.write_json(path, {"original": True})
    with pytest.raises(FileExistsError):
        bench.write_json(path, {"original": False})
    assert bench.read_json(path) == {"original": True}
    link = tmp_path / "link.json"
    link.symlink_to(tmp_path / "missing")
    with pytest.raises(FileExistsError):
        bench.write_json(link, {})


def test_catalog_is_readonly_and_unchanged(backup: Path) -> None:
    digest = bench.sha256(backup)
    before_files = sorted(backup.parent.iterdir())
    with bench.catalog(backup, digest) as connection:
        assert connection.execute("SELECT COUNT(*) FROM pokemon_reference_cards").fetchone()[0] == 1
        for sql in ("INSERT INTO pokemon_reference_cards VALUES (2)",
                    "CREATE TABLE accidental_seed (id INTEGER)", "PRAGMA user_version=999"):
            with pytest.raises(sqlite3.DatabaseError):
                connection.execute(sql)
    assert bench.sha256(backup) == digest
    assert sorted(backup.parent.iterdir()) == before_files


@pytest.mark.parametrize("problem", ["missing", "mismatch", "wal", "shm", "journal"])
def test_catalog_refuses_unverified_or_non_standalone(backup: Path, problem: str) -> None:
    digest = bench.sha256(backup)
    path = backup
    if problem == "missing":
        path = backup.parent / "absent.sqlite"
    elif problem == "mismatch":
        digest = "a" * 64
    else:
        Path(str(path) + "-" + problem).write_bytes(b"unmerged")
    with pytest.raises(ValueError, match="catalog_"):
        with bench.catalog(path, digest):
            pytest.fail("unverified catalogue opened")


def test_catalog_rejects_missing_tables(tmp_path: Path) -> None:
    path = tmp_path / "empty.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE other (id INTEGER)")
    with pytest.raises(ValueError, match="catalog_tables_missing"):
        with bench.catalog(path, bench.sha256(path)):
            pytest.fail("invalid catalogue opened")


def test_snapshot_detects_concurrent_change_and_retries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "module.py").write_text("VERSION = 1\n")
    monkeypatch.setattr(bench, "source_files", lambda root: [Path("module.py")])
    real_state = bench.source_state
    calls = 0

    def concurrent(root: Path) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        if calls == 2:
            (root / "module.py").write_text("VERSION = 2\n")
        return real_state(root)

    monkeypatch.setattr(bench, "source_state", concurrent)
    result = bench.freeze_sources(source, tmp_path / "captured")
    assert result["attempt"] == 2
    assert (tmp_path / "captured/attempt-1/REJECTED.json").is_file()
    assert (tmp_path / result["accepted"] / "module.py").read_text() == "VERSION = 2\n"
    with pytest.raises(FileExistsError):
        bench.freeze_sources(source, tmp_path / "captured")


def test_snapshot_refuses_continuously_mutating_sources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def unstable(root: Path) -> dict[str, Any]:
        raise ValueError("source_changed_during_read")
    monkeypatch.setattr(bench, "source_state", unstable)
    with pytest.raises(ValueError, match="unstable_after_three"):
        bench.freeze_sources(tmp_path, tmp_path / "captured")
    assert len(list((tmp_path / "captured").glob("*/REJECTED.json"))) == 3


def test_stable_ids_not_positions_or_titles() -> None:
    rows = [{"listing_id": "second", "title": "same"}, {"listing_id": "first", "title": "same"}]
    assert set(bench.keyed(rows)) == {"first", "second"}
    with pytest.raises(ValueError, match="duplicate"):
        bench.keyed(rows + [rows[0]])
    with pytest.raises(ValueError, match="missing"):
        bench.keyed([{"index": 1, "title": "same"}])


@pytest.mark.parametrize("outcome", ["result", "abstention", "error", "timeout"])
def test_execution_outcomes_are_distinct_and_logs_private(outcome: str, capsys: pytest.CaptureFixture[str]) -> None:
    def analyze(connection: Any, content: bytes) -> dict[str, Any]:
        if outcome == "error":
            raise ValueError("seller@example.invalid OCR FULL TEXT MUST NOT APPEAR")
        if outcome == "timeout":
            raise bench.CaseTimeout("private text")
        return {"status": "no_match" if outcome == "abstention" else "candidates",
                "recognized": {"names": [], "numbers": []}, "candidates": []}

    result = bench.execute_case(None, b"synthetic", analyze, lambda *args: {"status": "unidentified"})
    assert result["outcome"] == outcome
    assert result["duration_ns"] >= 0
    assert "seller@" not in json.dumps(result)
    assert "FULL TEXT" not in json.dumps(result)
    assert capsys.readouterr() == ("", "")


def fake_bundle(tmp_path: Path) -> Path:
    """Minimal integrity-checked bundle for testing unavailable variants without OCR."""
    bundle = tmp_path / "bundle"
    (bundle / "sources/attempt-1").mkdir(parents=True)
    bench.write_json(bundle / "annotations.blank.json", {})
    bench.write_json(bundle / "manifest.json", {
        "code": {"accepted": "sources/attempt-1", "files": {}}, "inputs": {},
        "catalog": {"sha256": "a" * 64}, "annotations_sha256": bench.sha256(bundle / "annotations.blank.json"),
        "cases": [{"listing_id": "stable-id", "sha256": "b" * 64}]})
    return bundle


@pytest.mark.parametrize("variant", bench.VARIANTS[1:])
def test_future_variant_explicitly_unavailable(tmp_path: Path, variant: str) -> None:
    bundle = fake_bundle(tmp_path)
    output = tmp_path / "run.json"
    bench.run(bundle, tmp_path / "does-not-exist.sqlite", output, variant)
    report = bench.read_json(output)
    assert report["reason"] == "implementation_missing"
    assert all(row["outcome"] == "unavailable" and row["duration_ns"] is None for row in report["records"])
    with pytest.raises(FileExistsError):
        bench.run(bundle, Path("absent"), output, variant)


def test_frozen_membership_and_input_hash_rechecked(tmp_path: Path) -> None:
    bundle = fake_bundle(tmp_path)
    (bundle / "sources/attempt-1/unexpected.py").write_text("pass")
    with pytest.raises(ValueError, match="membership_changed"):
        bench.verify_bundle(bundle)


def test_import_guard_supports_frozen_namespace_packages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    namespace = types.ModuleType("app.namespace")
    namespace.__path__ = [str(tmp_path / "app/namespace")]
    module = types.ModuleType("app.namespace.module")
    module.__file__ = str(tmp_path / "app/namespace/module.py")
    monkeypatch.setattr(bench.sys, "modules", {namespace.__name__: namespace, module.__name__: module})
    bench.verify_import_locations(tmp_path)
    module.__file__ = "/outside/the/frozen/tree.py"
    with pytest.raises(ValueError, match="non_frozen_application_import"):
        bench.verify_import_locations(tmp_path)


def paired_report() -> dict[str, Any]:
    """Synthetic reports describe harness states, not actual OCR predictions."""
    return {"catalog_version": "catalog-a", "input_version": "images-a", "labels_version": "labels-a",
            "records": [{"listing_id": value, "phase": "measured", "pass": 1,
                         "image_sha256": value, "outcome": "result", "duration_ns": 10,
                         "ocr": {"recognized": {"names": [], "numbers": []}}}
                        for value in ("a", "b")]}


def test_pairing_ignores_order_and_preserves_errors_absence_abstention() -> None:
    before = paired_report()
    after = copy.deepcopy(before)
    after["records"].reverse()
    after["records"][0].update(outcome="unavailable", duration_ns=None)
    after["records"][1].update(outcome="abstention", duration_ns=20)
    result = bench.compare(before, after)
    assert result["paired_count"] == 2
    assert result["pairs"][0]["duration_delta_ns"] == 10
    assert result["pairs"][1]["after"] == "unavailable"
    assert result["pairs"][1]["duration_delta_ns"] is None
    assert result["accuracy_delta"] is None


@pytest.mark.parametrize("problem", ["catalog_version", "input_version", "labels_version", "image", "ids", "duplicate"])
def test_pairing_refuses_changed_inputs(problem: str) -> None:
    before = paired_report()
    after = copy.deepcopy(before)
    if problem in after:
        after[problem] = "changed"
    elif problem == "image":
        after["records"][0]["image_sha256"] = "changed"
    elif problem == "ids":
        after["records"][0]["listing_id"] = "changed"
    else:
        after["records"].append(after["records"][0])
    with pytest.raises(ValueError):
        bench.compare(before, after)


def test_blank_annotations_have_no_accuracy_or_borrowed_predictions() -> None:
    cases = [{"listing_id": "independent"}]
    labels = bench.annotations(cases, "a" * 64)
    assert all(value is None for key, value in labels["annotations"][0].items()
               if key in {"expected_tcgdex_id", "printed_name", "printed_number", "human_region", "identity_determinable"})
    evaluator = bench.load_module("test_ocr_evaluator", ROOT / "scripts/evaluate_identification.py")
    report = {"items": [{"listing_id": "independent", "ocr_only": {"status": "identified", "tcgdex_id": "invented"}}]}
    evaluation = evaluator.evaluate_data(report, labels)
    # Inspect every exported metric, not status counts: no verified denominator exists.
    def metrics(value: Any) -> None:
        if isinstance(value, dict):
            if {"numerator", "denominator", "value"} <= value.keys():
                assert value["denominator"] == 0 and value["value"] is None
            for child in value.values():
                metrics(child)
        elif isinstance(value, list):
            for child in value:
                metrics(child)
    metrics(evaluation)


def test_timing_method_small_sample_and_empty() -> None:
    assert bench.timing([])["p95_ns"] is None
    assert bench.timing([1, 2, 3, 4])["median_ns"] == 2.5
    assert bench.timing(list(range(1, 21)))["p95_ns"] == 19


def test_fixtures_reproducible_and_refuse_overwrite(tmp_path: Path) -> None:
    first = fixtures.generate(tmp_path / "first")
    second = fixtures.generate(tmp_path / "second")
    assert first == second
    assert (tmp_path / "first/manifest.json").read_bytes() == (tmp_path / "second/manifest.json").read_bytes()
    for case in first["cases"]:
        assert bench.sha256(tmp_path / "first" / case["path"]) == case["sha256"]
    assert first["identity_ground_truth"] is None
    with pytest.raises(FileExistsError):
        fixtures.generate(tmp_path / "first")


@pytest.mark.parametrize("orientation", range(1, 9))
def test_existing_exif_preparation_matches_construction(tmp_path: Path, orientation: int) -> None:
    from app.identification.ocr import _prepare_image
    manifest = fixtures.generate(tmp_path / "synthetic")
    case = next(row for row in manifest["cases"] if row["case_id"] == f"exif-{orientation}")
    output = _prepare_image((tmp_path / "synthetic" / case["path"]).read_bytes())
    with Image.open(io.BytesIO(output)) as image:
        assert list(image.size) == case["expected"]["oriented_dimensions"]
        assert image.getexif().get(274) is None
        x, y = case["expected"]["original_top_left_pixel_after_orientation"]
        red, green, blue = image.getpixel((x, y))
        assert red > 220 and green < 40 and blue < 40


def test_fixture_geometry_and_future_contracts_are_construction_only(tmp_path: Path) -> None:
    manifest = fixtures.generate(tmp_path / "synthetic")
    cases = {case["case_id"]: case["expected"] for case in manifest["cases"]}
    off_center = cases["off-center"]
    assert off_center["full_photo_top20_bottom15_miss_card_text"] is True
    assert all(token["box"][1] >= 120 and token["box"][3] <= 510 for token in off_center["tokens"])
    nested = cases["nested-crops"]
    assert nested["pass_box"] == [80, 80, 160, 120]
    assert nested["expected_photo_box"] == [160, 120, 200, 140]
    assert cases["fragments"]["permitted_assembly"]["literal"] == "025/165"
    two_cards = cases["two-cards"]
    owners = {token["token_id"]: token["object_id"] for token in two_cards["tokens"]}
    for forbidden in two_cards["forbidden_assemblies"]:
        assert len({owners[token] for token in forbidden}) == 2
    assert cases["slab-label"]["forbidden_card_tokens"] == ["certificate"]
    assert cases["number-3"]["literal_must_survive"] == "108/59"
    assert all(case["future_acceptance"].startswith("not_executed") for case in manifest["cases"])


def test_inventory_reproducible_and_refuses_missing_photo(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    photo = root / "validation/ocr/marketplaces/runs/campaign/images/01.webp"
    photo.parent.mkdir(parents=True)
    Image.new("RGB", (120, 80), "white").save(photo)
    dataset = root / "dataset.json"
    dataset.write_text(json.dumps([{"url": "a", "platform": "synthetic", "image_url": "unused"},
                                   {"url": "b", "platform": "synthetic"}]))
    previous = {"campaign_id": "campaign", "dataset": {"path": "dataset.json", "sha256": bench.sha256(dataset), "listing_count": 2},
                "images": [{"path": str(photo.relative_to(root)), "sha256": bench.sha256(photo)}]}
    first = bench.inventory(root, previous)
    assert first == bench.inventory(root, previous)
    assert first[0]["dimensions"] == [120, 80]
    assert first[1]["availability"] == "unavailable"
    photo.unlink()
    with pytest.raises(ValueError, match="artifact_missing"):
        bench.inventory(root, previous)
