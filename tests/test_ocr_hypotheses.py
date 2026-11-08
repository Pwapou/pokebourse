"""Hypothèses de numéro (T07) : structure, variantes bornées, déduplication, recherche."""

import sqlite3
from pathlib import Path

import pytest

from app.identification import ocr_numbers
from app.identification.matcher import CardMatcher
from app.identification.ocr_numbers import (
    extract_name_readings,
    extract_number_readings,
    generate_number_hypotheses,
    hypothesis_features,
    parse_number,
    search_hypotheses,
)
from app.identification.ocr_text import reconstruct_lines
from app.identification.ocr_types import Deadline, OcrConfig, OcrLine, OcrReading, OcrToken
from app.storage.database import connect
from app.storage.migration_runner import apply_migrations
from app.tcgdex.cache import TcgdexCache


def _token(index: int, text: str, left: int, top: int = 100, width: int = 40, height: int = 20,
           line: int = 1, block: int = 1, confidence: float | None = 90.0) -> OcrToken:
    return OcrToken(
        pass_id="p1", token_index=index, text=text, box=(left, top, width, height),
        norm_box=(0.0, 0.0, 1.0, 1.0), photo_quad=None,
        group=(1, block, 1, line), confidence=confidence,
    )


def _tokens_lines(tokens: list[OcrToken]) -> tuple[tuple[OcrToken, ...], tuple[OcrLine, ...]]:
    materialized = tuple(tokens)
    return materialized, reconstruct_lines(materialized, pass_id="p1")


def test_parse_number_structures() -> None:
    fraction = parse_number("20/82")
    assert fraction is not None and fraction.kind == "fraction"
    assert (fraction.prefix, fraction.numerator, fraction.denominator, fraction.suffix) == (None, "20", "82", None)
    prefixed = parse_number("TG01/TG30")
    assert prefixed is None  # format non retenu par la grammaire initiale : pas d'invention
    promo = parse_number("SWSH020")
    assert promo is not None and promo.kind == "promo"
    assert (promo.prefix, promo.numerator) == ("SWSH", "020")
    assert parse_number("n") is None
    assert parse_number("4") is None  # nombre isolé sans structure : pas un numéro exploitable
    assert parse_number("") is None


def test_fraction_with_prefix_and_suffix_components() -> None:
    components = parse_number("SV4a 001/072")
    assert components is None
    direct = parse_number("001/072")
    assert direct is not None
    assert direct.prefix is None and direct.numerator == "001" and direct.denominator == "072"


def test_extract_joins_separated_slash_fragments() -> None:
    tokens, lines = _tokens_lines([_token(0, "025", 10), _token(1, "/", 52), _token(2, "165", 60)])
    readings = extract_number_readings(tokens, lines, object_id="obj-1", pass_role="full")
    assert [reading.raw_text for reading in readings] == ["025/165"]
    assert readings[0].token_refs == (("p1", 0), ("p1", 1), ("p1", 2))
    assert readings[0].confidence == pytest.approx(90.0)


def test_extract_rejects_wide_gaps_and_keeps_noise_at_diagnostic() -> None:
    tokens, lines = _tokens_lines([
        _token(0, "n", 10, height=20),
        _token(1, "20/82", 500),  # écart de plus de deux hauteurs médianes
    ])
    readings = extract_number_readings(tokens, lines, object_id="obj-1", pass_role="full")
    assert [reading.raw_text for reading in readings if reading.role == "number"] == ["20/82"]
    noise = [reading for reading in readings if reading.role == "unknown"]
    assert [reading.raw_text for reading in noise] == ["n"]
    assert all(reading.operations == ("rejected_no_structure",) for reading in noise)


def test_extract_two_line_fraction_via_slash() -> None:
    tokens, lines = _tokens_lines([
        _token(0, "20/", 10, top=10, line=1),
        _token(1, "82", 10, top=40, line=2),  # écart vertical ≤ une hauteur médiane
    ])
    readings = extract_number_readings(tokens, lines, object_id="obj-1", pass_role="full")
    joined = [reading for reading in readings if "two_line_join" in reading.operations]
    assert [reading.raw_text for reading in joined] == ["20/ 82"]


def test_extract_respects_reading_cap() -> None:
    tokens = [_token(index, f"{index}9/102", index * 45) for index in range(30)]
    tokens, lines = _tokens_lines(tokens)
    config = OcrConfig(max_number_readings=5)
    readings = extract_number_readings(tokens, lines, object_id="obj-1", pass_role="full", config=config)
    assert len(readings) <= 5


