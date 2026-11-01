import sqlite3
from pathlib import Path

import pytest

from app.backups import (
    backup_file,
    create_backup,
    list_backups,
    restore_backup,
    verify_backup,
)
from app.catalog import import_jsonl
from app.storage.database import connect
from app.storage.migration_runner import apply_migrations, check_database

ITEM_JSONL = (
    b'{"external_id":"pika-1","name":"Pikachu","set_name":"Evolutions",'
    b'"price_cents":1290}\n'
)


def initialize(database_path: Path) -> None:
    with connect(database_path) as connection:
        apply_migrations(connection)


def seeded_database(tmp_path: Path) -> Path:
    database_path = tmp_path / "arbitrage.db"
    initialize(database_path)
    with connect(database_path) as connection:
        import_jsonl(connection, ITEM_JSONL)
    return database_path


def item_count(database_path: Path) -> int:
    with connect(database_path) as connection:
        return connection.execute(
            "SELECT COUNT(*) FROM catalog_items"
        ).fetchone()[0]


def test_create_backup_copies_database_into_backups_directory(tmp_path: Path) -> None:
    database_path = seeded_database(tmp_path)

    backup_path = create_backup(database_path)

    assert backup_path.parent == tmp_path / "backups"
    assert backup_path.name.startswith("pokebourse-")
    assert backup_path.name.endswith(".sqlite")
    assert backup_path.exists()
    with sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True) as ro_connection:
        assert ro_connection.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    assert item_count(backup_path) == 1
    backups = list_backups(database_path)
    assert [entry["name"] for entry in backups] == [backup_path.name]
    assert backups[0]["size_bytes"] == backup_path.stat().st_size
    assert backups[0]["modified_at"]


def test_create_backup_with_explicit_output_and_no_overwrite(tmp_path: Path) -> None:
    database_path = seeded_database(tmp_path)
    destination = tmp_path / "copie.sqlite"

    create_backup(database_path, destination)

    assert destination.exists()
    assert item_count(destination) == 1
    with pytest.raises(RuntimeError, match="existe déjà"):
        create_backup(database_path, destination)


def test_create_backup_rejects_invalid_destination(tmp_path: Path) -> None:
    database_path = seeded_database(tmp_path)

    with pytest.raises(RuntimeError, match="base courante"):
        create_backup(database_path, database_path)


def test_verify_backup_rejects_non_sqlite_file(tmp_path: Path) -> None:
    invalid = tmp_path / "fake.sqlite"
    invalid.write_bytes(b"ceci n'est pas une base sqlite")

    with pytest.raises(RuntimeError, match="pas une base SQLite valide"):
        verify_backup(invalid)


def test_create_backup_rejects_corrupt_source(tmp_path: Path) -> None:
    corrupt = tmp_path / "corrupt.db"
    corrupt.write_bytes(b"garbage")

    with pytest.raises((RuntimeError, sqlite3.Error)):
        create_backup(corrupt)


def test_restore_roundtrip_creates_safety_backup(tmp_path: Path) -> None:
    database_path = seeded_database(tmp_path)
    backup_path = create_backup(database_path)

    with connect(database_path) as connection:
        connection.execute("DELETE FROM catalog_items")
        connection.commit()
    assert item_count(database_path) == 0

    safety_backup = restore_backup(database_path, backup_path)

    assert item_count(database_path) == 1
    assert safety_backup is not None
    assert safety_backup.exists()
    assert safety_backup.name != backup_path.name
    with connect(database_path) as connection:
        check_database(connection)


def test_restore_reapplies_missing_migrations(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    initialize(source)
    with connect(source) as connection:
        connection.execute("DROP TABLE import_failures")
        connection.execute(
            "DELETE FROM schema_migrations WHERE version = '0004_create_import_failures.sql'"
        )
        connection.commit()
    backup_path = tmp_path / "ancienne.sqlite"
    with connect(source) as source_connection, sqlite3.connect(backup_path) as target:
        source_connection.backup(target)

    target_database = tmp_path / "restored" / "live.db"
    restore_backup(target_database, backup_path)

    with connect(target_database) as connection:
        check_database(connection)
        failure_table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'import_failures'"
        ).fetchone()
        assert failure_table is not None


def test_backup_file_rejects_path_traversal(tmp_path: Path) -> None:
    database_path = seeded_database(tmp_path)
    create_backup(database_path)

    for malicious in ("../web.db", "..\\web.db", "/tmp/x.sqlite", ".hidden.sqlite"):
        with pytest.raises(RuntimeError, match="invalide"):
            backup_file(database_path, malicious)


def test_backup_file_verifies_integrity_and_presence(tmp_path: Path) -> None:
    database_path = seeded_database(tmp_path)

    with pytest.raises(RuntimeError, match="introuvable"):
        backup_file(database_path, "absente.sqlite")

    invalid = tmp_path / "backups" / "casse.sqlite"
    invalid.parent.mkdir(parents=True, exist_ok=True)
    invalid.write_bytes(b"pas une base")
    with pytest.raises(RuntimeError, match="pas une base SQLite valide"):
        backup_file(database_path, "casse.sqlite")


def test_list_backups_empty_directory(tmp_path: Path) -> None:
    assert list_backups(tmp_path / "absent.db") == []
