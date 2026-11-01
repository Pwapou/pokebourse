import json
from pathlib import Path

from app.cli import main


def test_migrate_then_check(tmp_path: Path, capsys) -> None:
    database_path = tmp_path / "arbitrage.db"

    migrate_result = main(["--database", str(database_path), "migrate"])
    repeated_result = main(["--database", str(database_path), "migrate"])
    check_result = main(["--database", str(database_path), "check"])

    output = capsys.readouterr().out
    assert migrate_result == 0
    assert repeated_result == 0
    assert check_result == 0
    assert "Migration appliquée : 0001_create_import_registry.sql" in output
    assert "Migration appliquée : 0003_create_profitability.sql" in output
    assert "Aucune migration en attente" in output
    assert "Base SQLite valide" in output


def test_cli_profitability_workflow(tmp_path: Path, capsys) -> None:
    database_path = tmp_path / "workflow.db"
    catalog_file = tmp_path / "annonces.jsonl"
    refs_file = tmp_path / "cotes.jsonl"

    catalog_file.write_text(
        json.dumps(
            {
                "external_id": "cli-1",
                "name": "Lugiatest",
                "set_name": "Neo Genesis",
                "card_number": "9/111",
                "condition": "NM",
                "price_cents": 15000,
            }
        ),
        encoding="utf-8",
    )
    refs_file.write_text(
        json.dumps(
            {
                "name": "Lugiatest",
                "set_name": "Neo Genesis",
                "card_number": "9/111",
                "condition": "NM",
                "reference_price_cents": 26000,
            }
        ),
        encoding="utf-8",
    )

    assert main(["--database", str(database_path), "migrate"]) == 0
    assert (
        main(
            [
                "--database",
                str(database_path),
                "import-catalog",
                str(catalog_file),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "--database",
                str(database_path),
                "import-references",
                str(refs_file),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "--database",
                str(database_path),
                "configure-fees",
                "--buyer-shipping-cents",
                "0",
                "--platform-fee-bps",
                "500",
                "--seller-fixed-fee-cents",
                "0",
                "--shipping-packaging-cents",
                "200",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert (
        main(
            [
                "--database",
                str(database_path),
                "analyze",
                "--only-opportunities",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["opportunity_count"] == 1
    assert payload["results"][0]["external_id"] == "cli-1"
    # 26000 - 1300 - 200 - 15000 = 9500
    assert payload["results"][0]["net_profit_cents"] == 9500
