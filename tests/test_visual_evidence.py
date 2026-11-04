"""Preuves visuelles conservées explicitement (T04) : stockage, statuts, purge,
sauvegarde, décisions fondées image et éligibilité visuelle du dataset.

Aucun réseau ni OCR réel : l'analyse éphémère a son moteur Tesseract mocké.
"""

import io
import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from app.backups import create_backup, restore_backup
from app.identification.dataset import build_dataset
from app.identification.evidence_store import (
    DEFAULT_MAX_EVIDENCE_BYTES,
    TRANSFORM_VERSION,
    attach_image_reading,
    delete_image_evidence,
    evidence_file_status,
    evidence_root,
    purge_expired_evidence,
    purge_unreferenced_evidence,
    store_image_evidence,
    verify_image_evidence,
)
from app.identification.ocr import analyze_image
from app.identification.resolution import capture_evidence, resolve_listing
from app.identification.reviews import ReviewInput, current_revision, save_review
from app.storage.database import connect
from app.storage.migration_runner import apply_migrations
from app.tcgdex.cache import TcgdexCache


@pytest.fixture
def database(tmp_path: Path) -> Iterator[tuple[sqlite3.Connection, Path]]:
    path = tmp_path / "evidence.db"
    with connect(path) as connection:
        apply_migrations(connection)
        TcgdexCache(connection).seed_initial_if_empty()
        connection.commit()
        yield connection, path


