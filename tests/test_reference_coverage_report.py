"""Tests du diagnostic hors ligne de couverture du référentiel TCGdex.

Toutes les bases sont synthétiques et temporaires : aucun appel réseau,
aucune donnée réelle, aucune écriture dans la base lue.
"""

import hashlib
import json
import socket
import sqlite3
from pathlib import Path

import pytest

from app.identification.normalization import normalize_text
from scripts.reference_coverage_report import (
    REPORT_VERSION,
    ReportError,
    build_report,
    export_json,
    inspect_schema,
    main,
    open_backup,
)

SCHEMA_FULL = """
CREATE TABLE pokemon_reference_sets (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    series TEXT,
    card_count_total INTEGER,
    card_count_official INTEGER,
    release_date TEXT,
    logo_url TEXT,
    symbol_url TEXT,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE TABLE pokemon_reference_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tcgdex_id TEXT NOT NULL UNIQUE,
    local_id TEXT NOT NULL,
    name TEXT NOT NULL,
    set_id TEXT NOT NULL REFERENCES pokemon_reference_sets(id),
    set_name TEXT NOT NULL,
    rarity TEXT,
    category TEXT,
    types TEXT,
    hp INTEGER,
    stage TEXT,
    illustrator TEXT,
    image_url TEXT,
    raw_data TEXT,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    normalized_name TEXT NOT NULL DEFAULT '',
    normalized_set_name TEXT NOT NULL DEFAULT '',
    canonical_local_id TEXT NOT NULL DEFAULT '',
    reference_language TEXT NOT NULL DEFAULT 'fr'
);
CREATE TABLE schema_migrations (version TEXT PRIMARY KEY);
CREATE TABLE tcgdex_sync_jobs (
    id INTEGER PRIMARY KEY,
    resource_key TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL CHECK(kind IN ('directory', 'set')),
    set_id TEXT,
    status TEXT NOT NULL CHECK(status IN ('queued', 'running', 'paused', 'completed', 'failed')),
    stage TEXT NOT NULL CHECK(stage IN ('manifest', 'details', 'done')),
    include_details INTEGER NOT NULL DEFAULT 1,
    manifest_json TEXT,
    expected_count INTEGER,
    summary_count INTEGER NOT NULL DEFAULT 0,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TEXT NOT NULL,
    lease_owner TEXT,
    lease_expires_at TEXT,
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_success_at TEXT
);
CREATE TABLE tcgdex_sync_cards (
    job_id INTEGER NOT NULL REFERENCES tcgdex_sync_jobs(id) ON DELETE CASCADE,
    tcgdex_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    summary_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    completed_at TEXT,
    PRIMARY KEY(job_id, tcgdex_id)
);
"""

SCHEMA_LEGACY = """
CREATE TABLE pokemon_reference_sets (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    series TEXT,
    card_count_total INTEGER,
    card_count_official INTEGER,
    release_date TEXT,
    logo_url TEXT,
    symbol_url TEXT,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE TABLE pokemon_reference_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tcgdex_id TEXT NOT NULL UNIQUE,
    local_id TEXT NOT NULL,
    name TEXT NOT NULL,
    set_id TEXT NOT NULL REFERENCES pokemon_reference_sets(id),
    set_name TEXT NOT NULL,
    image_url TEXT,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
"""


def create_backup(tmp_path: Path, schema: str = SCHEMA_FULL, name: str = "backup.sqlite") -> Path:
    path = tmp_path / name
    connection = sqlite3.connect(path)
    try:
        connection.executescript(schema)
        connection.commit()
    finally:
        connection.close()
    return path


def insert_set(
    connection: sqlite3.Connection,
    set_id: str,
    name: str,
    *,
    series: str | None = None,
    total: int | None = None,
    official: int | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO pokemon_reference_sets
            (id, name, series, card_count_total, card_count_official, release_date)
        VALUES (?, ?, ?, ?, ?, '2024-01-01')
        """,
        (set_id, name, series, total, official),
    )


def insert_card(
    connection: sqlite3.Connection,
    tcgdex_id: str,
    local_id: str,
    name: str,
    set_id: str,
    set_name: str,
    *,
    language: str = "fr",
    image_url: str | None = None,
) -> None:
    normalized = normalize_text(name)
    connection.execute(
        """
        INSERT INTO pokemon_reference_cards (
            tcgdex_id, local_id, name, set_id, set_name, image_url,
            normalized_name, normalized_set_name, canonical_local_id,
            reference_language
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            tcgdex_id,
            local_id,
            name,
            set_id,
            set_name,
            image_url,
            normalized,
            normalize_text(set_name),
            local_id.lstrip("0") or local_id,
            language,
        ),
    )


