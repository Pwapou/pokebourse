"""Persistance SQLite des profils vendeur et de la file d'enrichissement."""

import sqlite3
from datetime import UTC, datetime
from typing import Any

from app.sellers.models import SellerProfile


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def enqueue_seller(
    connection: sqlite3.Connection,
    *,
    platform: str,
    seller_external_id: str,
    login: str | None = None,
) -> bool:
    """Ajoute un vendeur à la file ; renvoie False s'il était déjà connu."""

    current = utc_now()
    with connection:
        cursor = connection.execute(
            """
            INSERT INTO seller_enrichment_queue (
                platform, seller_external_id, login, status, created_at, updated_at
            ) VALUES (?, ?, ?, 'pending', ?, ?)
            ON CONFLICT (platform, seller_external_id) DO NOTHING
            """,
            (platform, seller_external_id, login, current, current),
        )
    return cursor.rowcount > 0


def upsert_profile(
    connection: sqlite3.Connection, profile: SellerProfile
) -> int:
    """Crée ou actualise un profil vendeur ; renvoie son identifiant interne."""

    current = utc_now()
    values = (
        profile.login,
        profile.feedback_count,
        profile.positive_count,
        profile.neutral_count,
        profile.negative_count,
        profile.reputation_bps,
        profile.item_count,
        profile.response_rate_percent,
        profile.account_type,
        1 if profile.is_banned else 0,
        profile.profile_url,
        profile.fetched_at,
        1 if profile.is_favorite else 0,
        profile.user_notes,
        current,
        current,
    )
    with connection:
        connection.execute(
            """
            INSERT INTO seller_profiles (
                platform, seller_external_id, login, feedback_count,
                positive_count, neutral_count, negative_count, reputation_bps,
                item_count, response_rate_percent, account_type, is_banned,
                profile_url, fetched_at, is_favorite, user_notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (platform, seller_external_id) DO UPDATE SET
                login = excluded.login,
                feedback_count = excluded.feedback_count,
                positive_count = excluded.positive_count,
                neutral_count = excluded.neutral_count,
                negative_count = excluded.negative_count,
                reputation_bps = excluded.reputation_bps,
                item_count = excluded.item_count,
                response_rate_percent = excluded.response_rate_percent,
                account_type = excluded.account_type,
                is_banned = excluded.is_banned,
                profile_url = excluded.profile_url,
                fetched_at = excluded.fetched_at,
                is_favorite = CASE WHEN excluded.is_favorite = 1 THEN 1 ELSE seller_profiles.is_favorite END,
                user_notes = COALESCE(excluded.user_notes, seller_profiles.user_notes),
                updated_at = excluded.updated_at
            """,
            (profile.platform, profile.seller_external_id, *values),
        )
    row = connection.execute(
        """
        SELECT id FROM seller_profiles
        WHERE platform = ? AND seller_external_id = ?
        """,
        (profile.platform, profile.seller_external_id),
    ).fetchone()
    return int(row["id"])


def pending_sellers(
    connection: sqlite3.Connection, *, limit: int
) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in connection.execute(
            """
            SELECT id, platform, seller_external_id, login, attempts
            FROM seller_enrichment_queue
            WHERE status = 'pending'
            ORDER BY id
            LIMIT ?
            """,
            (max(1, limit),),
        ).fetchall()
    ]


def mark_done(connection: sqlite3.Connection, queue_id: int) -> None:
    with connection:
        connection.execute(
            """
            UPDATE seller_enrichment_queue
            SET status = 'done', last_error = NULL, updated_at = ?
            WHERE id = ?
            """,
            (utc_now(), queue_id),
        )


def mark_failed(
    connection: sqlite3.Connection, queue_id: int, message: str
) -> None:
    with connection:
        connection.execute(
            """
            UPDATE seller_enrichment_queue
            SET status = 'failed', attempts = attempts + 1,
                last_error = ?, updated_at = ?
            WHERE id = ?
            """,
            (message[:500], utc_now(), queue_id),
        )


def find_profile_id(
    connection: sqlite3.Connection, *, platform: str, seller_external_id: str
) -> int | None:
    row = connection.execute(
        """
        SELECT id FROM seller_profiles
        WHERE platform = ? AND seller_external_id = ?
        """,
        (platform, seller_external_id),
    ).fetchone()
    return int(row["id"]) if row is not None else None


def get_profile(
    connection: sqlite3.Connection, profile_id: int
) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT * FROM seller_profiles WHERE id = ?", (profile_id,)
    ).fetchone()
    return dict(row) if row is not None else None


def link_catalog_item(
    connection: sqlite3.Connection, *, item_id: int, profile_id: int
) -> None:
    with connection:
        connection.execute(
            "UPDATE catalog_items SET seller_profile_id = ? WHERE id = ?",
            (profile_id, item_id),
        )


def set_favorite(
    connection: sqlite3.Connection, profile_id: int, is_favorite: bool
) -> None:
    current = utc_now()
    with connection:
        connection.execute(
            "UPDATE seller_profiles SET is_favorite = ?, updated_at = ? WHERE id = ?",
            (1 if is_favorite else 0, current, profile_id),
        )


