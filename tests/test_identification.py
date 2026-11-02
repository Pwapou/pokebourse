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


@pytest.mark.parametrize(
    ("case_id", "title", "expected"),
    [
        (
            "mentali_ex_175_collectaura_9_5",
            "Mentali EX 175 CollectAura 9.5",
            {
                "local_id": "175",
                "card_number": "175",
                "set_card_count": None,
                "variant": "ex",
                "grading_company": "COLLECTAURA",
                "grade": "9.5",
            },
        ),
        (
            "mentali_ex_175_collectaura_9_5_lowercase",
            "mentali ex 175 collectaura 9.5",
            {
                "local_id": "175",
                "card_number": "175",
                "set_card_count": None,
                "variant": "ex",
                "grading_company": "COLLECTAURA",
                "grade": "9.5",
            },
        ),
        (
            "mentali_ex_psa10_glued",
            "Mentali ex PSA10",
            {
                "local_id": None,
                "card_number": None,
                "set_card_count": None,
                "variant": "ex",
                "grading_company": "PSA",
                "grade": "10",
            },
        ),
        (
            "mentali_cgc_9_5",
            "Mentali CGC 9.5",
            {
                "local_id": None,
                "card_number": None,
                "set_card_count": None,
                "variant": None,
                "grading_company": "CGC",
                "grade": "9.5",
            },
        ),
        (
            "mentali_ex_175_198_forces_temporelles_fraction_priority",
            "Mentali ex 175/198 Forces Temporelles",
            {
                "local_id": "175",
                "card_number": "175/198",
                "set_card_count": "198",
                "set_name": "Forces Temporelles",
                "variant": "ex",
                "grading_company": None,
                "grade": None,
            },
        ),
        (
            "mentali_ex_hash_175_prefix",
            "Mentali ex #175",
            {
                "local_id": "175",
                "card_number": "175",
                "set_card_count": None,
                "variant": "ex",
            },
        ),
        (
            "mentali_ex_numero_175_prefix",
            "Mentali ex n°175",
            {
                "local_id": "175",
                "card_number": "175",
                "set_card_count": None,
                "variant": "ex",
            },
        ),
        (
            "dracaufeu_4_102_set_de_base",
            "Dracaufeu 4/102 set de base",
            {
                "local_id": "4",
                "card_number": "4/102",
                "set_card_count": "102",
                "set_name": "Set de Base",
            },
        ),
        (
            "carte_pokemon_mentali_ex_175_sous_sleeve",
            "Carte pokemon Mentali ex 175 sous sleeve",
            {
                "local_id": "175",
                "card_number": "175",
                "set_card_count": None,
                "variant": "ex",
            },
        ),
    ],
    ids=lambda item: item if isinstance(item, str) and "_" in item else None,
)
def test_extract_features_parsing_matrix_3_3(
    case_id: str, title: str, expected: dict[str, object]
) -> None:
    features = extract_features(title)
    assert features.name is not None, f"[{case_id}] nom attendu pour {title!r}"
    for attr, expected_value in expected.items():
        assert getattr(features, attr) == expected_value, (
            f"[{case_id}] {attr}: attendu {expected_value!r}, obtenu {getattr(features, attr)!r}"
        )


@pytest.mark.parametrize(
    ("case_id", "title", "expected"),
    [
        (
            "reject_lot_50_cartes_mentali_4",
            "Lot de 50 cartes Pokémon dont Mentali 4",
            {"is_lot": True, "local_id": None, "card_number": None},
        ),
        (
            "reject_lot_50_cartes_dracaufeu_4",
            "Lot de 50 cartes, Dracaufeu 4",
            {"is_lot": True, "local_id": None, "card_number": None},
        ),
        (
            "reject_decimal_without_grading_company",
            "Mentali ex 9.5",
            {"local_id": None, "card_number": None, "grading_company": None, "grade": None},
        ),
        (
            "reject_single_digit_isolated",
            "Mentali ex 9",
            {"local_id": None, "card_number": None, "grading_company": None, "grade": None},
        ),
        (
            "reject_year_2023",
            "Carte Pokémon édition 2023",
            {"local_id": None, "card_number": None},
        ),
        (
            "reject_price_150_euro_glued",
            "Mentali 150€",
            {"local_id": None, "card_number": None},
        ),
        (
            "reject_price_150_euro_spaced",
            "Mentali 150 €",
            {"local_id": None, "card_number": None},
        ),
        (
            "reject_price_eur_and_percentage",
            "Mentali 120 eur 100%",
            {"local_id": None, "card_number": None},
        ),
        (
            "reject_quantity_x3",
            "Vends x3 Mentali ex",
            {"local_id": None, "card_number": None},
        ),
        (
            "reject_psa_9_grade_not_card_number",
            "Mentali PSA 9",
            {"local_id": None, "card_number": None, "grading_company": "PSA", "grade": "9"},
        ),
        (
            "reject_psa_10_spaced_grade_not_card_number",
            "Mentali PSA 10",
            {"local_id": None, "card_number": None, "grading_company": "PSA", "grade": "10"},
        ),
        (
            "reject_over_300_ref_9999",
            "Mentali Réf 9999",
            {"local_id": None, "card_number": None},
        ),
        (
            "reject_over_300_three_digits",
            "Mentali 350",
            {"local_id": None, "card_number": None},
        ),
        (
            "reject_generic_title_without_card_name_or_set",
            "Cartes 125 disponibles",
            {"name": None, "set_name": None, "local_id": None, "card_number": None},
        ),
    ],
    ids=lambda item: item if isinstance(item, str) and item.startswith("reject_") else None,
)
def test_extract_features_rejection_matrix_3_4(
    case_id: str, title: str, expected: dict[str, object]
) -> None:
    features = extract_features(title)
    for attr, expected_value in expected.items():
        assert getattr(features, attr) == expected_value, (
            f"[{case_id}] {attr}: attendu {expected_value!r}, obtenu {getattr(features, attr)!r}"
        )


