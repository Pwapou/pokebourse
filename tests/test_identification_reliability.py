"""Fiabilisation des numéros promotionnels, du classement et de l'OCR adaptatif."""
from __future__ import annotations

import io
import sqlite3
from pathlib import Path

import pytest
from PIL import Image

from app.identification.detector import extract_features
from app.identification.matcher import CardMatcher
from app.identification.ocr import analyze_image, extract_suggestions
from app.storage.database import connect
from app.storage.migration_runner import apply_migrations
from app.tcgdex.cache import TcgdexCache
from app.tcgdex.models import TcgdexCard, TcgdexSet


@pytest.fixture
def connection(tmp_path: Path):
    with connect(tmp_path / "reliability.db") as connection:
        apply_migrations(connection)
        cache = TcgdexCache(connection)
        cache.seed_initial_if_empty()
        cache.upsert_set(TcgdexSet(id="smp", name="Promo SM"))
        cache.upsert_card(TcgdexCard(
            id="smp-SM233", local_id="SM233", name="Évoli GX",
            set_id="smp", set_name="Promo SM", rarity="Promo",
        ))
        connection.commit()
        yield connection


@pytest.mark.parametrize("number", ["SM233", "SVP001", "SWSH020", "XY123", "BW001"])
def test_promotional_numbers_are_structured_evidence(number: str) -> None:
    features = extract_features(f"Carte promo {number}, excellent état")
    assert features.local_id == number
    assert features.card_number == number
    assert features.set_card_count is None


def test_promotional_ocr_o_is_normalized_to_zero() -> None:
    assert extract_features("Vipélierre Bwo1").local_id == "BW01"


@pytest.mark.parametrize("text", [
    "Prix SM 233 euros", "Promotion 2023", "150 €", "Édition 2024",
])
def test_prices_dates_and_plain_numbers_are_not_promotional_numbers(text: str) -> None:
    assert extract_features(text).local_id is None


def test_title_and_description_identify_evoli_gx_without_image(connection) -> None:
    cache = TcgdexCache(connection)
    cache.upsert_set(TcgdexSet(id="sm1", name="Soleil et Lune"))
    cache.upsert_card(TcgdexCard(
        id="sm1-1", local_id="1", name="Pikachu", set_id="sm1", set_name="Soleil et Lune",
    ))
    result = CardMatcher(cache).identify(
        "Evoli GX, Promo sm233, Soleil et lune, état excellent"
    )
    assert result.status == "identified"
    assert result.matched_card is not None
    assert result.matched_card.tcgdex_id == "smp-SM233"
    assert result.features.card_number == "SM233"
    assert result.candidates[0].score_criteria
    assert result.candidates[0].confidence_level == "élevé"


def test_dracaufeu_ex_fraction_keeps_exact_reference(connection) -> None:
    result = CardMatcher(TcgdexCache(connection)).identify("Dracaufeu-ex 199/165 151")
    assert result.status == "identified"
    assert result.matched_card is not None
    assert result.matched_card.local_id == "199"


def test_exact_number_survives_incorrect_ocr_name(connection) -> None:
    result = CardMatcher(TcgdexCache(connection)).identify("Evoli XY SM233")
    assert result.candidates[0].tcgdex_id == "smp-SM233"
    assert result.candidates[0].name_match_kind == "partial"
    assert result.status == "ambiguous"


def test_recognized_name_without_number_remains_a_scored_suggestion(connection) -> None:
    result = CardMatcher(TcgdexCache(connection)).identify("Évoli GX")
    assert result.status == "ambiguous"
    assert result.candidates[0].tcgdex_id == "smp-SM233"
    assert result.candidates[0].name_match_kind == "exact"
    assert result.candidates[0].confidence < 80


def test_shared_number_is_not_resolved_alphabetically(connection) -> None:
    cache = TcgdexCache(connection)
    cache.upsert_set(TcgdexSet(id="other", name="Autre promo"))
    cache.upsert_card(TcgdexCard(
        id="other-SM233", local_id="SM233", name="Évoli GX",
        set_id="other", set_name="Autre promo",
    ))
    result = CardMatcher(cache).identify("SM233")
    assert result.status == "ambiguous"
    assert result.matched_card is None
    assert {candidate.tcgdex_id for candidate in result.candidates} == {"smp-SM233", "other-SM233"}


