import json
from pathlib import Path

import pytest

from app.catalog import (
    CatalogImportError,
    catalog_data,
    catalog_export_rows,
    catalog_item_detail,
    import_jsonl,
    parse_jsonl,
)
from app.storage.database import connect
from app.storage.migration_runner import apply_migrations


def jsonl(*items: dict[str, object]) -> bytes:
    return "\n".join(json.dumps(item) for item in items).encode()


def sample_item(external_id: str = "annonce-001") -> dict[str, object]:
    return {
        "external_id": external_id,
        "name": "Pikachu",
        "set_name": "Évolutions",
        "card_number": "35/108",
        "condition": "NM",
        "price_cents": 1290,
        "currency": "eur",
        "seller": "Collection locale",
    }


def initialized_connection(tmp_path: Path):
    return connect(tmp_path / "catalog.db")


def test_parse_jsonl_validates_and_normalizes() -> None:
    items = parse_jsonl(jsonl(sample_item()))

    assert len(items) == 1
    assert items[0].currency == "EUR"


def test_parse_jsonl_reports_line_number() -> None:
    content = jsonl(sample_item()) + b"\n" + b'{"name": "incomplet"}'

    with pytest.raises(CatalogImportError, match="Ligne 2"):
        parse_jsonl(content)


def test_import_persists_items_and_filters_catalog(tmp_path: Path) -> None:
    with initialized_connection(tmp_path) as connection:
        apply_migrations(connection)

        imported = import_jsonl(connection, jsonl(sample_item()))
        result = catalog_data(connection, query="pikachu")

        assert imported == 1
        assert result["total"] == 1
        assert result["items"][0]["price_cents"] == 1290
        assert result["items"][0]["currency"] == "EUR"
        assert connection.execute(
            "SELECT status FROM import_batches"
        ).fetchone()[0] == "completed"


def test_duplicate_file_is_rejected(tmp_path: Path) -> None:
    with initialized_connection(tmp_path) as connection:
        apply_migrations(connection)
        content = jsonl(sample_item())
        import_jsonl(connection, content)

        with pytest.raises(CatalogImportError, match="déjà été importé"):
            import_jsonl(connection, content)

        assert connection.execute("SELECT COUNT(*) FROM catalog_items").fetchone()[0] == 1


def test_invalid_file_leaves_no_partial_import(tmp_path: Path) -> None:
    with initialized_connection(tmp_path) as connection:
        apply_migrations(connection)
        content = jsonl(sample_item()) + b"\n" + b"not-json"

        with pytest.raises(CatalogImportError):
            import_jsonl(connection, content)

        assert connection.execute("SELECT COUNT(*) FROM catalog_items").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0] == 0


def test_duplicate_external_id_rolls_back_batch(tmp_path: Path) -> None:
    with initialized_connection(tmp_path) as connection:
        apply_migrations(connection)
        import_jsonl(connection, jsonl(sample_item()))
        updated = sample_item()
        updated["name"] = "Pikachu illustrateur"

        with pytest.raises(CatalogImportError, match="identifiant externe"):
            import_jsonl(connection, jsonl(updated))

        assert connection.execute("SELECT COUNT(*) FROM catalog_items").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0] == 1


def bulk_items(count: int, name: str = "Carte", set_name: str = "Base Set") -> bytes:
    return jsonl(
        *(
            {
                "external_id": f"{set_name}-{name}-{index:03d}",
                "name": f"{name} {index:02d}",
                "set_name": set_name,
                "price_cents": 100 * (index + 1),
            }
            for index in range(count)
        )
    )


def test_catalog_data_paginates_and_clamps_pages(tmp_path: Path) -> None:
    with initialized_connection(tmp_path) as connection:
        apply_migrations(connection)
        import_jsonl(connection, bulk_items(30))

        first = catalog_data(connection)
        second = catalog_data(connection, page=2)
        negative = catalog_data(connection, page=-5)
        zero = catalog_data(connection, page=0)
        beyond = catalog_data(connection, page=999)

        assert first["total"] == 30
        assert first["per_page"] == 25
        assert first["total_pages"] == 2
        assert first["page"] == 1
        assert first["range_start"] == 1
        assert first["range_end"] == 25
        assert len(first["items"]) == 25
        assert second["page"] == 2
        assert second["range_start"] == 26
        assert second["range_end"] == 30
        assert len(second["items"]) == 5
        assert negative["page"] == 1
        assert zero["page"] == 1
        assert beyond["page"] == 2
        assert len(beyond["items"]) == 5


def test_catalog_data_empty_catalog_reports_zero_range(tmp_path: Path) -> None:
    with initialized_connection(tmp_path) as connection:
        apply_migrations(connection)

        result = catalog_data(connection)

        assert result["total"] == 0
        assert result["total_pages"] == 1
        assert result["range_start"] == 0
        assert result["range_end"] == 0
        assert result["items"] == []


