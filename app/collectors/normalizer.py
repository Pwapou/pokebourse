from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
import re
from typing import Any

from app.catalog import CatalogItem
from app.collectors.models import CollectedListing, ListingPlatform, parse_price_to_cents

UNKNOWN_CARD_NAME = "Carte non identifiée"
UNKNOWN_SET_NAME = "Non identifiée"

# Règle volontairement stricte : seul un libellé qui annonce explicitement une
# carte Pokémon peut fournir un nom ou une extension. Aucune heuristique ne
# devine ces métadonnées à partir d'un titre marketplace quelconque.
_EXPLICIT_CARD_PATTERN = re.compile(
    r"^\s*(?:carte\s+)?pok[ée]mon\s+"
    r"(?P<name>[A-ZÀ-Þ0-9][A-ZÀ-Þa-zà-ÿ0-9'’\. -]{1,60}?)"
    r"(?:\s+[-–—]\s+(?P<set>[A-ZÀ-Þ0-9][A-ZÀ-Þa-zà-ÿ0-9'’&()\. -]{1,100}))?"
    r"\s*$",
    re.IGNORECASE,
)


def parse_explicit_card_title(title: str) -> tuple[str | None, str | None]:
    match = _EXPLICIT_CARD_PATTERN.fullmatch(title)
    if match is None:
        return None, None
    name = " ".join(match.group("name").split())
    set_name = match.group("set")
    return name, " ".join(set_name.split()) if set_name else None


def catalog_item_from_listing(listing: CollectedListing) -> CatalogItem:
    """Convertit une annonce collectée sans inventer de métadonnées Pokémon."""

    parsed_name, parsed_set = parse_explicit_card_title(listing.title)
    return CatalogItem(
        external_id=listing.external_id,
        name=parsed_name or UNKNOWN_CARD_NAME,
        set_name=parsed_set or UNKNOWN_SET_NAME,
        price_cents=listing.price_cents,
        currency=listing.currency,
        seller=listing.seller,
        url=listing.url,
    )


def _value(payload: object, *names: str) -> Any:
    for name in names:
        if isinstance(payload, Mapping) and name in payload:
            return payload[name]
        if hasattr(payload, name):
            return getattr(payload, name)
    return None


def _image_url(image: Any) -> str | None:
    if image is None:
        return None
    if isinstance(image, str):
        return image
    if isinstance(image, Mapping):
        for key in ("url", "src", "large_url", "medium_url", "thumbnail_url"):
            value = image.get(key)
            if isinstance(value, str) and value:
                return value
        urls = image.get("urls")
        if isinstance(urls, Mapping):
            for key in ("large", "medium", "small", "thumbnail"):
                value = urls.get(key)
                if isinstance(value, str) and value:
                    return value
        return None
    for key in ("url", "src"):
        value = getattr(image, key, None)
        if isinstance(value, str) and value:
            return value
    return None


def _first_image_url(images: Any) -> str | None:
    if images is None:
        return None
    if isinstance(images, (str, Mapping)) or hasattr(images, "url"):
        return _image_url(images)
    if isinstance(images, (list, tuple)):
        for image in images:
            url = _image_url(image)
            if url:
                return url
    return None


