"""Indices de langue de l'exemplaire (T06.4) : méthode locale bornée et explicable.

La sélection Tesseract `fra+eng` ne détecte pas la langue de l'exemplaire ; le nom
du Pokémon, la langue du site ou la locale du catalogue ne la prouvent pas non plus.
Cette méthode compte des expressions discriminantes dans les fragments de texte de
la carte (hors étiquette et fond) : suggestion justifiée ou abstention explicite.
Aucune confirmation implicite : la proposition reste distincte d'une langue
déclarée ou confirmée, et tout désaccord avec une langue déclarée reste visible.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.identification.normalization import normalize_text
from app.identification.ocr_types import (
    LANGUAGE_CLUES_VERSION,
    LanguageHypothesis,
    OcrConfig,
)

# Lexique discriminant minimal, versionné (valeurs initiales expérimentales).
# Chaque paire oppose un marqueur français à son équivalent anglais distinct.
_CLUES: dict[str, frozenset[str]] = {
    "fr": frozenset({
        "pv", "faiblesse", "retraite", "evolue", "niveau", "attaque", "defense",
        "confusion", "poison", "paralyse", "endormi", "entrave",
    }),
    "en": frozenset({
        "hp", "weakness", "retreat", "evolves", "level", "attack", "damage",
        "poisoned", "asleep", "confused", "paralyzed",
    }),
}
# Mots communs aux deux langues (nom du Pokémon, « Pokémon », codes…) : jamais des indices.
_MIN_CLUES = 2
_DOMINANCE_RATIO = 2.0
_MIN_TEXT_LENGTH = 12


def clue_hits(fragments: Iterable[str]) -> dict[str, set[str]]:
    """Retourne les indices discriminants par langue, sur texte normalisé."""
    hits: dict[str, set[str]] = {"fr": set(), "en": set()}
    for fragment in fragments:
        normalized = normalize_text(fragment)
        if not normalized:
            continue
        words = set(normalized.split())
        for language, clues in _CLUES.items():
            hits[language].update(clues & words)
    return hits


def suggest_language(fragments: Iterable[str], *, declared_language: str | None = None,
                     config: OcrConfig | None = None) -> LanguageHypothesis:
    """Propose une langue à partir des fragments de la carte, ou s'abstient.

    Abstention : texte trop court, aucun indice, indices insuffisants ou conflit
    non tranché. Une suggestion mentionne ses fragments utiles et conserve tout
    désaccord avec une langue déclarée ; aucun score n'est une probabilité.
    """
    config = config or OcrConfig()
    kept = [fragment for fragment in fragments if fragment and fragment.strip()][: config.max_clue_fragments * 4]
    total_length = sum(len(fragment) for fragment in kept)
    if total_length < _MIN_TEXT_LENGTH:
        return LanguageHypothesis(
            language=None, clue_fragments=tuple(), reason="texte_trop_court",
            conflict=declared_language,
        )
    hits = clue_hits(kept)
    french = len(hits["fr"])
    english = len(hits["en"])
    if french == 0 and english == 0:
        return LanguageHypothesis(
            language=None, clue_fragments=tuple(), reason="aucun_indice_discriminant",
            conflict=declared_language,
        )
    dominant: str | None = None
    if french > 0 and english == 0 and french >= _MIN_CLUES:
        dominant = "fr"
    elif english > 0 and french == 0 and english >= _MIN_CLUES:
        dominant = "en"
    elif french >= _MIN_CLUES and english >= _MIN_CLUES:
        high, low = ("fr", "en") if french >= english else ("en", "fr")
        if max(french, english) >= _DOMINANCE_RATIO * min(french, english):
            dominant = high  # conflit tranché avec motif ; les deux restent comptés
    if dominant is None:
        return LanguageHypothesis(
            language=None, clue_fragments=tuple(), reason="indices_insuffisants_ou_conflit",
            conflict=declared_language,
        )
    clue_words = _CLUES[dominant] & hits[dominant]
    useful = tuple(
        fragment.strip() for fragment in kept
        if clue_words & set(normalize_text(fragment).split())
    )[: config.max_clue_fragments]
    reason = None
    if french > 0 and english > 0:
        reason = f"conflit_tranche:{max(french, english)}_contre_{min(french, english)}"
    return LanguageHypothesis(
        language=dominant, clue_fragments=useful, reason=reason, conflict=declared_language,
    )


LANGUAGE_MODULE_VERSION = LANGUAGE_CLUES_VERSION