def test_catalog_data_sort_whitelist_orders_results(tmp_path: Path) -> None:
    with initialized_connection(tmp_path) as connection:
        apply_migrations(connection)
        import_jsonl(
            connection,
            jsonl(
                {
                    "external_id": "a",
                    "name": "Pikachu",
                    "set_name": "Base Set",
                    "price_cents": 5000,
                },
                {
                    "external_id": "b",
                    "name": "dracaufeu",
                    "set_name": "Base Set",
                    "price_cents": 500,
                },
                {
                    "external_id": "c",
                    "name": "Alakazam",
                    "set_name": "Base Set",
                    "price_cents": 25000,
                },
            ),
        )

        by_price_asc = catalog_data(connection, sort="price_asc")
        by_price_desc = catalog_data(connection, sort="price_desc")
        by_name = catalog_data(connection, sort="name_asc")
        by_import_asc = catalog_data(connection, sort="import_asc")
        by_import_desc = catalog_data(connection, sort="import_desc")

        assert [row["price_cents"] for row in by_price_asc["items"]] == [500, 5000, 25000]
        assert [row["price_cents"] for row in by_price_desc["items"]] == [25000, 5000, 500]
        # Le tri par nom ignore la casse.
        assert [row["name"] for row in by_name["items"]] == [
            "Alakazam",
            "dracaufeu",
            "Pikachu",
        ]
        assert [row["id"] for row in by_import_asc["items"]] == sorted(
            row["id"] for row in by_import_desc["items"]
        )


def test_catalog_data_invalid_sort_falls_back_to_default(tmp_path: Path) -> None:
    with initialized_connection(tmp_path) as connection:
        apply_migrations(connection)
        import_jsonl(connection, bulk_items(3))

        result = catalog_data(connection, sort="imported_at; DROP TABLE catalog_items")

        assert result["sort"] == "import_desc"
        assert connection.execute(
            "SELECT COUNT(*) FROM catalog_items"
        ).fetchone()[0] == 3


def test_catalog_data_combines_filters_sort_and_page(tmp_path: Path) -> None:
    with initialized_connection(tmp_path) as connection:
        apply_migrations(connection)
        import_jsonl(connection, bulk_items(10, set_name="Base Set"))
        import_jsonl(connection, bulk_items(10, name="Jungle", set_name="Jungle"))

        filtered = catalog_data(
            connection, query="Jungle", set_name="Jungle", sort="price_desc", page=1
        )

        assert filtered["total"] == 10
        assert all(row["set_name"] == "Jungle" for row in filtered["items"])
        prices = [row["price_cents"] for row in filtered["items"]]
        assert prices == sorted(prices, reverse=True)


def test_catalog_export_rows_returns_all_filtered_results(tmp_path: Path) -> None:
    with initialized_connection(tmp_path) as connection:
        apply_migrations(connection)
        import_jsonl(connection, bulk_items(30, set_name="Base Set"))
        import_jsonl(connection, bulk_items(5, name="Jungle", set_name="Jungle"))

        all_rows = catalog_export_rows(connection)
        filtered = catalog_export_rows(connection, set_name="Jungle")

        assert len(all_rows) == 35
        assert len(filtered) == 5
        # Tri stable de l'export : nom insensible à la casse puis id.
        names = [row["name"] for row in all_rows]
        assert names == sorted(names, key=str.casefold)


def test_catalog_item_detail_returns_full_row_or_none(tmp_path: Path) -> None:
    with initialized_connection(tmp_path) as connection:
        apply_migrations(connection)
        import_jsonl(connection, jsonl(sample_item()))

        item = catalog_item_detail(connection, 1)

        assert item is not None
        assert item["name"] == "Pikachu"
        assert item["external_id"] == "annonce-001"
        assert item["source_name"] == "import-web"
        assert item["import_batch_id"] == 1
        assert catalog_item_detail(connection, 9999) is None


def test_reidentify_catalog_reattaches_items_once_reference_is_complete(
    tmp_path: Path,
) -> None:
    """Une annonce importée alors que le référentiel était incomplet est
    rattachée après le peuplement du catalogue (bouton « Réexaminer »)."""
    from app.catalog import reidentify_catalog

    with initialized_connection(tmp_path) as connection:
        apply_migrations(connection)
        # « Ronflex » n'existe pas dans les données seed : l'annonce reste non identifiée.
        # Le titre porte les preuves (numéro + extension), comme une vraie annonce.
        import_jsonl(
            connection,
            jsonl(
                {
                    **sample_item(),
                    "name": "Ronflex 143/102 Set de Base",
                    "set_name": "Set de Base",
                    "card_number": "143/102",
                }
            ),
        )
        row = connection.execute(
            "SELECT identification_status FROM catalog_items WHERE id = 1"
        ).fetchone()
        assert row["identification_status"] in ("unidentified", "ambiguous")

        # Le référentiel TCGdex arrive (ex. synchronisation complète).
        # L'extension « Set de Base » existe déjà dans les données seed (id base1).
        connection.execute(
            """
            INSERT INTO pokemon_reference_cards (tcgdex_id, local_id, name, set_id, set_name)
            VALUES ('base1-143', '143', 'Ronflex', 'base1', 'Set de Base')
            """
        )
        connection.commit()

        report = reidentify_catalog(connection)

        assert report["examined"] == 1
        assert report.get("identified") == 1
        refreshed = connection.execute(
            """
            SELECT identification_status, reference_card_id, name, card_number
            FROM catalog_items WHERE id = 1
            """
        ).fetchone()
        assert refreshed["identification_status"] == "identified"
        assert refreshed["reference_card_id"] is not None
        assert refreshed["name"] == "Ronflex"
        assert refreshed["card_number"] == "143"

        # Second passage : plus rien en attente, rien à réexaminer.
        assert reidentify_catalog(connection) == {"examined": 0}
