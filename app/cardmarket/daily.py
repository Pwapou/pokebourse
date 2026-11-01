"""Planification quotidienne de la synchronisation Cardmarket.

Le price guide officiel est régénéré une fois par jour (~02:45 heure de
Paris, soit ~01:45 UTC). Le worker relance ensuite la synchronisation des
cotes et des noms multilingues, à 02:20 UTC par défaut (configurable via
CARDMARKET_DAILY_SYNC_UTC, format « HH:MM », UTC). L'état persiste dans
`cardmarket_sync_state` : une exécution par jour, et au plus une tentative
par heure en cas d'échec réseau.
"""

import logging
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, time as day_time, timedelta
from typing import Any

from app.cardmarket import aliases as cardmarket_aliases
from app.cardmarket import guide as cardmarket_guide

logger = logging.getLogger(__name__)

STATE_KEY = "daily"
RETRY_BACKOFF = timedelta(hours=1)

LocaleFetcher = Callable[[str], list[dict[str, Any]]]


def parse_utc_time(raw: str) -> day_time:
    """Valide « HH:MM » (UTC) ; lève ValueError si le format est invalide."""
    try:
        hour_text, minute_text = raw.strip().split(":")
        hour, minute = int(hour_text), int(minute_text)
    except ValueError as error:
        raise ValueError(
            f"Horaire quotidien invalide « {raw} » (attendu HH:MM, UTC)."
        ) from error
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(
            f"Horaire quotidien invalide « {raw} » (attendu HH:MM, UTC)."
        )
    return day_time(hour, minute, tzinfo=UTC)


def _parse_timestamp(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def load_state(connection: sqlite3.Connection) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT last_success_at, last_attempt_at, detail
        FROM cardmarket_sync_state
        WHERE key = ?
        """,
        (STATE_KEY,),
    ).fetchone()
    return dict(row) if row is not None else None


def should_run(
    now: datetime,
    state: dict[str, Any] | None,
    run_time: day_time,
) -> bool:
    now_utc = now.astimezone(UTC)
    today_run = datetime.combine(now_utc.date(), run_time)
    if now_utc < today_run:
        return False  # le fichier du jour n'est pas encore régénéré.
    if state is None:
        return True
    last_success = _parse_timestamp(state.get("last_success_at"))
    if last_success is not None and last_success >= today_run:
        return False  # déjà synchronisé après la régénération du jour.
    last_attempt = _parse_timestamp(state.get("last_attempt_at"))
    if last_attempt is not None and now_utc - last_attempt < RETRY_BACKOFF:
        return False  # échec récent : on attend avant de réessayer.
    return True


def _stamp(now: datetime | None) -> str:
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def mark_attempt(
    connection: sqlite3.Connection,
    detail: str | None = None,
    *,
    now: datetime | None = None,
) -> None:
    stamp = _stamp(now)
    with connection:
        connection.execute(
            """
            INSERT INTO cardmarket_sync_state (key, last_attempt_at, detail)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                last_attempt_at = excluded.last_attempt_at,
                detail = excluded.detail,
                updated_at = excluded.updated_at
            """,
            (STATE_KEY, stamp, detail),
        )


def mark_success(
    connection: sqlite3.Connection, detail: str, *, now: datetime | None = None
) -> None:
    stamp = _stamp(now)
    with connection:
        connection.execute(
            """
            INSERT INTO cardmarket_sync_state (
                key, last_success_at, last_attempt_at, detail
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                last_success_at = excluded.last_success_at,
                last_attempt_at = excluded.last_attempt_at,
                detail = excluded.detail,
                updated_at = excluded.updated_at
            """,
            (STATE_KEY, stamp, stamp, detail),
        )


def run_daily_sync(
    connection: sqlite3.Connection,
    fetcher: LocaleFetcher = cardmarket_aliases.fetch_locale_cards,
) -> dict[str, Any]:
    """Synchronise cotes + noms ; propage les erreurs réseau à l'appelant."""
    guide_result = cardmarket_guide.sync_price_guide(connection)
    aliases_result = cardmarket_aliases.sync_name_aliases(connection, fetcher=fetcher)
    return {"guide": guide_result, "aliases": aliases_result}


def summarize(result: dict[str, Any]) -> str:
    """Compte-rendu court persisté dans cardmarket_sync_state.detail."""
    locales = ", ".join(
        f"{locale} {count}"
        for locale, count in result["aliases"]["per_locale"].items()
    )
    skipped = (
        f" (locales ignorées : {', '.join(result['aliases']['skipped'])})"
        if result["aliases"]["skipped"]
        else ""
    )
    return f"cotes {result['guide']['synced']} · alias {locales}{skipped}"


def maybe_run_daily_sync(
    connection: sqlite3.Connection,
    *,
    now: datetime | None = None,
    run_time_utc: str = "02:20",
    fetcher: LocaleFetcher = cardmarket_aliases.fetch_locale_cards,
) -> dict[str, Any] | None:
    """Exécute la synchro si elle est due ; retourne None sinon."""
    now = now or datetime.now(UTC)
    run_time = parse_utc_time(run_time_utc)
    state = load_state(connection)
    if not should_run(now, state, run_time):
        return None
    mark_attempt(connection, now=now)
    try:
        result = run_daily_sync(connection, fetcher=fetcher)
    except Exception:
        logger.exception("Synchronisation Cardmarket quotidienne en échec.")
        raise
    mark_success(connection, summarize(result), now=now)
    return result
