"""Échantillonnage, indépendance et traçabilité du pilote, sans réseau."""

import json
import sqlite3
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.catalog import delete_import_batch
from app.identification.annotation_pilot import (
    AnnotationAccessError, assignment, assignment_stage, pilot_dashboard, sample_pilot,
)
from app.identification.dataset import build_dataset
from app.identification.resolution import IdentificationConflictError, capture_evidence, resolve_listing
from app.identification.reviews import ReviewInput, current_revision, save_review
from app.storage.database import connect
from app.storage.migration_runner import apply_migrations, migration_files
from app.tcgdex.cache import TcgdexCache
from app.web import app


@pytest.fixture
def connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    with connect(tmp_path / "pilot.db") as connection:
        apply_migrations(connection)
        TcgdexCache(connection).seed_initial_if_empty()
        connection.commit()
        yield connection


def add_items(connection: sqlite3.Connection, count: int, status: str = "ambiguous", *, platform: str = "vinted", title: str | None = None) -> list[int]:
    """Construit une population locale de statuts initiaux contrôlés."""
    with connection:
        connection.execute("INSERT OR IGNORE INTO sources(name, kind) VALUES (?, 'api')", (platform,))
        source_id = connection.execute("SELECT id FROM sources WHERE name=?", (platform,)).fetchone()[0]
        cursor = connection.execute("INSERT INTO import_batches(source_id, input_checksum) VALUES (?, ?)",
                                    (source_id, f"batch-{connection.total_changes}"))
        batch_id = cursor.lastrowid
        ids = []
        start = connection.execute("SELECT count(*) FROM catalog_items").fetchone()[0]
        for index in range(count):
            original = title or f"Carte témoin {start + index}"
            cursor = connection.execute(
                """INSERT INTO catalog_items(source_id, import_batch_id, external_id, name,
                original_title, set_name, price_cents, raw_data, identification_status)
                VALUES (?, ?, ?, ?, ?, 'Inconnue', 100, ?, ?)""",
                (source_id, batch_id, f"item-{start + index}", original, original,
                 json.dumps({"description": "VF, texte original"}), status),
            )
            item_id = int(cursor.lastrowid)
            capture_evidence(connection, item_id)
            ids.append(item_id)
    return ids


def read(connection: sqlite3.Connection, task_id: int, operator: str, *, outcome: str = "insufficient_evidence", stage: str | None = None, text_sufficient: bool = False) -> int:
    """Enregistre une lecture selon le même contrat que le formulaire."""
    task = assignment(connection, task_id)
    stage = stage or assignment_stage(connection, task, operator)
    annotation_ids = [task["first_review_id"]] + ([task["second_review_id"]] if task["second_review_id"] else [])
    card = TcgdexCache(connection).get_card_by_tcgdex_id("base1-4")
    review = ReviewInput(
        outcome=outcome, text_sufficient=text_sufficient,
        validated_card_id=card.id if outcome == "matched" else None,
        review_kind="adjudication" if stage == "adjudication" else "annotation",
        reviewed_annotation_ids=annotation_ids if stage == "adjudication" else [],
    )
    return save_review(connection, task["listing_id"], review, expected_hash=task["input_hash"],
                       expected_revision=current_revision(connection, task["listing_id"]), operator=operator,
                       assignment_id=task_id, assignment_stage=stage)


def test_sampling_respects_quotas_probability_and_double_target(connection: sqlite3.Connection) -> None:
    for status in ("ambiguous", "unidentified", "identified", "lot"):
        add_items(connection, 200, status)
    assert sample_pilot(connection, seed="fixed-pilot") == 300
    rows = connection.execute("SELECT * FROM annotation_pilot_items").fetchall()
    assert Counter(row["initial_status"] for row in rows) == {"ambiguous": 150, "unidentified": 75, "identified": 60, "lot": 15}
    assert sum(row["requires_second"] for row in rows) == 60
    assert all(row["population_in_stratum"] == 200 for row in rows)
    assert sample_pilot(connection, seed="repeated") == 0
    assert connection.execute("SELECT count(*) FROM annotation_sampling_batches").fetchone()[0] == 1


