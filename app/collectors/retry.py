import logging
import random
import time
from collections.abc import Callable
from typing import TypeVar

from app.collectors.models import CollectorError
from app.supervision.errors import retry_after_seconds

T = TypeVar("T")
logger = logging.getLogger(__name__)


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


def is_retryable_http_status(status: int | None) -> bool:
    return status == 429 or status is None or status >= 500


def call_with_backoff(
    operation: Callable[[], T],
    *,
    operation_name: str,
    attempts: int = 3,
    base_delay_seconds: float = 1.0,
    max_delay_seconds: float = 8.0,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Exécute une opération réseau avec backoff exponentiel et jitter.

    Les 403 ne sont pas retentés : ils indiquent une protection anti-bot et le
    worker doit ralentir, jamais chercher à la contourner. Les erreurs 429 et
    5xx, ainsi que les erreurs réseau sans statut HTTP, sont retentées. Un
    en-tête Retry-After fourni par le serveur est respecté et borne le délai.
    """

    bounded_attempts = max(1, attempts)
    for attempt in range(1, bounded_attempts + 1):
        try:
            return operation()
        except CollectorError as error:
            status = _response_status(error)
            retryable = error.retryable or is_retryable_http_status(status)
            if attempt >= bounded_attempts or not retryable:
                raise
            delay = _next_delay(
                error,
                attempt,
                base_delay_seconds=base_delay_seconds,
                max_delay_seconds=max_delay_seconds,
            )
            logger.warning(
                "%s temporairement indisponible (tentative %d/%d) ; nouvel essai dans %.1fs.",
                operation_name,
                attempt,
                bounded_attempts,
                delay,
            )
            sleep(delay)
        except Exception as error:
            status = _response_status(error)
            retryable = is_retryable_http_status(status)
            if attempt >= bounded_attempts or not retryable:
                raise CollectorError(
                    f"{operation_name} indisponible (code HTTP {status})."
                    if status
                    else f"{operation_name} indisponible.",
                    retryable=False,
                ) from error
            delay = _next_delay(
                error,
                attempt,
                base_delay_seconds=base_delay_seconds,
                max_delay_seconds=max_delay_seconds,
            )
            logger.warning(
                "%s temporairement indisponible (tentative %d/%d) ; nouvel essai dans %.1fs.",
                operation_name,
                attempt,
                bounded_attempts,
                delay,
            )
            sleep(delay)
    raise CollectorError(f"{operation_name} indisponible.", retryable=False)


def _next_delay(
    error: BaseException,
    attempt: int,
    *,
    base_delay_seconds: float,
    max_delay_seconds: float,
) -> float:
    """Délai avant la prochaine tentative, en respectant Retry-After si fourni."""

    retry_after = retry_after_seconds(error)
    backoff = min(max_delay_seconds, base_delay_seconds * (2 ** (attempt - 1)))
    delay = backoff if retry_after is None else min(max(backoff, retry_after), 300.0)
    return delay * random.uniform(0.5, 1.5)
