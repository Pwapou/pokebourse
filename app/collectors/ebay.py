import json
import logging
import urllib.parse
import urllib.request
from typing import Any

from app.collectors.models import CollectionResult, CollectorError
from app.collectors.normalizer import normalize_ebay_item
from app.collectors.retry import call_with_backoff

logger = logging.getLogger(__name__)

EBAY_FR_SEARCH_URL = "https://www.ebay.fr/sch/i.html"
MIN_PER_PAGE = 1
MAX_PER_PAGE = 100


def _euros_from_cents(cents: int) -> str:
    """Convertit des centimes en montant décimal exact, sans virgule flottante."""
    if cents < 0:
        raise CollectorError("Le prix ne peut pas être négatif.")
    return f"{cents // 100}.{cents % 100:02d}"


def build_ebay_search_params(
    *,
    search_text: str,
    price_from: int | None = None,
    price_to: int | None = None,
    per_page: int = 50,
) -> dict[str, Any]:
    text = search_text.strip()
    if not text:
        raise CollectorError("Les mots-clés eBay sont obligatoires.")
    if price_from is not None and price_from < 0:
        raise CollectorError("Le prix minimum ne peut pas être négatif.")
    if price_to is not None and price_to < 0:
        raise CollectorError("Le prix maximum ne peut pas être négatif.")
    if price_from is not None and price_to is not None and price_from > price_to:
        raise CollectorError("Le prix minimum ne peut pas dépasser le prix maximum.")

    params: dict[str, Any] = {
        "_nkw": text,
        "_sop": 10,  # Nouveautés / Newest first
        "_ipg": min(max(per_page, MIN_PER_PAGE), MAX_PER_PAGE),
    }
    if price_from is not None:
        params["_udlo"] = _euros_from_cents(price_from)
    if price_to is not None:
        params["_udhi"] = _euros_from_cents(price_to)
    return params


def collect_ebay_listings(
    *,
    search_text: str,
    price_from: int | None = None,
    price_to: int | None = None,
    per_page: int = 50,
    search_func: Any = None,
) -> CollectionResult:
    """Collecte les annonces eBay récentes correspondant aux critères."""

    params = build_ebay_search_params(
        search_text=search_text,
        price_from=price_from,
        price_to=price_to,
        per_page=per_page,
    )

    def do_search() -> list[dict[str, Any]]:
        if search_func is not None:
            return search_func(params)
        # Requête vers l'API ou endpoint public avec en-têtes navigateur standards
        query_string = urllib.parse.urlencode(params)
        url = f"{EBAY_FR_SEARCH_URL}?{query_string}"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/json",
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            content = resp.read()
            # Si réponse JSON
            try:
                data = json.loads(content)
                if isinstance(data, list):
                    return data
                if isinstance(data, dict):
                    return data.get("items", data.get("listings", []))
            except Exception:
                pass
            return []

    try:
        raw_items = call_with_backoff(do_search, operation_name="Recherche eBay")
    except CollectorError:
        raise
    except Exception as error:
        raise CollectorError("Recherche eBay indisponible.") from error

    listings = []
    invalid_count = 0
    for item in raw_items or []:
        try:
            listings.append(normalize_ebay_item(item))
        except ValueError as error:
            invalid_count += 1
            logger.warning("Annonce eBay ignorée : %s", error)
    return CollectionResult(listings=listings, invalid_count=invalid_count)
