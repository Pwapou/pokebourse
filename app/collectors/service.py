import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Iterable

from pydantic import ValidationError

from app.collectors.models import CollectedListing, ListingPlatform
from app.collectors.normalizer import catalog_item_from_listing
from app.identification.matcher import CardMatcher
from app.sellers import repository as seller_repository
from app.tcgdex.cache import TcgdexCache


@dataclass(frozen=True)
class IngestionResult:
    processed_count: int
    created_count: int
    updated_count: int
    invalid_count: int


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def ensure_collection_source(
    connection: sqlite3.Connection, platform: ListingPlatform
) -> int:
    """Crée ou active la source dédiée à une plateforme marketplace."""

    connection.execute(
        """
        INSERT INTO sources (name, kind, enabled)
        VALUES (?, 'api', 1)
        ON CONFLICT(name) DO UPDATE SET enabled = 1
        """,
        (platform,),
    )
    source_id = connection.execute(
        "SELECT id FROM sources WHERE name = ?", (platform,)
    ).fetchone()[0]
    return int(source_id)


def _prepare_listing(listing: CollectedListing) -> tuple[object, ...] | None:
    try:
        catalog_item = catalog_item_from_listing(listing)
        # Revalidation explicite : la conversion ci-dessus ne doit jamais rendre
        # une annonce invalide acceptable par l'ingestion.
        catalog_item.model_validate(catalog_item)
        return (listing, catalog_item)
    except (ValidationError, ValueError):
        return None


