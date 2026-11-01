import json
from pathlib import Path

import pytest

from app.catalog import import_jsonl
from app.profitability import (
    FeeProfileUpdate,
    ProfitabilityError,
    ReferenceInput,
    delete_reference,
    evaluate_catalog,
    find_price_comparables,
    import_references_jsonl,
    parse_euros_to_cents,
    parse_percent_to_bps,
    update_active_fee_profile,
    upsert_reference,
)
from app.sellers.repository import record_purchase
from app.storage.database import connect
from app.storage.migration_runner import apply_migrations


def jsonl(*rows: dict[str, object]) -> bytes:
    return "\n".join(json.dumps(row) for row in rows).encode("utf-8")


def configure_fees(connection, **overrides: int) -> None:
    values = {
        "buyer_shipping_cents": 0,
        "platform_fee_bps": 500,
        "seller_fixed_fee_cents": 0,
        "shipping_packaging_cents": 200,
        "min_net_profit_cents": 500,
        "min_roi_bps": 1500,
        "min_catalog_samples": 2,
        **overrides,
    }
    update_active_fee_profile(connection, FeeProfileUpdate(**values))


def test_parse_euros_and_percent_helpers() -> None:
    assert parse_euros_to_cents("12,90", "Prix") == 1290
    assert parse_euros_to_cents("0", "Port") == 0
    assert parse_percent_to_bps("5", "Commission") == 500
    assert parse_percent_to_bps("12,5", "Commission") == 1250

    with pytest.raises(ProfitabilityError):
        parse_euros_to_cents("-1", "Prix")
    with pytest.raises(ProfitabilityError):
        parse_euros_to_cents("1,999", "Prix")
    with pytest.raises(ProfitabilityError):
        parse_percent_to_bps("150", "Commission", max_bps=10_000)


def test_reference_matching_priority_and_secret_rare_isolation(tmp_path: Path) -> None:
    with connect(tmp_path / "profit.db") as connection:
        apply_migrations(connection)
        configure_fees(connection)
        import_jsonl(
            connection,
            jsonl(
                {
                    "external_id": "pika-nm",
                    "name": "Pikachu",
                    "set_name": "Evolutions",
                    "card_number": "35/108",
                    "condition": "NM",
                    "price_cents": 1000,
                },
                {
                    "external_id": "pika-lp",
                    "name": "Pikachu",
                    "set_name": "Évolutions",
                    "card_number": "35/108",
                    "condition": "LP",
                    "price_cents": 1000,
                },
                {
                    "external_id": "pika-common",
                    "name": "Pikachu",
                    "set_name": "151",
                    "card_number": "025/165",
                    "condition": "NM",
                    "price_cents": 300,
                },
            ),
        )
        # Specific NM cote vs generic condition cote, plus a secret rare 173/165
        import_references_jsonl(
            connection,
            jsonl(
                {
                    "name": "Pikachu",
                    "set_name": "Évolutions",
                    "card_number": "35/108",
                    "condition": "NM",
                    "reference_price_cents": 2500,
                },
                {
                    "name": "Pikachu",
                    "set_name": "Évolutions",
                    "card_number": "35/108",
                    "reference_price_cents": 1500,
                },
                {
                    "name": "Pikachu",
                    "set_name": "151",
                    "card_number": "173/165",
                    "condition": "NM",
                    "reference_price_cents": 3500,
                },
            ),
        )

        evaluations, summary, _ = evaluate_catalog(connection)
        by_id = {row["external_id"]: row for row in evaluations}

        # Default profile: 0 buyer ship, 5% fee, 200 packaging, min 500 profit, min 15% ROI
        # pika-nm: 2500 - 125 - 200 - 1000 = +1175 cents (+117.5% ROI) -> opportunite
        assert by_id["pika-nm"]["reference_price_cents"] == 2500
        assert by_id["pika-nm"]["reference_source"] == "reference"
        assert by_id["pika-nm"]["net_profit_cents"] == 1175
        assert by_id["pika-nm"]["roi_bps"] == 11750
        assert by_id["pika-nm"]["verdict"] == "opportunite"

        # pika-lp falls back to generic condition cote (1500): 1500 - 75 - 200 - 1000 = +225 -> surveiller
        assert by_id["pika-lp"]["reference_price_cents"] == 1500
        assert by_id["pika-lp"]["net_profit_cents"] == 225
        assert by_id["pika-lp"]["verdict"] == "surveiller"

        # pika-common (025/165) must NOT match secret rare 173/165!
        assert by_id["pika-common"]["reference_price_cents"] is None
        assert by_id["pika-common"]["verdict"] == "sans_cote"
        assert summary["opportunity_count"] == 1
        assert summary["watch_count"] == 1
        assert summary["missing_count"] == 1


