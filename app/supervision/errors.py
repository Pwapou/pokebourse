"""Classification des erreurs de collecte côté agent.

Transforme exceptions, statuts HTTP et contenus de réponse en erreur structurée
avec code interne. Les pages de blocage et de vérification sont détectées même
servies en HTTP 200, et une recherche sans résultat n'est jamais confondue avec
un échec d'extraction.
"""

import logging
import re
from typing import Any

from app.supervision.models import (
    BLOCKING_ERROR_CODES,
    TRANSIENT_ERROR_CODES,
    ErrorCode,
    StructuredError,
    new_correlation_id,
    utc_now,
)

logger = logging.getLogger(__name__)

# Marqueurs de contenu signalant une page de vérification anti-bot servie
# avec un statut HTTP 200.
_CHALLENGE_MARKERS: tuple[str, ...] = (
    "datadome",
    "captcha",
    "challenge-platform",
    "cf-challenge",
    "g-recaptcha",
    "hcaptcha",
    "pardon our interruption",
    "are you a robot",
    "verify you are human",
    "accès temporairement restreint",
)

# Marqueurs de contenu signalant une redirection vers une page de connexion.
_AUTH_MARKERS: tuple[str, ...] = (
    "se connecter",
    "sign in",
    "log in",
    "login",
    "session expir",
    "session expirée",
    "authentication required",
)

_CAPTCHA_MARKER_PATTERN = re.compile(
    "|".join(re.escape(marker) for marker in _CHALLENGE_MARKERS), re.IGNORECASE
)
_AUTH_MARKER_PATTERN = re.compile(
    "|".join(re.escape(marker) for marker in _AUTH_MARKERS), re.IGNORECASE
)


def _response_status(error: BaseException) -> int | None:
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        response = getattr(current, "response", None)
        status = getattr(response, "status_code", None)
        if isinstance(status, int):
            return status
        current = current.__cause__ or current.__context__
    return None


def _response_text(error: BaseException, limit: int = 20_000) -> str:
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        response = getattr(current, "response", None)
        if response is not None:
            text = getattr(response, "text", None)
            if isinstance(text, str) and text:
                return text[:limit]
        current = current.__cause__ or current.__context__
    return ""


def contains_challenge(content: str) -> bool:
    """Détecte une page de blocage ou de vérification, y compris en HTTP 200."""

    return bool(content) and _CAPTCHA_MARKER_PATTERN.search(content) is not None


def contains_auth_wall(content: str) -> bool:
    """Détecte une page de connexion ou une session expirée."""

    return bool(content) and _AUTH_MARKER_PATTERN.search(content) is not None


def classify_error(
    error: BaseException,
    *,
    http_status: int | None = None,
    response_text: str | None = None,
) -> StructuredError:
    """Classe une exception en erreur structurée avec code interne.

    Un statut HTTP seul ne détermine jamais la cause exacte : le contenu de la
    réponse est inspecté en priorité pour repérer les vérifications anti-bot
    servies en HTTP 200.
    """

    status = http_status if http_status is not None else _response_status(error)
    text = response_text if response_text is not None else _response_text(error)
    code: ErrorCode
    message: str

    if contains_challenge(text):
        code = "SCRAPE_CHALLENGE_REQUIRED"
        message = "Le site exige une vérification anti-bot avant de répondre."
    elif contains_auth_wall(text):
        code = "SCRAPE_AUTH_REQUIRED"
        message = "Le site exige une connexion ou la session a expiré."
    elif status == 403:
        code = "SCRAPE_ACCESS_DENIED"
        message = "Accès refusé par le site (HTTP 403)."
    elif status == 429:
        code = "SCRAPE_RATE_LIMITED"
        message = "Trop de requêtes : le site limite momentanément l'accès (HTTP 429)."
    elif status is not None and status >= 500:
        code = "SCRAPE_NETWORK_ERROR"
        message = f"Le site a renvoyé une erreur serveur (HTTP {status})."
    elif _is_timeout(error):
        code = "SCRAPE_TIMEOUT"
        message = "Le délai d'attente de la réponse a été dépassé."
    elif _is_browser_crash(error):
        code = "SCRAPE_BROWSER_CRASH"
        message = "Le navigateur de collecte a été interrompu."
    elif _is_network_error(error):
        code = "SCRAPE_NETWORK_ERROR"
        message = "Erreur réseau ou DNS pendant la collecte."
    else:
        code = "SCRAPE_UNKNOWN_ERROR"
        message = f"Erreur non classée : {type(error).__name__}."

    return StructuredError(
        code=code,
        message=message,
        occurred_at=utc_now(),
        http_status=status,
        transient=code in TRANSIENT_ERROR_CODES,
        correlation_id=new_correlation_id(),
    )


def extraction_failed_error(detail: str = "") -> StructuredError:
    """Erreur structurée pour une page chargée mais inexploitable."""

    suffix = f" : {detail}" if detail else ""
    return StructuredError(
        code="SCRAPE_EXTRACTION_FAILED",
        message=f"La réponse a été reçue mais son contenu est incompatible avec le schéma attendu{suffix}.",
        occurred_at=utc_now(),
        http_status=None,
        transient=True,
        correlation_id=new_correlation_id(),
    )


def heartbeat_lost_error() -> StructuredError:
    return StructuredError(
        code="AGENT_HEARTBEAT_LOST",
        message="Aucun signal de vie reçu au-delà du délai configuré.",
        occurred_at=utc_now(),
        http_status=None,
        transient=False,
        correlation_id=new_correlation_id(),
    )


def is_blocking(error: StructuredError) -> bool:
    """Indique si l'erreur confirme un blocage nécessitant une intervention."""

    return error.code in BLOCKING_ERROR_CODES


def _is_timeout(error: BaseException) -> bool:
    if isinstance(error, TimeoutError):
        return True
    module = type(error).__module__.lower()
    name = type(error).__name__.lower()
    return "timeout" in name or (module.startswith(("httpx", "requests", "urllib3")) and "timeout" in name)


def _is_browser_crash(error: BaseException) -> bool:
    name = type(error).__name__.lower()
    return "browser" in name or "playwright" in type(error).__module__.lower() and (
        "closed" in name or "crash" in name
    )


def _is_network_error(error: BaseException) -> bool:
    import socket

    if isinstance(error, (ConnectionError, socket.gaierror, OSError)):
        return True
    name = type(error).__name__.lower()
    return any(
        marker in name
        for marker in ("connection", "connecterror", "dns", "network", "unreachable")
    )


def retry_after_seconds(error: BaseException) -> float | None:
    """Extrait un délai Retry-After d'une réponse, en secondes."""

    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        response = getattr(current, "response", None)
        headers = getattr(response, "headers", None)
        if headers is not None:
            value: Any = None
            try:
                value = headers.get("Retry-After") or headers.get("retry-after")
            except AttributeError:
                value = None
            if value is not None:
                try:
                    return max(0.0, float(str(value).strip()))
                except ValueError:
                    return None
        current = current.__cause__ or current.__context__
    return None


def validate_report_safety(report: dict[str, Any]) -> list[str]:
    """Vérifie qu'un rapport transmis ne contient aucun secret."""

    problems: list[str] = []
    serialized = repr(report).lower()
    for marker in ("set-cookie", "authorization", "bearer ", "password", "x-csrf"):
        if marker in serialized:
            problems.append(marker)
    return problems
