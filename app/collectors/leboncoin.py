import logging
from typing import Any

from app.collectors.models import CollectionResult, CollectorError
from app.collectors.normalizer import normalize_leboncoin_ad
from app.collectors.retry import call_with_backoff

logger = logging.getLogger(__name__)

MIN_LIMIT = 1
MAX_LIMIT = 100


def build_leboncoin_search_params(
    *,
    text: str,
    price_from: int | None = None,
    price_to: int | None = None,
    limit: int = 35,
    category: str | None = None,
) -> dict[str, Any]:
    cleaned_text = text.strip()
    if not cleaned_text:
        raise CollectorError("Les mots-clés Leboncoin sont obligatoires.")
    if price_from is not None and price_from < 0:
        raise CollectorError("Le prix minimum ne peut pas être négatif.")
    if price_to is not None and price_to < 0:
        raise CollectorError("Le prix maximum ne peut pas être négatif.")
    if price_from is not None and price_to is not None and price_from > price_to:
        raise CollectorError("Le prix minimum ne peut pas dépasser le prix maximum.")

    params: dict[str, Any] = {
        "text": cleaned_text,
        "page": 1,
        "limit": min(max(limit, MIN_LIMIT), MAX_LIMIT),
    }
    if price_from is not None or price_to is not None:
        params["price"] = [price_from, price_to]
    if category:
        params["category"] = category
    return params


def _contains_datadome_error(error: BaseException | None) -> bool:
    current = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if "datadome" in type(current).__name__.lower():
            return True
        current = current.__cause__ or current.__context__
    return False


def collect_leboncoin_listings(
    *,
    text: str,
    price_from: int | None = None,
    price_to: int | None = None,
    limit: int = 35,
    category: str | None = None,
) -> CollectionResult:
    """Recherche uniquement la première page Leboncoin, triée par nouveautés."""

    params = build_leboncoin_search_params(
        text=text,
        price_from=price_from,
        price_to=price_to,
        limit=limit,
        category=category,
    )
    try:
        import lbc
    except ImportError as error:
        raise CollectorError(
            "Le connecteur Leboncoin n'est pas installé dans l'environnement."
        ) from error

    category_value = None
    if category:
        category_value = getattr(lbc.Category, category, None)
        if category_value is None:
            raise CollectorError("Catégorie Leboncoin inconnue.")

    def search() -> Any:
        client = lbc.Client()
        return client.search(
            text=params["text"],
            page=params["page"],
            limit=params["limit"],
            sort=lbc.Sort.NEWEST,
            ad_type=lbc.AdType.OFFER,
            **({"price": params["price"]} if "price" in params else {}),
            **({"category": category_value} if category_value is not None else {}),
        )

    try:
        result = call_with_backoff(search, operation_name="Recherche Leboncoin")
    except CollectorError as error:
        if _contains_datadome_error(error.__cause__):
            logger.warning("Collecte Leboncoin bloquée par DataDome : %s", error)
            raise CollectorError(
                "Leboncoin a renvoyé une protection anti-bot (DataDome)."
            ) from error
        raise
    except Exception as error:
        if _contains_datadome_error(error):
            logger.warning("Collecte Leboncoin bloquée par DataDome : %s", error)
            raise CollectorError(
                "Leboncoin a renvoyé une protection anti-bot (DataDome)."
            ) from error
        raise CollectorError("Recherche Leboncoin indisponible.") from error

    listings = []
    invalid_count = 0
    for ad in getattr(result, "ads", result) or []:
        try:
            listings.append(normalize_leboncoin_ad(ad))
        except ValueError as error:
            invalid_count += 1
            logger.warning("Annonce Leboncoin ignorée : %s", error)
    return CollectionResult(listings=listings, invalid_count=invalid_count)