@pytest.fixture
def populated_backup(tmp_path: Path) -> Path:
    """Sauvegarde synthétique : deux extensions, locales fr/en, numéros partagés."""
    path = create_backup(tmp_path)
    connection = sqlite3.connect(path)
    try:
        insert_set(connection, "sv01", "Écarlate et Violet", series="Scarlet & Violet", total=2, official=2)
        insert_set(connection, "base1", "Base Set", series="Base", total=2, official=None)
        insert_card(connection, "sv01-1", "001", "Pikachu", "sv01", "Écarlate et Violet", image_url="https://img.example/1.png")
        insert_card(connection, "sv01-2", "002", "Évoli", "sv01", "Écarlate et Violet", language="en")
        insert_card(connection, "base1-1", "001", "Pikachu", "base1", "Base Set", image_url="https://img.example/2.png")
        connection.execute("INSERT INTO schema_migrations (version) VALUES ('0021_purchase_sale_price.sql')")
        connection.execute(
            """
            INSERT INTO tcgdex_sync_jobs (
                resource_key, kind, set_id, status, stage, expected_count,
                summary_count, attempts, next_attempt_at, created_at, updated_at,
                last_success_at
            ) VALUES ('set:sv01', 'set', 'sv01', 'completed', 'done', 2, 2, 1,
                      '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z',
                      '2026-01-01T00:01:00Z', '2026-01-01T00:01:00Z')
            """
        )
        job_id = connection.execute("SELECT id FROM tcgdex_sync_jobs").fetchone()[0]
        connection.execute(
            "INSERT INTO tcgdex_sync_cards (job_id, tcgdex_id, position, summary_json, status)"
            " VALUES (?, 'sv01-1', 0, '{}', 'completed')",
            (job_id,),
        )
        connection.commit()
    finally:
        connection.close()
    return path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Erreurs compréhensibles
# ---------------------------------------------------------------------------


def test_base_absente(tmp_path: Path) -> None:
    with pytest.raises(ReportError, match="Base absente"):
        build_report(tmp_path / "inexistante.sqlite")


def test_fichier_invalide(tmp_path: Path) -> None:
    path = tmp_path / "backup.sqlite"
    path.write_text("ceci n'est pas une base sqlite", encoding="utf-8")
    with pytest.raises(ReportError, match="Fichier invalide"):
        build_report(path)


def test_schema_incompatible(tmp_path: Path) -> None:
    path = tmp_path / "backup.sqlite"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE autre (id INTEGER)")
    connection.close()
    with pytest.raises(ReportError, match="Schéma incompatible.*pokemon_reference_sets"):
        build_report(path)


# ---------------------------------------------------------------------------
# Inventaire global
# ---------------------------------------------------------------------------


def test_referentiel_vide(tmp_path: Path) -> None:
    path = create_backup(tmp_path)
    report = build_report(path)
    assert report["global"]["sets_count"] == 0
    assert report["global"]["cards_count"] == 0
    assert report["global"]["languages"] == []
    assert report["sets"] == []
    assert report["global"]["schema_version"] is None


def test_inventaire_global(populated_backup: Path) -> None:
    report = build_report(populated_backup)
    global_info = report["global"]
    assert global_info["schema_version"] == "0021_purchase_sale_price.sql"
    assert global_info["sets_count"] == 2
    assert global_info["cards_count"] == 3
    assert global_info["cards_with_image_url"] == 2
    languages = {entry["language"]: entry["count"] for entry in global_info["languages"]}
    assert languages == {"en": 1, "fr": 2}
    assert global_info["missing_optional_fields"] == []


# ---------------------------------------------------------------------------
# Inventaire par extension
# ---------------------------------------------------------------------------


def test_extension_connue_sans_cartes(tmp_path: Path) -> None:
    path = create_backup(tmp_path)
    connection = sqlite3.connect(path)
    insert_set(connection, "swshp", "Promo SWSH", total=50)
    connection.commit()
    connection.close()
    report = build_report(path)
    entry = report["sets"][0]
    assert entry["set_id"] == "swshp"
    assert entry["local_cards"] == 0
    assert entry["coverage"]["status"] == "extension_connue_sans_cartes"
    assert entry["sync_job"] is None


