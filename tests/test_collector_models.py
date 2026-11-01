from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.collectors.models import (
    CollectedListing,
    ListingValidationError,
    parse_price_to_cents,
)
from app.collectors.normalizer import (
    UNKNOWN_CARD_NAME,
    UNKNOWN_SET_NAME,
    catalog_item_from_listing,
    normalize_leboncoin_ad,
    normalize_vinted_item,
    parse_explicit_card_title,
)


def test_price_conversion_uses_decimal_and_centimes() -> None:
    assert parse_price_to_cents("12,34") == 1234
    assert parse_price_to_cents("12.3") == 1230
    assert parse_price_to_cents("0") == 0
    assert parse_price_to_cents(7) == 700

    for value in ("-1", "abc", "", "1.234", None, True, 12.34):
        with pytest.raises(ListingValidationError):
            parse_price_to_cents(value)  # type: ignore[arg-type]


def test_explicit_card_title_rule_is_strict() -> None:
    assert parse_explicit_card_title("Carte Pokémon Pikachu - Évolutions") == (
        "Pikachu",
        "Évolutions",
    )
    assert parse_explicit_card_title("Pokémon Dracaufeu") == ("Dracaufeu", None)
    assert parse_explicit_card_title("Lot mystère Pokémon vintage") == (None, None)


def test_vinted_item_normalization() -> None:
    item = {
        "id": 123456,
        "title": "Carte Pokémon Pikachu - Évolutions",
        "price": "12,34",
        "currency": "EUR",
        "url": "https://www.vinted.fr/items/123456-pikachu",
        "photo": {"url": "https://images.vinted.net/photo.jpg"},
        "user": {"login": "Collectionneur"},
        "created_at": "2026-10-31T17:26:01Z",
    }

    listing = normalize_vinted_item(item)

    assert listing.source == "vinted"
    assert listing.external_id == "123456"
    assert listing.price_cents == 1234
    assert listing.url.host == "www.vinted.fr"
    assert listing.image_url.host == "images.vinted.net"
    assert listing.seller == "Collectionneur"
    assert listing.published_at == datetime(2026, 10, 31, 17, 26, 1, tzinfo=UTC)
    assert listing.raw_data["id"] == 123456


def test_leboncoin_ad_normalization() -> None:
    ad = {
        "id": "987654",
        "subject": "Carte Pokémon Mew",
        "price": "9.99",
        "url": "https://www.leboncoin.fr/ad/cartes-pokemon-987654",
        "images": [{"url": "https://img.leboncoin.fr/ad.jpg"}],
        "owner": {"name": "Vendeuse test"},
        "first_publication_date": "2026-11-01T09:00:00.000Z",
    }

    listing = normalize_leboncoin_ad(ad)

    assert listing.source == "leboncoin"
    assert listing.external_id == "987654"
    assert listing.price_cents == 999
    assert listing.url.host == "www.leboncoin.fr"
    assert listing.image_url.host == "img.leboncoin.fr"
    assert listing.seller == "Vendeuse test"
    assert listing.published_at is not None


def test_collected_listing_rejects_official_domain_mismatch() -> None:
    with pytest.raises(ValidationError):
        CollectedListing(
            source="vinted",
            external_id="1",
            title="Carte Pokémon Pikachu",
            price_cents=100,
            url="https://www.leboncoin.fr/ad/1",
        )


def test_catalog_conversion_never_invents_metadata() -> None:
    listing = CollectedListing(
        source="vinted",
        external_id="42",
        title="Lot mystère Pokémon vintage",
        price_cents=1290,
        url="https://www.vinted.fr/items/42",
    )

    item = catalog_item_from_listing(listing)

    assert item.external_id == "42"
    assert item.name == UNKNOWN_CARD_NAME
    assert item.set_name == UNKNOWN_SET_NAME
    assert item.card_number is None
    assert item.condition is None
    assert item.variant is None
    assert item.edition is None
    assert item.grading_company is None
    assert item.grade is None
    assert item.certification_number is None