@pytest.mark.parametrize(
    ("title", "expected_company", "expected_grade"),
    [
        ("Mentali CollectAura 9.5", "COLLECTAURA", "9.5"),
        ("Mentali Collect'Aura 9.5", "COLLECTAURA", "9.5"),
        ("Mentali Collect’Aura 10", "COLLECTAURA", "10"),
        ("Mentali Collect Aura 9", "COLLECTAURA", "9"),
        ("Pikachu psa10", "PSA", "10"),
        ("Pikachu PCA9.5", "PCA", "9.5"),
        ("Dracaufeu BGS 9.5", "BGS", "9.5"),
        ("Dracaufeu SGS 8", "SGS", "8"),
        ("Mentali PCA 9.25", None, None),
        ("MentaliPSA 10.5", None, None),
        ("Mentali UnknownGrader 9.5", None, None),
    ],
)
def test_extract_features_grading_companies_and_strict_grades(
    title: str, expected_company: str | None, expected_grade: str | None
) -> None:
    features = extract_features(title)
    assert features.grading_company == expected_company
    assert features.grade == expected_grade
    assert features.local_id is None


def test_matcher_real_case_mentali_175_collectaura_never_forces_identified(
    tmp_path: Path,
) -> None:
    from app.tcgdex.models import TcgdexCard, TcgdexSet

    db_path = tmp_path / "mentali_real_case.db"
    with connect(db_path) as conn:
        apply_migrations(conn)
        cache = TcgdexCache(conn)
        cache.seed_initial_if_empty()
        local_matcher = CardMatcher(cache)

        # 1. Référentiel seed seul (Mentali absent) : non identifiée mais preuves extraites et incertitude remontée
        res_seed = local_matcher.identify("Mentali EX 175 CollectAura 9.5")
        assert res_seed.status == "unidentified"
        assert res_seed.matched_card is None
        assert res_seed.features.local_id == "175"
        assert res_seed.features.card_number == "175"
        assert res_seed.features.set_card_count is None
        assert res_seed.features.grading_company == "COLLECTAURA"
        assert res_seed.features.grade == "9.5"
        assert "numéro isolé, sans dénominateur" in res_seed.uncertain_fields

        # 2. Référentiel enrichi avec Mentali ex #175 : candidat proposé en « ambiguous », jamais « identified » forcé
        with conn:
            cache.upsert_set(
                TcgdexSet(
                    id="sv05",
                    name="Forces Temporelles",
                    card_count_official=162,
                    card_count_total=218,
                )
            )
            cache.upsert_card(
                TcgdexCard(
                    id="sv05-175",
                    local_id="175",
                    name="Mentali ex",
                    set_id="sv05",
                    set_name="Forces Temporelles",
                    rarity="Double rare",
                )
            )

        res_enriched = local_matcher.identify("Mentali EX 175 CollectAura 9.5")
        assert res_enriched.status == "ambiguous"
        assert res_enriched.matched_card is None
        assert res_enriched.confidence is not None and res_enriched.confidence < 80
        assert res_enriched.candidates[0].tcgdex_id == "sv05-175"
        assert "numéro isolé, sans dénominateur" in res_enriched.uncertain_fields

        # Même avec le nom d'extension mais toujours sans dénominateur : reste au mieux « ambiguous »
        res_with_set_no_denom = local_matcher.identify(
            "Mentali EX 175 Forces Temporelles CollectAura 9.5"
        )
        assert res_with_set_no_denom.status == "ambiguous"
        assert res_with_set_no_denom.matched_card is None
        assert "numéro isolé, sans dénominateur" in res_with_set_no_denom.uncertain_fields

        # Avec fraction exacte compatible : « identified » normal conservé
        res_fraction = local_matcher.identify("Mentali ex 175/218 Forces Temporelles")
        assert res_fraction.status == "identified"
        assert res_fraction.matched_card is not None
        assert res_fraction.matched_card.tcgdex_id == "sv05-175"
        assert "numéro isolé, sans dénominateur" not in res_fraction.uncertain_fields


def test_matcher_grading_is_strictly_neutral_on_confidence_and_candidates(
    matcher: CardMatcher,
) -> None:
    # 1. Sans candidat local : la gradation ne crée aucun candidat
    unmatched = matcher.identify("Mentali PSA 9")
    assert unmatched.status == "unidentified"
    assert unmatched.confidence == 0
    assert unmatched.candidates == []
    assert unmatched.features.grading_company == "PSA"
    assert unmatched.features.grade == "9"

    # 2. Sur une annonce ambiguë : le score et les candidats sont identiques avec ou sans gradation
    plain_ambiguous = matcher.identify("Tortank 15")
    graded_ambiguous = matcher.identify("Tortank 15 CollectAura 9.5")
    assert plain_ambiguous.status == graded_ambiguous.status == "ambiguous"
    assert plain_ambiguous.confidence == graded_ambiguous.confidence
    assert [
        (c.tcgdex_id, c.confidence) for c in plain_ambiguous.candidates
    ] == [(c.tcgdex_id, c.confidence) for c in graded_ambiguous.candidates]

    # 3. Sur une annonce identifiée par fraction : le score est strictement identique
    plain_identified = matcher.identify("Dracaufeu VMAX 20/189 Ténèbres Embrasées")
    graded_identified = matcher.identify(
        "Dracaufeu VMAX 20/189 Ténèbres Embrasées PSA 10"
    )
    assert plain_identified.status == graded_identified.status == "identified"
    assert plain_identified.confidence == graded_identified.confidence

