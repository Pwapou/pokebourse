"""Sélection et ordonnancement des meilleures affaires pour le module Tendances (Lot 3)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any

from app.cardmarket import daily as cardmarket_daily
from app.profitability import (
    build_card_key,
    build_market_index,
    evaluate_listing,
    find_price_comparables,
    get_active_fee_profile,
)
from app.trends.models import BestOpportunityItem, OpportunitiesPage


def _latest_catalog_comparable_observation(
    connection: sqlite3.Connection, item: dict[str, Any]
) -> str | None:
    """Date la plus récente des annonces composant réellement la médiane stricte."""
    identity = {
        key: item.get(key)
        for key in (
            "name", "set_name", "card_number", "language", "condition", "currency",
            "variant", "edition", "grading_company", "grade",
        )
    }
    strict_key = build_card_key(**identity)
    rows = connection.execute(
        """
        SELECT id, name, set_name, card_number, language, condition, currency,
               variant, edition, grading_company, grade, last_seen_at, imported_at
        FROM catalog_items
        WHERE id != ? AND currency = ? AND condition IS NOT NULL AND condition != ''
        """,
        (item["id"], item["currency"]),
    ).fetchall()
    dates = [
        row["last_seen_at"] or row["imported_at"]
        for row in rows
        if build_card_key(**{key: row[key] for key in identity}) == strict_key
        and (row["last_seen_at"] or row["imported_at"])
    ]
    return max(dates) if dates else None


def _parse_iso_datetime(value: Any) -> datetime | None:
    """Parse une date ISO en objet datetime UTC."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        # Essayer format de date courte 'YYYY-MM-DD'
        try:
            dt = datetime.strptime(str(value).strip(), "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def get_best_opportunities(
    connection: sqlite3.Connection,
    *,
    now: datetime | None = None,
    max_quote_age_days: int = 30,
    set_name: str = "",
    rarity: str = "",
    language: str = "",
    limit: int = 20,
    offset: int = 0,
) -> OpportunitiesPage:
    """Sélectionne et classe les meilleures opportunités selon le moteur de rentabilité.

    Règles absolues :
    - réutilise evaluate_listing, get_active_fee_profile et find_price_comparables ;
    - aucun recalcul de frais, gain net, ROI ou verdict dans ce service ;
    - inclus uniquement les annonces actives, cartes unitaires identifiées avec cote disponible ;
    - inclus uniquement les calculs complets avec tous les frais nécessaires renseignés ;
    - exclut les lots, annonces ambiguës, inactives et les cotes expirées ;
    - tri par gain net décroissant, puis ROI décroissant, puis identifiant stable ;
    - le découpage par ``offset`` s'applique après le tri complet : l'ordre est
      stable d'une page à l'autre et ``total`` couvre toutes les opportunités éligibles.
    """
    now_utc = (now or datetime.now(UTC)).astimezone(UTC)
    profile = get_active_fee_profile(connection)
    market_index = build_market_index(connection, profile.min_catalog_samples)

    # Récupération de la fraîcheur globale Cardmarket
    cm_state = cardmarket_daily.load_state(connection)
    cm_last_sync = cm_state.get("last_success_at") if cm_state else None
    if not cm_last_sync:
        cm_row = connection.execute("SELECT MAX(fetched_at) FROM cardmarket_prices").fetchone()
        if cm_row and cm_row[0]:
            cm_last_sync = cm_row[0]

    # Requête de base pour les annonces éligibles
    sql = """
        SELECT c.id, c.external_id, c.name, c.set_name, c.card_number, c.language, c.condition,
               c.variant, c.edition, c.grading_company, c.grade, c.certification_number,
               c.price_cents, c.shipping_cents, c.currency, c.seller, c.url, c.imported_at, c.reference_card_id,
               c.first_seen_at, c.last_seen_at, c.image_url, c.is_active, c.is_lot, c.identification_status,
               s.name AS source_name,
               r.rarity AS ref_rarity,
               r.name AS ref_card_name,
               r.image_url AS ref_image_url
        FROM catalog_items c
        JOIN sources s ON s.id = c.source_id
        LEFT JOIN pokemon_reference_cards r ON r.id = c.reference_card_id
        WHERE c.is_active = 1
          AND c.is_lot = 0
          AND c.identification_status = 'identified'
          AND c.currency = ?
    """
    params: list[object] = [profile.currency]

    if set_name:
        sql += " AND (c.set_name = ? OR r.set_name = ?)"
        params.extend([set_name, set_name])
    if rarity:
        sql += " AND r.rarity = ?"
        params.append(rarity)
    if language:
        sql += " AND c.language = ?"
        params.append(language)

    rows = connection.execute(sql, params).fetchall()

    candidates: list[tuple[int, int, int, BestOpportunityItem]] = []

    for row in rows:
        row_dict = dict(row)
        evaluation = evaluate_listing(row_dict, profile, market_index)

        ref_price = evaluation.get("reference_price_cents")
        if ref_price is None or ref_price <= 0:
            continue

        # Frais manquants dans le profil
        if evaluation.get("missing_fee_fields"):
            continue

        net_profit = evaluation.get("net_profit_cents")
        roi_bps = evaluation.get("roi_bps")
        total_cost = evaluation.get("total_cost_cents")

        if net_profit is None or roi_bps is None or total_cost is None:
            continue

        if evaluation.get("verdict") != "opportunite":
            continue

        # Détermination de la date et fraîcheur de la cote
        ref_source = str(evaluation.get("reference_source") or "")
        quote_date_str: str | None = None

        if ref_source == "reference":
            # La date de saisie ou de modification ne date pas l'observation du prix.
            # Une référence sans date d'observation ne peut garantir sa fraîcheur.
            quote_date_str = evaluation.get("reference_observed_at")
        elif ref_source == "cardmarket_trend":
            quote_date_str = cm_last_sync
        elif ref_source == "catalog_median":
            quote_date_str = _latest_catalog_comparable_observation(connection, row_dict)

        if not quote_date_str:
            # Sans date de cote, impossibilité de garantir le seuil de fraîcheur explicite
            continue

        quote_dt = _parse_iso_datetime(quote_date_str)
        if quote_dt is None:
            continue

        age_seconds = (now_utc - quote_dt).total_seconds()
        age_days = 0 if age_seconds < 0 else int(age_seconds // 86400)

        if max_quote_age_days is not None and age_days > max_quote_age_days:
            # Cote expirée
            continue

        comparables = find_price_comparables(connection, row_dict, ref_price, limit=2)

        opportunity = BestOpportunityItem(
            listing_id=int(row_dict["id"]),
            external_id=str(row_dict["external_id"]),
            source_name=str(row_dict["source_name"]),
            name=str(row_dict["name"]),
            set_name=str(row_dict["set_name"]),
            card_number=row_dict.get("card_number"),
            condition=row_dict.get("condition"),
            language=row_dict.get("language"),
            reference_card_id=row_dict.get("reference_card_id"),
            purchase_price_cents=int(row_dict["price_cents"]),
            buyer_shipping_cents=int(evaluation["buyer_shipping_cents"]),
            total_cost_cents=int(total_cost),
            estimated_resale_cents=int(ref_price),
            net_profit_cents=int(net_profit),
            roi_bps=int(roi_bps),
            margin_bps=evaluation.get("margin_bps"),
            currency=str(row_dict["currency"]),
            reference_source=ref_source,
            reference_source_name=evaluation.get("reference_source_name"),
            quote_freshness_date=quote_date_str,
            quote_age_days=age_days,
            url=str(row_dict["url"]) if row_dict.get("url") else None,
            image_url=row_dict.get("image_url") or row_dict.get("ref_image_url"),
            verdict=str(evaluation.get("verdict")),
            verdict_label=str(evaluation.get("verdict_label")),
            comparables=comparables,
        )

        # Clé de tri : 1. gain net desc (-net_profit), 2. ROI desc (-roi_bps), 3. id asc
        candidates.append((
            -opportunity.net_profit_cents,
            -opportunity.roi_bps,
            opportunity.listing_id,
            opportunity,
        ))

    candidates.sort(key=lambda t: (t[0], t[1], t[2]))
    items = [c[3] for c in candidates]
    return OpportunitiesPage(items=items[offset : offset + limit], total=len(items))