def test_catalog_median_fallback_and_fee_profile_update(tmp_path: Path) -> None:
    with connect(tmp_path / "median.db") as connection:
        apply_migrations(connection)
        configure_fees(connection)
        import_jsonl(
            connection,
            jsonl(
                {
                    "external_id": "deal-1",
                    "name": "Dracaufeu",
                    "set_name": "Base Set",
                    "card_number": "4/102",
                    "condition": "LP",
                    "price_cents": 12000,
                },
                {
                    "external_id": "comp-2",
                    "name": "Dracaufeu",
                    "set_name": "Base Set",
                    "card_number": "4/102",
                    "condition": "LP",
                    "price_cents": 20000,
                },
                {
                    "external_id": "comp-3",
                    "name": "Dracaufeu",
                    "set_name": "Base Set",
                    "card_number": "4/102",
                    "condition": "LP",
                    "price_cents": 22000,
                },
            ),
        )

        # Median of the two other listings [20000, 22000] is 21000.
        evaluations, summary, _ = evaluate_catalog(connection)
        by_id = {row["external_id"]: row for row in evaluations}
        assert by_id["deal-1"]["reference_source"] == "catalog_median"
        assert by_id["deal-1"]["sample_count"] == 2
        assert by_id["deal-1"]["reference_price_cents"] == 21000
        # 21000 - 1050 (5%) - 200 - 12000 = +7750 cents -> opportunite
        assert by_id["deal-1"]["net_profit_cents"] == 7750
        assert by_id["deal-1"]["verdict"] == "opportunite"
        assert by_id["comp-2"]["verdict"] == "non_rentable"
        assert summary["median_match_count"] == 3

        # Tighten fees & thresholds so deal-1 drops to "surveiller"
        update_active_fee_profile(
            connection,
            FeeProfileUpdate(
                buyer_shipping_cents=500,
                platform_fee_bps=1250,
                seller_fixed_fee_cents=50,
                shipping_packaging_cents=350,
                min_net_profit_cents=6000,
                min_roi_bps=2000,
                min_catalog_samples=2,
            ),
        )
        updated_evals, _, _ = evaluate_catalog(connection)
        updated_deal = {row["external_id"]: row for row in updated_evals}["deal-1"]
        # Cost = 12500; proceeds = 21000 - 2625 - 50 - 350 = 17975; profit = 5475 (< 6000) -> surveiller
        assert updated_deal["net_profit_cents"] == 5475
        assert updated_deal["verdict"] == "surveiller"


def test_reference_upsert_delete_and_duplicate_line_rejection(tmp_path: Path) -> None:
    with connect(tmp_path / "refs.db") as connection:
        apply_migrations(connection)
        ref_id = upsert_reference(
            connection,
            ReferenceInput(
                name="Mewtwo",
                set_name="Base Set",
                card_number="10/102",
                reference_price_cents=4500,
            ),
        )
        same_id = upsert_reference(
            connection,
            ReferenceInput(
                name="mewtwo",
                set_name="base set",
                card_number="10/102",
                reference_price_cents=5200,
            ),
        )
        assert same_id == ref_id
        stored = connection.execute(
            "SELECT reference_price_cents FROM market_references WHERE id = ?",
            (ref_id,),
        ).fetchone()[0]
        assert stored == 5200

        assert delete_reference(connection, ref_id) is True
        assert delete_reference(connection, ref_id) is False

        duplicate_jsonl = jsonl(
            {"name": "Mew", "set_name": "151", "reference_price_cents": 1000},
            {"name": "mew", "set_name": "151", "reference_price_cents": 1200},
        )
        with pytest.raises(ProfitabilityError, match="Ligne 2"):
            import_references_jsonl(connection, duplicate_jsonl)


