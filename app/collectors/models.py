import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator

ListingPlatform = Literal["vinted", "leboncoin", "ebay", "wallapop"]

_OFFICIAL_DOMAINS: dict[str, tuple[str, ...]] = {
    "vinted": (
        "vinted.fr",
        "www.vinted.fr",
    ),
    "leboncoin": (
        "leboncoin.fr",
        "www.leboncoin.fr",
    ),
    "ebay": (
        "ebay.fr",
        "www.ebay.fr",
        "ebay.com",
        "www.ebay.com",
    ),
    "wallapop": (
        "wallapop.com",
        "www.wallapop.com",
        "es.wallapop.com",
        "fr.wallapop.com",
        "it.wallapop.com",
    ),
}

_OFFICIAL_IMAGE_DOMAINS: dict[str, tuple[str, ...]] = {
    "vinted": ("images.vinted.net",),
    "leboncoin": ("img.leboncoin.fr",),
    "ebay": (
        "i.ebayimg.com",
        "ebayimg.com",
        "thumbs.ebaystatic.com",
        "galleryplus.ebayimg.com",
    ),
    "wallapop": (
        "cdn.wallapop.com",
        "wallapop.com",
    ),
}

_PRICE_SPACES = re.compile(r"[\s\u00a0\u202f]")
_PRICE_PATTERN = re.compile(r"^\d+(?:[.,]\d{1,2})?$")


class CollectorError(RuntimeError):
    """Erreur de collecte, sans donnée sensible dans le message."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class ListingValidationError(ValueError):
    pass


@dataclass(frozen=True)
class CollectionResult:
    listings: list["CollectedListing"] = field(default_factory=list)
    invalid_count: int = 0


def parse_price_to_cents(value: object, field_name: str = "prix") -> int:
    """Convertit un prix décimal en centimes avec Decimal, jamais avec float.

    Les booléens et flottants sont refusés car ils ne sont pas une source
    fiable pour un prix collecté. Les chaînes acceptent la virgule ou le point
    comme séparateur décimal, avec au plus deux décimales.
    """

    if isinstance(value, bool):
        raise ListingValidationError(f"{field_name} invalide.")
    if isinstance(value, int):
        decimal_value = Decimal(value)
        text = str(value)
    elif isinstance(value, Decimal):
        decimal_value = value
        text = format(value, "f")
    elif isinstance(value, str):
        text = _PRICE_SPACES.sub("", value.strip())
        if not _PRICE_PATTERN.fullmatch(text):
            raise ListingValidationError(f"{field_name} invalide.")
        try:
            decimal_value = Decimal(text.replace(",", "."))
        except InvalidOperation as error:
            raise ListingValidationError(f"{field_name} invalide.") from error
    else:
        raise ListingValidationError(f"{field_name} invalide : type non pris en charge.")

    if not decimal_value.is_finite() or decimal_value < 0:
        raise ListingValidationError(f"{field_name} invalide.")
    cents = int((decimal_value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return cents


class CollectedListing(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: ListingPlatform
    external_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    price_cents: int = Field(ge=0, le=1_000_000_000)
    shipping_cents: int | None = Field(default=None, ge=0, le=1_000_000_000)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    url: AnyHttpUrl = Field(max_length=2048)
    image_url: AnyHttpUrl | None = Field(default=None, max_length=2048)
    seller: str | None = Field(default=None, max_length=200)
    seller_external_id: str | None = Field(default=None, max_length=100)
    published_at: datetime | None = None
    raw_data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("external_id")
    @classmethod
    def validate_external_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("identifiant externe obligatoire")
        return value

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        normalized = value.upper()
        if not normalized.isascii() or not normalized.isalpha():
            raise ValueError("devise composée de trois lettres attendue")
        return normalized

    @field_validator("url")
    @classmethod
    def validate_official_domain(cls, value: AnyHttpUrl, info) -> AnyHttpUrl:
        source = getattr(info, "data", {}).get("source")
        allowed = _OFFICIAL_DOMAINS.get(str(source or ""), ())
        host = (value.host or "").lower()
        if host not in allowed:
            raise ValueError("URL hors domaine officiel de la plateforme")
        return value

    @field_validator("image_url")
    @classmethod
    def validate_official_image_domain(
        cls, value: AnyHttpUrl | None, info
    ) -> AnyHttpUrl | None:
        if value is None:
            return None
        source = getattr(info, "data", {}).get("source")
        allowed = _OFFICIAL_IMAGE_DOMAINS.get(str(source or ""), ())
        host = (value.host or "").lower()
        vinted_image = str(source or "") == "vinted" and re.fullmatch(
            r"images\d*\.vinted\.net", host
        )
        ebay_image = str(source or "") == "ebay" and (
            host.endswith(".ebayimg.com") or host.endswith(".ebaystatic.com")
        )
        wallapop_image = str(source or "") == "wallapop" and host.endswith(".wallapop.com")
        if host not in allowed and not vinted_image and not ebay_image and not wallapop_image:
            raise ValueError("URL d’image hors domaine officiel de la plateforme")
        return value

    @field_validator("raw_data")
    @classmethod
    def validate_raw_data(cls, value: dict[str, Any]) -> dict[str, Any]:
        try:
            json.dumps(value)
        except (TypeError, ValueError) as error:
            raise ValueError("données brutes non sérialisables en JSON") from error
        return value
