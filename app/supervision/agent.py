"""Intégration de la supervision dans la planification des veilles.

Le superviseur entoure chaque collecte : il vérifie la suspension du
collecteur, transforme les exceptions en erreurs structurées et applique le
contrat de supervision. Le blocage d'un collecteur ne touche jamais les
collecteurs indépendants.
"""

import logging
import sqlite3
from typing import Any

from app.supervision.errors import classify_error, extraction_failed_error
from app.supervision.models import StructuredError
from app.supervision.service import SupervisionService

logger = logging.getLogger(__name__)


class WatchSupervisor:
    """Adapte le SupervisionService au cycle d'exécution des veilles."""

    def __init__(self, service: SupervisionService) -> None:
        self.service = service

    def initialize(self, connection: sqlite3.Connection) -> None:
        self.service.register(connection)
        self.service.mark_operational(connection)
        self.service.check_offline_agents(connection)

    def heartbeat(self, connection: sqlite3.Connection) -> None:
        try:
            self.service.heartbeat(connection)
        except sqlite3.Error as error:
            logger.warning("Signal de vie impossible à consigner : %s", error)

    def shutdown(self, connection: sqlite3.Connection) -> None:
        try:
            self.service.request_stop(connection)
        except sqlite3.Error as error:
            logger.warning("Arrêt volontaire impossible à consigner : %s", error)

    def is_suspended(self, connection: sqlite3.Connection, platform: str) -> bool:
        try:
            return self.service.is_collector_suspended(
                connection, collector_key=platform
            )
        except (sqlite3.Error, RuntimeError) as error:
            logger.warning("Suspension indécidable pour %s : %s", platform, error)
            return False

    def report_success(
        self, connection: sqlite3.Connection, *, platform: str, result_count: int
    ) -> None:
        try:
            self.service.report_success(
                connection, collector_key=platform, result_count=result_count
            )
        except sqlite3.Error as error:
            logger.warning("Succès de collecte impossible à consigner : %s", error)

    def report_failure(
        self, connection: sqlite3.Connection, *, platform: str, error: BaseException
    ) -> str | None:
        """Classe une exception en erreur structurée et l'applique au contrat.

        Retourne l'état résultant du collecteur, ou ``None`` si la consignation
        a échoué (la collecte doit quand même continuer ailleurs).
        """

        structured = classify_error(error)
        try:
            return self.service.report_error(
                connection, collector_key=platform, error=structured
            )
        except sqlite3.Error as db_error:
            logger.warning("Erreur de collecte impossible à consigner : %s", db_error)
            self.service.defer(structured)
            return None

    def report_extraction_failure(
        self, connection: sqlite3.Connection, *, platform: str, detail: str = ""
    ) -> str | None:
        structured: StructuredError = extraction_failed_error(detail)
        try:
            return self.service.report_error(
                connection, collector_key=platform, error=structured
            )
        except sqlite3.Error as db_error:
            logger.warning("Erreur d'extraction impossible à consigner : %s", db_error)
            self.service.defer(structured)
            return None


__all__ = ["WatchSupervisor"]