def listing(external_id: str, price_cents: int, **overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "external_id": external_id,
        "name": "Dracaufeu",
        "set_name": "Base Set",
        "card_number": "4/102",
        "condition": "NM",
        "price_cents": price_cents,
    }
    values.update(overrides)
    return values


def reference(price_cents: int, **overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "name": "Dracaufeu",
        "set_name": "Base Set",
        "card_number": "4/102",
        "condition": "NM",
        "reference_price_cents": price_cents,
    }
    values.update(overrides)
    return values


def test_unknown_fees_block_calculation_but_explicit_zero_is_known(tmp_path: Path) -> None:
    with connect(tmp_path / "unknown-fees.db") as connection:
        apply_migrations(connection)
        import_jsonl(connection, jsonl(listing("target", 8000)))
        import_references_jsonl(connection, jsonl(reference(10000)))

        rows, _, _ = evaluate_catalog(connection)
        assert rows[0]["reference_price_cents"] == 10000
        assert rows[0]["net_profit_cents"] is None
        assert rows[0]["verdict"] == "sans_cote"
        assert len(rows[0]["missing_fee_fields"]) == 4

        configure_fees(connection)
        rows, _, _ = evaluate_catalog(connection)
        assert rows[0]["missing_fee_fields"] == []
        assert rows[0]["net_profit_cents"] == 1300
        assert rows[0]["verdict"] == "opportunite"


def test_zero_total_cost_cannot_qualify_with_undefined_roi(tmp_path: Path) -> None:
    with connect(tmp_path / "zero-cost.db") as connection:
        apply_migrations(connection)
        configure_fees(connection)
        import_jsonl(connection, jsonl(listing("free", 0)))
        import_references_jsonl(connection, jsonl(reference(10000)))

        rows, _, _ = evaluate_catalog(connection)
        assert rows[0]["net_profit_cents"] == 9300
        assert rows[0]["roi_bps"] is None
        assert rows[0]["verdict"] == "sans_cote"


def test_roi_threshold_uses_exact_ratio_not_rounded_display(tmp_path: Path) -> None:
    with connect(tmp_path / "roi-rounding.db") as connection:
        apply_migrations(connection)
        configure_fees(
            connection,
            platform_fee_bps=0,
            shipping_packaging_cents=0,
            min_net_profit_cents=0,
            min_roi_bps=1500,
        )
        import_jsonl(connection, jsonl(listing("boundary", 20000)))
        import_references_jsonl(connection, jsonl(reference(22999)))

        rows, _, _ = evaluate_catalog(connection)
        assert rows[0]["net_profit_cents"] == 2999
        assert rows[0]["roi_bps"] == 1500
        assert rows[0]["verdict"] == "surveiller"


def test_zero_profit_qualifies_when_both_thresholds_are_zero(tmp_path: Path) -> None:
    with connect(tmp_path / "zero-thresholds.db") as connection:
        apply_migrations(connection)
        configure_fees(
            connection,
            platform_fee_bps=0,
            shipping_packaging_cents=0,
            min_net_profit_cents=0,
            min_roi_bps=0,
        )
        import_jsonl(connection, jsonl(listing("zero", 1000)))
        import_references_jsonl(connection, jsonl(reference(1000)))

        rows, _, _ = evaluate_catalog(connection)
        assert rows[0]["net_profit_cents"] == 0
        assert rows[0]["roi_bps"] == 0
        assert rows[0]["verdict"] == "opportunite"


def test_catalog_median_excludes_target_and_counts_independent_samples(tmp_path: Path) -> None:
    with connect(tmp_path / "independent-median.db") as connection:
        apply_migrations(connection)
        configure_fees(
            connection,
            platform_fee_bps=0,
            shipping_packaging_cents=0,
            min_net_profit_cents=450,
            min_roi_bps=4000,
        )
        import_jsonl(
            connection,
            jsonl(
                listing("target", 1000),
                listing("comp-1", 1400),
                listing("comp-2", 1600),
            ),
        )

        rows, _, _ = evaluate_catalog(connection)
        target = next(row for row in rows if row["external_id"] == "target")
        assert target["reference_price_cents"] == 1500
        assert target["sample_count"] == 2
        assert target["net_profit_cents"] == 500
        assert target["roi_bps"] == 5000
        assert target["verdict"] == "opportunite"


