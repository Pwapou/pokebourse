"""Enrichissement borné des profils vendeur, exécuté par le worker.

La file est traitée par petits quotas afin de respecter les plateformes :
en cas d'erreur, le vendeur est marqué en échec et l'incident remonte dans
la supervision du collecteur concerné — jamais de boucle de tentatives.
"""

import collections
import logging
import sqlite3
from collections.abc import Callable
from typing import Any

from app.profitability import enrich_catalog_items
from app.sellers import repository
from app.sellers.collect import PLATFORM_FETCHERS
from app.sellers.models import (
    SellerProfile,
    profile_from_row,
    reliability_rating,
)
from app.supervision.thresholds import is_stale

logger = logging.getLogger(__name__)

SellerFetcher = Callable[[str], SellerProfile]


class SellerService:
    def __init__(
        self,
        *,
        fetchers: dict[str, SellerFetcher] | None = None,
        per_tick: int = 3,
        cache_seconds: float = 86_400.0,
    ) -> None:
        self.fetchers = fetchers or dict(PLATFORM_FETCHERS)
        self.per_tick = max(1, per_tick)
        self.cache_seconds = cache_seconds

    def process_pending(
        self,
        connection: sqlite3.Connection,
        *,
        report_failure: Callable[[str, BaseException], Any] | None = None,
    ) -> dict[str, int]:
        """Traite un quota borné de la file et consolide les liens catalogue.

        Retourne les compteurs d'enrichissements réussis et en échec. Une
        erreur sur une plateforme ne bloque pas le traitement des autres.
        """

        summary = {"enriched": 0, "failed": 0}
        for pending in repository.pending_sellers(connection, limit=self.per_tick):
            platform = str(pending["platform"])
            seller_id = str(pending["seller_external_id"])
            fetcher = self.fetchers.get(platform)
            if fetcher is None:
                repository.mark_failed(connection, int(pending["id"]), "Plateforme inconnue.")
                summary["failed"] += 1
                continue
            try:
                profile = fetcher(seller_id)
            except Exception as error:
                message = str(error) or type(error).__name__
                repository.mark_failed(connection, int(pending["id"]), message)
                summary["failed"] += 1
                logger.warning(
                    "Enrichissement vendeur %s/%s en échec : %s",
                    platform,
                    seller_id,
                    message,
                )
                if report_failure is not None:
                    report_failure(platform, error)
                continue
            profile_id = repository.upsert_profile(connection, profile)
            repository.mark_done(connection, int(pending["id"]))
            self._relink_catalog_items(
                connection,
                platform=platform,
                seller_external_id=seller_id,
                profile_id=profile_id,
            )
            summary["enriched"] += 1
        return summary

    def profile_for_item(
        self,
        connection: sqlite3.Connection,
        *,
        platform: str | None,
        seller_profile_id: int | None,
        seller_external_id: str | None,
    ) -> dict[str, Any] | None:
        """Profil vendeur d'une annonce, rafraîchi si le cache est expiré."""

        profile_id = seller_profile_id
        if profile_id is None and platform and seller_external_id:
            profile_id = repository.find_profile_id(
                connection,
                platform=platform,
                seller_external_id=seller_external_id,
            )
        if profile_id is None:
            return None
        profile = repository.get_profile(connection, int(profile_id))
        if profile is None:
            return None
        if is_stale(str(profile["fetched_at"]), utc_now_text(), self.cache_seconds):
            self._schedule_refresh(
                connection,
                platform=str(profile["platform"]),
                seller_external_id=str(profile["seller_external_id"]),
                login=profile.get("login"),
            )
        return profile

    def list_sellers_directory(
        self,
        connection: sqlite3.Connection,
        *,
        platform: str | None = None,
        sort: str = "reputation",
        only_favorites: bool = False,
        query: str = "",
    ) -> list[dict[str, Any]]:
        """Référence et classe les vendeurs selon réputation, pépites ou volume d'achats."""

        raw_sellers = repository.list_sellers_with_aggregates(
            connection,
            platform=platform,
            only_favorites=only_favorites,
            query=query,
        )

        # Calcul des opportunités par vendeur depuis le catalogue
        seller_items = connection.execute(
            """
            SELECT c.*, s.name AS source_name
            FROM catalog_items c
            JOIN sources s ON s.id = c.source_id
            WHERE c.seller_profile_id IS NOT NULL
            """
        ).fetchall()

        opp_count: dict[int, int] = collections.defaultdict(int)
        if seller_items:
            enriched, _ = enrich_catalog_items(
                connection, [dict(r) for r in seller_items]
            )
            for it in enriched:
                if it.get("verdict") == "opportunite" and it.get("seller_profile_id"):
                    opp_count[int(it["seller_profile_id"])] += 1

        sellers: list[dict[str, Any]] = []
        for raw in raw_sellers:
            profile = profile_from_row(raw)
            rating = reliability_rating(profile)
            pid = int(raw["id"])
            item = dict(raw)
            item["profile"] = profile
            item["rating"] = rating
            item["opportunities_count"] = opp_count.get(pid, 0)
            sellers.append(item)

        if sort == "opportunities":
            sellers.sort(
                key=lambda s: (s["opportunities_count"], s["total_listings"]),
                reverse=True,
            )
        elif sort == "purchases":
            sellers.sort(
                key=lambda s: (s["purchases_count"], s["total_spent_cents"]),
                reverse=True,
            )
        elif sort == "name":
            sellers.sort(
                key=lambda s: (s.get("login") or s["seller_external_id"]).lower()
            )
        else:  # reputation
            sellers.sort(
                key=lambda s: (
                    s["rating"].stars if s["rating"].stars is not None else -1,
                    s.get("reputation_bps") or 0,
                    s.get("feedback_count") or 0,
                ),
                reverse=True,
            )

        return sellers

    def get_seller_summary(
        self, connection: sqlite3.Connection, profile_id: int
    ) -> dict[str, Any] | None:
        """Fiche complète d'un vendeur avec indicateurs, annonces et historique d'achats."""

        raw_profile = repository.get_profile(connection, profile_id)
        if raw_profile is None:
            return None
        profile = profile_from_row(raw_profile)
        rating = reliability_rating(profile)
        listings = repository.list_listings_for_seller(connection, profile_id)
        enriched_listings, fee_profile = enrich_catalog_items(connection, listings)
        purchases = repository.list_purchases(connection, seller_profile_id=profile_id)

        opportunities = [
            it for it in enriched_listings if it.get("verdict") == "opportunite"
        ]
        watches = [
            it for it in enriched_listings if it.get("verdict") == "surveiller"
        ]
        total_spent = sum(
            p.get("price_paid_cents", 0) + p.get("shipping_paid_cents", 0)
            for p in purchases
        )

        return {
            "profile": profile,
            "raw_profile": raw_profile,
            "rating": rating,
            "listings": enriched_listings,
            "fee_profile": fee_profile,
            "purchases": purchases,
            "total_listings": len(enriched_listings),
            "opportunities_count": len(opportunities),
            "watches_count": len(watches),
            "purchases_count": len(purchases),
            "total_spent_cents": total_spent,
        }

    def _schedule_refresh(
        self,
        connection: sqlite3.Connection,
        *,
        platform: str,
        seller_external_id: str,
        login: str | None,
    ) -> None:
        current = utc_now_text()
        with connection:
            connection.execute(
                """
                INSERT INTO seller_enrichment_queue (
                    platform, seller_external_id, login, status, created_at, updated_at
                ) VALUES (?, ?, ?, 'pending', ?, ?)
                ON CONFLICT (platform, seller_external_id) DO UPDATE SET
                    status = 'pending', login = excluded.login, updated_at = excluded.updated_at
                """,
                (platform, seller_external_id, login, current, current),
            )

    @staticmethod
    def _relink_catalog_items(
        connection: sqlite3.Connection,
        *,
        platform: str,
        seller_external_id: str,
        profile_id: int,
    ) -> None:
        source_id = connection.execute(
            "SELECT id FROM sources WHERE name = ?", (platform,)
        ).fetchone()
        if source_id is None:
            return
        with connection:
            connection.execute(
                """
                UPDATE catalog_items SET seller_profile_id = ?
                WHERE source_id = ? AND seller_external_id = ?
                """,
                (profile_id, int(source_id["id"]), seller_external_id),
            )


def utc_now_text() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


__all__ = ["SellerFetcher", "SellerService"]