def test_sampling_covers_platforms_and_redistributes_missing_statuses(connection: sqlite3.Connection) -> None:
    add_items(connection, 10, platform="vinted")
    add_items(connection, 10, platform="leboncoin")
    assert sample_pilot(connection, target_size=10, seed="platforms") == 10
    rows = connection.execute(
        "SELECT s.platform, i.selected_in_stratum, i.population_in_stratum FROM annotation_pilot_items i JOIN listing_identification_snapshots s ON s.id=i.snapshot_id"
    ).fetchall()
    assert Counter(row["platform"] for row in rows) == {"vinted": 5, "leboncoin": 5}
    assert all((row["selected_in_stratum"], row["population_in_stratum"]) == (5, 10) for row in rows)


def test_sampling_waves_complete_small_population_without_duplicates(connection: sqlite3.Connection) -> None:
    add_items(connection, 3)
    assert sample_pilot(connection, target_size=10, seed="wave-1") == 3
    assert sample_pilot(connection, seed="empty") == 0
    add_items(connection, 12)
    assert sample_pilot(connection, seed="wave-2") == 7
    dashboard = pilot_dashboard(connection, "reader-1")
    assert dashboard["selected"] == 10 and dashboard["second_required"] == 2
    assert dashboard["pilot"]["target_size"] == 10
    assert dashboard["batches"] == 2


def test_second_reader_must_be_distinct_and_finalization_is_separate(connection: sqlite3.Connection) -> None:
    add_items(connection, 1, title="Dracaufeu 4/102 Set de Base")
    sample_pilot(connection, target_size=1, seed="one")
    first = read(connection, 1, "reader-1", outcome="matched", text_sufficient=True)
    assert resolve_listing(connection, 1).decision_source == "automatic"
    with pytest.raises(AnnotationAccessError):
        read(connection, 1, "reader-1")
    second = read(connection, 1, "reader-2", outcome="no_catalog_match", text_sufficient=True)
    dashboard = pilot_dashboard(connection, "reader-1")
    assert dashboard["second_count"] == 1 and dashboard["identity_agreement"] == 0
    assert dashboard["text_agreement"] == 1 and dashboard["disagreements"] == 1
    assert dashboard["finalized"] == 0
    final = read(connection, 1, "reader-1", outcome="matched", text_sufficient=True)
    assert final > second > first
    assert resolve_listing(connection, 1).decision_source == "human"
    after = pilot_dashboard(connection, "reader-1")
    assert after["finalized"] == 1 and after["identity_agreement"] == 0
    assert after["diagnostics"]["correct"] == 1


def test_agreement_on_identity_and_text_are_separate(connection: sqlite3.Connection) -> None:
    add_items(connection, 1)
    sample_pilot(connection, target_size=1, seed="agreement")
    read(connection, 1, "reader-1")
    read(connection, 1, "reader-2", text_sufficient=True)
    dashboard = pilot_dashboard(connection, "reader-1")
    assert dashboard["identity_agreement"] == 1 and dashboard["text_agreement"] == 0


def test_withdrawn_final_decision_can_be_reexamined_without_losing_annotations(connection: sqlite3.Connection) -> None:
    add_items(connection, 1)
    sample_pilot(connection, target_size=1, seed="withdrawn")
    first = read(connection, 1, "reader-1")
    second = read(connection, 1, "reader-2")
    old_final = read(connection, 1, "reader-1")
    task = assignment(connection, 1)
    save_review(connection, task["listing_id"], ReviewInput(outcome="withdrawn", text_sufficient=False),
                expected_hash=task["input_hash"], expected_revision=current_revision(connection, task["listing_id"]))
    dashboard = pilot_dashboard(connection, "reader-1")
    assert dashboard["finalized"] == 0
    assert dashboard["items"][0]["stage"] == "adjudication"
    assert dashboard["items"][0]["final_revised"]
    new_final = read(connection, 1, "reader-1")
    after = assignment(connection, 1)
    assert after["final_review_id"] == new_final > old_final
    assert after["first_review_id"] == first and after["second_review_id"] == second
    assert pilot_dashboard(connection, "reader-1")["finalized"] == 1


