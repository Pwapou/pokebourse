import logging
import sqlite3
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.config import Settings
from app.monitoring import repository
from app.monitoring.models import WatchAlreadyRunningError
from app.monitoring.service import WatchService
from app.storage.database import connect
from app.storage.migration_runner import apply_migrations
from app.sellers.service import SellerService
from app.supervision.agent import WatchSupervisor

logger = logging.getLogger(__name__)


class WatchScheduler:
    """Planifie les veilles avec au plus une exécution simultanée par plateforme."""

    def __init__(
        self,
        database_path: Path,
        *,
        settings: Settings | None = None,
        service: WatchService | None = None,
        supervisor: WatchSupervisor | None = None,
        seller_service: SellerService | None = None,
    ) -> None:
        self.database_path = database_path
        self.settings = settings or Settings.from_env()
        self.service = service or WatchService(
            min_interval_seconds=self.settings.min_watch_interval_seconds
        )
        self._supervisor = supervisor
        self._seller_service = seller_service
        self._platform_locks = {
            platform: threading.Lock()
            for platform in ("vinted", "leboncoin", "ebay", "wallapop")
        }

    def initialize(self) -> None:
        with connect(self.database_path) as connection:
            apply_migrations(connection)
            recovered = repository.recover_interrupted_runs(connection)
            if self._supervisor is not None:
                self._supervisor.initialize(connection)
        if recovered:
            logger.warning("%d exécution(s) interrompue(s) clôturée(s).", recovered)

    def tick(self, *, now: datetime | None = None) -> dict[str, int]:
        """Exécute les veilles actives dont l'intervalle est écoulé."""

        current_time = now or datetime.now(UTC)
        oldest_due = (current_time - timedelta(days=3650)).isoformat(
            timespec="milliseconds"
        ).replace("+00:00", "Z")
        summary = {"executed": 0, "failed": 0, "skipped": 0, "suspended": 0}
        for platform in ("vinted", "leboncoin", "ebay", "wallapop"):
            lock = self._platform_locks[platform]
            if not lock.acquire(blocking=False):
                summary["skipped"] += 1
                continue
            try:
                with connect(self.database_path) as connection:
                    if self._is_platform_suspended(connection, platform):
                        summary["suspended"] += 1
                        continue
                    candidates = repository.active_watches_due(
                        connection, now=oldest_due, platform=platform
                    )
                for watch in candidates:
                    if not self._is_due(watch, current_time):
                        continue
                    try:
                        with connect(self.database_path) as connection:
                            result = self.service.run_watch_once(
                                connection, int(watch["id"])
                            )
                        self._report_platform_success(platform, result)
                        summary["executed"] += 1
                    except WatchAlreadyRunningError:
                        logger.info("Veille %d déjà en cours ; passage suivant.", watch["id"])
                        summary["skipped"] += 1
                    except Exception as error:
                        # L'erreur est déjà persistée dans l'exécution par le
                        # service ; les autres veilles doivent continuer.
                        logger.warning(
                            "Échec isolé de la veille %d : %s", watch["id"], error
                        )
                        self._report_platform_failure(platform, error)
                        summary["failed"] += 1
            finally:
                lock.release()
        return summary

    def _is_platform_suspended(
        self, connection: sqlite3.Connection, platform: str
    ) -> bool:
        if self._supervisor is None:
            return False
        if not self._supervisor.is_suspended(connection, platform):
            return False
        logger.info("Collecteur %s suspendu ; veilles de cette plateforme ignorées.", platform)
        return True

    def _report_platform_success(
        self, platform: str, result: dict[str, Any]
    ) -> None:
        if self._supervisor is None:
            return
        with connect(self.database_path) as connection:
            self._supervisor.report_success(
                connection,
                platform=platform,
                result_count=int(result.get("result_count", 0)),
            )

    def _report_platform_failure(self, platform: str, error: BaseException) -> None:
        if self._supervisor is None:
            return
        with connect(self.database_path) as connection:
            self._supervisor.report_failure(connection, platform=platform, error=error)

    def _process_sellers(self) -> None:
        """Traite un quota borné de la file vendeur, incidents remontés."""

        def report_failure(platform: str, error: BaseException) -> None:
            if self._supervisor is not None:
                with connect(self.database_path) as connection:
                    self._supervisor.report_failure(
                        connection, platform=platform, error=error
                    )

        try:
            with connect(self.database_path) as connection:
                summary = self._seller_service.process_pending(  # type: ignore[union-attr]
                    connection, report_failure=report_failure
                )
            if summary["enriched"] or summary["failed"]:
                logger.info(
                    "Enrichissement vendeur : %d profil(s) collecté(s), %d en échec.",
                    summary["enriched"],
                    summary["failed"],
                )
        except sqlite3.Error as error:
            logger.warning("Enrichissement vendeur impossible pour l'instant : %s", error)

    def process_identification_searches(self) -> int:
        """Traite une recherche distante à la fois, hors des transactions SQLite."""
        from app.identification.research import claim_search, process_claimed_search
        from app.tcgdex.client import TcgdexClient

        processed = 0
        for _ in range(self.settings.tcgdex_searches_per_tick):
            with connect(self.database_path) as connection:
                claimed = claim_search(connection)
            if claimed is None:
                break
            with connect(self.database_path) as connection:
                process_claimed_search(connection, claimed, TcgdexClient(max_retries=1))
            processed += 1
        return processed

    def run_forever(self, stop_event: threading.Event) -> None:
        self.initialize()
        logger.info(
            "Worker de veilles démarré (poll %.1fs, intervalle minimum %ds).",
            self.settings.watch_poll_seconds,
            self.settings.min_watch_interval_seconds,
        )
        last_heartbeat = 0.0
        heartbeat_interval = (
            self._supervisor.service.thresholds.heartbeat_interval_seconds
            if self._supervisor
            else 0.0
        )
        try:
            while not stop_event.is_set():
                self.tick()
                if self._supervisor is not None:
                    if time.monotonic() - last_heartbeat >= heartbeat_interval:
                        with connect(self.database_path) as connection:
                            self._supervisor.heartbeat(connection)
                        last_heartbeat = time.monotonic()
                if self._seller_service is not None:
                    self._process_sellers()
                try:
                    if not self.process_identification_searches():
                        self.process_tcgdex_sync()
                except (sqlite3.Error, OSError) as error:
                    logger.warning("Recherche TCGdex reportée : %s", error)
                try:
                    self._sync_cardmarket_daily(stop_event)
                except Exception as error:
                    logger.warning("Synchronisation Cardmarket reportée : %s", error)
                stop_event.wait(self.settings.watch_poll_seconds)
        finally:
            if self._supervisor is not None:
                with connect(self.database_path) as connection:
                    self._supervisor.shutdown(connection)
        logger.info("Worker de veilles arrêté.")

    def process_tcgdex_sync(self) -> bool:
        """Avance d'une requête le référentiel demandé, avec priorité aux recherches ciblées."""
        from app.tcgdex.sync import process_sync_step
        with connect(self.database_path) as connection:
            return process_sync_step(connection, interval_seconds=self.settings.tcgdex_sync_interval_seconds)

    def _sync_cardmarket_daily(self, stop_event: threading.Event) -> None:
        """Synchronisation quotidienne des cotes + noms Cardmarket (price guide
        régénéré ~01:45 UTC ; synchro planifiée juste après)."""
        if stop_event.is_set():
            return
        from app.cardmarket import daily as cardmarket_daily

        with connect(self.database_path) as connection:
            result = cardmarket_daily.maybe_run_daily_sync(
                connection,
                run_time_utc=self.settings.cardmarket_daily_sync_utc,
            )
        if result is not None:
            logger.info(
                "Synchronisation Cardmarket quotidienne : %s.",
                cardmarket_daily.summarize(result),
            )

    @staticmethod
    def _is_due(watch: dict[str, Any], now: datetime) -> bool:
        last_run = watch.get("last_run_at")
        if not last_run:
            return True
        try:
            last_run_at = datetime.fromisoformat(str(last_run).replace("Z", "+00:00"))
        except ValueError:
            return True
        if last_run_at.tzinfo is None:
            last_run_at = last_run_at.replace(tzinfo=UTC)
        return now >= last_run_at + timedelta(seconds=int(watch["interval_seconds"]))


def run_worker(
    database_path: Path,
    *,
    settings: Settings | None = None,
    stop_event: threading.Event | None = None,
) -> None:
    """Point d'entrère réutilisable par le module worker et les tests."""

    scheduler = WatchScheduler(database_path, settings=settings)
    scheduler.run_forever(stop_event or threading.Event())
