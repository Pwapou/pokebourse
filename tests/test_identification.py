import sqlite3
from collections.abc import Iterator
from pathlib import Path
import pytest

from app.identification.detector import extract_features
from app.identification.matcher import CardMatcher
from app.storage.database import connect
from app.storage.migration_runner import apply_migrations
from app.tcgdex.cache import TcgdexCache


@pytest.fixture
def matcher(tmp_path: Path) -> Iterator[CardMatcher]:
    db_path = tmp_path / "ident_test.db"
    with connect(db_path) as conn:
        apply_migrations(conn)
        cache = TcgdexCache(conn)
        cache.seed_initial_if_empty()
        yield CardMatcher(cache)


def test_extract_features_exact_card() -> None:
    features = extract_features(
        title="Carte Pokémon Dracaufeu 4/102 Set de Base Holo",
        description="Version française VF en état Near Mint. Pas d'échange.",
    )
    assert features.name == "Dracaufeu"
    assert features.card_number == "4/102"
    assert features.local_id == "4"
    assert features.set_card_count == "102"
    assert features.set_name == "Set de Base"
    assert features.variant == "Holo"
    assert features.language == "fr"
    assert features.condition == "Near Mint"
    assert features.is_lot is False


def test_extract_features_detects_lot_and_sealed_products() -> None:
    features_lot = extract_features(
        title="Lot de 50 cartes Pokémon diverses",
        description="En vrac, cartes communes et quelques holos.",
    )
    assert features_lot.is_lot is True
    assert features_lot.lot_reason is not None

    features_booster = extract_features(
        title="Booster Pokémon 151 scellé sous blister",
        description="Neuf sous blister officiel.",
    )
    assert features_booster.is_lot is True


def test_extract_features_grading() -> None:
    features = extract_features(
        title="Dracaufeu VMAX 20/189 PSA 10",
        description="Superbe carte certifiée PSA note 10.",
    )
    assert features.name == "Dracaufeu VMAX"
    assert features.card_number == "20/189"
    assert features.grading_company == "PSA"
    assert features.grade == "10"
    assert features.is_lot is False


def test_identification_clear_single_match(matcher: CardMatcher) -> None:
    result = matcher.identify("Carte Pokémon Dracaufeu 4/102 Set de Base Holo")
    assert result.status == "identified"
    assert result.confidence >= 80
    assert result.matched_card is not None
    assert result.matched_card.tcgdex_id == "base1-4"
    assert result.matched_card.name == "Dracaufeu"
    assert result.matched_card.set_name == "Set de Base"
    assert "nom exact" in result.reason
    assert "numéro 4 exact" in result.reason


def test_identification_ambiguous_marks_to_verify_without_forcing(matcher: CardMatcher) -> None:
    # "Pikachu" seul : existe dans Set de Base, Évolutions, 151
    result = matcher.identify("Pikachu bon état")
    assert result.status == "ambiguous"
    assert result.matched_card is None  # Ne force AUCUNE attribution arbitraire !
    assert len(result.candidates) >= 2
    assert "Ambiguïté" in result.reason or "À vérifier" in result.reason or "partielle" in result.reason


def test_identification_lot_does_not_attribute_single_card(matcher: CardMatcher) -> None:
    result = matcher.identify(
        title="Lot de 50 cartes Pokémon Dracaufeu Pikachu",
        description="Collection de 50 cartes en vrac.",
    )
    assert result.status == "lot"
    assert result.matched_card is None
    assert result.features.is_lot is True
    assert "lot" in result.reason.lower()


def test_identification_unidentified_remains_available(matcher: CardMatcher) -> None:
    result = matcher.identify("Figurine en plastique objet inconnu 12345")
    assert result.status == "unidentified"
    assert result.confidence == 0
    assert result.matched_card is None
    assert "nom" in result.missing_fields or "numéro" in result.missing_fields


def test_identification_close_variants_dracaufeu_ex_151(matcher: CardMatcher) -> None:
    # Dans 151, il y a Dracaufeu ex 006 (double rare) et 199 (illustration spéciale rare)
    result_006 = matcher.identify("Dracaufeu ex 006/165 151")
    assert result_006.status == "identified"
    assert result_006.matched_card is not None
    assert result_006.matched_card.local_id == "006"

    result_199 = matcher.identify("Dracaufeu ex 199/165 151 alternative")
    assert result_199.status == "identified"
    assert result_199.matched_card is not None
    assert result_199.matched_card.local_id == "199"


def test_identification_does_not_conclude_authenticity() -> None:
    features = extract_features("Dracaufeu 4/102 Set de Base")
    # L'état ou l'authenticité ne sont pas inventés
    assert features.condition is None
    assert features.grading_company is None
