from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.catalog import (
    delete_import_batch,
    import_batch_detail,
    import_failures_report,
    recent_import_failures,
    record_import_failure,
)
from app.cli import main
from app.storage.database import connect
from app.web import app

ITEM_A = (
    b'{"external_id":"pika-1","name":"Pikachu","set_name":"Evolutions",'
    b'"price_cents":1290,"condition":"NM"}\n'
)
ITEM_B = (
    b'{"external_id":"draco-1","name":"Dracaufeu","set_name":"Base Set",'
    b'"price_cents":25000,"seller":"Vendeur test"}\n'
)
BAD_JSONL = b'{"external_id":"ok","name":"Pikachu","set_name":"Evolutions","price_cents":100}\nnot-json\n'


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("POKEMON_DATABASE_PATH", str(tmp_path / "web.db"))
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def database_path(client: TestClient) -> Path:
    return Path(client.app.state.settings.database_path)


def import_file(client: TestClient, content: bytes, filename: str = "annonces.jsonl") -> None:
    response = client.post(
        "/imports",
        files={"file": (filename, content, "application/x-ndjson")},
        follow_redirects=False,
    )
    assert response.status_code == 303


def batch_ids(database_path: Path) -> list[int]:
    with connect(database_path) as connection:
        return [
            row[0]
            for row in connection.execute("SELECT id FROM import_batches ORDER BY id")
        ]


# --- Page Sauvegardes -------------------------------------------------------


def test_backups_page_create_download_and_restore_flow(
    client: TestClient, database_path: Path
) -> None:
    import_file(client, ITEM_A)
    page = client.get("/backups")
    assert page.status_code == 200
    assert "Aucune sauvegarde" in page.text

    created = client.post("/backups", follow_redirects=False)
    assert created.status_code == 303
    assert created.headers["location"].startswith("/backups?notice=")

    backups = client.get("/backups")
    assert "pokebourse-" in backups.text
    assert "Télécharger" in backups.text
    assert "Restaurer" in backups.text

    from app.backups import list_backups

    entries = list_backups(database_path)
    assert len(entries) == 1
    name = entries[0]["name"]

    download = client.get("/backups/download", params={"name": name})
    assert download.status_code == 200
    assert download.content == (database_path.parent / "backups" / name).read_bytes()

    # Destruction de la donnée, puis restauration sans confirmation : refusée.
    with connect(database_path) as connection:
        connection.execute("DELETE FROM catalog_items")
        connection.commit()
    refused = client.post(
        "/backups/restore", data={"name": name}, follow_redirects=False
    )
    assert refused.status_code == 303
    assert "confirmation" in refused.headers["location"]
    with connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM catalog_items").fetchone()[0] == 0

    # Restauration confirmée : la donnée revient, une sauvegarde de sécurité est créée.
    restored = client.post(
        "/backups/restore",
        data={"name": name, "confirm": "yes"},
        follow_redirects=False,
    )
    assert restored.status_code == 303
    assert "notice=" in restored.headers["location"]
    with connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM catalog_items").fetchone()[0] == 1
    assert len(list_backups(database_path)) == 2


def test_backup_download_protected_against_traversal(client: TestClient) -> None:
    response = client.get(
        "/backups/download", params={"name": "../web.db"}, follow_redirects=False
    )
    assert response.status_code == 303
    assert "error=" in response.headers["location"]

    missing = client.get(
        "/backups/download", params={"name": "absente.sqlite"}, follow_redirects=False
    )
    assert missing.status_code == 303


# --- Détail et suppression des lots -----------------------------------------


def test_import_batch_detail_page(client: TestClient, database_path: Path) -> None:
    import_file(client, ITEM_A + ITEM_B, "deux-annonces.jsonl")
    batch_id = batch_ids(database_path)[0]

    detail = client.get(f"/imports/{batch_id}")
    assert detail.status_code == 200
    assert "Lot #0001" in detail.text
    assert "import-web" in detail.text
    assert "EMPREINTE SHA-256" in detail.text
    assert "Pikachu" in detail.text
    assert "Dracaufeu" in detail.text
    assert 'href="/catalog/1"' in detail.text
    assert 'href="/catalog/2"' in detail.text

    missing = client.get("/imports/999", follow_redirects=False)
    assert missing.status_code == 303
    assert "introuvable" in missing.headers["location"]


