from __future__ import annotations

import csv
import io
import json
import sqlite3
from typing import Any

from app.catalog import build_common_listing_clauses
from app.catalog_export import CSV_COLUMNS as BASE_CSV_COLUMNS, csv_cell
from app.identification.matcher import CardMatcher
from app.identification.normalization import canonical_local_id, normalize_text
from app.profitability import enrich_catalog_items
from app.search.models import (
    CARD_SORTS,
    DEFAULT_CARD_SORT,
    DEFAULT_LISTING_SORT,
    LISTING_SORTS,
    PROFITABILITY_LISTING_SORTS,
    CardSearchResult,
    CardSearchSummary,
    ListingSearchResult,
    ListingSearchSummary,
    SearchFilters,
    SearchResults,
)
from app.tcgdex.cache import TcgdexCache

SEARCH_CSV_COLUMNS: tuple[tuple[str, str], ...] = (
    *BASE_CSV_COLUMNS,
    ("identification_status", "Statut d'identification"),
    ("is_lot", "Lot (1=oui, 0=non)"),
    ("ref_tcgdex_id", "ID TCGdex officiel"),
    ("ref_rarity", "Rareté officielle"),
    ("ref_release_year", "Année officielle"),
)

SEARCH_CSV_FILENAME = "pokebourse-recherche.csv"


def get_search_filter_options(connection: sqlite3.Connection) -> dict[str, list[str]]:
    """Récupère les listes distinctes pour alimenter les listes déroulantes de recherche."""
    # Sets combinés (référentiel + annonces)
    sets_rows = connection.execute(
        """
        SELECT name FROM pokemon_reference_sets
        UNION
        SELECT DISTINCT set_name AS name FROM catalog_items WHERE set_name IS NOT NULL AND set_name <> ''
        ORDER BY name COLLATE NOCASE ASC
        """
    ).fetchall()
    sets = [row[0] for row in sets_rows if row[0]]

    # Raretés du référentiel
    rarity_rows = connection.execute(
        """
        SELECT DISTINCT rarity
        FROM pokemon_reference_cards
        WHERE rarity IS NOT NULL AND rarity <> ''
        ORDER BY rarity COLLATE NOCASE ASC
        """
    ).fetchall()
    rarities = [row[0] for row in rarity_rows if row[0]]

    # États des annonces
    condition_rows = connection.execute(
        """
        SELECT DISTINCT condition
        FROM catalog_items
        WHERE condition IS NOT NULL AND condition <> ''
        ORDER BY condition COLLATE NOCASE ASC
        """
    ).fetchall()
    conditions = [row[0] for row in condition_rows if row[0]]

    # Langues des annonces
    lang_rows = connection.execute(
        """
        SELECT DISTINCT language
        FROM catalog_items
        WHERE language IS NOT NULL AND language <> ''
        ORDER BY language COLLATE NOCASE ASC
        """
    ).fetchall()
    languages = [row[0] for row in lang_rows if row[0]]

    # Gradation
    grading_rows = connection.execute(
        """
        SELECT DISTINCT grading_company
        FROM catalog_items
        WHERE grading_company IS NOT NULL AND grading_company <> ''
        ORDER BY grading_company COLLATE NOCASE ASC
        """
    ).fetchall()
    grading_companies = [row[0] for row in grading_rows if row[0]]

    return {
        "sets": sets,
        "rarities": rarities,
        "conditions": conditions,
        "languages": languages,
        "grading_companies": grading_companies,
    }


def _build_reference_cards_base_clauses(
    filters: SearchFilters,
) -> tuple[list[str], list[Any]]:
    where_clauses: list[str] = []
    params: list[Any] = []

    if filters.q:
        q_norm = normalize_text(filters.q)
        q_like = f"%{filters.q}%"
        q_norm_like = f"%{q_norm}%"
        local_canon = canonical_local_id(filters.q)
        where_clauses.append(
            "("
            "c.tcgdex_id = ? "
            "OR c.local_id = ? "
            "OR c.canonical_local_id = ? "
            "OR c.normalized_name LIKE ? "
            "OR c.name LIKE ?"
            ")"
        )
        params.extend([filters.q, filters.q, local_canon, q_norm_like, q_like])

    if filters.set_name:
        where_clauses.append("(c.set_name = ? OR s.name = ? OR s.id = ?)")
        params.extend([filters.set_name, filters.set_name, filters.set_name])

    return where_clauses, params