def test_reference_francaise_et_etrangere(populated_backup: Path) -> None:
    report = build_report(populated_backup)
    sv01 = next(entry for entry in report["sets"] if entry["set_id"] == "sv01")
    assert "fr=1" in sv01["languages"]
    assert "en=1" in sv01["languages"]
    assert sv01["coverage"]["status"] == "effectif_conforme"


def test_ecart_effectifs_sans_conclusion_abusive(tmp_path: Path) -> None:
    path = create_backup(tmp_path)
    connection = sqlite3.connect(path)
    insert_set(connection, "big", "Grande extension", total=200, official=198)
    insert_card(connection, "big-1", "1", "Carte A", "big", "Grande extension")
    insert_card(connection, "big-2", "2", "Carte B", "big", "Grande extension")
    connection.commit()
    connection.close()
    report = build_report(path)
    entry = report["sets"][0]
    assert entry["local_cards"] == 2
    coverage = entry["coverage"]
    assert coverage["status"] == "effectif_different_a_verifier"
    assert coverage["conclusion"] == "a_verifier"
    assert "cartes manquantes" in coverage["explication"]
    assert "ne" in coverage["explication"] or "pas" in coverage["explication"]


def test_effectif_annonce_absent_information_insuffisante(tmp_path: Path) -> None:
    path = create_backup(tmp_path)
    connection = sqlite3.connect(path)
    insert_set(connection, "nodata", "Sans effectif")
    insert_card(connection, "nodata-1", "1", "Carte", "nodata", "Sans effectif")
    connection.commit()
    connection.close()
    entry = build_report(path)["sets"][0]
    assert entry["coverage"]["status"] == "information_insuffisante"


def test_metadonnee_optionnelle_manquante(tmp_path: Path) -> None:
    path = create_backup(tmp_path, schema=SCHEMA_LEGACY)
    connection = sqlite3.connect(path)
    insert_set(connection, "sv01", "Écarlate et Violet")
    connection.execute(
        """
        INSERT INTO pokemon_reference_cards
            (tcgdex_id, local_id, name, set_id, set_name, image_url)
        VALUES ('sv01-1', '001', 'Pikachu', 'sv01', 'Écarlate et Violet', NULL)
        """
    )
    connection.commit()
    connection.close()
    report = build_report(path)
    assert report["global"]["languages"] is None
    assert "reference_language" in report["global"]["missing_optional_fields"]
    entry = report["sets"][0]
    assert entry["languages"] is None
    assert entry["detail_level"]["status"] == "information_indisponible"
    kinds = {a["kind"]: a["severity"] for a in report["anomalies"]}
    assert kinds["langues"] == "information_indisponible"


def test_etat_synchronisation_si_schema_le_permet(populated_backup: Path) -> None:
    report = build_report(populated_backup)
    sv01 = next(entry for entry in report["sets"] if entry["set_id"] == "sv01")
    assert sv01["sync_job"]["status"] == "completed"
    assert sv01["sync_job"]["stage"] == "done"
    assert sv01["detail_level"]["status"] == "etabli"
    assert sv01["detail_level"]["fiches_completees"] == 1
    base1 = next(entry for entry in report["sets"] if entry["set_id"] == "base1")
    assert base1["sync_job"] is None
    assert base1["detail_level"]["status"] == "aucune_demande_de_synchronisation"


# ---------------------------------------------------------------------------
# Recherche ciblée
# ---------------------------------------------------------------------------


def test_recherche_numero_identique_dans_plusieurs_extensions(populated_backup: Path) -> None:
    report = build_report(populated_backup, local_id="001")
    matches = report["search"]["matches"]
    assert report["search"]["match_count"] == 2
    assert {match["set_id"] for match in matches} == {"sv01", "base1"}
    assert matches == sorted(matches, key=lambda m: (m["name"].lower(), m["set_id"], m["local_id"]))


def test_recherche_par_extension_et_nom(populated_backup: Path) -> None:
    report = build_report(populated_backup, set_query="écarlate", card_name="pikachu")
    assert report["search"]["match_count"] == 1
    assert report["search"]["matches"][0]["set_id"] == "sv01"


def test_recherche_sans_resultat(populated_backup: Path) -> None:
    report = build_report(populated_backup, card_name="gempack 2")
    assert report["search"]["match_count"] == 0
    assert report["search"]["matches"] == []
    assert "ne démontre pas une absence" in report["search"]["note"]


