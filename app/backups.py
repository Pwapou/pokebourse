import os
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from app.storage.database import connect
from app.storage.migration_runner import apply_migrations, check_database

BACKUP_SUFFIX = ".sqlite"
EVIDENCE_DIRECTORY_NAME = "evidence"


def backups_directory(database_path: Path) -> Path:
    return database_path.parent / "backups"


def evidence_directory(database_path: Path) -> Path:
    """Espace de preuves visuelles conservé avec la base (T04)."""
    return database_path.parent / EVIDENCE_DIRECTORY_NAME


def create_backup(database_path: Path, output_path: Path | None = None, *, include_evidence: bool = True) -> Path:
    if not database_path.is_file():
        raise RuntimeError(f"Base introuvable : {database_path}")
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
    destination = output_path or backups_directory(database_path) / f"pokebourse-{timestamp}{BACKUP_SUFFIX}"
    if destination.resolve() == database_path.resolve():
        raise RuntimeError("La destination ne peut pas être la base courante.")
    if destination.exists():
        raise RuntimeError(f"La sauvegarde existe déjà : {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    evidence_destination = destination.with_name(destination.name + f".{EVIDENCE_DIRECTORY_NAME}")
    try:
        with connect(database_path) as source:
            integrity = source.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise RuntimeError(f"Intégrité SQLite invalide : {integrity}")
            with sqlite3.connect(destination) as target:
                source.backup(target)
                target.execute("PRAGMA journal_mode = DELETE")
        verify_backup(destination)
        source_evidence = evidence_directory(database_path)
        if include_evidence and source_evidence.is_dir():
            shutil.copytree(source_evidence, evidence_destination)
            with sqlite3.connect(f"file:{destination}?mode=ro", uri=True) as connection:
                report = _verify_sidecar(connection, evidence_destination)
            if not report["ok"]:
                raise RuntimeError(
                    "Intégrité des preuves visuelles invalide : "
                    f"manquantes={report['missing']} altérées={report['corrupted']}"
                )
    except Exception:
        destination.unlink(missing_ok=True)
        shutil.rmtree(evidence_destination, ignore_errors=True)
        raise
    return destination


def _verify_sidecar(connection: sqlite3.Connection, evidence_dir: Path) -> dict:
    """Contrôle les octets du sidecar de preuves contre les empreintes SQLite."""
    from app.identification.evidence_store import verify_evidence_store

    connection.row_factory = sqlite3.Row
    return verify_evidence_store(connection, evidence_dir)


def verify_backup(backup_path: Path) -> None:
    if not backup_path.is_file():
        raise RuntimeError(f"Sauvegarde introuvable : {backup_path}")
    try:
        with sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True) as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    except sqlite3.Error as error:
        raise RuntimeError("Le fichier n’est pas une base SQLite valide.") from error
    if integrity != "ok":
        raise RuntimeError(f"Intégrité de la sauvegarde invalide : {integrity}")


def list_backups(database_path: Path) -> list[dict[str, str | int]]:
    directory = backups_directory(database_path)
    if not directory.exists():
        return []
    backups = []
    for path in sorted(directory.glob(f"*{BACKUP_SUFFIX}"), reverse=True):
        stat = path.stat()
        backups.append(
            {
                "name": path.name,
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, UTC).strftime(
                    "%Y-%m-%dT%H:%M:%S.%fZ"
                ),
            }
        )
    return backups


def backup_file(database_path: Path, filename: str) -> Path:
    directory = backups_directory(database_path).resolve()
    if (
        Path(filename).name != filename
        or not filename.endswith(BACKUP_SUFFIX)
        or "/" in filename
        or "\\" in filename
        or filename.startswith(".")
    ):
        raise RuntimeError("Nom de sauvegarde invalide.")
    path = (directory / filename).resolve()
    if path.parent != directory:
        raise RuntimeError("Nom de sauvegarde invalide.")
    verify_backup(path)
    return path


def restore_backup(database_path: Path, backup_path: Path) -> Path | None:
    verify_backup(backup_path)
    evidence_sidecar = backup_path.with_name(backup_path.name + f".{EVIDENCE_DIRECTORY_NAME}")
    if evidence_sidecar.is_dir():
        with sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True) as connection:
            report = _verify_sidecar(connection, evidence_sidecar)
        if not report["ok"]:
            raise RuntimeError(
                "Restauration refusée : intégrité des preuves visuelles de la "
                f"sauvegarde invalide (manquantes={report['missing']} "
                f"altérées={report['corrupted']})."
            )
    database_path.parent.mkdir(parents=True, exist_ok=True)
    safety_backup = (
        create_backup(database_path) if database_path.exists() else None
    )
    temporary_path = database_path.with_name(f".restore-{datetime.now(UTC):%Y%m%d-%H%M%S-%f}.sqlite")
    temporary_evidence = database_path.parent / f".restore-{datetime.now(UTC):%Y%m%d-%H%M%S-%f}.{EVIDENCE_DIRECTORY_NAME}"
    archived_evidence: Path | None = None
    try:
        with sqlite3.connect(backup_path) as source, sqlite3.connect(temporary_path) as target:
            source.backup(target)
        with connect(temporary_path) as connection:
            apply_migrations(connection)
            check_database(connection)
        temporary_path.replace(database_path)
        for suffix in ("-wal", "-shm", "-journal"):
            Path(f"{database_path}{suffix}").unlink(missing_ok=True)
        if evidence_sidecar.is_dir():
            shutil.copytree(evidence_sidecar, temporary_evidence)
            target_evidence = evidence_directory(database_path)
            if target_evidence.exists():
                archived_evidence = target_evidence.with_name(
                    f".pre-restore-{datetime.now(UTC):%Y%m%d-%H%M%S-%f}.{EVIDENCE_DIRECTORY_NAME}"
                )
                os.replace(target_evidence, archived_evidence)
            os.replace(temporary_evidence, target_evidence)
            # L'ancien espace est intégralement contenu dans la sauvegarde de
            # sécurité : son archive temporaire est supprimée après succès.
            if archived_evidence is not None:
                shutil.rmtree(archived_evidence, ignore_errors=True)
                archived_evidence = None
    except Exception:
        temporary_path.unlink(missing_ok=True)
        shutil.rmtree(temporary_evidence, ignore_errors=True)
        if archived_evidence is not None and not evidence_directory(database_path).exists():
            os.replace(archived_evidence, evidence_directory(database_path))
        raise
    return safety_backup
