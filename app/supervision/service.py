"""Suivi backend des agents : états, seuils, suspension et exposition."""

import logging
import socket
import sqlite3
from collections import deque
from pathlib import Path
from typing import Any

from app.storage.database import connect
from app.supervision import repository
from app.supervision.errors import heartbeat_lost_error, is_blocking, validate_report_safety
from app.supervision.models import (
    StructuredError,
    SupervisionThresholds,
    transition_for,
    utc_now,
)
from app.supervision.thresholds import is_stale

logger = logging.getLogger(__name__)

DEFAULT_COLLECTOR_SITES: dict[str, str] = {
    "vinted": "Vinted",
    "leboncoin": "Leboncoin",
    "ebay": "eBay",
    "wallapop": "Wallapop",
}

SUPPORTED_PLATFORMS: tuple[str, ...] = ("vinted", "leboncoin", "ebay", "wallapop")


def default_agent_key() -> str:
    """Clé d'agent stable pour ce déploiement (hostname + répertoire de données)."""

    return f"pokebourse-worker@{socket.gethostname()}"


def detect_public_ip(probe_url: str | None, *, timeout_seconds: float = 5.0) -> str | None:
    """Récupère l'IP publique de sortie effective, ou ``None`` (IP inconnue).

    Aucune sonde n'est effectuée par défaut : sans URL configurée, l'IP reste
    inconnue et l'interface affiche « IP inconnue ».
    """

    if not probe_url:
        return None
    try:
        import urllib.request

        with urllib.request.urlopen(probe_url, timeout=timeout_seconds) as response:
            body = response.read(200).decode("utf-8", errors="replace").strip()
        return body or None
    except Exception as error:  # sonde indicative uniquement
        logger.info("Détection d'IP publique impossible : %s", type(error).__name__)
        return None