def test_generate_hypotheses_orders_literal_first_and_groups() -> None:
    reading = OcrReading(
        reading_id="num-obj-0", object_id="obj-1", role="number", raw_text="O25/165",
        token_refs=(("p1", 0),), pass_roles=("full",), confidence=42.0,
    )
    hypotheses, truncated = generate_number_hypotheses([reading])
    assert not truncated
    assert hypotheses[0].value == "O25/165" and hypotheses[0].operations == ("original",)
    assert hypotheses[0].rank == 1
    repaired = [hypothesis for hypothesis in hypotheses if hypothesis.operations != ("original",)]
    assert any(hypothesis.value == "025/165" and hypothesis.operations == ("letter_to_digit",) for hypothesis in repaired)
    assert all(hypothesis.alternative_group_id == "num-obj-0" for hypothesis in hypotheses)
    assert len(hypotheses) <= 4  # originale + au plus trois réparations


def test_generate_hypotheses_unicode_separator_and_insertion() -> None:
    reading = OcrReading(
        reading_id="num-obj-0", object_id="obj-1", role="number", raw_text="025 ／ 165",
        token_refs=(("p1", 0),), pass_roles=("full",), confidence=None,
    )
    hypotheses, _ = generate_number_hypotheses([reading])
    values = {hypothesis.value: hypothesis.operations for hypothesis in hypotheses}
    # Original et variante « separator_normalized » partagent la même valeur de
    # recherche : la déduplication par clé canonique les fusionne, le littéral
    # représente le groupe ; le séparateur Unicode reste tracé dans le brut lu.
    assert values["025/165"] == ("original",)
    assert reading.raw_text == "025 ／ 165"
    reading_108 = OcrReading(
        reading_id="num-obj-1", object_id="obj-1", role="number", raw_text="108/59",
        token_refs=(("p1", 1),), pass_roles=("full",), confidence=None,
    )
    hypotheses_108, _ = generate_number_hypotheses([reading_108])
    insertion = [hypothesis for hypothesis in hypotheses_108 if hypothesis.operations == ("insert_leading_1",)]
    assert [hypothesis.value for hypothesis in insertion] == ["108/159"]  # hypothèse, jamais une vérité


def test_generate_never_substitutes_promo_prefix() -> None:
    reading = OcrReading(
        reading_id="num-obj-0", object_id="obj-1", role="number", raw_text="SWSH020",
        token_refs=(("p1", 0),), pass_roles=("full",), confidence=None,
    )
    hypotheses, _ = generate_number_hypotheses([reading])
    assert hypotheses[0].value == "SWSH020"
    assert all(hypothesis.components.prefix == "SWSH" for hypothesis in hypotheses)


def test_generate_deduplicates_canonical_key_and_merges_origins() -> None:
    first = OcrReading(
        reading_id="num-a", object_id="obj-1", role="number", raw_text="025/165",
        token_refs=(("p1", 0),), pass_roles=("full",), confidence=90.0,
    )
    second = OcrReading(
        reading_id="num-b", object_id="obj-1", role="number", raw_text="25/165",
        token_refs=(("p1", 5),), pass_roles=("number",), confidence=10.0,
    )
    hypotheses, truncated = generate_number_hypotheses([first, second])
    matching = [hypothesis for hypothesis in hypotheses if hypothesis.value == "025/165"]
    assert len(matching) == 1  # zéros initiaux neutres : même clé canonique
    assert truncated is False
    origins = matching[0].origins
    assert "num-a" in origins and "num-b" in origins


def test_generate_enforces_search_value_cap_with_truncation_flag() -> None:
    readings = [
        OcrReading(
            reading_id=f"num-{index}", object_id="obj-1", role="number",
            raw_text=f"1{index:02d}/999", token_refs=(("p1", index),), pass_roles=("full",),
            confidence=None,
        )
        for index in range(20)
    ]
    config = OcrConfig(max_search_values=12)
    hypotheses, truncated = generate_number_hypotheses(readings, config)
    assert truncated is True
    assert len(hypotheses) == 12
    assert [hypothesis.rank for hypothesis in hypotheses] == list(range(1, 13))


def test_unsearchable_reading_produces_no_hypothesis_but_stays_raw() -> None:
    reading = OcrReading(
        reading_id="num-obj-0", object_id="obj-1", role="number", raw_text="n",
        token_refs=(("p1", 0),), pass_roles=("full",), confidence=None,
    )
    hypotheses, _ = generate_number_hypotheses([reading])
    assert hypotheses == ()
    assert reading.raw_text == "n"  # lecture brute intacte pour le diagnostic


