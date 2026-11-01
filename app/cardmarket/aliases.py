"""Alias multilingues des noms de cartes (pont FR ↔ EN ↔ KO ↔ JA ↔ ZH).

TCGdex identifie chaque carte par un ID international (ex. « sv03-125 ») et
expose le nom de la carte dans chaque langue via les endpoints
`/v2/{locale}/cards`. Ce module récupère les listes de cartes pour chaque
locale et construit une table d'alias locale permettant de relier le nom
d'une annonce (français, coréen, japonais, chinois…) au nom anglais utilisé
par Cardmarket.
"""

import logging
import sqlite3
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

SUPPORTED_LOCALES: tuple[str, ...] = ("fr", "en", "ko", "ja", "zh-tw")

LocaleFetcher = Callable[[str], list[dict[str, Any]]]


def base_card_name(name: str | None) -> str:
    """Normalise un nom de carte : retire le suffixe d'attaques Cardmarket.

    « Charizard [Fire Spin | Wing Attack] » → « charizard »
    « Dracaufeu-ex » → « dracaufeu-ex »
    """
    if not name:
        return ""
    without_suffix = name.split("[")[0]
    return " ".join(without_suffix.split()).casefold()


def fetch_locale_cards(locale: str) -> list[dict[str, Any]]:
    """Télécharge la liste des cartes dans une locale TCGdex.

    Import local volontaire : évite le cycle d'imports entre les packages
    app.tcgdex et app.identification lors du chargement du package.
    """
    from app.tcgdex.client import TCGDEX_LOCALE_BASE_URL, TcgdexClient

    client = TcgdexClient(base_url=TCGDEX_LOCALE_BASE_URL.format(locale=locale))
    return client.list_cards()


UPSERT_ALIAS_SQL = """
    INSERT INTO card_name_aliases (card_id, locale, name)
    SELECT p.id, ?, ? FROM pokemon_reference_cards p WHERE p.tcgdex_id = ?
    ON CONFLICT(card_id, locale) DO UPDATE SET
        name = excluded.name,
        updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
"""


def sync_name_aliases(
    connection: sqlite3.Connection,
    fetcher: LocaleFetcher = fetch_locale_cards,
) -> dict[str, Any]:
    """Construit / actualise la table card_name_aliases pour toutes les locales.

    Les locales indisponibles (API bénévole, 503 ponctuels) sont ignorées
    sans faire échouer la synchronisation ; le compte-rendu les liste.
    """
    per_locale: dict[str, int] = {}
    skipped: list[str] = []

    with connection:
        for locale in SUPPORTED_LOCALES:
            try:
                cards = fetcher(locale)
            except Exception as error:  # API bénévole : on passe à la suite.
                logger.warning("Alias %s indisponibles (%s).", locale, error)
                skipped.append(locale)
                continue
            count = 0
            for card in cards:
                tcgdex_id = card.get("id")
                name = str(card.get("name") or "").strip()
                if not tcgdex_id or not name:
                    continue
                cursor = connection.execute(
                    UPSERT_ALIAS_SQL, (locale, name, str(tcgdex_id))
                )
                count += cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
            per_locale[locale] = count

    return {"per_locale": per_locale, "skipped": skipped}


def card_ids_for_name(
    connection: sqlite3.Connection, name: str | None
) -> list[int]:
    """Retourne les identifiants de cartes référentiel portant ce nom (toute locale)."""
    if not name or not name.strip():
        return []
    rows = connection.execute(
        """
        SELECT DISTINCT card_id FROM card_name_aliases
        WHERE lower(trim(name)) = lower(trim(?))
        """,
        (name.strip(),),
    ).fetchall()
    return [int(row["card_id"]) for row in rows]


def english_name_for_card(
    connection: sqlite3.Connection, card_id: int
) -> str | None:
    """Nom anglais (canal Cardmarket) d'une carte du référentiel."""
    row = connection.execute(
        """
        SELECT name FROM card_name_aliases
        WHERE card_id = ? AND locale = 'en'
        """,
        (card_id,),
    ).fetchone()
    return str(row["name"]) if row else None
