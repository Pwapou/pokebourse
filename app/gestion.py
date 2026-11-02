"""Index de gestion avancée : états réels, en lecture seule.

Cette vue regroupe les points d'entrée des modules secondaires (vendeurs,
veilles, imports, TCGdex, annotations, agents, sauvegardes) avec uniquement
des indicateurs réellement disponibles en base. Aucune donnée n'est inventée :
un état inconnu reste affiché comme tel.
"""

import sqlite3
from pathlib import Path
from typing import Any

from app.backups import list_backups


def _count(connection: sqlite3.Connection, sql: str, params: tuple = ()) -> int:
    return int(connection.execute(sql, params).fetchone()[0])


def gestion_page_data(
    connection: sqlite3.Connection, database_path: Path
) -> dict[str, Any]:
    """Indicateurs réels de chaque module avancé, pour la page d'index."""
    latest_backup: dict[str, Any] | None = None
    backups = list_backups(database_path)
    if backups:
        latest_backup = backups[0]

    pilot = connection.execute(
        "SELECT id, target_size, created_at FROM annotation_pilots ORDER BY id DESC LIMIT 1"
    ).fetchone()

    return {
        "vendeurs_count": _count(connection, "SELECT COUNT(*) FROM seller_profiles"),
        "veilles_total": _count(connection, "SELECT COUNT(*) FROM listing_watches"),
        "veilles_actives": _count(
            connection, "SELECT COUNT(*) FROM listing_watches WHERE is_active = 1"
        ),
        "imports_total": _count(connection, "SELECT COUNT(*) FROM import_batches"),
        "imports_echoues": _count(
            connection,
            "SELECT COUNT(*) FROM import_batches WHERE status != 'completed'",
        ),
        "import_failures": _count(connection, "SELECT COUNT(*) FROM import_failures"),
        "tcgdex_sets": _count(connection, "SELECT COUNT(*) FROM pokemon_reference_sets"),
        "tcgdex_cartes": _count(
            connection, "SELECT COUNT(*) FROM pokemon_reference_cards"
        ),
        "tcgdex_jobs_en_cours": _count(
            connection,
            "SELECT COUNT(*) FROM tcgdex_sync_jobs WHERE status IN ('queued', 'running')",
        ),
        "tcgdex_jobs_en_erreur": _count(
            connection, "SELECT COUNT(*) FROM tcgdex_sync_jobs WHERE status = 'failed'"
        ),
        "annotations_pilot": dict(pilot) if pilot is not None else None,
        "annotations_total": (
            _count(
                connection,
                "SELECT COUNT(*) FROM annotation_pilot_items WHERE pilot_id = ?",
                (pilot["id"],),
            )
            if pilot is not None
            else 0
        ),
        "annotations_premiere_lecture": (
            _count(
                connection,
                "SELECT COUNT(*) FROM annotation_pilot_items WHERE pilot_id = ? AND first_review_id IS NOT NULL",
                (pilot["id"],),
            )
            if pilot is not None
            else 0
        ),
        "agents_total": _count(connection, "SELECT COUNT(*) FROM supervision_agents"),
        "incidents_actifs": _count(
            connection,
            "SELECT COUNT(*) FROM supervision_incidents WHERE is_active = 1",
        ),
        "derniere_sauvegarde": latest_backup,
    }