def _format_card_metadata_diagnostic(
    filters: SearchFilters,
    missing_rarity_count: int,
    missing_year_count: int,
) -> str | None:
    has_rarity_filter = bool(filters.rarity)
    has_year_filter = filters.year_min is not None or filters.year_max is not None

    if has_rarity_filter or has_year_filter:
        parts: list[str] = []
        if has_rarity_filter and missing_rarity_count > 0:
            parts.append(
                f"{missing_rarity_count} carte{'s' if missing_rarity_count > 1 else ''} "
                f"sans rareté chargée (filtre « {filters.rarity} »)"
            )
        if has_year_filter and missing_year_count > 0:
            parts.append(
                f"{missing_year_count} carte{'s' if missing_year_count > 1 else ''} "
                "sans année de sortie chargée"
            )
        if parts:
            return (
                "Diagnostic métadonnées : "
                + " et ".join(parts)
                + " dans le cache local n'ont pas pu être évaluées par ces filtres "
                "(donnée non chargée ≠ preuve d'absence)."
            )

    partial_parts: list[str] = []
    if missing_rarity_count > 0:
        partial_parts.append(
            f"{missing_rarity_count} carte{'s' if missing_rarity_count > 1 else ''} sans rareté chargée"
        )
    if missing_year_count > 0:
        partial_parts.append(
            f"{missing_year_count} carte{'s' if missing_year_count > 1 else ''} sans année de sortie chargée"
        )
    if partial_parts:
        return (
            "Métadonnées partielles : "
            + " et ".join(partial_parts)
            + " dans le cache local (manifeste d'extension importé sans détail complet — "
            "donnée non chargée ≠ preuve d'absence)."
        )
    return None


def _build_reference_cards_query(
    filters: SearchFilters,
) -> tuple[str, str, list[Any]]:
    where_clauses, params = _build_reference_cards_base_clauses(filters)

    if filters.rarity:
        where_clauses.append("c.rarity = ?")
        params.append(filters.rarity)

    if filters.year_min is not None:
        where_clauses.append(
            "length(s.release_date) >= 4 AND CAST(substr(s.release_date, 1, 4) AS INTEGER) >= ?"
        )
        params.append(filters.year_min)

    if filters.year_max is not None:
        where_clauses.append(
            "length(s.release_date) >= 4 AND CAST(substr(s.release_date, 1, 4) AS INTEGER) <= ?"
        )
        params.append(filters.year_max)

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    # Tri
    sort = filters.sort if filters.sort in CARD_SORTS else (DEFAULT_CARD_SORT if filters.q else "name_asc")
    if sort == "relevance" and filters.q:
        order_sql = (
            "CASE "
            "WHEN lower(c.tcgdex_id) = lower(?) THEN 0 "
            "WHEN lower(c.name) = lower(?) THEN 1 "
            "WHEN c.normalized_name LIKE ? THEN 2 "
            "ELSE 3 END, "
            "s.release_date DESC, c.canonical_local_id ASC, c.id ASC"
        )
        order_params = [filters.q, filters.q, f"%{normalize_text(filters.q)}%"]
    elif sort == "name_desc":
        order_sql = "c.name COLLATE NOCASE DESC, c.id DESC"
        order_params = []
    elif sort == "release_desc":
        order_sql = "s.release_date DESC, c.name COLLATE NOCASE ASC, c.id ASC"
        order_params = []
    elif sort == "release_asc":
        order_sql = "s.release_date ASC, c.name COLLATE NOCASE ASC, c.id ASC"
        order_params = []
    elif sort == "local_id_asc":
        order_sql = "c.canonical_local_id ASC, c.id ASC"
        order_params = []
    else:  # name_asc
        order_sql = "c.name COLLATE NOCASE ASC, c.id ASC"
        order_params = []

    return where_sql, f"ORDER BY {order_sql}", [*params, *order_params]


