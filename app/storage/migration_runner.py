import sqlite3
from importlib import resources

MIGRATIONS_PACKAGE = "app.storage.migrations"


def migration_files() -> list[tuple[str, str]]:
    directory = resources.files(MIGRATIONS_PACKAGE)
    return [
        (item.name, item.read_text(encoding="utf-8"))
        for item in sorted(directory.iterdir(), key=lambda entry: entry.name)
        if item.is_file() and item.name.endswith(".sql")
    ]


def apply_migrations(connection: sqlite3.Connection) -> list[str]:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        )
        """
    )
    applied = {
        row["version"]
        for row in connection.execute("SELECT version FROM schema_migrations")
    }
    newly_applied: list[str] = []
    for version, script in migration_files():
        if version in applied:
            continue
        try:
            connection.executescript(script)
        except sqlite3.Error as error:
            connection.rollback()
            raise RuntimeError(f"Échec de la migration {version}") from error
        newly_applied.append(version)
    return newly_applied


def check_database(connection: sqlite3.Connection) -> None:
    integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        raise RuntimeError(f"Intégrité SQLite invalide : {integrity}")

    migration_table = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
    ).fetchone()
    if migration_table is None:
        raise RuntimeError("Base non initialisée : exécutez la commande migrate")

    applied = {
        row["version"]
        for row in connection.execute("SELECT version FROM schema_migrations")
    }
    pending = [version for version, _ in migration_files() if version not in applied]
    if pending:
        raise RuntimeError(f"Migrations en attente : {', '.join(pending)}")