def _seller_name(user: Any) -> str | None:
    if user is None:
        return None
    if isinstance(user, str):
        return user
    for key in ("login", "name", "username"):
        value = _value(user, key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _seller_external_id(payload: Any) -> str | None:
    """Identifiant public du vendeur, sans jamais dépendre d'un appel réseau."""

    for key in ("_user_id", "user_id", "seller_id"):
        value = getattr(payload, key, None)
        if value is not None and not callable(value):
            return str(value)
    for key in ("owner", "user", "seller"):
        nested = _value(payload, key)
        if nested is None or isinstance(nested, (str, bytes, bool)):
            continue
        value = _value(nested, "user_id", "id", "seller_id")
        if value is not None and str(value).strip():
            return str(value)
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _price_value(value: Any) -> Any:
    """Adapte un prix collecté (souvent un float de bibliothèque) avant validation.

    Les bibliothèques de scraping renvoient le prix en float ; parse_price_to_cents
    refuse les floats par principe, donc on les convertit via leur représentation
    textuelle la plus courte, exacte en décimal.
    """

    if isinstance(value, float) and not isinstance(value, bool):
        return Decimal(str(value))
    return value


def _serializable_raw(payload: object, *, source: ListingPlatform) -> dict[str, Any]:
    if isinstance(payload, Mapping):
        return dict(payload)
    # Les objets des bibliothèques de scraping peuvent être des dataclasses
    # contenant un client HTTP (non sérialisable) : on n'extrait que les clés
    # utiles via les attributs, jamais asdict() qui copierait tout récursivement.
    allowed_keys = {
        "vinted": (
            "id",
            "title",
            "price",
            "currency",
            "url",
            "photo",
            "user",
            "created_at",
            "published_at",
            "raw_data",
        ),
        "leboncoin": (
            "id",
            "subject",
            "price",
            "url",
            "images",
            "image",
            "owner",
            "seller",
            "created_at",
            "published_at",
            "raw_data",
        ),
        "ebay": (
            "id",
            "item_id",
            "title",
            "price",
            "shipping",
            "currency",
            "url",
            "image",
            "images",
            "seller",
            "created_at",
            "published_at",
            "raw_data",
        ),
        "wallapop": (
            "id",
            "title",
            "price",
            "currency",
            "url",
            "web_slug",
            "images",
            "image",
            "user",
            "seller",
            "created_at",
            "published_at",
            "raw_data",
        ),
    }[source]
    raw: dict[str, Any] = {}
    for key in allowed_keys:
        value = _value(payload, key)
        if isinstance(value, (str, int, float, bool)) or value is None:
            raw[key] = value
        elif isinstance(value, Mapping):
            raw[key] = dict(value)
    return raw


def _absolute_url(url: Any, base: str) -> str:
    """Absolutise un chemin relatif renvoyé par l'API (ex. '/items/123')."""

    text = str(url or "").strip()
    if not text:
        return ""
    if text.startswith("/"):
        return f"{base}{text}"
    return text


def normalize_vinted_item(item: object) -> CollectedListing:
    external_id = _value(item, "id", "item_id", "external_id")
    title = _value(item, "title", "name", "subject")
    price = _value(item, "price", "price_amount")
    currency = _value(item, "currency", "currency_code") or "EUR"
    url = _absolute_url(_value(item, "url", "item_url", "link"), "https://www.vinted.fr")
    image = _first_image_url(_value(item, "photo", "photos", "image", "images"))
    seller = _seller_name(_value(item, "user", "seller", "owner"))
    seller_external_id = _seller_external_id(item)
    published_at = _parse_datetime(
        _value(item, "published_at", "created_at", "created_at_ts")
    )
    if external_id is not None:
        external_id = str(external_id)
    return CollectedListing(
        source="vinted",
        external_id=external_id or "",
        title=str(title or ""),
        price_cents=parse_price_to_cents(_price_value(price), "prix Vinted"),
        shipping_cents=None,
        currency=str(currency),
        url=str(url or ""),
        image_url=image,
        seller=seller,
        seller_external_id=seller_external_id,
        published_at=published_at,
        raw_data=_serializable_raw(item, source="vinted"),
    )


def normalize_leboncoin_ad(ad: object) -> CollectedListing:
    external_id = _value(ad, "id", "ad_id", "external_id", "list_id")
    title = _value(ad, "subject", "title", "name")
    price = _value(ad, "price", "price_amount")
    url = _value(ad, "url", "ad_url", "link")
    images = _value(ad, "images", "image", "photos")
    seller = _seller_name(_value(ad, "owner", "seller", "user"))
    seller_external_id = _seller_external_id(ad)
    published_at = _parse_datetime(
        _value(ad, "published_at", "created_at", "first_publication_date", "index_date")
    )
    if external_id is not None:
        external_id = str(external_id)
    return CollectedListing(
        source="leboncoin",
        external_id=external_id or "",
        title=str(title or ""),
        price_cents=parse_price_to_cents(_price_value(price), "prix Leboncoin"),
        shipping_cents=None,
        currency="EUR",
        url=str(url or ""),
        image_url=_first_image_url(images),
        seller=seller,
        seller_external_id=seller_external_id,
        published_at=published_at,
        raw_data=_serializable_raw(ad, source="leboncoin"),
    )


def normalize_ebay_item(item: object) -> CollectedListing:
    external_id = _value(item, "id", "item_id", "itemId", "external_id")
    title = _value(item, "title", "subject", "name")
    price = _value(item, "price", "price_amount", "current_price")
    shipping = _value(item, "shipping_cents", "shipping", "shipping_cost", "postage")
    currency = _value(item, "currency", "currency_code") or "EUR"
    url = _value(item, "url", "item_url", "link", "viewItemURL")
    if not url and external_id:
        url = f"https://www.ebay.fr/itm/{external_id}"
    image = _first_image_url(
        _value(item, "image", "image_url", "images", "galleryURL", "picture_urls")
    )
    seller = _seller_name(_value(item, "seller", "user", "seller_username", "sellerUserName"))
    seller_external_id = _seller_external_id(item)
    published_at = _parse_datetime(
        _value(item, "published_at", "created_at", "startTime")
    )
    if external_id is not None:
        external_id = str(external_id)

    shipping_cents = None
    if shipping is not None:
        try:
            shipping_cents = parse_price_to_cents(_price_value(shipping), "port eBay")
        except ValueError:
            shipping_cents = None

    return CollectedListing(
        source="ebay",
        external_id=external_id or "",
        title=str(title or ""),
        price_cents=parse_price_to_cents(_price_value(price), "prix eBay"),
        shipping_cents=shipping_cents,
        currency=str(currency),
        url=str(url or ""),
        image_url=image,
        seller=seller,
        seller_external_id=seller_external_id,
        published_at=published_at,
        raw_data=_serializable_raw(item, source="ebay"),
    )


def normalize_wallapop_item(item: object) -> CollectedListing:
    external_id = _value(item, "id", "item_id", "itemId", "external_id")
    title = _value(item, "title", "subject", "name")
    price = _value(item, "price", "price_amount")
    currency = _value(item, "currency", "currency_code") or "EUR"
    web_slug = _value(item, "web_slug", "slug")
    url = _value(item, "url", "link")
    if not url:
        if web_slug:
            url = f"https://fr.wallapop.com/item/{web_slug}"
        elif external_id:
            url = f"https://fr.wallapop.com/item/{external_id}"
    images = _value(item, "images", "image", "photos")
    if isinstance(images, list) and images and isinstance(images[0], Mapping) and "original" in images[0]:
        image = images[0]["original"]
    else:
        image = _first_image_url(images)
    seller = _seller_name(_value(item, "user", "seller", "owner"))
    if not seller and isinstance(_value(item, "user"), Mapping):
        seller = _value(_value(item, "user"), "micro_name", "web_slug")
    seller_external_id = _seller_external_id(item)
    published_at = _parse_datetime(
        _value(item, "published_at", "created_at", "modified_at")
    )
    if external_id is not None:
        external_id = str(external_id)
    return CollectedListing(
        source="wallapop",
        external_id=external_id or "",
        title=str(title or ""),
        price_cents=parse_price_to_cents(_price_value(price), "prix Wallapop"),
        shipping_cents=None,
        currency=str(currency),
        url=str(url or ""),
        image_url=image,
        seller=seller,
        seller_external_id=seller_external_id,
        published_at=published_at,
        raw_data=_serializable_raw(item, source="wallapop"),
    )
