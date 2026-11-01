import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from app.storage.database import connect
from app.storage.migration_runner import apply_migrations, check_database

BACKUP_SUFFIX = ".sqlite"


def backups_directory(database_path: Path) -> Path:
    return database_path.parent / "backups"


def create_backup(database_path: Path, output_path: Path | None = None) -> Path:
    if not database_path.is_file():
        raise RuntimeError(f"Base introuvable : {database_path}")
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
    destination = output_path or backups_directory(database_path) / f"pokebourse-{timestamp}{BACKUP_SUFFIX}"
    if destination.resolve() == database_path.resolve():
        raise RuntimeError("La destination ne peut pas être la base courante.")
    if destination.exists():
        raise RuntimeError(f"La sauvegarde existe déjà : {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with connect(database_path) as source:
            integrity = source.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise RuntimeError(f"Intégrité SQLite invalide : {integrity}")
            with sqlite3.connect(destination) as target:
                source.backup(target)
                target.execute("PRAGMA journal_mode = DELETE")
        verify_backup(destination)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return destination


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
    database_path.parent.mkdir(parents=True, exist_ok=True)
    safety_backup = (
        create_backup(database_path) if database_path.exists() else None
    )
    temporary_path = database_path.with_name(f".restore-{datetime.now(UTC):%Y%m%d-%H%M%S-%f}.sqlite")
    try:
        with sqlite3.connect(backup_path) as source, sqlite3.connect(temporary_path) as target:
            source.backup(target)
        with connect(temporary_path) as connection:
            apply_migrations(connection)
            check_database(connection)
        temporary_path.replace(database_path)
        for suffix in ("-wal", "-shm", "-journal"):
            Path(f"{database_path}{suffix}").unlink(missing_ok=True)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    return safety_backup