def test_extract_name_readings_declass_generic_but_keeps_catalog_and_short_names() -> None:
    catalog = ("Pikachu", "Mew", "Tortank obscur")
    lines = (
        OcrLine(pass_id="p1", group=(1, 1, 1, 1), text="PV 80", box=(0, 0, 10, 10), token_indexes=(0,)),
        OcrLine(pass_id="p1", group=(1, 1, 1, 2), text="Pikachu", box=(0, 20, 10, 10), token_indexes=(1,)),
        OcrLine(pass_id="p1", group=(1, 1, 1, 3), text="Mew", box=(0, 40, 10, 10), token_indexes=(2,)),
        OcrLine(pass_id="p1", group=(1, 1, 1, 4), text="Dresseur", box=(0, 60, 10, 10), token_indexes=(3,)),
        OcrLine(pass_id="p1", group=(1, 1, 1, 5), text="Tortank", box=(0, 80, 10, 10), token_indexes=(4,)),
    )
    readings = extract_name_readings(lines, object_id="obj-1", pass_role="full", catalog_names=catalog)
    assert [reading.raw_text for reading in readings] == ["Pikachu", "Mew"]
    without_catalog = extract_name_readings(lines, object_id="obj-1", pass_role="full")
    # Avec vocabulaire : seuls les noms du catalogue sont proposés (« Tortank » seul
    # n'y figure pas) ; sans vocabulaire : « Mew » (3 lettres) exige le catalogue.
    assert [reading.raw_text for reading in without_catalog] == ["Pikachu", "Tortank"]


@pytest.fixture
def matcher(tmp_path: Path) -> CardMatcher:
    path = tmp_path / "hypotheses.sqlite"
    with connect(path) as connection:
        apply_migrations(connection)
        TcgdexCache(connection).seed_initial_if_empty()
        yield CardMatcher(TcgdexCache(connection), seed_if_empty=False, repair_index=False)


def _reading(raw: str, reading_id: str = "num-obj-0", confidence: float | None = None) -> OcrReading:
    return OcrReading(
        reading_id=reading_id, object_id="obj-1", role="number", raw_text=raw,
        token_refs=(("p1", 0),), pass_roles=("full",), confidence=confidence,
    )


def test_search_unions_candidates_and_exposes_alternatives(matcher: CardMatcher) -> None:
    hypotheses, _ = generate_number_hypotheses([_reading("58/102")])
    search = search_hypotheses(matcher, hypotheses, {"num-obj-0": ("Pikachu",)})
    base1_58 = next(candidate for candidate in search.suggestions if candidate.tcgdex_id == "base1-58")
    assert base1_58.literal_support
    assert "58/1102" in base1_58.alternatives  # insertion du même groupe, proposée jamais imposée
    assert search.suggestions[0].confidence >= search.suggestions[-1].confidence


def test_search_continues_after_miss_and_marks_contradictions(matcher: CardMatcher) -> None:
    hypotheses, _ = generate_number_hypotheses([
        _reading("999/102", "num-miss"),
        _reading("58/102", "num-hit"),
    ])
    search = search_hypotheses(matcher, hypotheses, {"num-miss": ("Pikachu",), "num-hit": ("Pikachu",)})
    assert any(candidate.tcgdex_id == "base1-58" for candidate in search.suggestions)
    assert search.values_examined == len(hypotheses)  # toutes les hypothèses examinées


def test_search_respects_combination_cap(matcher: CardMatcher) -> None:
    readings = [_reading(f"1{index:02d}/102", f"num-{index}") for index in range(8)]
    hypotheses, _ = generate_number_hypotheses(readings)
    config = OcrConfig(max_name_number_combos=3)
    search = search_hypotheses(
        matcher, hypotheses, {f"num-{index}": ("Pikachu", "Raichu", "Roucoups") for index in range(8)},
        config=config,
    )
    assert search.truncated
    assert search.combos_used == 3
    assert any("search_truncated" in item for item in search.diagnostics)


def test_search_checks_deadline_between_hypotheses(matcher: CardMatcher) -> None:
    hypotheses, _ = generate_number_hypotheses([_reading("58/102")])
    deadline = Deadline(20.0, clock=iter([0.0, 100.0]).__next__)
    with pytest.raises(Exception):
        search_hypotheses(matcher, hypotheses, {}, deadline=deadline)


def test_hypothesis_features_reuse_matcher_contract(matcher: CardMatcher) -> None:
    components = parse_number("20/82")
    assert components is not None
    hypothesis = generate_number_hypotheses([_reading("20/82")])[0][0]
    features = hypothesis_features(hypothesis, "Pikachu")
    assert features.local_id == "20" and features.set_card_count == "82"
    candidates = matcher.retrieve_candidates(features)
    assert any(candidate.tcgdex_id == "base1-58" for candidate in candidates)


def test_full_analysis_fragment_n_is_diagnostic_only(matcher: CardMatcher) -> None:
    tokens, lines = _tokens_lines([_token(0, "Pikachu", 10, top=10), _token(1, "n", 100, top=200)])
    readings = [
        *extract_name_readings(lines, object_id="obj-1", pass_role="full", catalog_names=("Pikachu",)),
        *extract_number_readings(tokens, lines, object_id="obj-1", pass_role="full"),
    ]
    hypotheses, _ = generate_number_hypotheses(readings)
    assert all(hypothesis.value != "n" for hypothesis in hypotheses)
    noise = [reading for reading in readings if reading.role == "unknown"]
    assert [reading.raw_text for reading in noise] == ["n"]
    search = search_hypotheses(matcher, hypotheses, {})
    assert search.suggestions == ()  # pas d'identité fabriquée depuis un fragment
