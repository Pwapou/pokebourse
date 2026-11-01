"""Supervision des agents de scraping.

Ce paquet contient le contrat partagé (états, codes d'erreur, erreur
structurée), la classification des erreurs côté agent, le suivi backend
(SQLite) et le récepteur utilisé par le worker. L'agent, le backend et
l'interface consomment tous les mêmes définitions de ``app.supervision.models``.
"""

from app.supervision.models import (
    AGENT_STATES,
    ERROR_CODES,
    AgentState,
    ErrorCode,
    StructuredError,
    SupervisionThresholds,
    TransitionRule,
    transition_for,
)

__all__ = [
    "AGENT_STATES",
    "ERROR_CODES",
    "AgentState",
    "ErrorCode",
    "StructuredError",
    "SupervisionThresholds",
    "TransitionRule",
    "transition_for",
]