def test_catalog_median_rejects_unknown_condition_and_certified_raw_mix(
    tmp_path: Path,
) -> None:
    with connect(tmp_path / "condition-isolation.db") as connection:
        apply_migrations(connection)
        configure_fees(connection)
        import_jsonl(
            connection,
            jsonl(
                listing("graded", 1000, condition="Graded", grading_company="PSA", grade="10"),
                listing("unknown", 1000, condition=None),
                listing("raw-1", 10000),
                listing("raw-2", 12000),
            ),
        )

        rows, _, _ = evaluate_catalog(connection)
        by_id = {row["external_id"]: row for row in rows}
        assert by_id["graded"]["reference_price_cents"] is None
        assert by_id["graded"]["verdict"] == "sans_cote"
        assert by_id["unknown"]["reference_price_cents"] is None
        assert by_id["unknown"]["verdict"] == "sans_cote"


def test_variants_and_certifications_are_part_of_comparability(tmp_path: Path) -> None:
    with connect(tmp_path / "variant-isolation.db") as connection:
        apply_migrations(connection)
        configure_fees(connection)
        import_jsonl(
            connection,
            jsonl(
                listing("holo", 1000, variant="Holo"),
                listing("reverse-1", 10000, variant="Reverse"),
                listing("reverse-2", 12000, variant="Reverse"),
            ),
        )
        import_references_jsonl(
            connection, jsonl(reference(15000, variant="Reverse"))
        )

        rows, _, _ = evaluate_catalog(connection)
        by_id = {row["external_id"]: row for row in rows}
        assert by_id["holo"]["reference_price_cents"] is None
        assert by_id["reverse-1"]["reference_price_cents"] == 15000

        stored = connection.execute(
            "SELECT variant, grading_company, grade FROM catalog_items WHERE external_id = 'holo'"
        ).fetchone()
        assert dict(stored) == {"variant": "Holo", "grading_company": None, "grade": None}


def test_reference_provenance_and_fallback_scope_are_resolved(tmp_path: Path) -> None:
    with connect(tmp_path / "provenance.db") as connection:
        apply_migrations(connection)
        configure_fees(connection)
        import_jsonl(
            connection,
            jsonl(listing("target", 1000, variant="Holo", condition="LP")),
        )
        import_references_jsonl(
            connection,
            jsonl(
                reference(
                    2500,
                    variant="Holo",
                    condition=None,
                    source_name="Cardmarket",
                    reference_kind="ventes_conclues",
                    observed_at="2026-10-31",
                    source_url="https://example.com/sales",
                    sample_size=12,
                    note="Ventes sur 30 jours",
                )
            ),
        )

        rows, _, _ = evaluate_catalog(connection)
        assert rows[0]["reference_source_name"] == "Cardmarket"
        assert rows[0]["reference_kind"] == "ventes_conclues"
        assert rows[0]["reference_kind_label"] == "Ventes conclues"
        assert rows[0]["reference_observed_at"] == "2026-10-31"
        assert rows[0]["reference_source_url"] == "https://example.com/sales"
        assert rows[0]["sample_count"] == 12
        assert rows[0]["reference_match_scope"] == "etat_generique"
        assert rows[0]["reference_note"] == "Ventes sur 30 jours"


def test_half_cent_rounding_is_characterized(tmp_path: Path) -> None:
    from app.profitability import median_cents

    assert median_cents([100, 101]) == 101
    with connect(tmp_path / "rounding.db") as connection:
        apply_migrations(connection)
        configure_fees(connection, shipping_packaging_cents=0)
        import_jsonl(connection, jsonl(listing("rounding", 1000)))
        import_references_jsonl(connection, jsonl(reference(1999)))

        rows, _, _ = evaluate_catalog(connection)
        assert rows[0]["platform_fee_cents"] == 100