def test_wrong_task_or_stage_rolls_back_review_and_link(connection: sqlite3.Connection) -> None:
    add_items(connection, 2)
    sample_pilot(connection, target_size=2, seed="atomic")
    read(connection, 1, "reader-1")
    with pytest.raises(IdentificationConflictError):
        read(connection, 1, "reader-2", stage="first")
    assert connection.execute("SELECT count(*) FROM listing_identification_reviews").fetchone()[0] == 1
    assert assignment(connection, 1)["second_review_id"] is None
    other = assignment(connection, 2)
    review = ReviewInput(outcome="insufficient_evidence", text_sufficient=False, review_kind="annotation")
    with pytest.raises(IdentificationConflictError):
        save_review(connection, other["listing_id"], review, expected_hash=other["input_hash"], expected_revision=0,
                    operator="reader-2", assignment_id=1, assignment_stage="second")
    assert connection.execute("SELECT count(*) FROM listing_identification_reviews").fetchone()[0] == 1


def test_changed_proofs_remove_progress_and_can_be_replaced(connection: sqlite3.Connection) -> None:
    add_items(connection, 1)
    sample_pilot(connection, target_size=1, seed="old")
    read(connection, 1, "reader-1")
    with connection:
        connection.execute("UPDATE catalog_items SET original_title='Preuves nouvelles' WHERE id=1")
        capture_evidence(connection, 1)
    dashboard = pilot_dashboard(connection, "reader-1")
    assert dashboard["first_count"] == dashboard["selected"] == 0 and dashboard["obsolete"] == 1
    with pytest.raises(AnnotationAccessError):
        read(connection, 1, "reader-2")
    assert sample_pilot(connection, seed="new") == 1
    assert pilot_dashboard(connection, "reader-2")["selected"] == 1


def test_deleting_import_preserves_sampling_audit(connection: sqlite3.Connection) -> None:
    add_items(connection, 1)
    sample_pilot(connection, target_size=1, seed="delete")
    read(connection, 1, "reader-1")
    assert delete_import_batch(connection, 1)
    dashboard = pilot_dashboard(connection, "reader-2")
    assert dashboard["selected"] == dashboard["first_count"] == 0
    assert dashboard["obsolete"] == 1
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    exported = list(map(json.loads, build_dataset(connection).decode().splitlines()))
    assert any(row["type"] == "sampling_batch" for row in exported)


def test_export_contains_exact_sampling_fractions_and_roles(connection: sqlite3.Connection) -> None:
    add_items(connection, 10)
    sample_pilot(connection, target_size=5, seed="export")
    task = connection.execute("SELECT id FROM annotation_pilot_items WHERE requires_second=1").fetchone()[0]
    read(connection, task, "first-local")
    read(connection, task, "second-local")
    rows = list(map(json.loads, build_dataset(connection).decode().splitlines()))
    assert rows[0]["schema_version"] == "identity-pilot-v2"
    batch = next(row for row in rows if row["type"] == "sampling_batch")
    assert batch["selected_count"] == 5 and batch["double_count"] == 1
    reviews = [row for row in rows if row["type"] == "review"]
    assert {row["pilot_assignment"]["role"] for row in reviews} == {"first", "second"}
    assert all(row["sampling_probability"] == 0.5 for row in reviews)
    assert all(row["pilot_assignment"]["selected_in_stratum"] == 5 for row in reviews)
    assert all(not row["eligible_for_text_training"] for row in reviews)
    assert "first-local" not in build_dataset(connection).decode()
    assert build_dataset(connection) == build_dataset(connection)


