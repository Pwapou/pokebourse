"""Normalisation partagée par l'extraction, l'index local et les recherches."""

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