def set_user_notes(
    connection: sqlite3.Connection, profile_id: int, notes: str | None
) -> None:
    current = utc_now()
    cleaned = notes.strip() if notes and notes.strip() else None
    with connection:
        connection.execute(
            "UPDATE seller_profiles SET user_notes = ?, updated_at = ? WHERE id = ?",
            (cleaned, current, profile_id),
        )


def record_purchase(
    connection: sqlite3.Connection,
    *,
    catalog_item_id: int | None = None,
    seller_profile_id: int | None = None,
    seller_name: str,
    card_name: str,
    set_name: str | None = None,
    card_number: str | None = None,
    condition: str | None = None,
    price_paid_cents: int,
    shipping_paid_cents: int = 0,
    currency: str = "EUR",
    platform: str | None = None,
    status: str = "recu",
    notes: str | None = None,
    purchased_at: str | None = None,
) -> int:
    current = utc_now()
    p_date = purchased_at or current
    with connection:
        cursor = connection.execute(
            """
            INSERT INTO purchases (
                catalog_item_id, seller_profile_id, seller_name, card_name,
                set_name, card_number, condition, price_paid_cents, shipping_paid_cents,
                currency, platform, status, notes, purchased_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                catalog_item_id,
                seller_profile_id,
                seller_name,
                card_name,
                set_name,
                card_number,
                condition,
                price_paid_cents,
                shipping_paid_cents,
                currency,
                platform,
                status,
                notes,
                p_date,
                current,
                current,
            ),
        )
    return int(cursor.lastrowid)


def list_purchases(
    connection: sqlite3.Connection,
    *,
    seller_profile_id: int | None = None,
    limit: int | None = 100,
) -> list[dict[str, Any]]:
    query = "SELECT * FROM purchases"
    params: list[Any] = []
    if seller_profile_id is not None:
        query += " WHERE seller_profile_id = ?"
        params.append(seller_profile_id)
    query += " ORDER BY purchased_at DESC, id DESC"
    if limit is not None:
        query += " LIMIT ?"
        params.append(max(1, limit))
    rows = connection.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def update_purchase_status(
    connection: sqlite3.Connection, purchase_id: int, *, status: str,
    sale_price_cents: int | None,
) -> bool:
    """Update the purchase lifecycle and recorded sale price, if it exists."""
    if status not in ("commande", "recu", "en_vente", "vendu"):
        raise ValueError("Statut d'achat invalide.")
    if sale_price_cents is not None and sale_price_cents < 0:
        raise ValueError("Le prix de vente doit être positif ou nul.")
    with connection:
        cursor = connection.execute(
            "UPDATE purchases SET status = ?, sale_price_cents = ?, updated_at = ? WHERE id = ?",
            (status, sale_price_cents, utc_now(), purchase_id),
        )
    return cursor.rowcount > 0


def list_listings_for_seller(
    connection: sqlite3.Connection, profile_id: int
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT c.*, s.name AS source_name
        FROM catalog_items c
        JOIN sources s ON s.id = c.source_id
        WHERE c.seller_profile_id = ?
        ORDER BY c.first_seen_at DESC, c.id DESC
        """,
        (profile_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def list_sellers_with_aggregates(
    connection: sqlite3.Connection,
    *,
    platform: str | None = None,
    only_favorites: bool = False,
    query: str = "",
) -> list[dict[str, Any]]:
    sql = """
        SELECT
            sp.*,
            COALESCE(ci_stats.total_listings, 0) AS total_listings,
            COALESCE(p_stats.purchases_count, 0) AS purchases_count,
            COALESCE(p_stats.total_spent_cents, 0) AS total_spent_cents
        FROM seller_profiles sp
        LEFT JOIN (
            SELECT seller_profile_id, COUNT(*) AS total_listings
            FROM catalog_items
            WHERE seller_profile_id IS NOT NULL
            GROUP BY seller_profile_id
        ) ci_stats ON ci_stats.seller_profile_id = sp.id
        LEFT JOIN (
            SELECT
                seller_profile_id,
                COUNT(*) AS purchases_count,
                SUM(price_paid_cents + shipping_paid_cents) AS total_spent_cents
            FROM purchases
            WHERE seller_profile_id IS NOT NULL
            GROUP BY seller_profile_id
        ) p_stats ON p_stats.seller_profile_id = sp.id
        WHERE 1 = 1
    """
    params: list[Any] = []
    if platform and platform in ("vinted", "leboncoin", "ebay", "wallapop"):
        sql += " AND sp.platform = ?"
        params.append(platform)
    if only_favorites:
        sql += " AND sp.is_favorite = 1"
    if query:
        sql += " AND (sp.login LIKE ? OR sp.seller_external_id LIKE ?)"
        pattern = f"%{query.strip()}%"
        params.extend([pattern, pattern])

    rows = connection.execute(sql, params).fetchall()
    return [dict(row) for row in rows]