def test_ocr_noise_does_not_become_a_name(connection) -> None:
    result = extract_suggestions(connection, "Carte\nÉra\nÉvoli GX\nSM233")
    assert result["recognized"] == {"names": ["Évoli GX"], "numbers": ["SM233"]}
    assert result["candidates"][0]["tcgdex_id"] == "smp-SM233"
    assert "Carte" not in result["recognized"]["names"]
    assert "Éra" not in result["recognized"]["names"]


def test_unreadable_image_is_rejected(connection) -> None:
    with pytest.raises(ValueError, match="illisible"):
        analyze_image(connection, b"ceci n'est pas une image")


def test_incomplete_catalog_does_not_invent_identity(tmp_path: Path) -> None:
    with connect(tmp_path / "empty.db") as connection:
        apply_migrations(connection)
        result = CardMatcher(TcgdexCache(connection), seed_if_empty=False).identify("Évoli GX SM233")
        assert result.status == "unidentified"
        assert result.matched_card is None
        assert result.features.local_id == "SM233"


def _image() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (400, 600), "white").save(output, format="PNG")
    return output.getvalue()


def test_ocr_skips_targeted_passes_when_first_result_is_sufficient(connection, monkeypatch) -> None:
    calls: list[int] = []

    def read(_image: bytes, psm: int = 11) -> str:
        calls.append(psm)
        return "Évoli GX SM233"

    monkeypatch.setattr("app.identification.ocr._run_tesseract", read)
    result = analyze_image(connection, _image())
    assert result["candidates"][0]["tcgdex_id"] == "smp-SM233"
    assert calls == [11]


def test_ocr_uses_targeted_passes_only_after_insufficient_result(connection, monkeypatch) -> None:
    calls: list[int] = []

    def read(_image: bytes, psm: int = 11) -> str:
        calls.append(psm)
        return "" if len(calls) == 1 else "Évoli GX SM233"

    monkeypatch.setattr("app.identification.ocr._run_tesseract", read)
    result = analyze_image(connection, _image())
    assert result["candidates"][0]["tcgdex_id"] == "smp-SM233"
    assert calls == [11, 6]


@pytest.mark.parametrize("title, description", [
    ("Carte Pokémon Évoli V vendu avec 3 cartes en plus", None),
    ("Carte Pokémon Évoli V", "vendue avec trois cartes supplémentaires"),
    ("Carte Pokémon Évoli V + 3 cartes offertes", None),
    ("Dracaufeu 4/102 vendu avec une carte en plus", None),
    ("Dracaufeu 4/102", "vendu avec 3 cartes"),
    ("Dracaufeu 4/102", "avec trois cartes supplémentaires"),
    ("Dracaufeu 4/102", "carte seule, pas un lot, mais + 3 cartes offertes"),
])
def test_included_extra_cards_are_lots(connection, title: str, description: str | None) -> None:
    result = CardMatcher(TcgdexCache(connection)).identify(title, description)
    assert result.features.is_lot is True
    assert result.status == "lot"
    assert result.features.lot_reason
    assert result.reason == result.features.lot_reason
    assert result.matched_card is None
    assert result.candidates == []


@pytest.mark.parametrize("text", [
    "carte avec protection",
    "carte avec 3 photos",
    "Dracaufeu 4/102 carte Pokémon",
    "Dracaufeu 4 / 102 carte Pokémon",
    "carte seule, pas un lot",
    "carte seule, pas un lot de cartes Pokémon",
    "carte seule, sans lot Pokémon",
    "1 carte Pokémon avec boîtier",
])
def test_single_card_accessories_photos_and_negations_are_not_lots(text: str) -> None:
    features = extract_features(text)
    assert features.is_lot is False
    assert features.lot_reason is None


@pytest.mark.parametrize("description", [
    "une carte au choix parmi 3",
    "carte au choix parmi plusieurs",
    "3 cartes Pokémon au choix, une seule vendue",
    "une carte à choisir parmi trois",
])
def test_card_selection_never_accepts_the_first_recognized_card(connection, description: str) -> None:
    # Le titre suffit à identifier une référence exacte sans cette description.
    matcher = CardMatcher(TcgdexCache(connection))
    assert matcher.identify("Dracaufeu 4/102 Set de Base").status == "identified"
    result = matcher.identify("Dracaufeu 4/102 Set de Base", description)
    assert result.status == "ambiguous"
    assert result.features.is_lot is False
    assert result.matched_card is None
    assert "choix" in result.reason


