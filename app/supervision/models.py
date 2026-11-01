"""Contrat de supervision partagé entre agent, backend et interface.

Les états et codes définis ici sont la seule source de vérité : le worker
(agent), le service de suivi (backend) et les pages web consomment ces
mêmes littéraux. Toute évolution du contrat se fait dans ce module.
"""

from datetime import UTC, datetime
from typing import Literal
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# États
# ---------------------------------------------------------------------------

AgentState = Literal[
    "starting",
    "operational",
    "degraded",
    "blocked",
    "offline",
    "stopped",
]

AGENT_STATES: tuple[str, ...] = (
    "starting",
    "operational",
    "degraded",
    "blocked",
    "offline",
    "stopped",
)

STATE_LABELS: dict[str, str] = {
    "starting": "En démarrage",
    "operational": "Opérationnel",
    "degraded": "Dégradé",
    "blocked": "Bloqué",
    "offline": "Hors ligne",
    "stopped": "Arrêté",
}

# États considérés comme un fonctionnement nominal pour un collecteur.
HEALTHY_STATES: frozenset[str] = frozenset({"operational", "degraded"})

# ---------------------------------------------------------------------------
# Codes d'erreur internes
# ---------------------------------------------------------------------------

ErrorCode = Literal[
    "SCRAPE_ACCESS_DENIED",
    "SCRAPE_RATE_LIMITED",
    "SCRAPE_CHALLENGE_REQUIRED",
    "SCRAPE_AUTH_REQUIRED",
    "SCRAPE_TIMEOUT",
    "SCRAPE_NETWORK_ERROR",
    "SCRAPE_BROWSER_CRASH",
    "SCRAPE_EXTRACTION_FAILED",
    "SCRAPE_UNKNOWN_ERROR",
    "AGENT_HEARTBEAT_LOST",
]

ERROR_CODES: tuple[str, ...] = (
    "SCRAPE_ACCESS_DENIED",
    "SCRAPE_RATE_LIMITED",
    "SCRAPE_CHALLENGE_REQUIRED",
    "SCRAPE_AUTH_REQUIRED",
    "SCRAPE_TIMEOUT",
    "SCRAPE_NETWORK_ERROR",
    "SCRAPE_BROWSER_CRASH",
    "SCRAPE_EXTRACTION_FAILED",
    "SCRAPE_UNKNOWN_ERROR",
    "AGENT_HEARTBEAT_LOST",
)

ERROR_CODE_LABELS: dict[str, str] = {
    "SCRAPE_ACCESS_DENIED": "Accès refusé",
    "SCRAPE_RATE_LIMITED": "Limitation de requêtes",
    "SCRAPE_CHALLENGE_REQUIRED": "Vérification anti-bot requise",
    "SCRAPE_AUTH_REQUIRED": "Connexion requise",
    "SCRAPE_TIMEOUT": "Délai dépassé",
    "SCRAPE_NETWORK_ERROR": "Erreur réseau",
    "SCRAPE_BROWSER_CRASH": "Navigateur interrompu",
    "SCRAPE_EXTRACTION_FAILED": "Extraction impossible",
    "SCRAPE_UNKNOWN_ERROR": "Erreur non classée",
    "AGENT_HEARTBEAT_LOST": "Signal de vie perdu",
}

# Codes confirmant un blocage nécessitant une intervention : le collecteur
# concerné est suspendu, les autres collecteurs ne sont pas impactés.
BLOCKING_ERROR_CODES: frozenset[str] = frozenset(
    {
        "SCRAPE_ACCESS_DENIED",
        "SCRAPE_CHALLENGE_REQUIRED",
        "SCRAPE_AUTH_REQUIRED",
    }
)

# Codes correspondant à des erreurs temporaires : état dégradé, tentatives bornées.
TRANSIENT_ERROR_CODES: frozenset[str] = frozenset(
    {
        "SCRAPE_RATE_LIMITED",
        "SCRAPE_TIMEOUT",
        "SCRAPE_NETWORK_ERROR",
        "SCRAPE_BROWSER_CRASH",
        "SCRAPE_EXTRACTION_FAILED",
    }
)


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def new_correlation_id() -> str:
    return uuid.uuid4().hex[:16]