def test_migration_from_0013_is_additive_and_idempotent(tmp_path: Path) -> None:
    with connect(tmp_path / "upgrade.db") as connection:
        connection.execute("CREATE TABLE schema_migrations(version TEXT PRIMARY KEY)")
        for version, script in migration_files():
            if version < "0014":
                connection.executescript(script)
        assert apply_migrations(connection) == [version for version, _ in migration_files() if version >= "0014"]
        assert apply_migrations(connection) == []


def test_existing_pilot_and_reviews_survive_pending_migrations(tmp_path: Path) -> None:
    """Une évolution ultérieure doit conserver les liens d'un pilote déjà commencé."""
    with connect(tmp_path / "existing-pilot.db") as connection:
        apply_migrations(connection)
        TcgdexCache(connection).seed_initial_if_empty()
        connection.commit()
        add_items(connection, 1)
        sample_pilot(connection, target_size=1, seed="before-upgrade")
        review_id = read(connection, 1, "reader-1")
        before = assignment(connection, 1)
        # Préparer l'état historique sans invoquer le code courant sur un schéma
        # ancien : les nouvelles colonnes n'existaient pas dans ces snapshots.
        for table, columns in (("listing_identity_evidence", ("observations_json", "pipeline_version", "observations_explicit")),
                               ("listing_identification_snapshots", ("observations_json", "pipeline_version"))):
            for column in columns:
                connection.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
        connection.execute("DELETE FROM schema_migrations WHERE version='0022_identification_observations.sql'")
        connection.commit()
        apply_migrations(connection)
        after = assignment(connection, 1)
        assert after["snapshot_id"] == after["current_snapshot_id"] == before["snapshot_id"]
        assert after["first_review_id"] == review_id
        assert pilot_dashboard(connection, "reader-2")["first_count"] == 1
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_queue_web_flow_does_not_reveal_first_opinion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database = tmp_path / "web.db"
    monkeypatch.setenv("POKEMON_DATABASE_PATH", str(database))
    with TestClient(app) as client:
        assert "Le pilote n’a pas encore commencé" in client.get("/annotations").text
        with connect(database) as connection:
            add_items(connection, 1, title="Dracaufeu 4/102 Set de Base")
        assert client.post("/annotations/sample").status_code == 200
        page = client.get("/annotations/items/1?q=base1-4")
        assert page.status_code == 200 and "Première lecture indépendante" in page.text
        with connect(database) as connection:
            task = assignment(connection, 1)
        data = {"evidence_hash": task["input_hash"], "revision": 0,
                "outcome": "no_catalog_match", "review_kind": "annotation", "text_sufficient": "true",
                "assignment_id": 1, "assignment_stage": "first", "comment": "FIRST-SECRET"}
        assert client.post("/catalog/1/review", data=data).status_code == 200
        assert client.get("/annotations/items/1").status_code == 403
        app.state.settings = app.state.settings.model_copy(update={"review_operator": "reader-2"})
        second = client.get("/annotations/items/1?blind=false")
        assert second.status_code == 200
        assert "premier avis reste masqué" in second.text
        assert "FIRST-SECRET" not in second.text and "Historique des lectures" not in second.text
        assert 'name="blind"' not in second.text and "Afficher l’historique" not in second.text
        assert 'value="adjudication"' not in second.text
        data["assignment_stage"] = "second"
        assert client.post("/catalog/1/review", data=data).status_code == 200
        final_page = client.get("/annotations/items/1")
        assert "Lectures à valider" in final_page.text
        data.update(review_kind="adjudication", assignment_stage="adjudication", annotation_ids="1,2")
        assert client.post("/catalog/1/review", data=data).status_code == 200
        with connect(database) as connection:
            assert pilot_dashboard(connection, "reader-2")["finalized"] == 1
        assert client.get("/annotations/items/999").status_code == 404
