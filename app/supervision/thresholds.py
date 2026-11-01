"""Helpers de temps pour la supervision."""

from datetime import UTC, datetime


def parse_utc(value: str) -> datetime:
    """Parse un horodatage ISO stocké en base (suffixe Z) en datetime UTC."""

    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def is_stale(reference: str, now: str, max_age_seconds: float) -> bool:
    """Indique si ``reference`` est plus vieux que ``max_age_seconds`` à ``now``."""

    try:
        age = (parse_utc(now) - parse_utc(reference)).total_seconds()
    except ValueError:
        return True
    return age > max_age_seconds