# ---------------------------------------------------------------------------
# Erreur structurée
# ---------------------------------------------------------------------------


class StructuredError(BaseModel):
    """Erreur de collecte telle que transmise à l'interface.

    Le code HTTP d'origine est conservé séparément du code interne : un statut
    HTTP seul ne suffit pas à identifier la cause exacte (un CAPTCHA peut être
    servi en HTTP 200). Aucun cookie, jeton ou mot de passe ne doit figurer
    dans ``message``.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    code: ErrorCode
    message: str = Field(min_length=1, max_length=500)
    occurred_at: str = Field(min_length=10, max_length=40)
    http_status: int | None = Field(default=None, ge=100, le=599)
    transient: bool
    correlation_id: str = Field(min_length=8, max_length=64)

    @field_validator("message")
    @classmethod
    def reject_secrets_in_message(cls, value: str) -> str:
        lowered = value.lower()
        for marker in ("cookie", "set-cookie", "authorization", "bearer ", "token", "password"):
            if marker in lowered:
                raise ValueError("le message d'erreur ne doit contenir aucun secret")
        return value


# ---------------------------------------------------------------------------
# Seuils configurables et règles de transition
# ---------------------------------------------------------------------------


class SupervisionThresholds(BaseModel):
    """Délais configurables de la supervision."""

    model_config = ConfigDict(frozen=True)

    heartbeat_interval_seconds: float = Field(default=30.0, gt=0, le=3600.0)
    offline_after_seconds: float = Field(default=90.0, gt=0, le=86_400.0)
    degraded_after_consecutive_errors: int = Field(default=3, ge=1, le=100)
    blocked_after_consecutive_blocks: int = Field(default=2, ge=1, le=20)
    suspend_seconds: float = Field(default=900.0, gt=0, le=86_400.0)
    max_deferred_errors: int = Field(default=100, ge=1, le=10_000)


class TransitionRule(BaseModel):
    """Règle de transition entre deux états."""

    model_config = ConfigDict(frozen=True)

    from_states: frozenset[str]
    to_state: AgentState
    reason: str


# Règles du contrat. Un signal de vie ne fait jamais passer un collecteur
# « bloqué » à « opérationnel » : seule une collecte réussie le permet.
TRANSITION_RULES: tuple[TransitionRule, ...] = (
    TransitionRule(
        from_states=frozenset({"starting"}),
        to_state="operational",
        reason="Initialisation terminée.",
    ),
    TransitionRule(
        from_states=frozenset({"operational"}),
        to_state="degraded",
        reason="Erreurs temporaires répétées perturbant la collecte.",
    ),
    TransitionRule(
        from_states=frozenset({"operational", "degraded"}),
        to_state="blocked",
        reason="Blocage confirmé par le site cible.",
    ),
    TransitionRule(
        from_states=frozenset({"operational", "degraded", "blocked"}),
        to_state="offline",
        reason="Absence de signal de vie au-delà du délai configuré.",
    ),
    TransitionRule(
        from_states=frozenset({"operational", "degraded", "blocked", "offline"}),
        to_state="stopped",
        reason="Arrêt volontaire de l'agent.",
    ),
    TransitionRule(
        from_states=frozenset({"offline"}),
        to_state="operational",
        reason="Signal de vie retrouvé.",
    ),
    TransitionRule(
        from_states=frozenset({"degraded"}),
        to_state="operational",
        reason="Collecte réussie.",
    ),
)

_PROCESS_ONLY_TRANSITIONS: frozenset[str] = frozenset({"offline", "stopped"})


def transition_for(from_state: str, to_state: str) -> TransitionRule | None:
    """Retourne la règle autorisant une transition, ou ``None`` si interdite."""

    for rule in TRANSITION_RULES:
        if rule.to_state == to_state and from_state in rule.from_states:
            return rule
    return None


def is_process_level(state: str) -> bool:
    """Indique si un état ne concerne que le processus (agent), pas les collecteurs."""

    return state in _PROCESS_ONLY_TRANSITIONS
