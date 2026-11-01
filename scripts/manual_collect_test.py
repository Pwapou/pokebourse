"""Test manuel réel, volontairement hors de pytest.

Effectue au maximum une recherche sur une plateforme et affiche un résumé.
Aucune écriture SQLite n'est réalisée ici.
"""

import argparse
from typing import Sequence

from app.collectors.leboncoin import collect_leboncoin_listings
from app.collectors.models import CollectionResult, CollectorError
from app.collectors.vinted import collect_vinted_listings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Contrôle manuel limité d'une recherche marketplace"
    )
    parser.add_argument("platform", choices=("vinted", "leboncoin"))
    parser.add_argument("query", help="Mots-clés de recherche")
    parser.add_argument(
        "--limit", type=int, default=5, help="Nombre maximal de résultats (1 à 100)"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.platform == "vinted":
            result: CollectionResult = collect_vinted_listings(
                search_text=args.query,
                per_page=args.limit,
            )
        else:
            result = collect_leboncoin_listings(
                text=args.query,
                limit=args.limit,
            )
    except CollectorError as error:
        print(f"Échec de la collecte : {error}")
        return 1

    print(f"Plateforme : {args.platform}")
    print(f"Résultats valides : {len(result.listings)}")
    print(f"Annonces ignorées : {result.invalid_count}")
    for listing in result.listings[:5]:
        price = f"{listing.price_cents // 100}.{listing.price_cents % 100:02d}"
        print(f"- {listing.external_id} | {listing.title} | {price} €")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
