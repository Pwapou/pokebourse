"""Orchestrateur de recherche externe contrôlée (TCGdex, eBay et sources autorisées)."""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.collectors.ebay import collect_ebay_listings
from app.collectors.models import CollectedListing, CollectorError, ListingPlatform
from app.collectors.service import ingest_collected_listings
from app.identification.research import enqueue_search, get_search_by_id
from app.search.models import SearchFilters
from app.tcgdex.cache import TcgdexCache

logger = logging.getLogger(__name__)

ExternalSourceStatus = Literal[
    "idle",
    "queued",
    "running",
    "completed",
    "partial",
    "unavailable",
    "error",
]


class ExternalSearchItem(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    source: str
    external_id: str
    title: str
    price_cents: int
    currency: str = "EUR"
    shipping_cents: int | None = None
    seller: str | None = None
    seller_external_id: str | None = None
    url: str | None = None
    image_url: str | None = None
    condition: str | None = None
    raw_data: dict[str, Any] = Field(default_factory=dict)


class ExternalSourceReport(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    source: str
    source_name: str
    is_available: bool = True
    status: ExternalSourceStatus = "idle"
    criteria: dict[str, Any] = Field(default_factory=dict)
    items: list[ExternalSearchItem] = Field(default_factory=list)
    total_found: int = 0
    partial: bool = False
    error_code: str | None = None
    error_message: str | None = None
    fetched_at: str | None = None
    duration_ms: int | None = None
    task_id: int | None = None
    info_message: str | None = None


class ExternalSearchSummary(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    query: str
    sources: dict[str, ExternalSourceReport]
    triggered_at: str


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def query_external_tcgdex(
    connection: sqlite3.Connection,
    filters: SearchFilters,
) -> ExternalSourceReport:
    """Enfile une recherche de référence ciblée via la file persistante du worker.
    
    Aucun appel réseau direct n'est effectué pendant la requête web ; la demande
    est dédupliquée et traitée en tâche de fond par le worker existant.
    """
    clean_text = filters.q.strip()
    clean_set = filters.set_name.strip()

    if not clean_text and not clean_set:
        return ExternalSourceReport(
            source="tcgdex",
            source_name="TCGdex (Référentiel officiel)",
            is_available=True,
            status="idle",
            info_message="Indiquez un nom, un numéro de carte ou une extension pour interroger TCGdex.",
        )

    criteria: dict[str, str] = {}
    if clean_text:
        # Si le texte contient uniquement des chiffres ou des chiffres avec slash (ex 58 ou 58/102)
        if clean_text.isdigit() or ("/" in clean_text and clean_text.split("/")[0].strip().isdigit()):
            criteria["local_id"] = clean_text.split("/")[0].strip()
        elif "-" in clean_text and len(clean_text) < 30 and not " " in clean_text:
            criteria["tcgdex_id"] = clean_text
        else:
            criteria["name"] = clean_text
    if clean_set:
        criteria["set_name"] = clean_set

    try:
        with connection:
            search_id = enqueue_search(connection, item_id=None, criteria=criteria)
        row = get_search_by_id(connection, search_id)
        status: ExternalSourceStatus = "queued"
        items: list[ExternalSearchItem] = []
        info = "Demande transmise à la file persistante TCGdex. Le worker la traitera à son prochain passage."

        if row:
            db_status = row["status"]
            if db_status == "completed":
                status = "completed"
                card_ids_raw = row["result_card_ids_json"]
                if card_ids_raw:
                    try:
                        card_ids = json.loads(card_ids_raw)
                        cache = TcgdexCache(connection)
                        cards = cache.get_cards_by_ids(card_ids)
                        for c in cards:
                            items.append(
                                ExternalSearchItem(
                                    source="tcgdex",
                                    external_id=c.tcgdex_id,
                                    title=f"{c.name} ({c.set_name} #{c.local_id})",
                                    price_cents=0,
                                    currency="EUR",
                                    url=f"https://www.tcgdex.net/cards/{c.tcgdex_id}",
                                    image_url=c.image_url,
                                    raw_data={"tcgdex_id": c.tcgdex_id, "local_id": c.local_id, "rarity": c.rarity},
                                )
                            )
                        info = f"{len(items)} carte(s) trouvée(s) et synchronisée(s) dans le cache local."
                    except Exception as err:
                        logger.warning("Erreur lors de la lecture des cartes TCGdex : %s", err)
            elif db_status == "running":
                status = "running"
                info = "Recherche TCGdex en cours d'exécution par le worker."
            elif db_status == "empty":
                status = "completed"
                info = "TCGdex ne référence aucune carte correspondant exactement à ces critères."
            elif db_status == "failed":
                status = "error"
                info = f"Échec de la recherche TCGdex : {row['error_message'] or 'Erreur inconnue'}"

        return ExternalSourceReport(
            source="tcgdex",
            source_name="TCGdex (Référentiel officiel)",
            is_available=True,
            status=status,
            criteria=criteria,
            task_id=search_id,
            items=items,
            total_found=len(items),
            fetched_at=row["updated_at"] if row else _utc_now_iso(),
            info_message=info,
        )
    except Exception as error:
        logger.warning("Impossible d'enfiler la recherche TCGdex : %s", error)
        return ExternalSourceReport(
            source="tcgdex",
            source_name="TCGdex (Référentiel officiel)",
            is_available=True,
            status="error",
            criteria=criteria,
            error_code="enqueue_error",
            error_message=str(error),
            info_message=f"Erreur d'enregistrement : {error}",
        )


def query_external_ebay(
    filters: SearchFilters,
    *,
    search_func: Any = None,
) -> ExternalSourceReport:
    """Interroge eBay de façon bornée avec timeout et isolation des erreurs."""
    clean_text = filters.q.strip()
    if not clean_text and filters.set_name.strip():
        clean_text = filters.set_name.strip()

    if not clean_text:
        return ExternalSourceReport(
            source="ebay",
            source_name="eBay",
            is_available=True,
            status="idle",
            info_message="Indiquez des mots-clés de recherche pour interroger eBay.",
        )

    criteria = {
        "search_text": clean_text,
        "price_from": filters.price_min_cents,
        "price_to": filters.price_max_cents,
    }

    start = time.perf_counter()
    try:
        result = collect_ebay_listings(
            search_text=clean_text,
            price_from=filters.price_min_cents,
            price_to=filters.price_max_cents,
            per_page=25,
            search_func=search_func,
        )
        duration_ms = int((time.perf_counter() - start) * 1000)

        items: list[ExternalSearchItem] = []
        for l in result.listings:
            items.append(
                ExternalSearchItem(
                    source="ebay",
                    external_id=l.external_id,
                    title=l.title,
                    price_cents=l.price_cents,
                    currency=l.currency,
                    shipping_cents=l.shipping_cents,
                    seller=l.seller,
                    seller_external_id=l.seller_external_id,
                    url=str(l.url) if l.url else None,
                    image_url=str(l.image_url) if l.image_url else None,
                    raw_data=l.raw_data or {},
                )
            )

        status: ExternalSourceStatus = "completed"
        if result.invalid_count > 0:
            status = "partial"

        return ExternalSourceReport(
            source="ebay",
            source_name="eBay",
            is_available=True,
            status=status,
            criteria=criteria,
            items=items,
            total_found=len(items),
            partial=result.invalid_count > 0,
            fetched_at=_utc_now_iso(),
            duration_ms=duration_ms,
            info_message=f"{len(items)} annonce(s) trouvée(s) sur eBay.",
        )
    except CollectorError as error:
        duration_ms = int((time.perf_counter() - start) * 1000)
        return ExternalSourceReport(
            source="ebay",
            source_name="eBay",
            is_available=True,
            status="error",
            criteria=criteria,
            error_code="collector_error",
            error_message=str(error),
            duration_ms=duration_ms,
            info_message=f"Recherche eBay indisponible : {error}",
        )
    except Exception as error:
        duration_ms = int((time.perf_counter() - start) * 1000)
        return ExternalSourceReport(
            source="ebay",
            source_name="eBay",
            is_available=True,
            status="error",
            criteria=criteria,
            error_code="network_error",
            error_message=str(error),
            duration_ms=duration_ms,
            info_message="Erreur réseau lors de la communication avec eBay.",
        )


def report_unavailable_marketplace(
    platform_key: str,
    platform_name: str,
    reason: str,
) -> ExternalSourceReport:
    """Rapporte une source marketplace non autorisée en conformité avec SOURCES.md."""
    return ExternalSourceReport(
        source=platform_key,
        source_name=platform_name,
        is_available=False,
        status="unavailable",
        info_message=reason,
    )


def execute_external_search(
    connection: sqlite3.Connection,
    filters: SearchFilters,
    *,
    ebay_search_func: Any = None,
) -> ExternalSearchSummary:
    """Orchestre la recherche externe sur toutes les sources configurées.
    
    Aucune transaction SQLite n'est maintenue ouverte pendant les requêtes réseau.
    Les erreurs d'une source n'impactent pas les autres sources.
    """
    now_iso = _utc_now_iso()
    sources_reports: dict[str, ExternalSourceReport] = {}

    # 1. TCGdex (asynchrone via file persistante SQLite)
    tcgdex_report = query_external_tcgdex(connection, filters)
    sources_reports["tcgdex"] = tcgdex_report

    # 2. eBay (autorisé)
    ebay_report = query_external_ebay(filters, search_func=ebay_search_func)
    sources_reports["ebay"] = ebay_report

    # 3. Vinted (non autorisé en scraping direct selon SOURCES.md)
    vinted_report = report_unavailable_marketplace(
        platform_key="vinted",
        platform_name="Vinted",
        reason=(
            "Collecte directe non autorisée par les CGU Vinted (protection anti-bot). "
            "Utilisez l'extension Pokébourse Capture ou l'import de fichier JSONL."
        ),
    )
    sources_reports["vinted"] = vinted_report

    # 4. Leboncoin (non autorisé en scraping direct selon SOURCES.md)
    leboncoin_report = report_unavailable_marketplace(
        platform_key="leboncoin",
        platform_name="Leboncoin",
        reason=(
            "Collecte directe non autorisée par les CGU Leboncoin (protection DataDome). "
            "Utilisez l'extension Pokébourse Capture ou l'import de fichier JSONL."
        ),
    )
    sources_reports["leboncoin"] = leboncoin_report

    return ExternalSearchSummary(
        query=filters.q,
        sources=sources_reports,
        triggered_at=now_iso,
    )


def import_external_listing(
    connection: sqlite3.Connection,
    item: ExternalSearchItem,
) -> int:
    """Importe une annonce externe retenue avec déduplication stricte et intégrité."""
    if item.source != "ebay":
        raise ValueError("Seules les annonces eBay obtenues par la recherche externe sont importables.")
    platform: ListingPlatform = "ebay"

    item_url = item.url
    if not item_url:
        if platform == "ebay":
            item_url = f"https://www.ebay.fr/itm/{item.external_id}"
        elif platform == "vinted":
            item_url = f"https://www.vinted.fr/items/{item.external_id}"
        elif platform == "leboncoin":
            item_url = f"https://www.leboncoin.fr/ad/{item.external_id}"
        elif platform == "wallapop":
            item_url = f"https://es.wallapop.com/item/{item.external_id}"
        else:
            item_url = f"https://www.ebay.fr/itm/{item.external_id}"

    collected = CollectedListing(
        source=platform,
        external_id=item.external_id,
        title=item.title,
        price_cents=item.price_cents,
        shipping_cents=item.shipping_cents,
        currency=item.currency,
        url=item_url,
        image_url=item.image_url,
        seller=item.seller,
        seller_external_id=item.seller_external_id,
        raw_data=item.raw_data or {"title": item.title, "external_id": item.external_id},
    )

    # Création d'un batch d'import pour lier l'annonce
    source_name = platform
    with connection:
        connection.execute(
            """
            INSERT INTO sources (name, kind, enabled)
            VALUES (?, 'api', 1)
            ON CONFLICT(name) DO UPDATE SET enabled = 1
            """,
            (source_name,),
        )
        source_id = connection.execute(
            "SELECT id FROM sources WHERE name = ?", (source_name,)
        ).fetchone()[0]

        checksum = f"external-{item.source}-{item.external_id}"
        connection.execute(
            """
            INSERT INTO import_batches (source_id, input_checksum, status)
            VALUES (?, ?, 'completed')
            ON CONFLICT(source_id, input_checksum) DO UPDATE SET status = 'completed'
            """,
            (source_id, checksum),
        )
        batch_id = int(
            connection.execute(
                "SELECT id FROM import_batches WHERE source_id = ? AND input_checksum = ?",
                (source_id, checksum),
            ).fetchone()[0]
        )

    ingest_result = ingest_collected_listings(
        connection,
        [collected],
        platform=platform,
        import_batch_id=batch_id,
    )

    if ingest_result.created_count == 0 and ingest_result.updated_count == 0:
        if ingest_result.invalid_count > 0:
            raise ValueError("Données d'annonce externe invalides pour l'import.")

    # Récupération de l'identifiant catalog_items
    row = connection.execute(
        "SELECT id FROM catalog_items WHERE source_id = ? AND external_id = ?",
        (source_id, item.external_id),
    ).fetchone()
    if row is None:
        raise LookupError("L'annonce n'a pas pu être retrouvée après ingestion.")
    return int(row["id"])
