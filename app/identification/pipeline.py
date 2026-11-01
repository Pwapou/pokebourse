"""Point d'entrée commun, strictement local pendant l'ingestion."""

import sqlite3

from app.identification.resolution import Resolution, apply_resolution, resolve_listing


def resolve_and_apply(connection: sqlite3.Connection, item_id: int, *, auto_enrich: bool = False) -> Resolution:
    resolution = resolve_listing(connection, item_id)
    apply_resolution(connection, item_id, resolution)
    if auto_enrich and resolution.result.status in ("unidentified", "ambiguous") and resolution.decision_source != "human":
        features = resolution.result.features
        criteria = {
            "name": features.name,
            "local_id": features.local_id,
            "set_name": features.set_name,
        }
        try:
            from app.identification.research import enqueue_search
            enqueue_search(connection, item_id, criteria)
        except ValueError:
            # Une annonce sans critère utile reste valide et consultable.
            pass
    return resolution
