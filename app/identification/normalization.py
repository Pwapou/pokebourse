"""Normalisation partagée par l'extraction, l'index local et les recherches."""

from collections.abc import Collection
import re
import unicodedata


def normalize_text(value: str | None) -> str:
    """Normalise Unicode, accents, casse, ponctuation et espaces sans inventer d'alias."""
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFKD", value)
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^\w]+", " ", stripped.casefold(), flags=re.UNICODE).split())


def canonical_local_id(value: str | None) -> str:
    """Compare les numéros complets : seuls les zéros initiaux d'une partie numérique sont neutres."""
    if value is None:
        return ""
    cleaned = normalize_text(value).replace(" ", "").upper()
    match = re.fullmatch(r"(.*?)(\d+)", cleaned)
    if not match:
        return cleaned
    prefix, digits = match.groups()
    return f"{prefix}{digits.lstrip('0') or '0'}"


def valid_card_number(value: str, attested_ids: Collection[str] = ()) -> bool:
    """Valide une fraction/un numéro, ou une référence alphabétique attestée localement."""
    match = re.fullmatch(r"([A-Za-z0-9]{1,5})(?:\s*/\s*([0-9]{1,3}))?", value.strip())
    return bool(match and (any(char.isdigit() for char in match[1]) or
                           canonical_local_id(match[1]) in attested_ids))
