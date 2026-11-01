"""Synchronisation du price guide Cardmarket officiel.

Cardmarket publie chaque jour (vers 02:45 CET) deux fichiers publics, sans
authentification ni scraping :
- le price guide : prix (tendance, moyennes 1/7/30 jours, holo) par idProduct ;
- le catalogue des cartes : noms par idProduct.

Ce module télécharge ces deux fichiers, les joint par idProduct et remplit la
table locale cardmarket_prices. Une synchronisation par jour suffit : le
contenu ne change qu'après la régénération quotidienne du guide.
"""

import json
import logging
import sqlite3
import urllib.request
from datetime import UTC, datetime
from typing import Any, Callable

from app.cardmarket.aliases import base_card_name
from app.cardmarket.client import euros_to_cents

logger = logging.getLogger(__name__)

POKEMON_PRICE_GUIDE_URL = (
    "https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json"
)
POKEMON_PRODUCTS_URL = (
    "https://downloads.s3.cardmarket.com/productCatalog/productList/products_singles_6.json"
)
GUIDE_TIMEOUT_SECONDS = 60.0

Fetcher = Callable[[str], dict[str, Any]]


def download_json(url: str, timeout: float = GUIDE_TIMEOUT_SECONDS) -> dict[str, Any]:
    """Télécharge un fichier JSON officiel Cardmarket (aucune authentification)."""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Pokebourse/1.0 (Pokemon Card Arbitrage; Local Fair Use)",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Fichier Cardmarket invalide (objet attendu) : {url}")
    return data


def to_utc_iso(raw: object) -> str:
    """Convertit l'horodatage Cardmarket (« 2026-11-01T02:47:16+0100 ») en ISO UTC."""
    if not raw:
        return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    text = str(raw).strip()
    try:
        parsed = datetime.strptime(text, "%Y-%m-%dT%H:%M:%S%z")
        return parsed.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    except ValueError:
        return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_price_entries(
    entries: list[dict[str, Any]],
) -> dict[int, dict[str, int | None]]:
    """Indexe les entrées du price guide par idProduct (prix en centimes entiers)."""
    indexed: dict[int, dict[str, int | None]] = {}
    for entry in entries:
        try:
            product_id = int(entry["idProduct"])
        except (KeyError, TypeError, ValueError):
            continue
        indexed[product_id] = {
            "trend": euros_to_cents(entry.get("trend")),
            "avg1": euros_to_cents(entry.get("avg1")),
            "avg7": euros_to_cents(entry.get("avg7")),
            "avg30": euros_to_cents(entry.get("avg30")),
        }
    return indexed


def parse_product_entries(
    entries: list[dict[str, Any]],
) -> dict[int, str]:
    """Indexe les noms de produits par idProduct."""
    indexed: dict[int, str] = {}
    for entry in entries:
        try:
            product_id = int(entry["idProduct"])
        except (KeyError, TypeError, ValueError):
            continue
        name = str(entry.get("name") or "").strip()
        if name:
            indexed[product_id] = name
    return indexed


UPSERT_PRICE_SQL = """
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
"""


def _backfill_missing_name_base(connection: sqlite3.Connection) -> None:
    """Calcule name_base pour les lignes anciennes ne l'ayant pas encore."""
    rows = connection.execute(
        "SELECT id, card_name FROM cardmarket_prices WHERE name_base IS NULL"
    ).fetchall()
    if not rows:
        return
    connection.executemany(
        "UPDATE cardmarket_prices SET name_base = ? WHERE id = ?",
        [(base_card_name(row["card_name"]), row["id"]) for row in rows],
    )


def sync_price_guide(
    connection: sqlite3.Connection,
    fetcher: Fetcher = download_json,
) -> dict[str, Any]:
    """Télécharge les fichiers officiels et synchronise cardmarket_prices.

    Retourne un compte-rendu : date du guide, nombre de produits du guide,
    nombre de cartes synchronisées et nombre ignorés (sans nom dans le
    catalogue).
    """
    guide = fetcher(POKEMON_PRICE_GUIDE_URL)
    catalogue = fetcher(POKEMON_PRODUCTS_URL)

    created_at = to_utc_iso(guide.get("createdAt"))
    prices = parse_price_entries(guide.get("priceGuides") or [])
    products = parse_product_entries(catalogue.get("products") or [])

    rows: list[tuple[Any, ...]] = []
    for product_id, price in prices.items():
        name = products.get(product_id)
        if not name:
            continue
        rows.append(
            (
                product_id,
                None,
                name,
                None,
                "en",
                price["trend"],
                price["avg1"],
                price["avg7"],
                price["avg30"],
                "EUR",
                created_at,
                base_card_name(name),
            )
        )

    with connection:
        connection.executemany(UPSERT_PRICE_SQL, rows)
        _backfill_missing_name_base(connection)

    result = {
        "created_at": created_at,
        "guide_products": len(prices),
        "synced": len(rows),
        "skipped": len(prices) - len(rows),
    }
    logger.info(
        "Price guide Cardmarket synchronisé : %(synced)d cartes "
        "(guide du %(created_at)s, %(skipped)d ignorés).",
        result,
    )
    return result
