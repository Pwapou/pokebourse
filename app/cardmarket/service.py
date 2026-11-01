"""Services métier du référentiel de prix Cardmarket.

Stockage local des prix de marché (SQLite) et rafraîchissement à la demande
via l'API officielle. Aucune collecte de masse : un seul produit est demandé
par action utilisateur, ce qui respecte les quotas de l'API.
"""

import sqlite3
from typing import Any, Mapping

from app.cardmarket.aliases import (
    base_card_name,
    card_ids_for_name,
    english_name_for_card,
)
from app.cardmarket.client import (
    CardmarketClient,
    CardmarketNotConfiguredError,
    CardmarketNotFoundError,
)
from app.cardmarket.models import CardmarketPrice
from app.config import Settings


def credentials_configured(settings: Settings) -> bool:
    """Les quatre identifiants OAuth sont-ils tous renseignés ?"""
    return all(
        (
            settings.cardmarket_app_token,
            settings.cardmarket_app_secret,
            settings.cardmarket_access_token,
            settings.cardmarket_access_secret,
        )
    )


def client_from_settings(settings: Settings) -> CardmarketClient:
    """Construit le client API à partir de la configuration, ou lève NotConfigured."""
    if not credentials_configured(settings):
        raise CardmarketNotConfiguredError(
            "API Cardmarket non configurée : renseignez CARDMARKET_APP_TOKEN, "
            "CARDMARKET_APP_SECRET, CARDMARKET_ACCESS_TOKEN et "
            "CARDMARKET_ACCESS_SECRET."
        )
    return CardmarketClient(
        app_token=settings.cardmarket_app_token or "",
        app_secret=settings.cardmarket_app_secret or "",
        access_token=settings.cardmarket_access_token or "",
        access_secret=settings.cardmarket_access_secret or "",
    )


def find_prices_by_base_name(
    connection: sqlite3.Connection, base_name: str
) -> list[sqlite3.Row]:
    """Retourne les produits Cardmarket dont le nom de base correspond."""
    if not base_name:
        return []
    return connection.execute(
        """
        SELECT product_id, card_name, expansion_name, language,
               trend_price_cents, avg1_price_cents, avg7_price_cents,
               avg30_price_cents, currency, tcg_dex_id, fetched_at, name_base
        FROM cardmarket_prices
        WHERE name_base = ?
        ORDER BY trend_price_cents DESC
        """,
        (base_name,),
    ).fetchall()


def prices_for_item(
    connection: sqlite3.Connection, item: Mapping[str, Any]
) -> list[sqlite3.Row]:
    """Retourne les snapshots Cardmarket correspondant à l'annonce (0, 1 ou plusieurs).

    Stratégie :
    1. correspondance directe sur le nom de base de l'annonce (titres anglais) ;
    2. pont multilingue : carte identifiée TCGdex (ref_tcgdex_id) ou nom trouvé
       dans card_name_aliases (fr, en, ko, ja, zh-tw) → nom anglais → recherche.
    Plusieurs lignes = plusieurs extensions partagent le nom (fourchette affichée).
    """
    row_data = dict(item)
    name = str(row_data.get("name") or "").strip()

    rows = find_prices_by_base_name(connection, base_card_name(name))
    if rows:
        return rows

    card_ids: list[int] = []
    ref_tcgdex_id = row_data.get("ref_tcgdex_id")
    if ref_tcgdex_id:
        ref_row = connection.execute(
            "SELECT id FROM pokemon_reference_cards WHERE tcgdex_id = ?",
            (str(ref_tcgdex_id),),
        ).fetchone()
        if ref_row is not None:
            card_ids.append(int(ref_row["id"]))
    for card_id in card_ids_for_name(connection, name):
        if card_id not in card_ids:
            card_ids.append(card_id)

    for card_id in card_ids:
        english = english_name_for_card(connection, card_id)
        if not english:
            continue
        rows = find_prices_by_base_name(connection, base_card_name(english))
        if rows:
            return rows
    return []


def price_for_item(
    connection: sqlite3.Connection, item: Mapping[str, Any]
) -> sqlite3.Row | None:
    """Premier snapshot correspondant, ou None (compatibilité ascendante)."""
    rows = prices_for_item(connection, item)
    return rows[0] if rows else None