@pytest.mark.parametrize("phrase", [
    "en plus", "en bon état", "en excellent état", "VO", "version originale VO",
])
def test_french_preposition_and_vo_do_not_prove_english(connection, phrase: str) -> None:
    result = CardMatcher(TcgdexCache(connection)).identify("Dracaufeu 4/102 Set de Base", phrase)
    assert result.features.language is None
    assert result.status == "identified"
    assert result.matched_card is not None


@pytest.mark.parametrize("mention, language", [
    ("carte anglaise", "en"), ("English", "en"), ("langue : EN", "en"),
    ("VO English", "en"), ("carte française", "fr"), ("VF", "fr"),
    ("français", "fr"), ("FR", "fr"), ("French", "fr"),
    ("carte japonaise", "ja"), ("Japanese", "ja"), ("JP", "ja"), ("jap", "ja"),
])
def test_explicit_language_mentions_remain_recognized(connection, mention: str, language: str) -> None:
    result = CardMatcher(TcgdexCache(connection)).identify("Dracaufeu 4/102 Set de Base", mention)
    assert result.features.language == language
    if language != "fr":
        assert result.status == "unidentified"
        assert result.matched_card is None


@pytest.mark.parametrize("condition", [
    "nearmint", "near-mint", "near mint", "NEARMINT", "Near-Mint",
    "nEaR   mInT", "near\tmint", "near\u00a0mint", "near - mint",
])
def test_near_mint_spellings_share_declared_condition(condition: str) -> None:
    assert extract_features("Dracaufeu 4/102", f"état déclaré : {condition}").condition == "Near Mint"


@pytest.mark.parametrize("title", [
    "Dracaufeu ex 199/165", "Dracaufeu EX 199/165", "Dracaufeu-ex 199/165 151",
])
def test_ex_suffix_does_not_declare_excellent_condition(connection, title: str) -> None:
    result = CardMatcher(TcgdexCache(connection)).identify(title)
    assert result.status == "identified"
    assert result.matched_card is not None
    assert result.matched_card.tcgdex_id == "sv03.5-199"
    assert result.features.variant == "ex"
    assert result.features.condition is None
    assert "état" in result.uncertain_fields


@pytest.mark.parametrize("mention", ["excellent", "Excellent état", "état EX", "État : EX", "condition EX"])
def test_explicit_excellent_condition_is_preserved(mention: str) -> None:
    features = extract_features("Dracaufeu ex 199/165", mention)
    assert features.condition == "Excellent"
    assert features.variant == "ex"


@pytest.mark.parametrize("mention, expected", [("mint", "Neuf"), ("neuf", "Neuf"), ("PSA 9", None)])
def test_condition_equivalences_are_not_expanded(mention: str, expected: str | None) -> None:
    assert extract_features("Dracaufeu 4/102", mention).condition == expected


@pytest.mark.parametrize("title, description", [
    ("Dracaufeu 4/102 Set de Base VF", "English"),
    ("Dracaufeu 4/102 Set de Base English", "VF"),
    ("Dracaufeu 4/102 Set de Base", "langue : FR/EN"),
    ("Dracaufeu 4/102 Set de Base", "français ou japonais"),
    ("Dracaufeu 4/102 Set de Base", "English / Japanese"),
])
def test_multiple_language_evidence_blocks_automatic_identity(
    connection: sqlite3.Connection, title: str, description: str,
) -> None:
    """L'ordre des langues observées ne doit jamais arbitrer l'impression vendue."""
    result = CardMatcher(TcgdexCache(connection)).identify(title, description)
    assert result.features.language is None
    assert len(result.features.languages) == 2
    assert result.status == "ambiguous"
    assert result.matched_card is None
    assert result.candidates == []
    assert "langues multiples ou contradictoires" in result.reason
    assert "langue" in result.uncertain_fields