class SupervisionService:
    """Reçoit les rapports de l'agent et applique le contrat de supervision."""

    def __init__(
        self,
        database_path: Path,
        *,
        thresholds: SupervisionThresholds | None = None,
        agent_key: str | None = None,
        agent_name: str = "Worker de veilles Pokébourse",
        deployment_id: str | None = None,
        ip_probe_url: str | None = None,
    ) -> None:
        self.database_path = database_path
        self.thresholds = thresholds or SupervisionThresholds()
        self.agent_key = agent_key or default_agent_key()
        self.agent_name = agent_name
        self.deployment_id = deployment_id or self.agent_key
        self.ip_probe_url = ip_probe_url
        self._deferred: deque[StructuredError] = deque(
            maxlen=self.thresholds.max_deferred_errors
        )
        self._consecutive_errors: dict[str, int] = {}
        self._consecutive_blocks: dict[str, int] = {}
        self.agent_id: int | None = None
        self.public_ip: str | None = None

    # -- Enregistrement et cycle de vie --------------------------------------

    def register(self, connection: sqlite3.Connection) -> int:
        """Enregistre le déploiement et l'initialise à l'état « en démarrage »."""

        self.public_ip = detect_public_ip(self.ip_probe_url)
        collectors = tuple(
            (key, DEFAULT_COLLECTOR_SITES[key]) for key in SUPPORTED_PLATFORMS
        )
        self.agent_id = repository.register_agent(
            connection,
            agent_key=self.agent_key,
            name=self.agent_name,
            deployment_id=self.deployment_id,
            public_ip=self.public_ip,
            collectors=collectors,
        )
        repository.set_process_state(
            connection,
            agent_id=self.agent_id,
            to_state="starting",
            message="Agent enregistré ou réenregistré.",
        )
        connection.execute(
            """
            UPDATE supervision_collectors SET state = 'starting', suspended_until = NULL
            WHERE agent_id = ?
            """,
            (self.agent_id,),
        )
        logger.info(
            "Agent de supervision enregistré : %s (id %s).",
            self.agent_key,
            self.agent_id,
        )
        return self.agent_id

    def mark_operational(self, connection: sqlite3.Connection) -> None:
        """Passe le processus à « opérationnel » après son initialisation."""

        self._require_agent()
        self._transition_process(connection, "operational", "Initialisation terminée.")
        for key in SUPPORTED_PLATFORMS:
            state = repository.collector_state(
                connection, agent_id=self.agent_id, collector_key=key  # type: ignore[arg-type]
            )
            if state is not None and state["state"] == "starting":
                repository.record_collector_state(
                    connection,
                    agent_id=self.agent_id,  # type: ignore[arg-type]
                    collector_key=key,
                    to_state="operational",
                    message="Collecteur initialisé.",
                )

    def request_stop(self, connection: sqlite3.Connection) -> None:
        """Consigne un arrêt volontaire : l'agent reste identifié comme arrêté."""

        self._require_agent()
        self._transition_process(
            connection,
            "stopped",
            "Arrêt volontaire du worker.",
            stop_reason="voluntary",
        )

    # -- Signaux de vie -------------------------------------------------------

    def heartbeat(self, connection: sqlite3.Connection) -> None:
        """Reçoit un signal de vie ; ne touche jamais l'état des collecteurs."""

        self._require_agent()
        stale_states = ("offline",)
        row = connection.execute(
            "SELECT process_state FROM supervision_agents WHERE id = ?",
            (self.agent_id,),
        ).fetchone()
        if row is not None and str(row["process_state"]) in stale_states:
            self._transition_process(
                connection, "operational", "Signal de vie retrouvé."
            )
        repository.record_heartbeat(
            connection,
            agent_id=self.agent_id,  # type: ignore[arg-type]
            public_ip=self.public_ip,
            collector_ips={key: self.public_ip for key in SUPPORTED_PLATFORMS},
        )
        self._flush_deferred(connection)

    def check_offline_agents(
        self, connection: sqlite3.Connection, *, now: str | None = None
    ) -> list[int]:
        """Passe hors ligne les agents dont le signal de vie a été perdu."""

        lost = repository.mark_lost_agents(
            connection,
            now=now or utc_now(),
            offline_after_seconds=self.thresholds.offline_after_seconds,
        )
        if self.agent_id is not None and self.agent_id in lost:
            error = heartbeat_lost_error()
            for key in SUPPORTED_PLATFORMS:
                self._consecutive_errors[key] = 0
                self._consecutive_blocks[key] = 0
        for agent_id in lost:
            logger.warning("Agent %s passé hors ligne (signal de vie perdu).", agent_id)
        return lost

    # -- Rapports de collecte --------------------------------------------------

    def report_success(
        self,
        connection: sqlite3.Connection,
        *,
        collector_key: str,
        result_count: int,
        occurred_at: str | None = None,
    ) -> None:
        """Une collecte réussie répare le collecteur : retour à « opérationnel »."""

        self._require_agent()
        self._consecutive_errors[collector_key] = 0
        self._consecutive_blocks[collector_key] = 0
        repository.record_collector_success(
            connection,
            agent_id=self.agent_id,  # type: ignore[arg-type]
            collector_key=collector_key,
            result_count=result_count,
            occurred_at=occurred_at,
        )

    def report_error(
        self,
        connection: sqlite3.Connection,
        *,
        collector_key: str,
        error: StructuredError,
    ) -> str:
        """Applique le contrat à une erreur structurée reçue de l'agent.

        Retourne l'état résultant du collecteur. Les erreurs temporaires
        dégradent après un seuil de répétitions ; un blocage confirmé suspend
        le collecteur concerné sans interrompre les autres.
        """

        self._require_agent()
        safety = validate_report_safety(error.model_dump())
        if safety:
            logger.error("Rapport d'erreur rejeté (secret détecté) : %s", safety)
            raise ValueError("Le rapport contient des données sensibles.")
        current = repository.collector_state(
            connection, agent_id=self.agent_id, collector_key=collector_key  # type: ignore[arg-type]
        )
        if current is None:
            raise LookupError(f"Collecteur inconnu : {collector_key}")

        if is_blocking(error):
            self._consecutive_blocks[collector_key] = (
                self._consecutive_blocks.get(collector_key, 0) + 1
            )
            if (
                self._consecutive_blocks[collector_key]
                >= self.thresholds.blocked_after_consecutive_blocks
            ):
                to_state = "blocked"
            else:
                to_state = "degraded"
        elif error.transient:
            self._consecutive_errors[collector_key] = (
                self._consecutive_errors.get(collector_key, 0) + 1
            )
            self._consecutive_blocks[collector_key] = 0
            if (
                self._consecutive_errors[collector_key]
                >= self.thresholds.degraded_after_consecutive_errors
            ):
                to_state = "degraded"
            else:
                to_state = str(current["state"])
        else:
            to_state = "degraded"

        if to_state != str(current["state"]) and transition_for(
            str(current["state"]), to_state
        ) is None:
            to_state = str(current["state"])

        suspended_until = None
        if to_state == "blocked":
            suspended_until = self._suspend_deadline()
        repository.record_collector_error(
            connection,
            agent_id=self.agent_id,  # type: ignore[arg-type]
            collector_key=collector_key,
            error=error,
            to_state=to_state,
            suspended_until=suspended_until,
        )
        logger.warning(
            "Collecteur %s : %s (%s) → état %s.",
            collector_key,
            error.code,
            error.correlation_id,
            to_state,
        )
        return to_state

    def resume_collector(
        self, connection: sqlite3.Connection, *, collector_key: str
    ) -> None:
        """Relance manuellement un collecteur suspendu."""

        self._require_agent()
        self._consecutive_errors[collector_key] = 0
        self._consecutive_blocks[collector_key] = 0
        repository.record_collector_state(
            connection,
            agent_id=self.agent_id,  # type: ignore[arg-type]
            collector_key=collector_key,
            to_state="operational",
            message="Reprise manuelle du collecteur.",
        )

    def is_collector_suspended(
        self, connection: sqlite3.Connection, *, collector_key: str, now: str | None = None
    ) -> bool:
        """Un collecteur bloqué est suspendu tant que son délai n'est pas échu."""

        self._require_agent()
        current_now = now or utc_now()
        row = repository.collector_state(
            connection, agent_id=self.agent_id, collector_key=collector_key  # type: ignore[arg-type]
        )
        if row is None or row["state"] != "blocked":
            return False
        return self._suspension_active(row, current_now)

    def _suspension_active(self, row: dict[str, Any], now: str) -> bool:
        until = row.get("suspended_until")
        return until is not None and str(until) > now

    # -- Transmission différée bornée -------------------------------------------

    def defer(self, error: StructuredError) -> None:
        """Met en attente un rapport impossible à transmettre (file bornée)."""

        self._deferred.append(error)

    def _flush_deferred(self, connection: sqlite3.Connection) -> None:
        while self._deferred:
            error = self._deferred.popleft()
            try:
                connection.execute(
                    """
                    INSERT INTO supervision_events (
                        agent_id, event_type, error_code, message, http_status,
                        correlation_id, occurred_at, received_at
                    ) VALUES (?, 'error', ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.agent_id,
                        error.code,
                        error.message,
                        error.http_status,
                        error.correlation_id,
                        error.occurred_at,
                        utc_now(),
                    ),
                )
                connection.commit()
            except sqlite3.Error:
                self._deferred.appendleft(error)
                logger.warning("Transmission différée impossible pour l'instant.")
                break

    # -- Exposition à l'interface ------------------------------------------------

    def list_agents(self, connection: sqlite3.Connection) -> list[dict[str, Any]]:
        now = utc_now()
        agents = repository.list_agents(connection)
        for agent in agents:
            heartbeat = agent.get("last_heartbeat_at")
            agent["is_stale"] = (
                heartbeat is None
                or is_stale(str(heartbeat), now, self.thresholds.offline_after_seconds)
            ) and agent["process_state"] not in ("stopped",)
            for collector in agent["collectors"]:
                until = collector.get("suspended_until")
                collector["suspension_active"] = (
                    collector["state"] == "blocked"
                    and until is not None
                    and str(until) > now
                )
        return agents

    def agent_detail(
        self, connection: sqlite3.Connection, agent_id: int
    ) -> dict[str, Any] | None:
        return repository.agent_detail(connection, agent_id)

    # -- Internes -----------------------------------------------------------------

    def _transition_process(
        self,
        connection: sqlite3.Connection,
        to_state: str,
        message: str,
        *,
        stop_reason: str | None = None,
    ) -> None:
        row = connection.execute(
            "SELECT process_state FROM supervision_agents WHERE id = ?",
            (self.agent_id,),
        ).fetchone()
        if row is None:
            return
        from_state = str(row["process_state"])
        if from_state == to_state:
            return
        if transition_for(from_state, to_state) is None:
            logger.info(
                "Transition processus %s → %s non autorisée, ignorée.",
                from_state,
                to_state,
            )
            return
        repository.set_process_state(
            connection,
            agent_id=self.agent_id,  # type: ignore[arg-type]
            to_state=to_state,
            message=message,
            stop_reason=stop_reason,
        )

    def _suspend_deadline(self) -> str:
        from datetime import timedelta

        from app.supervision.thresholds import parse_utc

        deadline = parse_utc(utc_now()) + timedelta(
            seconds=self.thresholds.suspend_seconds
        )
        return deadline.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def _require_agent(self) -> None:
        if self.agent_id is None:
            raise RuntimeError("Agent non enregistré : appeler register() d'abord.")


__all__ = [
    "DEFAULT_COLLECTOR_SITES",
    "SUPPORTED_PLATFORMS",
    "SupervisionService",
    "default_agent_key",
    "detect_public_ip",
]
