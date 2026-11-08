"""Indices de langue de l'exemplaire (T06.4) : suggestion étayée ou abstention."""

from app.identification.ocr_language import LANGUAGE_MODULE_VERSION, clue_hits, suggest_language
from app.identification.ocr_types import OcrConfig, LanguageHypothesis

_FRENCH_CARD = [
    "Attaque Tonnerre Inflige 30 dégâts",
    "Faiblesse : Combat  Retraite : énergie",
    "Évolue de Pikachu Niveau 32 PV 80",
]
_ENGLISH_CARD = [
    "Attack Thunder Shock does 30 damage",
    "Weakness: Fighting  Retreat Cost: energy",
    "Evolves from Pikachu Level 32 HP 80",
]


def test_french_fragments_propose_french_with_clues() -> None:
    hypothesis = suggest_language(_FRENCH_CARD)
    assert isinstance(hypothesis, LanguageHypothesis)
    assert hypothesis.language == "fr"
    assert len(hypothesis.clue_fragments) >= 1
    assert len(hypothesis.clue_fragments) <= 6
    assert hypothesis.method_version == LANGUAGE_MODULE_VERSION
    assert hypothesis.reason is None
    assert all(fragment in _FRENCH_CARD for fragment in hypothesis.clue_fragments)


def test_english_fragments_propose_english() -> None:
    hypothesis = suggest_language(_ENGLISH_CARD)
    assert hypothesis.language == "en"
    assert hypothesis.clue_fragments


def test_common_pokemon_name_abstains() -> None:
    hypothesis = suggest_language(["Pikachu", "Pokémon 20/82"])
    assert hypothesis.language is None
    assert hypothesis.reason == "aucun_indice_discriminant"


def test_short_text_abstains() -> None:
    hypothesis = suggest_language(["PV 80"])
    assert hypothesis.language is None
    assert hypothesis.reason == "texte_trop_court"


def test_single_clue_is_insufficient() -> None:
    hypothesis = suggest_language(["Retraite : énergie incolore et autres marqueurs du jeu de cartes"])
    assert hypothesis.language is None
    assert hypothesis.reason == "indices_insuffisants_ou_conflit"


def test_balanced_conflict_abstains() -> None:
    fragments = ["PV HP faiblesse weakness retraite retreat attack attaque"]
    hypothesis = suggest_language(fragments)
    assert hypothesis.language is None
    assert hypothesis.reason == "indices_insuffisants_ou_conflit"


def test_dominant_conflict_suggests_with_reason() -> None:
    fragments = ["PV PV faiblesse retraite weakness HP attaque"]
    hypothesis = suggest_language(fragments)
    assert hypothesis.language == "fr"
    assert hypothesis.reason and hypothesis.reason.startswith("conflit_tranche")


def test_declared_language_disagreement_stays_visible() -> None:
    hypothesis = suggest_language(_ENGLISH_CARD, declared_language="fr")
    assert hypothesis.language == "en"
    assert hypothesis.conflict == "fr"


def test_clue_fragments_are_capped() -> None:
    fragments = [f"PV faiblesse retraite attaque évolue niveau ligne {index}" for index in range(10)]
    hypothesis = suggest_language(fragments, config=OcrConfig(max_clue_fragments=3))
    assert hypothesis.language == "fr"
    assert len(hypothesis.clue_fragments) <= 3


def test_clue_hits_count_distinct_clues() -> None:
    hits = clue_hits(["PV PV PV faiblesse faiblesse"])
    assert hits["fr"] == {"pv", "faiblesse"}
    assert hits["en"] == set()
