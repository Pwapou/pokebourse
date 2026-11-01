import json
import logging
import sqlite3
from collections.abc import Callable
from typing import Any

from app.collectors.ebay import collect_ebay_listings
from app.collectors.leboncoin import collect_leboncoin_listings
from app.collectors.models import CollectionResult, CollectorError
from app.collectors.service import ingest_collected_listings
from app.collectors.vinted import collect_vinted_listings
from app.collectors.wallapop import collect_wallapop_listings
from app.monitoring import repository
from app.monitoring.models import (
    WatchAlreadyRunningError,
    WatchInput,
    WatchNotFoundError,
    WatchValidationError,
)

logger = logging.getLogger(__name__)

Collector = Callable[..., CollectionResult]


def default_collectors() -> dict[str, Collector]:
    return {
        "vinted": lambda **params: collect_vinted_listings(
            search_text=params["search_text"],
            price_from=params.get("price_from"),
            price_to=params.get("price_to"),
        ),
        "leboncoin": lambda **params: collect_leboncoin_listings(
            text=params["search_text"],
            price_from=params.get("price_from"),
            price_to=params.get("price_to"),
            category=params.get("category"),
        ),
        "ebay": lambda **params: collect_ebay_listings(
            search_text=params["search_text"],
            price_from=params.get("price_from"),
            price_to=params.get("price_to"),
        ),
        "wallapop": lambda **params: collect_wallapop_listings(
            search_text=params["search_text"],
            price_from=params.get("price_from"),
            price_to=params.get("price_to"),
        ),
    }


class WatchService:
    def __init__(
        self,
        *,
        min_interval_seconds: int = 120,
        collectors: dict[str, Collector] | None = None,
    ) -> None:
        self.min_interval_seconds = min_interval_seconds
        self.collectors = collectors or default_collectors()

    def list_watches(self, connection: sqlite3.Connection) -> list[sqlite3.Row]:
        return repository.list_watches(connection)

    def create_watch(self, connection: sqlite3.Connection, watch: WatchInput) -> int:
        try:
            return repository.create_watch(
                connection,
                watch,
                min_interval_seconds=self.min_interval_seconds,
            )
        except ValueError as error:
            raise WatchValidationError(str(error)) from error

    def update_watch(
        self, connection: sqlite3.Connection, watch_id: int, watch: WatchInput
    ) -> None:
        try:
            repository.update_watch(
                connection,
                watch_id,
                watch,
                min_interval_seconds=self.min_interval_seconds,
            )
        except ValueError as error:
            raise WatchValidationError(str(error)) from error

    def pause_watch(self, connection: sqlite3.Connection, watch_id: int) -> None:
        repository.set_watch_active(connection, watch_id, False)

    def resume_watch(self, connection: sqlite3.Connection, watch_id: int) -> None:
        repository.set_watch_active(connection, watch_id, True)

    def delete_watch(self, connection: sqlite3.Connection, watch_id: int) -> None:
        repository.delete_watch(connection, watch_id)

    def run_watch_once(
        self, connection: sqlite3.Connection, watch_id: int
    ) -> dict[str, Any]:
        """Exécute une veille une seule fois et consolide ses résultats."""

        watch = repository.get_watch(connection, watch_id)
        collector = self.collectors.get(watch["platform"])
        if collector is None:
            raise CollectorError("Plateforme de veille inconnue.")
        try:
            params = json.loads(watch["search_params"])
            if not isinstance(params, dict) or not params.get("search_text"):
                raise WatchValidationError("Paramètres de recherche invalides.")
        except json.JSONDecodeError as error:
            raise WatchValidationError("Paramètres de recherche invalides.") from error

        run_id = repository.start_run(connection, watch)
        result_count = 0
        created_count = 0
        updated_count = 0
        invalid_count = 0
        try:
            collection = collector(**params)
            result_count = len(collection.listings) + collection.invalid_count
            invalid_count = collection.invalid_count
            batch_id = self._run_batch_id(connection, run_id)
            ingestion = ingest_collected_listings(
                connection,
                collection.listings,
                platform=watch["platform"],
                import_batch_id=batch_id,
            )
            created_count = ingestion.created_count
            updated_count = ingestion.updated_count
            invalid_count += ingestion.invalid_count
            repository.finish_run(
                connection,
                run_id,
                status="success",
                result_count=result_count,
                created_count=created_count,
                updated_count=updated_count,
                invalid_count=invalid_count,
            )
        except Exception as error:
            message = str(error) or type(error).__name__
            repository.finish_run(
                connection,
                run_id,
                status="failed",
                result_count=result_count,
                created_count=created_count,
                updated_count=updated_count,
                invalid_count=invalid_count,
                error_message=message,
            )
            if isinstance(error, (CollectorError, WatchValidationError)):
                raise
            raise CollectorError("Exécution de la veille impossible.") from error

        logger.info(
            "Veille %d exécutée : %d résultat(s), %d créée(s), %d mise(s) à jour.",
            watch_id,
            result_count,
            created_count,
            updated_count,
        )
        return {
            "run_id": run_id,
            "watch_id": watch_id,
            "status": "success",
            "result_count": result_count,
            "created_count": created_count,
            "updated_count": updated_count,
            "invalid_count": invalid_count,
        }

    @staticmethod
    def _run_batch_id(connection: sqlite3.Connection, run_id: int) -> int:
        row = connection.execute(
            "SELECT import_batch_id FROM listing_watch_runs WHERE id = ?", (run_id,)
        ).fetchone()
        if row is None or row["import_batch_id"] is None:
            raise CollectorError("Lot d'ingestion introuvable pour l'exécution.")
        return int(row["import_batch_id"])


__all__ = [
    "WatchAlreadyRunningError",
    "WatchNotFoundError",
    "WatchService",
    "WatchValidationError",
]