def test_delete_batch_requires_confirmation_and_preserves_other_data(
    client: TestClient, database_path: Path
) -> None:
    import_file(client, ITEM_A, "lot-a.jsonl")
    import_file(client, ITEM_B, "lot-b.jsonl")
    first, second = batch_ids(database_path)

    # Donnée du moteur de rentabilité : ne doit jamais être touchée.
    with connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO market_references (
                card_key, name, set_name, reference_price_cents
            ) VALUES ('pikachu|evolutions', 'Pikachu', 'Évolutions', 3000)
            """
        )
        connection.commit()

    refused = client.post(f"/imports/{first}/delete", follow_redirects=False)
    assert refused.status_code == 303
    assert "confirmation" in refused.headers["location"]
    assert batch_ids(database_path) == [first, second]

    deleted = client.post(
        f"/imports/{first}/delete", data={"confirm": "yes"}, follow_redirects=False
    )
    assert deleted.status_code == 303
    assert batch_ids(database_path) == [second]

    with connect(database_path) as connection:
        items = {
            row[0]
            for row in connection.execute("SELECT external_id FROM catalog_items")
        }
        assert items == {"draco-1"}
        references = connection.execute(
            "SELECT COUNT(*) FROM market_references"
        ).fetchone()[0]
        assert references == 1


def test_delete_unknown_batch_redirects_with_error(
    client: TestClient, database_path: Path
) -> None:
    import_file(client, ITEM_A)
    batch_id = batch_ids(database_path)[0]

    response = client.post(
        f"/imports/{batch_id + 1}/delete",
        data={"confirm": "yes"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "introuvable" in response.headers["location"]


# --- Enregistrement et rapport des échecs ------------------------------------


def test_failed_web_import_is_recorded_and_reported(
    client: TestClient, database_path: Path
) -> None:
    import_file(client, BAD_JSONL, "casse.jsonl")

    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert "Échecs récents" in dashboard.text
    assert "casse.jsonl" in dashboard.text
    assert "JSON invalide" in dashboard.text

    report = client.get("/imports/failures/report")
    assert report.status_code == 200
    assert "text/plain" in report.headers["content-type"]
    assert "casse.jsonl" in report.text
    assert "JSON invalide" in report.text
    assert "Empreinte SHA-256" in report.text
    assert "import-web" in report.text

    with connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM catalog_items").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0] == 0
        failures = recent_import_failures(connection)
        assert len(failures) == 1
        assert failures[0]["filename"] == "casse.jsonl"
        assert len(failures[0]["input_checksum"]) == 64


def test_duplicate_import_is_recorded_as_failure(
    client: TestClient, database_path: Path
) -> None:
    import_file(client, ITEM_A, "dup.jsonl")
    import_file(client, ITEM_A, "dup.jsonl")

    with connect(database_path) as connection:
        failures = recent_import_failures(connection)
        assert len(failures) == 1
        assert "déjà été importé" in failures[0]["error_message"]
        assert connection.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0] == 1


def test_report_when_no_failure_is_readable(client: TestClient) -> None:
    report = client.get("/imports/failures/report")
    assert report.status_code == 200
    assert "Aucun échec d'import enregistré" in report.text


# --- Fonctions catalogue (détail, suppression, échecs) -----------------------


def test_batch_detail_and_transactional_delete(tmp_path: Path) -> None:
    from app.catalog import import_jsonl
    from app.storage.migration_runner import apply_migrations

    database_path = tmp_path / "arbitrage.db"
    with connect(database_path) as connection:
        apply_migrations(connection)
        import_jsonl(connection, ITEM_A)
        import_jsonl(connection, ITEM_B)
        detail = import_batch_detail(connection, 1)
        assert detail is not None
        assert detail["batch"]["source_name"] == "import-web"
        assert len(detail["items"]) == 1
        assert len(detail["batch"]["input_checksum"]) == 64
        assert import_batch_detail(connection, 999) is None

        assert delete_import_batch(connection, 1) is True
        assert delete_import_batch(connection, 1) is False
        remaining = connection.execute(
            "SELECT external_id FROM catalog_items"
        ).fetchall()
        assert [row[0] for row in remaining] == ["draco-1"]


def test_record_and_report_failures(tmp_path: Path) -> None:
    from app.storage.migration_runner import apply_migrations

    database_path = tmp_path / "arbitrage.db"
    with connect(database_path) as connection:
        apply_migrations(connection)
        record_import_failure(
            connection,
            source_name="import-cli",
            filename="fichier.jsonl",
            content=b"contenu",
            error_message="Ligne 1 : JSON invalide.",
        )
        failures = recent_import_failures(connection)
        assert len(failures) == 1
        report = import_failures_report(connection)
        assert "fichier.jsonl" in report
        assert "import-cli" in report
        assert "Ligne 1 : JSON invalide." in report


# --- CLI sauvegarde / restauration -------------------------------------------


def test_cli_backup_creates_timestamped_file(tmp_path: Path, capsys) -> None:
    database_path = tmp_path / "arbitrage.db"
    assert main(["--database", str(database_path), "migrate"]) == 0

    result = main(["--database", str(database_path), "backup"])
    output = capsys.readouterr().out
    assert result == 0
    printed = output.strip().splitlines()[-1].removeprefix("Sauvegarde créée : ")
    backup_path = Path(printed)
    assert backup_path.exists()
    assert backup_path.parent == tmp_path / "backups"


def test_cli_backup_with_explicit_output(tmp_path: Path, capsys) -> None:
    database_path = tmp_path / "arbitrage.db"
    main(["--database", str(database_path), "migrate"])
    destination = tmp_path / "copie.sqlite"

    result = main(["--database", str(database_path), "backup", "--output", str(destination)])

    assert result == 0
    assert destination.exists()


def test_cli_backup_missing_database_fails(tmp_path: Path, capsys) -> None:
    result = main(["--database", str(tmp_path / "absente.db"), "backup"])
    captured = capsys.readouterr()

    assert result == 1
    assert "base introuvable" in captured.err


def test_cli_restore_requires_yes_confirmation(tmp_path: Path, capsys) -> None:
    database_path = tmp_path / "arbitrage.db"
    main(["--database", str(database_path), "migrate"])
    backup_path = tmp_path / "backups" / "sauvegarde.sqlite"
    assert (
        main(["--database", str(database_path), "backup", "--output", str(backup_path)])
        == 0
    )

    refused = main(["--database", str(database_path), "restore", str(backup_path)])
    captured = capsys.readouterr()
    assert refused == 2
    assert "--yes" in captured.err


def test_cli_restore_roundtrip(tmp_path: Path, capsys) -> None:
    database_path = tmp_path / "arbitrage.db"
    main(["--database", str(database_path), "migrate"])
    jsonl_path = tmp_path / "annonces.jsonl"
    jsonl_path.write_bytes(ITEM_A)
    assert main(["--database", str(database_path), "import-catalog", str(jsonl_path)]) == 0
    backup_path = tmp_path / "backups" / "sauvegarde.sqlite"
    assert (
        main(["--database", str(database_path), "backup", "--output", str(backup_path)])
        == 0
    )
    with connect(database_path) as connection:
        connection.execute("DELETE FROM catalog_items")
        connection.commit()

    result = main(
        ["--database", str(database_path), "restore", str(backup_path), "--yes"]
    )
    output = capsys.readouterr().out
    assert result == 0
    assert "Sauvegarde de sécurité" in output
    with connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM catalog_items").fetchone()[0] == 1


def test_cli_restore_invalid_backup_fails(tmp_path: Path, capsys) -> None:
    database_path = tmp_path / "arbitrage.db"
    main(["--database", str(database_path), "migrate"])
    invalid = tmp_path / "casse.sqlite"
    invalid.write_bytes(b"pas une base")

    result = main(["--database", str(database_path), "restore", str(invalid), "--yes"])

    assert result == 1
    assert "Erreur" in capsys.readouterr().err
