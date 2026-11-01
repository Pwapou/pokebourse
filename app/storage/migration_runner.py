import sqlite3
import re
from importlib import resources

MIGRATIONS_PACKAGE = "app.storage.migrations"


def _apply_table_rebuild(connection: sqlite3.Connection, script: str) -> None:
    """Reconstruit des tables sans casser leurs références ni valider un état invalide.

    Les cascades SQLite lors de DROP TABLE détruiraient les références entrantes.
    Leur contrôle est suspendu sur cette seule connexion de migration, puis
    vérifié avant le COMMIT, et réactivé même si la migration est annulée.
    Le SQL conserve son BEGIN IMMEDIATE et son COMMIT final obligatoire.
    """
    pending_script, removed = re.subn(r"\bCOMMIT\s*;\s*$", "", script, flags=re.IGNORECASE)
    if removed != 1 or not script.lstrip().upper().startswith("BEGIN IMMEDIATE;"):
        raise sqlite3.OperationalError("Une reconstruction exige BEGIN IMMEDIATE et un COMMIT final.")
    # executescript() effectue aussi ce commit implicite dans le chemin historique.
    connection.commit()
    connection.execute("PRAGMA foreign_keys = OFF")
    connection.execute("PRAGMA legacy_alter_table = ON")
    try:
        connection.executescript(pending_script)
        if not connection.in_transaction:
            raise sqlite3.OperationalError("La migration doit rester transactionnelle jusqu'au contrôle des clés.")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise sqlite3.IntegrityError("La reconstruction créerait des références invalides.")
        connection.commit()
    finally:
        if connection.in_transaction:
            connection.rollback()
        connection.execute("PRAGMA legacy_alter_table = OFF")
        connection.execute("PRAGMA foreign_keys = ON")


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
            if re.search(r"\bDROP\s+TABLE\b", script, flags=re.IGNORECASE):
                _apply_table_rebuild(connection, script)
            else:
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