def seed_cardmarket_bridge(connection, extra_locales: bool = True) -> None:
    """Référentiel + alias multilingues + 2 produits Cardmarket (trend 35/30 €)."""
    from app.cardmarket.aliases import base_card_name

    connection.execute(
        "INSERT INTO pokemon_reference_sets (id, name) VALUES ('sv03', 'Flammes Obsidiennes')"
    )
    connection.execute(
        """
        INSERT INTO pokemon_reference_cards (tcgdex_id, local_id, name, set_id, set_name)
        VALUES ('sv03-125', '125', 'Dracaufeu-ex', 'sv03', 'Flammes Obsidiennes')
        """
    )
    card_id = connection.execute("SELECT id FROM pokemon_reference_cards").fetchone()[0]
    locales = [("fr", "Dracaufeu-ex"), ("en", "Charizard ex")]
    if extra_locales:
        locales += [("ko", "리자몽 ex"), ("ja", "リザードンex"), ("zh-tw", "噴火龍 ex")]
    for locale, name in locales:
        connection.execute(
            "INSERT INTO card_name_aliases (card_id, locale, name) VALUES (?, ?, ?)",
            (card_id, locale, name),
        )
    for product_id, trend in ((9001, 35000), (9002, 30000)):
        card_name = "Charizard ex"
        connection.execute(
            """
            INSERT INTO cardmarket_prices (product_id, card_name, trend_price_cents,
                                           currency, name_base)
            VALUES (?, ?, ?, 'EUR', ?)
            """,
            (product_id, card_name, trend, base_card_name(card_name)),
        )
    connection.commit()


def test_cardmarket_trend_fallback_via_multilingual_alias(tmp_path: Path) -> None:
    with connect(tmp_path / "cm-alias.db") as connection:
        apply_migrations(connection)
        configure_fees(connection)
        seed_cardmarket_bridge(connection)
        import_jsonl(
            connection,
            jsonl(
                listing(
                    "drac-fr",
                    20000,
                    name="Dracaufeu-ex",
                    set_name="Flammes Obsidiennes",
                    card_number="125/197",
                )
            ),
        )

        evaluations, summary, _ = evaluate_catalog(connection)
        row = evaluations[0]
        # Repli Cardmarket : le plus bas des prix tendances des produits assortis.
        assert row["reference_price_cents"] == 30000
        assert row["reference_source"] == "cardmarket_trend"
        assert row["sample_count"] == 2
        # 30000 - 1500 (commission 5 %) - 200 (envoi) - 20000 = 8300
        assert row["net_profit_cents"] == 8300
        assert row["verdict"] == "opportunite"
        assert summary["cardmarket_match_count"] == 1


def test_cardmarket_trend_fallback_direct_name_and_korean_alias(tmp_path: Path) -> None:
    with connect(tmp_path / "cm-direct.db") as connection:
        apply_migrations(connection)
        configure_fees(connection)
        seed_cardmarket_bridge(connection)
        import_jsonl(
            connection,
            jsonl(
                listing(
                    "drac-en",
                    23000,
                    name="Charizard ex",
                    set_name="Obsidian Flames",
                    card_number="125/197",
                ),
                listing(
                    "drac-ko",
                    25000,
                    name="리자몽 ex",
                    set_name="Obsidian Flames",
                    card_number="223/197",
                ),
            ),
        )

        evaluations, summary, _ = evaluate_catalog(connection)
        by_id = {row["external_id"]: row for row in evaluations}
        # Nom anglais : correspondance directe sur le nom de base.
        assert by_id["drac-en"]["reference_source"] == "cardmarket_trend"
        assert by_id["drac-en"]["reference_price_cents"] == 30000
        assert by_id["drac-en"]["verdict"] == "opportunite"
        # Nom coréen : pont multilingue via les alias (ko → en).
        assert by_id["drac-ko"]["reference_source"] == "cardmarket_trend"
        assert by_id["drac-ko"]["reference_price_cents"] == 30000
        assert summary["cardmarket_match_count"] == 2


