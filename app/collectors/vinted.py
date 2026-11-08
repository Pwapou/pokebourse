import logging
from typing import Any

from app.collectors.models import CollectionResult, CollectorError
from app.collectors.normalizer import normalize_vinted_item
from app.collectors.retry import call_with_backoff

logger = logging.getLogger(__name__)

VINTED_DOMAIN = "https://www.vinted.fr"
MIN_PER_PAGE = 1
MAX_PER_PAGE = 48


def _euros_from_cents(cents: int) -> str:
    """Convertit des centimes en montant décimal exact, sans virgule flottante."""
    if cents < 0:
        raise CollectorError("Le prix ne peut pas être négatif.")
    return f"{cents // 100}.{cents % 100:02d}"


def build_vinted_search_params(
    *,
    search_text: str,
    price_from: int | None = None,
    price_to: int | None = None,
    per_page: int = 24,
) -> dict[str, Any]:
    text = search_text.strip()
    if not text:
        raise CollectorError("Les mots-clés Vinted sont obligatoires.")
    if price_from is not None and price_from < 0:
        raise CollectorError("Le prix minimum ne peut pas être négatif.")
    if price_to is not None and price_to < 0:
        raise CollectorError("Le prix maximum ne peut pas être négatif.")
    if price_from is not None and price_to is not None and price_from > price_to:
        raise CollectorError("Le prix minimum ne peut pas dépasser le prix maximum.")

    params: dict[str, Any] = {
        "search_text": text,
        "order": "newest",
        "page": 1,
        "per_page": min(max(per_page, MIN_PER_PAGE), MAX_PER_PAGE),
    }
    if price_from is not None:
        params["price_from"] = _euros_from_cents(price_from)
    if price_to is not None:
        params["price_to"] = _euros_from_cents(price_to)
    return params


def collect_vinted_listings(
    *,
    search_text: str,
    price_from: int | None = None,
    price_to: int | None = None,
    per_page: int = 24,
) -> CollectionResult:
    """Recherche uniquement la première page Vinted, triée par nouveautés."""

    params = build_vinted_search_params(
        search_text=search_text,
        price_from=price_from,
        price_to=price_to,
        per_page=per_page,
    )
    try:
        from vinted_scraper import VintedScraper
    except ImportError as error:
        raise CollectorError(
            "Le connecteur Vinted n'est pas installé dans l'environnement."
        ) from error

    def search() -> Any:
        scraper = VintedScraper(VINTED_DOMAIN)
        return scraper.search(params)

    try:
        raw_items = call_with_backoff(search, operation_name="Recherche Vinted")
    except CollectorError:
        raise
    except Exception as error:
        raise CollectorError("Recherche Vinted indisponible.") from error

    listings = []
    invalid_count = 0
    for item in raw_items or []:
        try:
            listings.append(normalize_vinted_item(item))
        except ValueError as error:
            invalid_count += 1
            logger.warning("Annonce Vinted ignorée : %s", error)
    return CollectionResult(listings=listings, invalid_count=invalid_count)