def upsert_price(connection: sqlite3.Connection, price: CardmarketPrice) -> None:
    """Insère ou actualise le snapshot d'un produit Cardmarket."""
    with connection:
        connection.execute(
            """
            INSERT INTO cardmarket_prices (
                product_id, tcg_dex_id, card_name, expansion_name, language,
                trend_price_cents, avg1_price_cents, avg7_price_cents,
                avg30_price_cents, currency, fetched_at, name_base
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(product_id) DO UPDATE SET
                tcg_dex_id = excluded.tcg_dex_id,
                card_name = excluded.card_name,
                expansion_name = excluded.expansion_name,
                language = excluded.language,
                trend_price_cents = excluded.trend_price_cents,
                avg1_price_cents = excluded.avg1_price_cents,
                avg7_price_cents = excluded.avg7_price_cents,
                avg30_price_cents = excluded.avg30_price_cents,
                currency = excluded.currency,
                fetched_at = excluded.fetched_at,
                name_base = excluded.name_base,
                updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            """,
            (
                price.product_id,
                price.tcg_dex_id,
                price.card_name,
                price.expansion_name,
                price.language,
                price.trend_price_cents,
                price.avg1_price_cents,
                price.avg7_price_cents,
                price.avg30_price_cents,
                price.currency,
                price.fetched_at,
                base_card_name(price.card_name),
            ),
        )


def parse_product_price(product: Mapping[str, Any]) -> CardmarketPrice | None:
    """Transforme l'entité Produit Cardmarket en snapshot de prix (centimes entiers)."""
    from app.cardmarket.client import euros_to_cents

    product_id = product.get("idProduct") or product.get("id")
    name = product.get("name")
    if not product_id or not name:
        return None
    expansion = product.get("expansion")
    if isinstance(expansion, Mapping):
        expansion_name = expansion.get("enName") or expansion.get("name")
    else:
        expansion_name = product.get("expansionName")
    price_guide = product.get("priceGuide")
    if not isinstance(price_guide, Mapping):
        price_guide = {}
    return CardmarketPrice(
        product_id=int(product_id),
        card_name=str(name),
        expansion_name=str(expansion_name) if expansion_name else None,
        trend_price_cents=euros_to_cents(price_guide.get("TREND")),
        avg1_price_cents=euros_to_cents(price_guide.get("AVG1")),
        avg7_price_cents=euros_to_cents(price_guide.get("AVG7")),
        avg30_price_cents=euros_to_cents(price_guide.get("AVG30")),
        tcg_dex_id=(
            str(product["tcgDexId"]) if product.get("tcgDexId") else None
        ),
    )


def refresh_price_for_item(
    connection: sqlite3.Connection,
    item: Mapping[str, Any],
    settings: Settings,
) -> CardmarketPrice | None:
    """Recherche la carte sur Cardmarket (API officielle) et stocke son prix.

    Retourne None si aucun produit ne correspond exactement au nom de l'annonce.
    """
    client = client_from_settings(settings)
    return refresh_price_for_item_with_client(connection, item, client)


def refresh_price_for_item_with_client(
    connection: sqlite3.Connection,
    item: Mapping[str, Any],
    client: CardmarketClient,
) -> CardmarketPrice | None:
    """Variante testable : le client est fourni (mocké dans les tests)."""
    row_data = dict(item)
    name = str(row_data.get("name") or "").strip()
    if not name:
        return None
    products = client.find_products(name)
    exact = [
        product
        for product in products
        if str(product.get("name", "")).strip().casefold() == name.casefold()
    ]
    if not exact:
        raise CardmarketNotFoundError(
            f"Aucun produit Cardmarket ne correspond exactement à « {name} »."
        )
    product_id = int(exact[0]["idProduct"])
    product = client.get_product(product_id)
    price = parse_product_price(product)
    if price is None:
        raise CardmarketNotFoundError(
            f"Produit Cardmarket {product_id} sans identité exploitable."
        )
    upsert_price(connection, price)
    return price
