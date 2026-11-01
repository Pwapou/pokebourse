"""Persistance du radar, dans la transaction de l'appelant."""

import sqlite3
from typing import Literal


def record_observation(
    connection: sqlite3.Connection,
    listing_id: int,
    *,
    price_cents: int,
    shipping_cents: int | None,
    currency: str,
    available: int | None,
    observed_at: str,
    origin: Literal["collecteur", "import", "extension"],
) -> None:
    """Ajoute uniquement un état économique nouveau et son événement associé."""
    previous = connection.execute(
        "SELECT price_cents, shipping_cents, currency, available FROM listing_observations "
        "WHERE listing_id = ? ORDER BY id DESC LIMIT 1", (listing_id,)
    ).fetchone()
    current = (price_cents, shipping_cents, currency, available)
    if previous is not None and tuple(previous) == current:
        return
    cursor = connection.execute(
        "INSERT INTO listing_observations "
        "(listing_id, price_cents, shipping_cents, currency, available, observed_at, origin) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (listing_id, *current, observed_at, origin),
    )
    kind = "creation" if previous is None else (
        "baisse_prix" if previous[2] == currency and price_cents < previous[0] else "changement"
    )
    connection.execute(
        "INSERT INTO listing_events (listing_id, observation_id, kind, created_at) VALUES (?, ?, ?, ?)",
        (listing_id, cursor.lastrowid, kind, observed_at),
    )


def set_decision(connection: sqlite3.Connection, listing_id: int, state: str | None, reason: str | None = None) -> None:
    """Enregistre une décision ou rétablit l'annonce dans les nouvelles."""
    if state is None:
        connection.execute("DELETE FROM listing_decisions WHERE listing_id = ?", (listing_id,))
    elif state in {"a_examiner", "ecartee"}:
        connection.execute(
            "INSERT INTO listing_decisions (listing_id, state, reason) VALUES (?, ?, ?) "
            "ON CONFLICT(listing_id) DO UPDATE SET state=excluded.state, reason=excluded.reason, "
            "updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')", (listing_id, state, reason)
        )
    else:
        raise ValueError("Décision inconnue")