def test_recherche_url_image_presente_ou_absente(populated_backup: Path) -> None:
    report = build_report(populated_backup, set_query="sv01")
    flags = {match["name"]: match["has_image_url"] for match in report["search"]["matches"]}
    assert flags == {"Pikachu": True, "Évoli": False}


# ---------------------------------------------------------------------------
# Anomalies
# ---------------------------------------------------------------------------


def test_references_orphelines_signalees(tmp_path: Path) -> None:
    path = create_backup(tmp_path)
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys = OFF")
    insert_card(connection, "orphelin-1", "1", "Carte perdue", "inconnu", "Inconnu")
    connection.commit()
    connection.close()
    report = build_report(path)
    anomaly = next(a for a in report["anomalies"] if a["kind"] == "references_orphelines")
    assert anomaly["severity"] == "probleme_confirme"
    assert anomaly["count"] == 1
    assert len(anomaly["examples"]) <= 5


def test_numeros_partages_entre_extensions_ne_sont_pas_des_doublons(populated_backup: Path) -> None:
    report = build_report(populated_backup)
    anomaly = next(a for a in report["anomalies"] if a["kind"] == "numeros_partages_entre_extensions")
    assert anomaly["severity"] == "information"
    assert anomaly["count"] >= 1
    assert "pas automatiquement des doublons" in anomaly["explication"]


def test_numero_manquant(tmp_path: Path) -> None:
    path = create_backup(tmp_path)
    connection = sqlite3.connect(path)
    insert_set(connection, "s1", "Extension")
    insert_card(connection, "s1-1", "", "Sans numéro", "s1", "Extension")
    connection.commit()
    connection.close()
    report = build_report(path)
    anomaly = next(a for a in report["anomalies"] if a["kind"] == "numeros_manquants")
    assert anomaly["severity"] == "probleme_confirme"
    assert anomaly["count"] == 1


# ---------------------------------------------------------------------------
# Sorties, non-modification et héréméticité
# ---------------------------------------------------------------------------


def test_export_json_versionne_et_deterministe(populated_backup: Path, tmp_path: Path) -> None:
    output = tmp_path / "rapport.json"
    report = build_report(populated_backup)
    export_json(report, output)
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["report_version"] == REPORT_VERSION
    assert payload["generated_at"]
    assert [entry["set_id"] for entry in payload["sets"]] == ["base1", "sv01"]


def test_export_json_refuse_ecrasement(populated_backup: Path, tmp_path: Path) -> None:
    output = tmp_path / "rapport.json"
    output.write_text("pré-existant", encoding="utf-8")
    with pytest.raises(ReportError, match="Refus d'écraser"):
        export_json(build_report(populated_backup), output)
    assert output.read_text(encoding="utf-8") == "pré-existant"


def test_base_non_modifiee(populated_backup: Path) -> None:
    before = sha256(populated_backup)
    report = build_report(populated_backup, set_query="sv01", card_name="Pikachu")
    assert report["global"]["cards_count"] == 3
    assert sha256(populated_backup) == before
    sidecars = list(populated_backup.parent.glob(populated_backup.name + "-*"))
    assert sidecars == []


def test_ouverture_uniquement_lecture(populated_backup: Path) -> None:
    connection = open_backup(populated_backup)
    try:
        inspect_schema(connection)
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("DELETE FROM pokemon_reference_cards")
    finally:
        connection.close()


def test_fonctionnement_sans_reseau(populated_backup: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden_socket(*args: object, **kwargs: object) -> socket.socket:
        raise AssertionError("appel réseau interdit pendant le diagnostic")

    monkeypatch.setattr(socket, "socket", forbidden_socket)
    report = build_report(populated_backup, local_id="001")
    assert report["search"]["match_count"] == 2


def test_cli_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
    assert "lecture seule" in capsys.readouterr().out


def test_cli_erreur_code_retour(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(tmp_path / "absente.sqlite")]) == 2
    assert "Erreur" in capsys.readouterr().err


def test_cli_nominal(populated_backup: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(populated_backup)]) == 0
    out = capsys.readouterr().out
    assert "INVENTAIRE GLOBAL" in out
    assert "Écarlate et Violet" in out
    assert "AVERTISSEMENTS MÉTHODOLOGIQUES" in out
