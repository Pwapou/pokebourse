"""Recherche humaine complète par identifiant/nom et repli lexical explicite."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.identification.matcher import CardMatcher
from app.identification.normalization import canonical_local_id, normalize_text
from app.tcgdex.models import ReferenceCardRecord

if TYPE_CHECKING:
    from app.tcgdex.cache import TcgdexCache


@dataclass(frozen=True)
class ReferenceSearchResult:
    """Distingue une recherche exacte de propositions orthographiques."""

    cards: list[ReferenceCardRecord]
    approximate: bool = False


def search_references(
    cache: TcgdexCache, *, name: str = "", local_id: str | None = None,
    set_name: str | None = None, tcgdex_id: str | None = None, limit: int = 26, offset: int = 0,
) -> ReferenceSearchResult:
    """Préserve la pagination des résultats exacts ; les fautes restent des suggestions."""
    exact_id = tcgdex_id or (name if cache.get_card_by_tcgdex_id(name) else None)
    parameters = {"name": name if not exact_id else None, "local_id": local_id,
                  "set_query": set_name, "tcgdex_id": exact_id}
    exact = cache.find_cards(**parameters, limit=limit, offset=offset)
    if exact or exact_id or not name.strip() or cache.find_cards(**parameters, limit=1, offset=0):
        return ReferenceSearchResult(exact)
    result = CardMatcher(cache, seed_if_empty=False, repair_index=False).identify(name)
    ordered = [candidate for candidate in result.candidates if not candidate.contradictions
               and (not local_id or canonical_local_id(candidate.local_id) == canonical_local_id(local_id))]
    cards = {card.id: card for card in cache.get_cards_by_ids([candidate.card_id for candidate in ordered])}
    ordered = [candidate for candidate in ordered if not set_name or cards[candidate.card_id].set_id == set_name
               or normalize_text(set_name) in normalize_text(candidate.set_name)]
    selected = ordered[max(0, offset):max(0, offset) + max(1, min(limit, 200))]
    return ReferenceSearchResult([cards[candidate.card_id] for candidate in selected],
                                 any(candidate.name_match_kind == "fuzzy" for candidate in ordered))
