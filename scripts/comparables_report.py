"""Rapport de vérification : comparables de prix sur la base locale (lecture seule).

Pour chaque annonce évaluée avec un prix de revente estimé, affiche les
annonces comparables et les achats déjà revendus qui étayent l'estimation.
"""

import sqlite3

from app.profitability import (
    build_market_index,
    evaluate_listing,
    find_price_comparables,
    get_active_fee_profile,
)


def money(cents: int) -> str:
    return f"{cents / 100:,.2f}".replace(",", " ").replace(".", ",") + " €"


def main() -> None:
    connection = sqlite3.connect(
        "file:/data/pokemon-arbitrage.db?mode=ro", uri=True
    )
    connection.row_factory = sqlite3.Row

    profile = get_active_fee_profile(connection)
    market_index = build_market_index(connection, profile.min_catalog_samples)
    rows = connection.execute(
        """
        SELECT id, external_id, name, set_name, card_number, language, condition,
               variant, edition, grading_company, grade, certification_number,
               price_cents, currency, seller, url, imported_at, reference_card_id
        FROM catalog_items
        ORDER BY id DESC
        """
    ).fetchall()

    with_evidence = 0
    shown = 0
    for row in rows:
        item = dict(row)
        evaluation = evaluate_listing(item, profile, market_index)
        if evaluation["reference_price_cents"] is None:
            continue
        comparables = find_price_comparables(
            connection, item, evaluation["reference_price_cents"]
        )
        if (
            not comparables["listings"]
            and not comparables["sales"]
            and not comparables["references"]
        ):
            continue
        with_evidence += 1
        if shown >= 15:
            continue
        shown += 1
        ref = evaluation["reference_price_cents"]
        print("=" * 78)
        print(
            f"#{item['id']} {item['name']} · {item['set_name']}"
            f" · N° {item['card_number'] or '—'} · achat {money(item['price_cents'])}"
        )
        print(
            f"  Revente estimée : {money(ref)}"
            f" (source : {evaluation['reference_source']},"
            f" {evaluation['sample_count']} échantillon(s))"
        )
        for ref in comparables["references"]:
            delta = ref["delta_cents"]
            sign = "+" if delta > 0 else ""
            print(
                f"  REF COTE    : {money(ref['reference_price_cents'])}"
                f" ({sign}{money(delta) if delta >= 0 else '-' + money(-delta)} vs estimation)"
                f" · {ref['reference_kind_label'] or ref['reference_kind']}"
                f" · {ref['source_name'] or 'source ?'}"
                f" · le {(ref['observed_at'] or '?')[:10]}"
            )
            if ref["source_url"]:
                print(f"                {ref['source_url']}")
        for listing in comparables["listings"]:
            delta = listing["delta_cents"]
            sign = "+" if delta > 0 else ""
            state = "" if listing["is_active"] else " [inactive]"
            print(
                f"  EN VENTE    : {money(listing['price_cents'])}"
                f" ({sign}{money(delta) if delta >= 0 else '-' + money(-delta)} vs estimation)"
                f" · {listing['source_name']} · {listing['seller'] or 'vendeur inconnu'}"
                f" · {listing['condition'] or 'état ?'}{state}"
            )
            if listing["url"]:
                print(f"                {listing['url']}")
        for sale in comparables["sales"]:
            delta = sale["delta_cents"]
            sign = "+" if delta > 0 else ""
            print(
                f"  REVENDU     : {money(sale['price_paid_cents'])}"
                f" ({sign}{money(delta) if delta >= 0 else '-' + money(-delta)} vs estimation)"
                f" · {sale['platform'] or 'plateforme ?'}"
                f" · le {sale['purchased_at'][:10]}"
            )

    total_evaluated = sum(
        1
        for row in rows
        if evaluate_listing(dict(row), profile, market_index)["reference_price_cents"]
        is not None
    )
    print("=" * 78)
    print(
        f"Résumé : {len(rows)} annonce(s), {total_evaluated} évaluée(s),"
        f" {with_evidence} avec au moins un comparable (annonces ou ventes)."
    )


if __name__ == "__main__":
    main()