def png_bytes(color: tuple[int, int, int] = (120, 40, 200), size: tuple[int, int] = (32, 24)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def jpeg_with_exif() -> bytes:
    buffer = io.BytesIO()
    image = Image.new("RGB", (24, 32), (10, 200, 90))
    exif = Image.Exif()
    exif[0x0112] = 6  # orientation d'origine à conserver comme repère
    image.save(buffer, format="JPEG", exif=exif)
    return buffer.getvalue()


def add_item(connection: sqlite3.Connection, title: str = "Dracaufeu 4/102 Set de Base") -> int:
    with connection:
        connection.execute("INSERT OR IGNORE INTO sources(name, kind) VALUES ('vinted', 'api')")
        source_id = connection.execute("SELECT id FROM sources WHERE name='vinted'").fetchone()[0]
        cursor = connection.execute(
            "INSERT INTO import_batches(source_id, input_checksum) VALUES (?, ?)",
            (source_id, f"batch-t04-{connection.total_changes}"),
        )
        external_id = f"ext-t04-{connection.total_changes}"
        cursor = connection.execute(
            """INSERT INTO catalog_items(source_id, import_batch_id, external_id, name, original_title,
            set_name, price_cents, raw_data, identification_status)
            VALUES (?, ?, ?, ?, ?, 'Set de Base', 100, '{}', 'ambiguous')""",
            (source_id, cursor.lastrowid, external_id, title, title),
        )
        return int(cursor.lastrowid)


def seed_card(connection: sqlite3.Connection):
    return TcgdexCache(connection).get_card_by_tcgdex_id("base1-4")


def decide_with_image(
    connection: sqlite3.Connection, database_path: Path, item_id: int, evidence_id: int,
    *, basis: str = "image",
) -> int:
    evidence = capture_evidence(connection, item_id)
    card = seed_card(connection)
    review = ReviewInput(
        outcome="matched", review_kind="decision", validated_card_id=card.id,
        evidence_basis=basis, image_evidence_id=evidence_id, text_sufficient=basis == "both",
    )
    return save_review(
        connection, item_id, review, expected_hash=evidence["hash"],
        expected_revision=current_revision(connection, item_id), operator="lecteur-1",
        database_path=database_path,
    )


def dataset_records(content: bytes) -> tuple[dict, list[dict]]:
    lines = [json.loads(line) for line in content.decode("utf-8").splitlines()]
    manifest = next(row for row in lines if row["type"] == "manifest")
    return manifest, [row for row in lines if row["type"] == "review"]


def test_analyze_image_is_ephemeral_and_stores_nothing(database: tuple[sqlite3.Connection, Path]) -> None:
    connection, path = database
    with patch("app.identification.ocr._run_tesseract", return_value="") as tesseract:
        result = analyze_image(connection, png_bytes())
    assert tesseract.call_count >= 1
    assert connection.execute("SELECT count(*) FROM listing_image_evidence").fetchone()[0] == 0
    assert connection.execute("SELECT count(*) FROM listing_image_evidence_readings").fetchone()[0] == 0
    assert not (path.parent / "evidence").exists()
    assert "status" in result


def test_store_evidence_deduplicates_and_validates_contract(database: tuple[sqlite3.Connection, Path]) -> None:
    connection, path = database
    content = png_bytes()
    first = store_image_evidence(connection, path, content, purpose="benchmark")
    second = store_image_evidence(connection, path, content, purpose="annotation")
    assert first["id"] == second["id"]
    assert connection.execute("SELECT count(*) FROM listing_image_evidence").fetchone()[0] == 1
    assert connection.execute("SELECT count(*) FROM listing_image_evidence").fetchone()[0] == 1
    with pytest.raises(ValueError, match="Périmètre"):
        store_image_evidence(connection, path, png_bytes((1, 2, 3)), purpose="entrainement")
    with pytest.raises(LookupError):
        store_image_evidence(connection, path, png_bytes((1, 2, 3)), listing_id=9999)
    with pytest.raises(ValueError, match="Quota"):
        store_image_evidence(connection, path, png_bytes((1, 2, 3)), max_bytes=0)
    # La déduplication rattache une annonce à une preuve orpheline existante.
    orphan = store_image_evidence(connection, path, png_bytes((9, 9, 9)))
    item_id = add_item(connection)
    linked = store_image_evidence(connection, path, png_bytes((9, 9, 9)), listing_id=item_id)
    assert linked["id"] == orphan["id"] and linked["listing_id"] == item_id


def test_store_evidence_cleans_exif_and_keeps_orientation_marker(database: tuple[sqlite3.Connection, Path]) -> None:
    connection, path = database
    record = store_image_evidence(connection, path, jpeg_with_exif(), purpose="confirmation")
    assert record["exif_orientation"] == 6
    stored = evidence_root(path) / record["storage_path"]
    assert stored.is_file() and stored.read_bytes() == (evidence_root(path) / record["storage_path"]).read_bytes()
    with Image.open(stored) as image:
        assert image.format == "PNG"
        assert not image.getexif()  # aucune métadonnée EXIF conservée
        assert image.size == (record["width"], record["height"])
    # La référence de pixels correspond aux pixels réellement stockés.
    import hashlib

    with Image.open(stored) as image:
        assert hashlib.sha256(image.convert("RGB").tobytes()).hexdigest() == record["pixel_sha256"]


def test_store_evidence_enforces_quota(database: tuple[sqlite3.Connection, Path]) -> None:
    connection, path = database
    first = store_image_evidence(connection, path, png_bytes(), max_bytes=10_000)
    with pytest.raises(ValueError, match="Quota"):
        store_image_evidence(connection, path, png_bytes((250, 0, 0)), max_bytes=first["byte_size"])
    assert connection.execute("SELECT count(*) FROM listing_image_evidence").fetchone()[0] == 1
    assert DEFAULT_MAX_EVIDENCE_BYTES == 512 * 1024 * 1024


def test_evidence_file_statuses_and_verification(database: tuple[sqlite3.Connection, Path]) -> None:
    connection, path = database
    record = store_image_evidence(connection, path, png_bytes())
    evidence_id = record["id"]
    stored = evidence_root(path) / record["storage_path"]
    assert evidence_file_status(connection, path, evidence_id) == "present"
    assert verify_image_evidence(connection, path)["ok"] is True

    stored.unlink()
    assert evidence_file_status(connection, path, evidence_id) == "missing"
    report = verify_image_evidence(connection, path)
    assert report["ok"] is False and report["missing"] == [evidence_id]

    stored.write_bytes(b"octets corrompus")
    assert evidence_file_status(connection, path, evidence_id) == "corrupted"

    delete_image_evidence(connection, path, evidence_id)
    assert evidence_file_status(connection, path, evidence_id) == "deleted"
    assert not stored.exists()
    assert verify_image_evidence(connection, path)["ok"] is True  # purge logique : plus rien à vérifier
    with pytest.raises(LookupError):
        evidence_file_status(connection, path, 9999)


def test_attach_reading_contract(database: tuple[sqlite3.Connection, Path]) -> None:
    connection, path = database
    record = store_image_evidence(connection, path, png_bytes())
    reading_id = attach_image_reading(
        connection, image_evidence_id=record["id"], field="name", value="Dracaufeu",
        source="manual", region=(0, 0, 32, 24),
    )
    row = connection.execute("SELECT * FROM listing_image_evidence_readings WHERE id=?", (reading_id,)).fetchone()
    assert row["transform_version"] == TRANSFORM_VERSION
    assert json.loads(row["region_json"]) == [0, 0, 32, 24]
    with pytest.raises(ValueError, match="Région"):
        attach_image_reading(connection, image_evidence_id=record["id"], field="name", value="x", source="manual", region=(1, 2, 3))
    with pytest.raises(ValueError, match="Région"):
        attach_image_reading(connection, image_evidence_id=record["id"], field="name", value="x", source="manual", region=(5, 0, 2, 10))
    with pytest.raises(ValueError, match="Champ"):
        attach_image_reading(connection, image_evidence_id=record["id"], field="prix", value="x", source="manual")
    with pytest.raises(ValueError, match="Champ"):
        attach_image_reading(connection, image_evidence_id=record["id"], field="name", value="x", source="robot")
    delete_image_evidence(connection, path, record["id"])
    with pytest.raises(ValueError, match="supprimée"):
        attach_image_reading(connection, image_evidence_id=record["id"], field="name", value="x", source="manual")


def test_purges_only_unreferenced_and_expired_evidence(database: tuple[sqlite3.Connection, Path]) -> None:
    connection, path = database
    item_id = add_item(connection)
    orphan = store_image_evidence(connection, path, png_bytes((1, 1, 1)))["id"]
    attached = store_image_evidence(connection, path, png_bytes((2, 2, 2)), listing_id=item_id)["id"]
    decided = store_image_evidence(connection, path, png_bytes((3, 3, 3)), listing_id=item_id)["id"]
    decide_with_image(connection, path, item_id, decided)

    connection.execute(
        "UPDATE listing_image_evidence SET created_at='2020-01-01T00:00:00.000Z' WHERE id IN (?, ?)",
        (orphan, attached),
    )
    with pytest.raises(ValueError, match="rétention"):
        purge_expired_evidence(connection, path, days=0)
    assert purge_unreferenced_evidence(connection, path) == 1
    assert evidence_file_status(connection, path, orphan) == "deleted"
    assert evidence_file_status(connection, path, attached) == "present"  # rattachée à une annonce
    assert evidence_file_status(connection, path, decided) == "present"  # étayée par une décision
    # Seule la preuve vieillie sans décision rattachée est purgée par la rétention.
    assert purge_expired_evidence(connection, path, days=30) == 1
    assert evidence_file_status(connection, path, attached) == "deleted"
    assert evidence_file_status(connection, path, decided) == "present"


def test_backup_sidecar_restores_evidence_bytes(database: tuple[sqlite3.Connection, Path], tmp_path: Path) -> None:
    connection, path = database
    item_id = add_item(connection)
    record = store_image_evidence(connection, path, png_bytes(), listing_id=item_id)
    connection.commit()
    backup = create_backup(path)
    assert backup.is_file()
    sidecar = backup.with_name(backup.name + ".evidence")
    assert sidecar.is_dir() and (sidecar / record["storage_path"]).is_file()

    restored_path = tmp_path / "restored" / "pokebourse.db"
    restore_backup(restored_path, backup)
    with connect(restored_path) as restored:
        assert restored.execute("SELECT count(*) FROM listing_image_evidence").fetchone()[0] == 1
        assert evidence_file_status(restored, restored_path, record["id"]) == "present"
        row = restored.execute("SELECT * FROM listing_image_evidence WHERE id=?", (record["id"],)).fetchone()
        assert row["sha256"] == record["sha256"] and row["listing_id"] == item_id


def test_review_input_requires_consistent_visual_basis(database: tuple[sqlite3.Connection, Path]) -> None:
    connection, path = database
    item_id = add_item(connection)
    record = store_image_evidence(connection, path, png_bytes(), listing_id=item_id)
    with pytest.raises(Exception, match="preuve explicitement conservée"):
        ReviewInput(outcome="lot", evidence_basis="image", text_sufficient=True)
    with pytest.raises(Exception, match="« image » ou « both »"):
        ReviewInput(outcome="lot", evidence_basis="text", image_evidence_id=record["id"], text_sufficient=True)
    # Fondée image, une reconnaissance ne suppose pas un texte suffisant.
    review = ReviewInput(
        outcome="matched", validated_card_id=seed_card(connection).id,
        evidence_basis="image", image_evidence_id=record["id"], text_sufficient=False,
    )
    assert review.evidence_basis == "image"


def test_save_review_persists_visual_basis_and_rejects_absent_bytes(
    database: tuple[sqlite3.Connection, Path], tmp_path: Path,
) -> None:
    connection, path = database
    item_id = add_item(connection)
    record = store_image_evidence(connection, path, png_bytes(), listing_id=item_id)
    review_id = decide_with_image(connection, path, item_id, record["id"], basis="both")
    row = connection.execute("SELECT * FROM listing_identification_reviews WHERE id=?", (review_id,)).fetchone()
    assert row["evidence_basis"] == "both" and row["image_evidence_id"] == record["id"]
    assert resolve_listing(connection, item_id).decision_source == "human"

    other_item = add_item(connection, "Évoli 51/64 Jungle")
    other = store_image_evidence(connection, path, png_bytes((5, 5, 5)), listing_id=other_item)
    delete_image_evidence(connection, path, other["id"])
    evidence = capture_evidence(connection, other_item)
    card = seed_card(connection)
    with pytest.raises(ValueError, match="supprimée"):
        save_review(
            connection, other_item,
            ReviewInput(outcome="matched", validated_card_id=card.id, evidence_basis="image",
                        image_evidence_id=other["id"], text_sufficient=False),
            expected_hash=evidence["hash"], expected_revision=current_revision(connection, other_item),
            operator="lecteur-2", database_path=path,
        )
    # Une base différente (octets absents de l'espace de preuves) est refusée.
    elsewhere = tmp_path / "ailleurs.db"
    with connect(elsewhere) as other_connection:
        apply_migrations(other_connection)
    missing_bytes = store_image_evidence(connection, path, png_bytes((6, 6, 6)), listing_id=other_item)
    (evidence_root(path) / missing_bytes["storage_path"]).unlink()
    evidence = capture_evidence(connection, other_item)
    with pytest.raises(ValueError, match="octets"):
        save_review(
            connection, other_item,
            ReviewInput(outcome="matched", validated_card_id=card.id, evidence_basis="image",
                        image_evidence_id=missing_bytes["id"], text_sufficient=False),
            expected_hash=evidence["hash"], expected_revision=current_revision(connection, other_item),
            operator="lecteur-2", database_path=path,
        )
    # Sans chemin de base, la preuve référencée doit au moins exister.
    orphan = store_image_evidence(connection, path, png_bytes((7, 7, 7)))
    with pytest.raises(ValueError, match="introuvable"):
        save_review(
            connection, other_item,
            ReviewInput(outcome="matched", validated_card_id=card.id, evidence_basis="image",
                        image_evidence_id=9999, text_sufficient=False),
            expected_hash=evidence["hash"], expected_revision=current_revision(connection, other_item),
            operator="lecteur-2",
        )
    assert orphan["purpose"] == "benchmark"


def test_dataset_marks_visual_eligibility_and_reexamination(database: tuple[sqlite3.Connection, Path]) -> None:
    connection, path = database
    item_id = add_item(connection)
    visual = store_image_evidence(connection, path, png_bytes(), listing_id=item_id)
    visual_review = decide_with_image(connection, path, item_id, visual["id"], basis="image")

    text_item = add_item(connection, "Pikachu 58/102 Set de Base")
    evidence = capture_evidence(connection, text_item)
    text_review = save_review(
        connection, text_item,
        ReviewInput(outcome="matched", validated_card_id=seed_card(connection).id, text_sufficient=True),
        expected_hash=evidence["hash"], expected_revision=current_revision(connection, text_item),
        operator="lecteur-3", database_path=path,
    )

    manifest, records = dataset_records(build_dataset(connection, database_path=path))
    by_review = {record["review_id"]: record for record in records}
    assert manifest["schema_version"] == "identity-pilot-v2"
    assert manifest["visual_eligible_count"] == 1 and manifest["needs_reexamination_count"] == 0
    visual_record = by_review[visual_review]
    assert visual_record["evidence_basis"] == "image"
    assert visual_record["eligible_for_visual_training"] is True
    assert visual_record["image_evidence"]["sha256"] == visual["sha256"]
    assert visual_record["image_evidence_status"] == "present"
    assert "storage_path" not in visual_record["image_evidence"]
    text_record = by_review[text_review]
    assert text_record["evidence_basis"] == "text" and text_record["image_evidence"] is None
    assert text_record["eligible_for_text_training"] is True
    assert text_record["eligible_for_visual_training"] is False

    # La disparition des octets rend le label visuel inéligible et à réexaminer.
    (evidence_root(path) / visual["storage_path"]).unlink()
    manifest, records = dataset_records(build_dataset(connection, database_path=path))
    by_review = {record["review_id"]: record for record in records}
    assert manifest["visual_eligible_count"] == 0 and manifest["needs_reexamination_count"] == 1
    assert by_review[visual_review]["needs_reexamination"] is True
    assert by_review[visual_review]["image_evidence_status"] == "missing"
    assert by_review[visual_review]["eligible_for_visual_training"] is False
    assert "image_evidence_missing" in by_review[visual_review]["visual_exclusion_reasons"]
    assert by_review[text_review]["eligible_for_text_training"] is True  # règles texte inchangées


def test_restore_after_logical_delete_reactivates_same_record(database: tuple[sqlite3.Connection, Path]) -> None:
    connection, path = database
    item_id = add_item(connection)
    record = store_image_evidence(connection, path, png_bytes(), purpose="benchmark", listing_id=item_id)
    connection.commit()
    delete_image_evidence(connection, path, record["id"])
    connection.commit()
    assert evidence_file_status(connection, path, record["id"]) == "deleted"

    reactivated = store_image_evidence(connection, path, png_bytes(), purpose="confirmation", listing_id=item_id)
    connection.commit()
    assert reactivated["id"] == record["id"], "l'identité de la preuve est conservée"
    assert reactivated["deleted_at"] is None and reactivated["purpose"] == "confirmation"
    assert evidence_file_status(connection, path, record["id"]) == "present"


def test_backup_fails_when_sidecar_evidence_is_degraded(database: tuple[sqlite3.Connection, Path], tmp_path: Path) -> None:
    connection, path = database
    item_id = add_item(connection)
    record = store_image_evidence(connection, path, png_bytes(), purpose="benchmark", listing_id=item_id)
    connection.commit()

    (evidence_root(path) / record["storage_path"]).write_bytes(b"octets alteres")
    with pytest.raises(RuntimeError, match="Intégrité des preuves"):
        create_backup(path, tmp_path / "degraded.sqlite")
    assert not (tmp_path / "degraded.sqlite").exists()
    assert not (tmp_path / "degraded.sqlite.evidence").exists()

    (evidence_root(path) / record["storage_path"]).unlink()
    with pytest.raises(RuntimeError, match="Intégrité des preuves"):
        create_backup(path, tmp_path / "missing.sqlite")
    assert not (tmp_path / "missing.sqlite").exists()


def test_restore_refuses_backup_with_degraded_sidecar(database: tuple[sqlite3.Connection, Path], tmp_path: Path) -> None:
    connection, path = database
    item_id = add_item(connection)
    store_image_evidence(connection, path, png_bytes(), purpose="benchmark", listing_id=item_id)
    connection.commit()
    backup = create_backup(path, tmp_path / "ok.sqlite")
    target = tmp_path / "restored.db"
    sidecar_file = next(Path(f"{backup}.evidence").rglob("*.png"))
    sidecar_file.write_bytes(b"altere")
    with pytest.raises(RuntimeError, match="Restauration refusée"):
        restore_backup(target, backup)
    assert not target.exists()


def test_cli_verify_and_purge_evidence(database: tuple[sqlite3.Connection, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    from app.cli import main

    connection, path = database
    item_id = add_item(connection)
    attached = store_image_evidence(connection, path, png_bytes((1, 1, 1)), purpose="annotation", listing_id=item_id)
    orphan = store_image_evidence(connection, path, png_bytes((2, 2, 2)), purpose="benchmark")
    connection.commit()

    monkeypatch.setenv("POKEMON_DATABASE_PATH", str(path))
    assert main(["verify-evidence"]) == 0
    assert main(["purge-evidence"]) == 0
    out = capsys.readouterr().out
    assert "Preuves orphelines purgées : 1" in out
    connection.commit()
    row = connection.execute("SELECT deleted_at FROM listing_image_evidence WHERE id=?", (orphan["id"],)).fetchone()
    assert row["deleted_at"] is not None, "la preuve orpheline est marquée supprimée"
    assert connection.execute("SELECT deleted_at FROM listing_image_evidence WHERE id=?", (attached["id"],)).fetchone()["deleted_at"] is None

    (evidence_root(path) / attached["storage_path"]).unlink()
    assert main(["verify-evidence"]) == 1
    assert "Fichiers manquants" in capsys.readouterr().out


def test_web_route_persists_visual_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """La route web doit persister la preuve même sans commit de l'appelant."""
    from fastapi.testclient import TestClient

    from app.web import app

    database = tmp_path / "web-evidence.sqlite"
    with connect(database) as connection:
        apply_migrations(connection)
        connection.execute("INSERT INTO sources (name, kind) VALUES ('demo', 'demo')")
        connection.execute("INSERT INTO import_batches (source_id, input_checksum) VALUES (1, 'batch-web')")
        connection.execute(
            """INSERT INTO catalog_items (source_id, import_batch_id, external_id, name,
            original_title, set_name, price_cents, raw_data)
            VALUES (1, 1, 'web-1', 'Dracaufeu', 'Dracaufeu 4/102', 'Set de Base', 100, '{}')"""
        )
        connection.commit()
    monkeypatch.setenv("POKEMON_DATABASE_PATH", str(database))
    with TestClient(app) as client:
        response = client.post(
            "/catalog/1/preuves-visuelles",
            files={"file": ("photo.png", png_bytes(), "image/png")},
            data={"purpose": "confirmation"},
            follow_redirects=False,
        )
        assert response.status_code == 303
    with connect(database) as connection:
        row = connection.execute(
            "SELECT listing_id, purpose FROM listing_image_evidence"
        ).fetchone()
        assert row is not None, "la preuve POSTée via l'interface doit survivre à la fermeture de la connexion"
        assert row["listing_id"] == 1 and row["purpose"] == "confirmation"