@pytest.mark.parametrize("description, expected", [
    ("VF, français, French", ("fr",)),
    ("langue : en, English", ("en",)),
    ("carte japonaise (JP)", ("ja",)),
    ("langue : ja", ("ja",)),
    ("langue : jp", ("ja",)),
    ("langue : US", ("en",)),
    ("[EN]", ("en",)),
    ("en bon état, carte en excellent état, VO", ()),
])
def test_language_observations_are_unique_and_explicit(description: str, expected: tuple[str, ...]) -> None:
    """Plusieurs mentions de la même langue constituent une seule valeur observée."""
    features = extract_features("Carte Pokémon", description)
    assert features.languages == expected
    assert features.language == (expected[0] if expected else None)


@pytest.mark.parametrize("raw, normalized", [
    ("nEaR   mInT", "Near Mint"), ("near-mint", "Near Mint"),
    ("nearmint", "Near Mint"), ("très bon état", "Near Mint"),
    ("neuf", "Neuf"), ("État : EX", "Excellent"),
])
def test_declared_condition_retains_exact_raw_excerpt(raw: str, normalized: str) -> None:
    """Le libellé normalisé ne remplace pas la déclaration textuelle du vendeur."""
    features = extract_features("Dracaufeu ex 199/165", f"Déclaration : {raw}.")
    assert features.condition == normalized
    assert features.condition_raw == raw


def test_absent_condition_and_grading_do_not_invent_a_declaration() -> None:
    """Ni suffixe ni note de gradation ne constituent un état déclaré."""
    features = extract_features("Dracaufeu ex 199/165 PSA 10")
    assert features.condition is None
    assert features.condition_raw is None


@pytest.mark.parametrize("title", [
    "Évoli V 0113/15 Gem Pack 2",
    "Évoli V 0113/15 gempack 2",
    "Mentali 175 Gem Pack 2",
    "Carte Pokémon Gem Pack 2",
    "Dracaufeu 4/102 numéro de série 102 carte Pokémon",
    "Dracaufeu 4/102, serial number: 102 carte Pokémon",
    "Dracaufeu 4/102, numéro de série 102/200 carte Pokémon",
])
def test_reference_labels_are_not_sale_quantities(title: str) -> None:
    """Un numéro et un nom d'extension ne décrivent pas des objets supplémentaires."""
    assert extract_features(title).is_lot is False


@pytest.mark.parametrize("description", [
    "numéro de série 102 carte Pokémon", "serial number: 102 carte Pokémon",
])
def test_serial_number_is_not_reused_as_card_number(description: str) -> None:
    """Un numéro étiqueté comme série ne devient pas un numéro de carte isolé."""
    features = extract_features("Dracaufeu", description)
    assert features.is_lot is False
    assert features.card_number is None


@pytest.mark.parametrize("set_name", ["Gem Pack 2", "Collection de cartes", "Booster Test"])
def test_catalog_set_mentions_do_not_trigger_lot_rules(set_name: str) -> None:
    """La protection du vocabulaire local n'ajoute aucun alias d'extension."""
    features = extract_features(f"Dracaufeu 4/102 {set_name}", catalog_sets=[set_name])
    assert features.set_name == set_name
    assert features.is_lot is False
    assert extract_features(f"Coffret Pokémon, carte de {set_name}", catalog_sets=[set_name]).is_lot is True


@pytest.mark.parametrize("title", [
    "Pack Pokémon scellé", "Pack de 3 boosters", "Pack 151 scellé",
    "2 packs Pokémon", "Booster Gem Pack 2 scellé", "Coffret Pokémon",
    "Lot de trois cartes", "Trois cartes Pokémon", "Évoli + trois cartes offertes",
])
def test_explicit_product_context_and_written_quantities_remain_lots(title: str) -> None:
    """Les produits scellés et quantités vendues conservent leur classification."""
    assert extract_features(title).is_lot is True


def test_gem_pack_case_keeps_observations_without_inventing_an_alias(connection: sqlite3.Connection) -> None:
    """Le correctif de lot n'invente ni extension française ni identité dans un cache incomplet."""
    result = CardMatcher(TcgdexCache(connection)).identify("Evoli V 0113/15 gempack 2 nearmint")
    assert result.features.is_lot is False
    assert result.features.card_number == "0113/15"
    assert result.features.set_name is None
    assert result.features.language is None
    assert result.features.condition == "Near Mint"
    assert result.features.condition_raw == "nearmint"
    assert result.status == "unidentified"
    assert result.matched_card is None