def search_reference_cards(
    connection: sqlite3.Connection,
    filters: SearchFilters,
) -> CardSearchSummary:
    where_sql, order_sql, params = _build_reference_cards_query(filters)
    base_clauses, base_params = _build_reference_cards_base_clauses(filters)
    base_where_sql = f"WHERE {' AND '.join(base_clauses)}" if base_clauses else ""

    diag_row = connection.execute(
        f"""
        SELECT
            COALESCE(SUM(CASE WHEN c.rarity IS NULL OR trim(c.rarity) = '' THEN 1 ELSE 0 END), 0) AS missing_rarity,
            COALESCE(SUM(CASE WHEN s.release_date IS NULL OR length(trim(s.release_date)) < 4 THEN 1 ELSE 0 END), 0) AS missing_year
        FROM pokemon_reference_cards c
        JOIN pokemon_reference_sets s ON s.id = c.set_id
        {base_where_sql}
        """,
        base_params,
    ).fetchone()
    missing_rarity_count = int(diag_row["missing_rarity"] or 0)
    missing_year_count = int(diag_row["missing_year"] or 0)

    # Paramètres de comptage : sans les paramètres d'ordonnancement s'ils sont dans ORDER BY
    count_params = params[: -len(filters.q and filters.sort == "relevance" and [1, 2, 3] or [])] if (filters.q and filters.sort == "relevance") else params

    total = connection.execute(
        f"""
        SELECT COUNT(*)
        FROM pokemon_reference_cards c
        JOIN pokemon_reference_sets s ON s.id = c.set_id
        {where_sql}
        """,
        count_params,
    ).fetchone()[0]

    is_approximate = False
    items: list[CardSearchResult] = []

    if total > 0:
        total_pages = (total + filters.per_page - 1) // filters.per_page
        current_page = min(filters.page, total_pages)
        offset = (current_page - 1) * filters.per_page
        rows = connection.execute(
            f"""
            SELECT
                c.id, c.tcgdex_id, c.local_id, c.name, c.set_id, c.set_name,
                c.rarity, c.category, c.types, c.hp, c.stage, c.illustrator,
                c.image_url, s.release_date,
                CASE WHEN length(s.release_date) >= 4
                     THEN CAST(substr(s.release_date, 1, 4) AS INTEGER)
                     ELSE NULL END AS release_year
            FROM pokemon_reference_cards c
            JOIN pokemon_reference_sets s ON s.id = c.set_id
            {where_sql}
            {order_sql}
            LIMIT ? OFFSET ?
            """,
            [*params, filters.per_page, offset],
        ).fetchall()

        for row in rows:
            types_list = []
            if row["types"]:
                try:
                    types_list = json.loads(row["types"])
                    if not isinstance(types_list, list):
                        types_list = []
                except Exception:
                    types_list = []

            items.append(
                CardSearchResult(
                    id=row["id"],
                    tcgdex_id=row["tcgdex_id"],
                    local_id=row["local_id"],
                    name=row["name"],
                    set_id=row["set_id"],
                    set_name=row["set_name"],
                    release_date=row["release_date"],
                    release_year=row["release_year"],
                    rarity=row["rarity"],
                    category=row["category"],
                    types=types_list,
                    hp=row["hp"],
                    stage=row["stage"],
                    illustrator=row["illustrator"],
                    image_url=row["image_url"],
                )
            )
    elif filters.q and filters.q.strip():
        # Repli approximatif (fuzzy / distance d'édition)
        cache = TcgdexCache(connection)
        matcher = CardMatcher(cache, seed_if_empty=False, repair_index=False)
        match_result = matcher.identify(filters.q)
        ordered_candidates = [
            candidate for candidate in match_result.candidates
            if not candidate.contradictions
        ]
        if ordered_candidates:
            card_ids = [cand.card_id for cand in ordered_candidates]
            ref_cards = {card.id: card for card in cache.get_cards_by_ids(card_ids)}

            # Récupération des release_date pour ces cartes
            sets_dict = {
                s["id"]: s for s in cache.list_sets()
            }

            approx_items: list[CardSearchResult] = []
            fuzzy_missing_rarity = 0
            fuzzy_missing_year = 0
            for cand in ordered_candidates:
                card = ref_cards.get(cand.card_id)
                if not card:
                    continue
                set_info = sets_dict.get(card.set_id)
                release_date = set_info.get("release_date") if set_info else None
                release_year = (
                    int(release_date[:4])
                    if release_date and len(release_date) >= 4 and release_date[:4].isdigit()
                    else None
                )

                # Filtre par extension si demandé
                if filters.set_name:
                    if card.set_name != filters.set_name and card.set_id != filters.set_name:
                        continue

                if not card.rarity or not str(card.rarity).strip():
                    fuzzy_missing_rarity += 1
                if release_year is None:
                    fuzzy_missing_year += 1

                # Filtre par rareté si demandé
                if filters.rarity:
                    if card.rarity != filters.rarity:
                        continue

                # Filtre par année si demandé
                if filters.year_min is not None:
                    if release_year is None or release_year < filters.year_min:
                        continue
                if filters.year_max is not None:
                    if release_year is None or release_year > filters.year_max:
                        continue

                types_list = []
                if card.types:
                    try:
                        types_list = json.loads(card.types) if isinstance(card.types, str) else list(card.types)
                    except Exception:
                        types_list = []

                approx_items.append(
                    CardSearchResult(
                        id=card.id,
                        tcgdex_id=card.tcgdex_id,
                        local_id=card.local_id,
                        name=card.name,
                        set_id=card.set_id,
                        set_name=card.set_name,
                        release_date=release_date,
                        release_year=release_year,
                        rarity=card.rarity,
                        category=card.category,
                        types=types_list,
                        hp=card.hp,
                        stage=card.stage,
                        illustrator=card.illustrator,
                        image_url=card.image_url,
                    )
                )

            if missing_rarity_count == 0 and fuzzy_missing_rarity > 0:
                missing_rarity_count = fuzzy_missing_rarity
            if missing_year_count == 0 and fuzzy_missing_year > 0:
                missing_year_count = fuzzy_missing_year

            if approx_items:
                is_approximate = True
                total = len(approx_items)
                total_pages = (total + filters.per_page - 1) // filters.per_page
                current_page = min(filters.page, total_pages)
                offset = (current_page - 1) * filters.per_page
                items = approx_items[offset : offset + filters.per_page]

    total_pages = max(1, (total + filters.per_page - 1) // filters.per_page)
    current_page = min(max(1, filters.page), total_pages)
    range_start = (current_page - 1) * filters.per_page + 1 if total else 0
    range_end = min((current_page - 1) * filters.per_page + filters.per_page, total)
    metadata_diagnostic = _format_card_metadata_diagnostic(
        filters=filters,
        missing_rarity_count=missing_rarity_count,
        missing_year_count=missing_year_count,
    )

    return CardSearchSummary(
        items=items,
        total=total,
        is_approximate=is_approximate,
        page=current_page,
        per_page=filters.per_page,
        total_pages=total_pages,
        range_start=range_start,
        range_end=range_end,
        missing_rarity_count=missing_rarity_count,
        missing_year_count=missing_year_count,
        metadata_diagnostic=metadata_diagnostic,
    )


def _build_listings_non_reference_clauses(
    filters: SearchFilters,
) -> tuple[list[str], list[Any]]:
    where_clauses, where_params = build_common_listing_clauses(
        query=filters.q,
        set_name=filters.set_name,
        source=filters.source,
        ident_status=filters.ident_status,
        include_reference_fields=True,
    )

    if filters.condition:
        where_clauses.append("LOWER(c.condition) = LOWER(?)")
        where_params.append(filters.condition)

    if filters.language:
        where_clauses.append("LOWER(c.language) = LOWER(?)")
        where_params.append(filters.language)

    if filters.variant:
        where_clauses.append("LOWER(c.variant) LIKE LOWER(?)")
        where_params.append(f"%{filters.variant}%")

    if filters.edition:
        where_clauses.append("LOWER(c.edition) LIKE LOWER(?)")
        where_params.append(f"%{filters.edition}%")

    if filters.grading_company:
        where_clauses.append("LOWER(c.grading_company) = LOWER(?)")
        where_params.append(filters.grading_company)

    if filters.grade:
        where_clauses.append("LOWER(c.grade) = LOWER(?)")
        where_params.append(filters.grade)

    if filters.price_min_cents is not None:
        where_clauses.append("c.price_cents >= ?")
        where_params.append(filters.price_min_cents)

    if filters.price_max_cents is not None:
        where_clauses.append("c.price_cents <= ?")
        where_params.append(filters.price_max_cents)

    if filters.lot_filter == "exclude":
        where_clauses.append("c.is_lot = 0")
    elif filters.lot_filter == "only":
        where_clauses.append("c.is_lot = 1")

    return where_clauses, where_params


def _format_listing_metadata_diagnostic(
    filters: SearchFilters,
    missing_rarity_count: int,
    missing_year_count: int,
) -> str | None:
    has_rarity_filter = bool(filters.rarity)
    has_year_filter = filters.year_min is not None or filters.year_max is not None

    if has_rarity_filter or has_year_filter:
        parts: list[str] = []
        if has_rarity_filter and missing_rarity_count > 0:
            parts.append(
                f"{missing_rarity_count} annonce{'s' if missing_rarity_count > 1 else ''} "
                f"rattachée{'s' if missing_rarity_count > 1 else ''} à une carte sans rareté chargée"
            )
        if has_year_filter and missing_year_count > 0:
            parts.append(
                f"{missing_year_count} annonce{'s' if missing_year_count > 1 else ''} "
                f"rattachée{'s' if missing_year_count > 1 else ''} à une carte sans année de sortie chargée"
            )
        if parts:
            return (
                "Diagnostic métadonnées : "
                + " et ".join(parts)
                + " dans le cache local n'ont pas pu être évaluées par ces filtres "
                "(donnée non chargée ≠ preuve d'absence)."
            )

    partial_parts: list[str] = []
    if missing_rarity_count > 0:
        partial_parts.append(
            f"{missing_rarity_count} annonce{'s' if missing_rarity_count > 1 else ''} "
            f"rattachée{'s' if missing_rarity_count > 1 else ''} à une carte sans rareté chargée"
        )
    if missing_year_count > 0:
        partial_parts.append(
            f"{missing_year_count} annonce{'s' if missing_year_count > 1 else ''} "
            f"rattachée{'s' if missing_year_count > 1 else ''} à une carte sans année de sortie chargée"
        )
    if partial_parts:
        return (
            "Métadonnées partielles : "
            + " et ".join(partial_parts)
            + " dans le cache local (donnée non chargée ≠ preuve d'absence)."
        )
    return None


def _build_listings_query(
    filters: SearchFilters,
) -> tuple[str, str, list[Any], list[Any]]:
    where_clauses, where_params = _build_listings_non_reference_clauses(filters)

    # RÈGLE D'OR : Rareté et Année passent impérativement par reference_card_id
    if filters.rarity:
        where_clauses.append("c.reference_card_id IS NOT NULL AND r.rarity = ?")
        where_params.append(filters.rarity)

    if filters.year_min is not None:
        where_clauses.append(
            "c.reference_card_id IS NOT NULL "
            "AND length(r_set.release_date) >= 4 "
            "AND CAST(substr(r_set.release_date, 1, 4) AS INTEGER) >= ?"
        )
        where_params.append(filters.year_min)

    if filters.year_max is not None:
        where_clauses.append(
            "c.reference_card_id IS NOT NULL "
            "AND length(r_set.release_date) >= 4 "
            "AND CAST(substr(r_set.release_date, 1, 4) AS INTEGER) <= ?"
        )
        where_params.append(filters.year_max)

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    # Tri
    sort = filters.sort if filters.sort in LISTING_SORTS else (DEFAULT_LISTING_SORT if filters.q else "import_desc")
    order_params: list[Any] = []
    if sort == "relevance" and filters.q:
        order_sql = (
            "CASE "
            "WHEN lower(c.name) = lower(?) THEN 0 "
            "WHEN lower(c.name) LIKE lower(?) THEN 1 "
            "ELSE 2 END, "
            "c.imported_at DESC, c.id DESC"
        )
        order_params = [filters.q, f"%{filters.q}%"]
    elif sort == "import_asc":
        order_sql = "c.imported_at ASC, c.id ASC"
    elif sort == "price_asc":
        order_sql = "c.price_cents ASC, c.id ASC"
    elif sort == "price_desc":
        order_sql = "c.price_cents DESC, c.id DESC"
    elif sort == "name_asc":
        order_sql = "c.name COLLATE NOCASE ASC, c.id ASC"
    elif sort == "name_desc":
        order_sql = "c.name COLLATE NOCASE DESC, c.id DESC"
    elif sort in PROFITABILITY_LISTING_SORTS:
        # Tri réalisé en Python après enrichissement rentabilité : ordre SQL
        # uniquement stable pour la récupération de toutes les lignes filtrées.
        order_sql = "c.id ASC"
    else:  # import_desc
        order_sql = "c.imported_at DESC, c.id DESC"

    return where_sql, f"ORDER BY {order_sql}", where_params, order_params


def search_catalog_listings(
    connection: sqlite3.Connection,
    filters: SearchFilters,
    enrich_profitability: bool = True,
) -> ListingSearchSummary:
    where_sql, order_sql, where_params, order_params = _build_listings_query(filters)

    total = connection.execute(
        f"""
        SELECT COUNT(*)
        FROM catalog_items c
        JOIN sources s ON s.id = c.source_id
        LEFT JOIN pokemon_reference_cards r ON r.id = c.reference_card_id
        LEFT JOIN pokemon_reference_sets r_set ON r_set.id = r.set_id
        {where_sql}
        """,
        where_params,
    ).fetchone()[0]

    total_pages = max(1, (total + filters.per_page - 1) // filters.per_page)
    current_page = min(filters.page, total_pages)
    offset = (current_page - 1) * filters.per_page

    select_sql = f"""
        SELECT
            c.id, c.external_id, c.name, c.set_name, c.card_number, c.language,
            c.condition, c.variant, c.edition, c.grading_company, c.grade,
            c.certification_number, c.price_cents, c.shipping_cents, c.currency, c.seller, c.url,
            c.imported_at, c.original_title, c.is_lot,
            c.identification_status, c.reference_card_id, c.identification_confidence,
            c.identification_reason, c.seller_profile_id, c.seller_external_id,
            s.name AS source_name, s.kind AS source_kind,
            r.name AS ref_name, r.tcgdex_id AS ref_tcgdex_id, r.rarity AS ref_rarity,
            r.image_url AS ref_image_url, r.local_id AS ref_local_id,
            r_set.name AS ref_set_name, r_set.release_date AS ref_release_date,
            CASE WHEN length(r_set.release_date) >= 4
                 THEN CAST(substr(r_set.release_date, 1, 4) AS INTEGER)
                 ELSE NULL END AS ref_release_year,
            sp.reputation_bps AS sp_reputation_bps,
            sp.is_banned AS sp_is_banned,
            sp.feedback_count AS sp_feedback_count
        FROM catalog_items c
        JOIN sources s ON s.id = c.source_id
        LEFT JOIN pokemon_reference_cards r ON r.id = c.reference_card_id
        LEFT JOIN pokemon_reference_sets r_set ON r_set.id = r.set_id
        LEFT JOIN seller_profiles sp ON sp.id = c.seller_profile_id
        {where_sql}
    """

    is_profitability_sort = enrich_profitability and filters.sort in PROFITABILITY_LISTING_SORTS

    if is_profitability_sort:
        # Le tri gain net / ROI repose sur l'évaluation complète de la
        # rentabilité (frais, cote de marché, comparables) : impossible en SQL.
        # Toutes les annonces filtrées sont évaluées puis triées en Python avec
        # un ordre stable ; la pagination est appliquée en mémoire ensuite.
        all_rows = connection.execute(
            f"{select_sql} ORDER BY c.id ASC",
            where_params,
        ).fetchall()
        if all_rows:
            enriched_rows, _ = enrich_catalog_items(connection, all_rows)
        else:
            enriched_rows = []

        def _profitability_key(row: dict[str, Any]) -> tuple[bool, int, bool, int, int]:
            net = row.get("net_profit_cents")
            roi = row.get("roi_bps")
            # Annonces sans évaluation complète classées en dernier ;
            # l'identifiant en clé finale garantit un ordre stable total.
            if filters.sort == "net_profit_desc":
                return (net is None, -(net or 0), roi is None, -(roi or 0), int(row["id"]))
            return (roi is None, -(roi or 0), net is None, -(net or 0), int(row["id"]))

        enriched_rows.sort(key=_profitability_key)
        total = len(enriched_rows)
        total_pages = max(1, (total + filters.per_page - 1) // filters.per_page)
        current_page = min(max(1, filters.page), total_pages)
        offset = (current_page - 1) * filters.per_page
        enriched_rows = enriched_rows[offset : offset + filters.per_page]
    else:
        rows = connection.execute(
            f"{select_sql} {order_sql} LIMIT ? OFFSET ?",
            [*where_params, *order_params, filters.per_page, offset],
        ).fetchall()

        if enrich_profitability and rows:
            enriched_rows, _ = enrich_catalog_items(connection, rows)
        else:
            enriched_rows = [dict(r) for r in rows]

    items: list[ListingSearchResult] = []
    for row in enriched_rows:
        items.append(
            ListingSearchResult(
                id=row["id"],
                external_id=row["external_id"],
                name=row["name"],
                set_name=row["set_name"],
                card_number=row.get("card_number"),
                language=row["language"],
                condition=row.get("condition"),
                variant=row.get("variant"),
                edition=row.get("edition"),
                grading_company=row.get("grading_company"),
                grade=row.get("grade"),
                certification_number=row.get("certification_number"),
                price_cents=row["price_cents"],
                currency=row["currency"],
                seller=row.get("seller"),
                url=row.get("url"),
                imported_at=row["imported_at"],
                original_title=row.get("original_title"),
                source_name=row["source_name"],
                source_kind=row["source_kind"],
                identification_status=row["identification_status"],
                is_lot=row["is_lot"],
                reference_card_id=row.get("reference_card_id"),
                identification_confidence=row.get("identification_confidence"),
                identification_reason=row.get("identification_reason"),
                seller_profile_id=row.get("seller_profile_id"),
                seller_external_id=row.get("seller_external_id"),
                ref_name=row.get("ref_name"),
                ref_tcgdex_id=row.get("ref_tcgdex_id"),
                ref_rarity=row.get("ref_rarity"),
                ref_image_url=row.get("ref_image_url"),
                ref_local_id=row.get("ref_local_id"),
                ref_set_name=row.get("ref_set_name"),
                ref_release_date=row.get("ref_release_date"),
                ref_release_year=row.get("ref_release_year"),
                total_cost_cents=row.get("total_cost_cents"),
                reference_price_cents=row.get("reference_price_cents"),
                reference_source=row.get("reference_source"),
                sample_count=row.get("sample_count"),
                net_profit_cents=row.get("net_profit_cents"),
                roi_bps=row.get("roi_bps"),
                verdict=row.get("verdict"),
            )
        )

    total_pages = max(1, (total + filters.per_page - 1) // filters.per_page)
    current_page = min(max(1, filters.page), total_pages)
    range_start = (current_page - 1) * filters.per_page + 1 if total else 0
    range_end = min((current_page - 1) * filters.per_page + filters.per_page, total)

    if filters.rarity or filters.year_min is not None or filters.year_max is not None:
        base_clauses, base_params = _build_listings_non_reference_clauses(filters)
        base_clauses_with_ref = [*base_clauses, "c.reference_card_id IS NOT NULL"]
        base_where_sql = f"WHERE {' AND '.join(base_clauses_with_ref)}"
        diag_row = connection.execute(
            f"""
            SELECT
                COALESCE(SUM(CASE WHEN r.rarity IS NULL OR trim(r.rarity) = '' THEN 1 ELSE 0 END), 0) AS missing_rarity,
                COALESCE(SUM(CASE WHEN r_set.release_date IS NULL OR length(trim(r_set.release_date)) < 4 THEN 1 ELSE 0 END), 0) AS missing_year
            FROM catalog_items c
            JOIN sources s ON s.id = c.source_id
            LEFT JOIN pokemon_reference_cards r ON r.id = c.reference_card_id
            LEFT JOIN pokemon_reference_sets r_set ON r_set.id = r.set_id
            {base_where_sql}
            """,
            base_params,
        ).fetchone()
        missing_rarity_count = int(diag_row["missing_rarity"] or 0)
        missing_year_count = int(diag_row["missing_year"] or 0)
    else:
        missing_rarity_count = sum(
            1
            for item in items
            if item.reference_card_id is not None and (not item.ref_rarity or not str(item.ref_rarity).strip())
        )
        missing_year_count = sum(
            1
            for item in items
            if item.reference_card_id is not None and item.ref_release_year is None
        )

    metadata_diagnostic = _format_listing_metadata_diagnostic(
        filters=filters,
        missing_rarity_count=missing_rarity_count,
        missing_year_count=missing_year_count,
    )

    return ListingSearchSummary(
        items=items,
        total=total,
        page=current_page,
        per_page=filters.per_page,
        total_pages=total_pages,
        range_start=range_start,
        range_end=range_end,
        missing_rarity_count=missing_rarity_count,
        missing_year_count=missing_year_count,
        metadata_diagnostic=metadata_diagnostic,
    )


def search_all(
    connection: sqlite3.Connection,
    filters: SearchFilters,
) -> SearchResults:
    cards_summary = None
    listings_summary = None

    if filters.scope in ("all", "cards"):
        cards_summary = search_reference_cards(connection, filters)

    if filters.scope in ("all", "listings"):
        listings_summary = search_catalog_listings(connection, filters)

    return SearchResults(
        filters=filters,
        cards=cards_summary,
        listings=listings_summary,
    )


def search_listings_export_rows(
    connection: sqlite3.Connection,
    filters: SearchFilters,
) -> list[sqlite3.Row]:
    """Exporte l'ensemble des annonces correspondant aux filtres, sans pagination."""
    where_sql, _, where_params, _ = _build_listings_query(filters)
    return connection.execute(
        f"""
        SELECT
            c.id, c.external_id, c.name, c.set_name, c.card_number, c.language,
            c.condition, c.variant, c.edition, c.grading_company, c.grade,
            c.certification_number, c.price_cents, c.shipping_cents, c.currency, c.seller, c.url,
            c.imported_at, c.original_title, c.is_lot,
            c.identification_status, c.reference_card_id,
            s.name AS source_name, s.kind AS source_kind,
            r.name AS ref_name, r.tcgdex_id AS ref_tcgdex_id, r.rarity AS ref_rarity,
            r_set.release_date AS ref_release_date,
            CASE WHEN length(r_set.release_date) >= 4
                 THEN CAST(substr(r_set.release_date, 1, 4) AS INTEGER)
                 ELSE NULL END AS ref_release_year
        FROM catalog_items c
        JOIN sources s ON s.id = c.source_id
        LEFT JOIN pokemon_reference_cards r ON r.id = c.reference_card_id
        LEFT JOIN pokemon_reference_sets r_set ON r_set.id = r.set_id
        {where_sql}
        ORDER BY c.name COLLATE NOCASE ASC, c.id ASC
        """,
        where_params,
    ).fetchall()


def build_search_csv(rows: list[sqlite3.Row]) -> bytes:
    """Construit un export CSV des résultats avec BOM UTF-8 et protection des cellules."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow([header for _, header in SEARCH_CSV_COLUMNS])
    for row in rows:
        data = dict(row)
        writer.writerow([csv_cell(data.get(key)) for key, _ in SEARCH_CSV_COLUMNS])
    return buffer.getvalue().encode("utf-8-sig")