def test_reference_and_median_take_priority_over_cardmarket(tmp_path: Path) -> None:
    with connect(tmp_path / "cm-priority.db") as connection:
        apply_migrations(connection)
        configure_fees(connection)
        seed_cardmarket_bridge(connection)
        import_jsonl(
            connection,
            jsonl(
                listing(
                    "with-ref",
                    20000,
                    name="Dracaufeu-ex",
                    set_name="Flammes Obsidiennes",
                    card_number="125/197",
                ),
                # Médiane : deux annonces NM strictement comparables, l'évaluée exclue.
                listing("median-a", 40000, name="Ronflex"),
                listing("median-b", 44000, name="Ronflex"),
                listing("median-c", 46000, name="Ronflex"),
            ),
        )
        import_references_jsonl(
            connection,
            jsonl(
                reference(
                    20000,
                    name="Dracaufeu-ex",
                    set_name="Flammes Obsidiennes",
                    card_number="125/197",
                )
            ),
        )

        evaluations, summary, _ = evaluate_catalog(connection)
        by_id = {row["external_id"]: row for row in evaluations}
        assert by_id["with-ref"]["reference_source"] == "reference"
        assert by_id["with-ref"]["reference_price_cents"] == 20000
        assert by_id["median-a"]["reference_source"] == "catalog_median"
        assert by_id["median-a"]["reference_price_cents"] == 45000
        assert summary["cardmarket_match_count"] == 0


def test_cardmarket_trend_ignored_for_non_eur_listing(tmp_path: Path) -> None:
    with connect(tmp_path / "cm-fx.db") as connection:
        apply_migrations(connection)
        configure_fees(connection)
        seed_cardmarket_bridge(connection)
        import_jsonl(
            connection,
            jsonl(
                listing(
                    "drac-usd",
                    20000,
                    name="Dracaufeu-ex",
                    set_name="Flammes Obsidiennes",
                    card_number="125/197",
                    currency="USD",
                )
            ),
        )

        rows, summary, _ = evaluate_catalog(connection)
        assert rows[0]["reference_price_cents"] is None
        assert rows[0]["verdict"] == "sans_cote"
        assert summary["cardmarket_match_count"] == 0


def test_find_price_comparables_lists_evidence(tmp_path: Path) -> None:
    with connect(tmp_path / "comparables.db") as connection:
        apply_migrations(connection)
        configure_fees(connection)
        import_jsonl(
            connection,
            jsonl(
                {
                    "external_id": "pika-target",
                    "name": "Pikachu",
                    "set_name": "Evolutions",
                    "card_number": "35/108",
                    "condition": "NM",
                    "price_cents": 1000,
                },
                {
                    "external_id": "pika-exact",
                    "name": "Pikachu",
                    "set_name": "Évolutions",
                    "card_number": "35/108",
                    "condition": "NM",
                    "price_cents": 2500,
                },
                {
                    "external_id": "pika-close",
                    "name": "Pikachu",
                    "set_name": "Évolutions",
                    "card_number": "35/108",
                    "condition": "NM",
                    "price_cents": 2400,
                },
                {
                    "external_id": "other-card",
                    "name": "Dracaufeu",
                    "set_name": "Évolutions",
                    "card_number": "11/108",
                    "condition": "NM",
                    "price_cents": 2500,
                },
            ),
        )
        target = dict(
            connection.execute(
                "SELECT * FROM catalog_items WHERE external_id = 'pika-target'"
            ).fetchone()
        )

        comparables = find_price_comparables(connection, target, 2500)

        listing_ids = [row["id"] for row in comparables["listings"]]
        target_id = int(target["id"])
        other_id = connection.execute(
            "SELECT id FROM catalog_items WHERE external_id = 'other-card'"
        ).fetchone()[0]
        assert target_id not in listing_ids
        assert other_id not in listing_ids
        assert len(comparables["listings"]) == 2
        assert comparables["listings"][0]["delta_cents"] == 0
        assert comparables["listings"][1]["delta_cents"] == -100

        record_purchase(
            connection,
            seller_name="vendeur-1",
            card_name="Pikachu",
            set_name="Évolutions",
            card_number="35/108",
            condition="NM",
            price_paid_cents=2550,
            status="vendu",
        )
        record_purchase(
            connection,
            seller_name="vendeur-2",
            card_name="Pikachu",
            set_name="Évolutions",
            price_paid_cents=3000,
            status="recu",
        )
        comparables = find_price_comparables(connection, target, 2500)
        assert len(comparables["sales"]) == 1
        assert comparables["sales"][0]["delta_cents"] == 50

        empty = find_price_comparables(connection, target, None)
        assert empty == {"listings": [], "sales": []}