def ingest_collected_listings(
    connection: sqlite3.Connection,
    listings: Iterable[CollectedListing],
    *,
    platform: ListingPlatform,
    import_batch_id: int,
) -> IngestionResult:
    """Ingère des annonces validées, sans doublon logique par plateforme.

    Toutes les annonces sont d'abord validées, puis l'écriture complète est
    transactionnelle. Une annonce invalide est comptabilisée et ignorée sans
    annuler ni corrompre les annonces valides du même passage.
    """

    prepared: list[tuple[CollectedListing, object]] = []
    invalid_count = 0
    raw_count = 0
    for listing in listings:
        raw_count += 1
        if listing.source != platform:
            invalid_count += 1
            continue
        converted = _prepare_listing(listing)
        if converted is None:
            invalid_count += 1
            continue
        prepared.append(converted)  # type: ignore[arg-type]

    created_count = 0
    updated_count = 0
    now = utc_now()
    matcher = CardMatcher(TcgdexCache(connection))

    with connection:
        source_id = ensure_collection_source(connection, platform)
        for listing, item in prepared:
            existing = connection.execute(
                """
                SELECT id, price_cents, shipping_cents, currency, seller, url,
                       name, set_name, card_number, original_title, raw_data,
                       identification_status, reference_card_id,
                       identification_confidence, identification_reason, is_lot
                FROM catalog_items
                WHERE source_id = ? AND external_id = ?
                """,
                (source_id, listing.external_id),
            ).fetchone()
            raw_data = json.dumps(listing.raw_data, ensure_ascii=False, sort_keys=True)

            ident = matcher.identify(listing.title, raw_data=listing.raw_data)
            name = item.name
            set_name = item.set_name
            card_number = item.card_number
            variant = item.variant
            condition = item.condition
            grading_company = item.grading_company
            grade = item.grade
            ref_card_id = None
            is_lot = 1 if ident.features.is_lot else 0

            if ident.status == "identified" and ident.matched_card:
                name = ident.matched_card.name
                set_name = ident.matched_card.set_name
                card_number = ident.matched_card.local_id
                ref_card_id = ident.matched_card.id
                if ident.features.variant:
                    variant = ident.features.variant
                if ident.features.condition:
                    condition = ident.features.condition
                if ident.features.grading_company:
                    grading_company = ident.features.grading_company
                    grade = ident.features.grade
            elif ident.status == "lot":
                name = listing.title
                set_name = "Lot / Coffret"
                card_number = None
                is_lot = 1
            elif ident.status == "ambiguous":
                if ident.features.name:
                    name = ident.features.name
                if ident.features.set_name:
                    set_name = ident.features.set_name
                if ident.features.card_number:
                    card_number = ident.features.card_number
                if ident.features.variant:
                    variant = ident.features.variant

            values = {
                "external_id": listing.external_id,
                "name": name,
                "set_name": set_name,
                "card_number": card_number,
                "language": ident.features.language or item.language,
                "condition": condition,
                "variant": variant,
                "edition": item.edition,
                "grading_company": grading_company,
                "grade": grade,
                "certification_number": item.certification_number,
                "price_cents": item.price_cents,
                "currency": item.currency,
                "seller": item.seller,
                "url": str(item.url) if item.url else None,
                "original_title": listing.title,
                "last_seen_at": now,
                "published_at": (
                    listing.published_at.isoformat() if listing.published_at else None
                ),
                "image_url": str(listing.image_url) if listing.image_url else None,
                "shipping_cents": listing.shipping_cents,
                "seller_external_id": listing.seller_external_id,
                "is_active": 1,
                "raw_data": raw_data,
                "identification_status": ident.status,
                "reference_card_id": ref_card_id,
                "identification_confidence": ident.confidence,
                "identification_reason": ident.reason,
                "is_lot": is_lot,
            }
            if existing is None:
                insert_cursor = connection.execute(
                    """
                    INSERT INTO catalog_items (
                        source_id, import_batch_id, external_id, name, set_name,
                        card_number, language, condition, variant, edition,
                        grading_company, grade, certification_number,
                        price_cents, currency, seller, url, imported_at,
                        original_title, first_seen_at, last_seen_at,
                        published_at, image_url, shipping_cents,
                        seller_external_id, is_active,
                        raw_data, identification_status, reference_card_id,
                        identification_confidence, identification_reason, is_lot
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        source_id,
                        import_batch_id,
                        values["external_id"],
                        values["name"],
                        values["set_name"],
                        values["card_number"],
                        values["language"],
                        values["condition"],
                        values["variant"],
                        values["edition"],
                        values["grading_company"],
                        values["grade"],
                        values["certification_number"],
                        values["price_cents"],
                        values["currency"],
                        values["seller"],
                        values["url"],
                        now,
                        values["original_title"],
                        now,
                        values["last_seen_at"],
                        values["published_at"],
                        values["image_url"],
                        values["shipping_cents"],
                        values["seller_external_id"],
                        values["is_active"],
                        values["raw_data"],
                        values["identification_status"],
                        values["reference_card_id"],
                        values["identification_confidence"],
                        values["identification_reason"],
                        values["is_lot"],
                    ),
                )
                item_id = int(insert_cursor.lastrowid)
                created_count += 1
            else:
                item_id = int(existing["id"])
                _update_existing_listing(connection, existing, values)
                if _listing_changed(existing, values):
                    updated_count += 1

            from app.config import Settings
            from app.identification.pipeline import resolve_and_apply
            resolve_and_apply(connection, item_id, auto_enrich=Settings.from_env().tcgdex_auto_enrich)

            if listing.seller_external_id:
                seller_repository.enqueue_seller(
                    connection,
                    platform=platform,
                    seller_external_id=listing.seller_external_id,
                    login=listing.seller,
                )

    return IngestionResult(
        processed_count=raw_count - invalid_count,
        created_count=created_count,
        updated_count=updated_count,
        invalid_count=invalid_count,
    )


def _listing_changed(existing: sqlite3.Row, values: dict[str, Any]) -> bool:
    return (
        int(existing["price_cents"]) != values["price_cents"]
        or (existing["shipping_cents"] is None) != (values["shipping_cents"] is None)
        or (
            existing["shipping_cents"] is not None
            and values["shipping_cents"] is not None
            and int(existing["shipping_cents"]) != values["shipping_cents"]
        )
        or existing["currency"] != values["currency"]
        or existing["seller"] != values["seller"]
        or existing["url"] != values["url"]
        or existing["name"] != values["name"]
        or existing["set_name"] != values["set_name"]
        or existing["original_title"] != values["original_title"]
        or existing["raw_data"] != values["raw_data"]
        or existing["identification_status"] != values["identification_status"]
        or existing["reference_card_id"] != values["reference_card_id"]
    )


def _update_existing_listing(
    connection: sqlite3.Connection, existing: sqlite3.Row, values: dict[str, Any]
) -> None:
    connection.execute(
        """
        UPDATE catalog_items SET
            name = ?, set_name = ?, card_number = ?, language = ?,
            condition = ?, variant = ?, edition = ?, grading_company = ?,
            grade = ?, certification_number = ?, price_cents = ?,
            currency = ?, seller = ?, url = ?, original_title = ?,
            last_seen_at = ?, published_at = ?, image_url = ?,
            shipping_cents = ?, seller_external_id = ?, is_active = ?, raw_data = ?,
            identification_status = ?, reference_card_id = ?,
            identification_confidence = ?, identification_reason = ?,
            is_lot = ?
        WHERE id = ?
        """,
        (
            values["name"],
            values["set_name"],
            values["card_number"],
            values["language"],
            values["condition"],
            values["variant"],
            values["edition"],
            values["grading_company"],
            values["grade"],
            values["certification_number"],
            values["price_cents"],
            values["currency"],
            values["seller"],
            values["url"],
            values["original_title"],
            values["last_seen_at"],
            values["published_at"],
            values["image_url"],
            values["shipping_cents"],
            values["seller_external_id"],
            values["is_active"],
            values["raw_data"],
            values["identification_status"],
            values["reference_card_id"],
            values["identification_confidence"],
            values["identification_reason"],
            values["is_lot"],
            existing["id"],
        ),
    )
