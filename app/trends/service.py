"""Services métier pour les tendances de prix et l'activité des annonces (Lot 3)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from app.cardmarket import daily as cardmarket_daily
from app.trends.models import (
    ListingActivityItem,
    ListingActivityPage,
    PriceMovementsPage,
    PriceVariation,
    TrendsFilters,
    TrendsPageData,
)
from app.trends.opportunities import get_best_opportunities


def compute_price_variation(
    current_price_cents: int | None,
    reference_price_cents: int | None,
    currency: str = "EUR",
    ref_currency: str = "EUR",
) -> tuple[int, int] | None:
    """Calcule la variation absolue (centimes) et relative (points de base).

    Formules :
    - delta_cents = current_price_cents - reference_price_cents
    - delta_bps = round_half_up((delta_cents * 10 000) / reference_price_cents)

    Exclusions strictes :
    - l'un des prix est absent (None) ;
    - le prix de référence est nul ou négatif (<= 0) ;
    - les devises sont incompatibles.
    """
    if current_price_cents is None or reference_price_cents is None:
        return None
    if reference_price_cents <= 0:
        return None
    if currency.strip().upper() != ref_currency.strip().upper():
        return None

    delta_cents = current_price_cents - reference_price_cents
    delta_ratio = (Decimal(delta_cents) * Decimal(10_000)) / Decimal(reference_price_cents)
    delta_bps = int(delta_ratio.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return delta_cents, delta_bps


def get_price_movements(
    connection: sqlite3.Connection,
    *,
    period: Literal["7_30", "1_7"] = "7_30",
    set_name: str = "",
    limit: int = 20,
    offset: int = 0,
) -> PriceMovementsPage:
    """Retourne une page (hausses, baisses, totaux) d'après cardmarket_prices.

    Le tri est calculé sur la liste complète avant découpage : la pagination
    par ``offset`` conserve donc un ordre stable d'une page à l'autre.
    """
    if period == "1_7":
        curr_col = "avg1_price_cents"
        ref_col = "avg7_price_cents"
    else:
        curr_col = "avg7_price_cents"
        ref_col = "avg30_price_cents"

    query = f"""
        SELECT cp.product_id, cp.card_name, cp.expansion_name, cp.tcg_dex_id,
               cp.{curr_col} AS current_price,
               cp.{ref_col} AS reference_price,
               cp.currency, cp.fetched_at, cp.name_base
        FROM cardmarket_prices cp
        WHERE cp.{curr_col} IS NOT NULL
          AND cp.{ref_col} IS NOT NULL
          AND cp.{ref_col} > 0
          AND cp.currency = 'EUR'
    """
    params: list[object] = []
    if set_name:
        query += " AND (cp.expansion_name = ? OR cp.product_id IN (" \
                 "SELECT DISTINCT p.product_id FROM cardmarket_prices p " \
                 "JOIN card_name_aliases a ON a.name = p.card_name " \
                 "JOIN pokemon_reference_cards r ON r.id = a.card_id " \
                 "WHERE r.set_name = ?))"
        params.extend([set_name, set_name])

    rows = connection.execute(query, params).fetchall()

    # Pré-chargement des alias pour qualification du rattachement
    alias_counts: dict[str, int] = {}
    for r in connection.execute("SELECT lower(name) AS n, COUNT(DISTINCT card_id) AS c FROM card_name_aliases GROUP BY lower(name)").fetchall():
        alias_counts[str(r["n"])] = int(r["c"])

    hausses: list[PriceVariation] = []
    baisses: list[PriceVariation] = []

    for row in rows:
        calc = compute_price_variation(
            row["current_price"],
            row["reference_price"],
            row["currency"],
            "EUR",
        )
        if calc is None:
            continue
        delta_cents, delta_bps = calc

        tcg_dex_id = row["tcg_dex_id"]
        card_name = str(row["card_name"])
        name_base = str(row["name_base"] or "").casefold()

        if tcg_dex_id:
            match_status = "certifie"
            attachment_limits = f"Rattaché au référentiel TCGdex ({tcg_dex_id})."
        else:
            count = alias_counts.get(name_base) or alias_counts.get(card_name.casefold(), 0)
            if count == 1:
                match_status = "partiel"
                attachment_limits = "Rattachement partiel : nom anglais Cardmarket associé au nom de base, extension et état non garantis sur le guide public."
            elif count > 1:
                match_status = "ambigu"
                attachment_limits = f"Rattachement partiel multiple ({count} cartes partageant le nom de base) : extension/variante potentiellement distincte."
            else:
                match_status = "non_lie"
                attachment_limits = "Produit Cardmarket sans correspondance dans le référentiel TCGdex local."

        item = PriceVariation(
            product_id=int(row["product_id"]),
            card_name=card_name,
            expansion_name=row["expansion_name"],
            tcg_dex_id=tcg_dex_id,
            current_price_cents=int(row["current_price"]),
            reference_price_cents=int(row["reference_price"]),
            delta_cents=delta_cents,
            delta_bps=delta_bps,
            currency=str(row["currency"]),
            source="Cardmarket",
            fetched_at=str(row["fetched_at"]),
            period=period,
            match_status=match_status,
            attachment_limits=attachment_limits,
        )

        if delta_cents > 0:
            hausses.append(item)
        elif delta_cents < 0:
            baisses.append(item)

    # Tri hausses : plus forte hausse relative en points de base d'abord, puis centimes, puis id
    hausses.sort(key=lambda x: (-x.delta_bps, -x.delta_cents, x.product_id))

    # Tri baisses : plus forte baisse relative en points de base d'abord (la plus négative), puis centimes, puis id
    baisses.sort(key=lambda x: (x.delta_bps, x.delta_cents, x.product_id))

    total_compared = len(hausses) + len(baisses)
    return PriceMovementsPage(
        hausses=hausses[offset : offset + limit],
        baisses=baisses[offset : offset + limit],
        total_compared=total_compared,
        hausses_total=len(hausses),
        baisses_total=len(baisses),
    )


def get_listing_activity(
    connection: sqlite3.Connection,
    *,
    now: datetime | None = None,
    window_days: int = 30,
    set_name: str = "",
    rarity: str = "",
    language: str = "",
    min_observations: int = 1,
    limit: int = 20,
    offset: int = 0,
) -> ListingActivityPage:
    """Calcule l'activité des annonces sur une fenêtre glissante UTC de 30 jours.

    Métriques calculées par carte unitaire identifiée :
    - distinct_listings_count : nombre d'annonces distinctes observées ;
    - new_listings_count : nombre de nouvelles annonces avec first_seen_at dans la fenêtre ;
    - active_listings_count : nombre d'annonces actuellement actives.

    Règles absolues :
    - libellé métier obligatoire : « Activité des annonces » ;
    - interdiction formelle de présenter ces métriques comme des « ventes » ;
    - exclusion des lots et des annonces ambiguës ;
    - la réingestion d'une annonce déjà existante n'augmente pas distinct_listings_count ;
    - le découpage par ``offset`` s'applique après le tri SQL : l'ordre est
      stable d'une page à l'autre et ``total`` couvre toutes les cartes éligibles.
    """
    now_utc = (now or datetime.now(UTC)).astimezone(UTC)
    window_start = (now_utc - timedelta(days=window_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    window_end = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    sql = """
        SELECT
            c.reference_card_id,
            r.tcgdex_id,
            r.name AS card_name,
            r.set_name,
            r.local_id,
            r.rarity,
            r.image_url,
            c.currency,
            COUNT(DISTINCT c.id) AS distinct_listings_count,
            COUNT(DISTINCT CASE
                WHEN COALESCE(c.first_seen_at, c.imported_at) >= ?
                 AND COALESCE(c.first_seen_at, c.imported_at) <= ?
                THEN c.id
            END) AS new_listings_count,
            COUNT(DISTINCT CASE WHEN c.is_active = 1 THEN c.id END) AS active_listings_count,
            MIN(c.price_cents) AS min_price_cents,
            MAX(c.price_cents) AS max_price_cents
        FROM catalog_items c
        JOIN pokemon_reference_cards r ON r.id = c.reference_card_id
        WHERE c.is_lot = 0
          AND c.identification_status = 'identified'
          AND c.reference_card_id IS NOT NULL
          AND (
              (COALESCE(c.last_seen_at, c.imported_at) >= ?
               AND COALESCE(c.last_seen_at, c.imported_at) <= ?)
              OR EXISTS (
                  SELECT 1 FROM listing_observations o
                  WHERE o.listing_id = c.id
                    AND o.observed_at >= ?
                    AND o.observed_at <= ?
              )
          )
    """
    params: list[object] = [
        window_start, window_end,
        window_start, window_end,
        window_start, window_end,
    ]

    if set_name:
        sql += " AND (r.set_name = ? OR c.set_name = ?)"
        params.extend([set_name, set_name])
    if rarity:
        sql += " AND r.rarity = ?"
        params.append(rarity)
    if language:
        sql += " AND c.language = ?"
        params.append(language)

    group_sql = """
        GROUP BY c.reference_card_id, r.tcgdex_id, r.name, r.set_name, r.local_id, r.rarity, r.image_url, c.currency
        HAVING COUNT(DISTINCT c.id) >= ?
    """
    total = connection.execute(
        f"SELECT COUNT(*) FROM ({sql} {group_sql})",
        [*params, min_observations],
    ).fetchone()[0]

    rows = connection.execute(
        f"""
        {sql}
        {group_sql}
        ORDER BY distinct_listings_count DESC, new_listings_count DESC, card_name ASC, c.reference_card_id ASC
        LIMIT ? OFFSET ?
        """,
        [*params, min_observations, limit, offset],
    ).fetchall()
    items: list[ListingActivityItem] = []
    for row in rows:
        items.append(
            ListingActivityItem(
                reference_card_id=int(row["reference_card_id"]),
                tcgdex_id=row["tcgdex_id"],
                card_name=str(row["card_name"]),
                set_name=str(row["set_name"]),
                local_id=row["local_id"],
                rarity=row["rarity"],
                image_url=row["image_url"],
                distinct_listings_count=int(row["distinct_listings_count"]),
                new_listings_count=int(row["new_listings_count"]),
                active_listings_count=int(row["active_listings_count"]),
                min_price_cents=int(row["min_price_cents"]) if row["min_price_cents"] is not None else None,
                max_price_cents=int(row["max_price_cents"]) if row["max_price_cents"] is not None else None,
                currency=str(row["currency"] or "EUR"),
            )
        )
    return ListingActivityPage(items=items, total=int(total))


def get_trends_page_data(
    connection: sqlite3.Connection,
    filters: TrendsFilters,
    *,
    now: datetime | None = None,
) -> TrendsPageData:
    """Rassemble toutes les sections pour la vue /trends."""
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    computed_at = moment.strftime("%Y-%m-%dT%H:%M:%SZ")

    cardmarket_sync = cardmarket_daily.load_state(connection)
    last_cardmarket_sync_at = cardmarket_sync.get("last_success_at") if cardmarket_sync else None
    if not last_cardmarket_sync_at:
        # La synchronisation manuelle du guide enregistre la date sur les cotes,
        # indépendamment de l'état de la synchronisation quotidienne complète.
        last_cardmarket_sync_at = connection.execute(
            "SELECT MAX(fetched_at) FROM cardmarket_prices"
        ).fetchone()[0]

    # T3.1 : variations de prix
    period_lit: Literal["7_30", "1_7"] = "1_7" if filters.period == "1_7" else "7_30"
    limit = filters.limit
    offset = (filters.page - 1) * limit
    movements = get_price_movements(
        connection,
        period=period_lit,
        set_name=filters.set_name,
        limit=limit,
        offset=offset,
    )

    # T3.2 : activité des annonces sur 30 jours
    activity_page = get_listing_activity(
        connection,
        now=moment,
        window_days=30,
        set_name=filters.set_name,
        rarity=filters.rarity,
        language=filters.language,
        min_observations=filters.min_observations,
        limit=limit,
        offset=offset,
    )

    # T3.3 : meilleures affaires
    opportunities_page = get_best_opportunities(
        connection,
        now=moment,
        max_quote_age_days=filters.max_quote_age_days,
        set_name=filters.set_name,
        rarity=filters.rarity,
        language=filters.language,
        limit=limit,
        offset=offset,
    )

    # Listes pour les sélecteurs de filtres
    sets_rows = connection.execute(
        """
        SELECT DISTINCT name FROM pokemon_reference_sets
        UNION
        SELECT DISTINCT set_name FROM catalog_items WHERE set_name IS NOT NULL AND set_name != ''
        ORDER BY 1
        """
    ).fetchall()
    available_sets = [str(r[0]) for r in sets_rows if r[0]]

    rarity_rows = connection.execute(
        "SELECT DISTINCT rarity FROM pokemon_reference_cards WHERE rarity IS NOT NULL AND rarity != '' ORDER BY 1"
    ).fetchall()
    available_rarities = [str(r[0]) for r in rarity_rows]

    lang_rows = connection.execute(
        "SELECT DISTINCT language FROM catalog_items WHERE language IS NOT NULL AND language != '' ORDER BY 1"
    ).fetchall()
    available_languages = [str(r[0]) for r in lang_rows]

    # Vérification des états (vide / partiel / complet)
    catalog_count = connection.execute("SELECT COUNT(*) FROM catalog_items").fetchone()[0]
    cm_count = connection.execute("SELECT COUNT(*) FROM cardmarket_prices").fetchone()[0]

    has_data = catalog_count > 0 or cm_count > 0
    is_empty = catalog_count == 0 and cm_count == 0
    is_partial = False
    partial_reason = None

    if not is_empty:
        if cm_count == 0 and catalog_count > 0:
            is_partial = True
            partial_reason = "Aucune cote Cardmarket synchronisée : les variations de prix sont indisponibles. Seule l'activité des annonces est observable."
        elif catalog_count == 0 and cm_count > 0:
            is_partial = True
            partial_reason = "Aucune annonce importée dans le catalogue : l'activité des annonces et les opportunités d'arbitrage sont vides."

    return TrendsPageData(
        computed_at=computed_at,
        last_cardmarket_sync_at=last_cardmarket_sync_at,
        filters=filters,
        page=filters.page,
        hausses=movements.hausses,
        baisses=movements.baisses,
        total_price_compared=movements.total_compared,
        hausses_total=movements.hausses_total,
        baisses_total=movements.baisses_total,
        listing_activity=activity_page.items,
        activity_total=activity_page.total,
        best_opportunities=opportunities_page.items,
        opportunities_total=opportunities_page.total,
        available_sets=available_sets,
        available_rarities=available_rarities,
        available_languages=available_languages,
        has_data=has_data,
        is_empty=is_empty,
        is_partial=is_partial,
        partial_reason=partial_reason,
    )
