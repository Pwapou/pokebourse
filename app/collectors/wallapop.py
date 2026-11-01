import json
import logging
import urllib.parse
import urllib.request
from typing import Any

from app.collectors.models import CollectionResult, CollectorError
from app.collectors.normalizer import normalize_wallapop_item
from app.collectors.retry import call_with_backoff

logger = logging.getLogger(__name__)

WALLAPOP_API_SEARCH_URL = "https://api.wallapop.com/api/v3/general/search"
MIN_PER_PAGE = 1
MAX_PER_PAGE = 60


def build_wallapop_search_params(
    *,
    search_text: str,
    price_from: int | None = None,
    price_to: int | None = None,
    per_page: int = 40,
) -> dict[str, Any]:
    text = search_text.strip()
    if not text:
        raise CollectorError("Les mots-clés Wallapop sont obligatoires.")
    if price_from is not None and price_from < 0:
        raise CollectorError("Le prix minimum ne peut pas être négatif.")
    if price_to is not None and price_to < 0:
        raise CollectorError("Le prix maximum ne peut pas être négatif.")
    if price_from is not None and price_to is not None and price_from > price_to:
        raise CollectorError("Le prix minimum ne peut pas dépasser le prix maximum.")

    params: dict[str, Any] = {
        "keywords": text,
        "order_by": "creation_date_desc",
        "step": 0,
    }
    if price_from is not None:
        params["min_sale_price"] = price_from // 100
    if price_to is not None:
        params["max_sale_price"] = (price_to + 99) // 100
    return params


def collect_wallapop_listings(
    *,
    search_text: str,
    price_from: int | None = None,
    price_to: int | None = None,
    per_page: int = 40,
    search_func: Any = None,
) -> CollectionResult:
    """Collecte les annonces Wallapop récentes correspondant aux critères."""

    params = build_wallapop_search_params(
        search_text=search_text,
        price_from=price_from,
        price_to=price_to,
        per_page=per_page,
    )

    def do_search() -> list[dict[str, Any]]:
        if search_func is not None:
            return search_func(params)
        query_string = urllib.parse.urlencode(params)
        url = f"{WALLAPOP_API_SEARCH_URL}?{query_string}"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
            "Accept-Language": "fr-FR,fr;q=0.9,es;q=0.8,en;q=0.7",
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            content = resp.read()
            data = json.loads(content)
            if isinstance(data, dict):
                return data.get("search_objects", data.get("items", []))
            if isinstance(data, list):
                return data
            return []

    try:
        raw_items = call_with_backoff(do_search, operation_name="Recherche Wallapop")
    except CollectorError:
        raise
    except Exception as error:
        raise CollectorError("Recherche Wallapop indisponible.") from error

    listings = []
    invalid_count = 0
    for item in raw_items or []:
        try:
            listings.append(normalize_wallapop_item(item))
        except ValueError as error:
            invalid_count += 1
            logger.warning("Annonce Wallapop ignorée : %s", error)
    return CollectionResult(listings=listings, invalid_count=invalid_count)
