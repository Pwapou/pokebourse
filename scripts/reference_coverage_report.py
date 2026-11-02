"""Diagnostic hors ligne, en lecture seule, du référentiel TCGdex local.

Ce lot prépare T05 de TASKING_IDENTIFICATION_FIABLE.md : il distingue un
problème de couverture du catalogue d'un problème d'identification.

Garanties du module :
- ouverture de la base exclusivement en lecture seule (URI ``mode=ro``) ;
- aucune migration, aucune initialisation, aucun seed ;
- aucun appel réseau, aucun worker, aucun OCR, aucun matcher ;
- aucune écriture dans la base ni dans les fichiers adjacents (-wal, -shm).

La commande reçoit explicitement le chemin d'une sauvegarde SQLite cohérente,
de préférence produite par le mécanisme de sauvegarde de Pokébourse
(``pokemon-arbitrage backup``). Ne pas lui passer la base opérationnelle ni
une copie naïve d'un fichier WAL actif : une telle copie peut être
incohérente. Le rapport signale d'ailleurs si le fichier ouvert est encore en
mode journal WAL.

Interprétation à conserver (rappelée dans chaque sortie) :
- une langue enregistrée historiquement par défaut n'est pas une preuve de la
  langue d'un exemplaire vendu ;
- une URL d'image renseignée ne signifie pas qu'une image a été téléchargée,
  vérifiée ou reste accessible ;
- un écart numérique entre effectif local et effectif annoncé n'est pas, à lui
  seul, une preuve de cartes manquantes (locales, sous-séries et conventions
  de comptage peuvent différer) ;
- une carte absente de cette sauvegarde n'existe nulle part : seule
  l'absence dans ce référentiel figé est rapportée.
"""

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

from app.identification.normalization import canonical_local_id, normalize_text

REPORT_VERSION = 1
MAX_EXAMPLES = 5

REQUIRED_TABLES = ("pokemon_reference_sets", "pokemon_reference_cards")

# Colonnes optionnelles du référentiel (ajoutées par la migration 0012) : leur
# absence sur une ancienne sauvegarde est signalée, jamais compensée.
OPTIONAL_CARD_COLUMNS = (
    "reference_language",
    "canonical_local_id",
    "normalized_name",
    "normalized_set_name",
    "rarity",
    "category",
    "types",
    "hp",
    "stage",
    "illustrator",
    "raw_data",
)

MEANING_ANNOUNCED_TOTAL = (
    "effectif total déclaré par la fiche d'extension TCGdex, selon la locale "
    "et les conventions de comptage du fournisseur"
)
MEANING_ANNOUNCED_OFFICIAL = (
    "effectif officiel déclaré par la fiche d'extension TCGdex, selon la "
    "locale et les conventions de comptage du fournisseur"
)
MEANING_COUNT_GAP = (
    "un écart numérique n'est pas une preuve de cartes manquantes : locales, "
    "sous-séries et conventions de comptage peuvent différer"
)

METHOD_WARNINGS = (
    "Une langue enregistrée historiquement par défaut n'est pas une preuve de "
    "la langue d'un exemplaire vendu.",
    "Une URL d'image renseignée ne signifie pas qu'une image a été "
    "téléchargée, vérifiée ou reste accessible.",
    "Un écart entre effectif local et effectif annoncé n'implique pas, à lui "
    "seul, des cartes manquantes.",
    "Une carte absente de cette sauvegarde n'existe nulle part : seule "
    "l'absence dans ce référentiel figé est rapportée.",
)

DIAGNOSTIC_LIMITS = (
    "Analyse figée d'une sauvegarde : aucune donnée live, aucun réseau, aucun "
    "enrichissement.",
    "La recherche ciblée est un outil de diagnostic, pas un identifieur "
    "d'annonce : elle retourne toutes les correspondances sans en choisir.",
    "Les exemples d'anomalies sont bornés ; les effectifs complets restent "
    "dans les compteurs.",
    "Seules les tables du référentiel et les métadonnées de synchronisation "
    "sont lues : aucune annonce, vendeur, contact ou donnée brute exportée.",
)


class ReportError(RuntimeError):
    """Erreur compréhensible remontée à l'utilisateur (base absente, fichier
    invalide ou schéma incompatible)."""


@dataclass(frozen=True)
class SchemaInfo:
    """Colonnes et tables réellement disponibles dans la sauvegarde lue."""

    card_columns: frozenset[str]
    set_columns: frozenset[str]
    has_schema_migrations: bool
    has_sync_jobs: bool
    has_sync_cards: bool

    @property
    def has_languages(self) -> bool:
        return "reference_language" in self.card_columns

    @property
    def has_canonical_ids(self) -> bool:
        return "canonical_local_id" in self.card_columns

    @property
    def has_normalized_name(self) -> bool:
        return "normalized_name" in self.card_columns

    @property
    def has_normalized_set_name(self) -> bool:
        return "normalized_set_name" in self.card_columns


# ---------------------------------------------------------------------------
# Ouverture et validation de la sauvegarde
# ---------------------------------------------------------------------------


def open_backup(path: Path) -> sqlite3.Connection:
    """Ouvre la sauvegarde en lecture seule, sans aucune initialisation."""
    if not path.is_file():
        raise ReportError(f"Base absente : {path}")
    try:
        connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise ReportError(f"Impossible d'ouvrir la base en lecture seule : {path}") from exc
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone()
    except sqlite3.DatabaseError as exc:
        connection.close()
        raise ReportError(
            f"Fichier invalide : ce n'est pas une base SQLite lisible ({path.name})."
        ) from exc
    return connection


def inspect_schema(connection: sqlite3.Connection) -> SchemaInfo:
    """Vérifie les tables requises et inventorielles colonnes disponibles."""
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    missing = [table for table in REQUIRED_TABLES if table not in tables]
    if missing:
        raise ReportError(
            "Schéma incompatible : table(s) manquante(s) "
            + ", ".join(missing)
            + ". Ce fichier n'est pas une sauvegarde du référentiel Pokémon."
        )

    def columns(table: str) -> frozenset[str]:
        return frozenset(
            row[1] for row in connection.execute(f"PRAGMA table_info({table})")
        )

    return SchemaInfo(
        card_columns=columns("pokemon_reference_cards"),
        set_columns=columns("pokemon_reference_sets"),
        has_schema_migrations="schema_migrations" in tables,
        has_sync_jobs="tcgdex_sync_jobs" in tables,
        has_sync_cards="tcgdex_sync_cards" in tables,
    )


def check_integrity(connection: sqlite3.Connection) -> str:
    """Contrôle d'intégrité rapide ; lève ReportError si la base est corrompue."""
    try:
        result = connection.execute("PRAGMA quick_check").fetchone()
    except sqlite3.DatabaseError as exc:
        raise ReportError(f"Fichier invalide : contrôle d'intégrité impossible ({exc}).") from exc
    status = result[0] if result else "unknown"
    if status != "ok":
        raise ReportError(f"Intégrité SQLite compromise : {status}")
    return status


def journal_mode(connection: sqlite3.Connection) -> str:
    row = connection.execute("PRAGMA journal_mode").fetchone()
    return str(row[0]) if row else "unknown"


# ---------------------------------------------------------------------------
# 1. Inventaire global
# ---------------------------------------------------------------------------


def build_global_inventory(connection: sqlite3.Connection, schema: SchemaInfo) -> dict[str, Any]:
    version: str | None = None
    migrations_applied: int | None = None
    if schema.has_schema_migrations:
        row = connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1"
        ).fetchone()
        version = row[0] if row else None
        migrations_applied = connection.execute(
            "SELECT COUNT(*) FROM schema_migrations"
        ).fetchone()[0]

    sets_count = connection.execute("SELECT COUNT(*) FROM pokemon_reference_sets").fetchone()[0]
    cards_count = connection.execute("SELECT COUNT(*) FROM pokemon_reference_cards").fetchone()[0]
    with_image = connection.execute(
        "SELECT COUNT(*) FROM pokemon_reference_cards"
        " WHERE image_url IS NOT NULL AND image_url <> ''"
    ).fetchone()[0]

    languages: list[dict[str, Any]] | None = None
    if schema.has_languages:
        languages = [
            {"language": row[0], "count": row[1]}
            for row in connection.execute(
                "SELECT reference_language, COUNT(*) FROM pokemon_reference_cards"
                " GROUP BY reference_language ORDER BY reference_language"
            )
        ]

    missing_fields = [
        column for column in OPTIONAL_CARD_COLUMNS if column not in schema.card_columns
    ]

    return {
        "schema_version": version,
        "migrations_applied": migrations_applied,
        "sets_count": sets_count,
        "cards_count": cards_count,
        "cards_with_image_url": with_image,
        "cards_without_image_url": cards_count - with_image,
        "languages": languages,
        "missing_optional_fields": missing_fields,
        "notes": [
            "La langue enregistrée par défaut (historiquement 'fr') n'est pas "
            "une preuve de la langue d'un exemplaire vendu.",
            "Une URL d'image renseignée ne prouve ni téléchargement, ni "
            "vérification, ni accessibilité actuelle.",
        ],
    }


# ---------------------------------------------------------------------------
# 2. Inventaire par extension
# ---------------------------------------------------------------------------


def _latest_sync_job(
    connection: sqlite3.Connection, schema: SchemaInfo, set_id: str
) -> dict[str, Any] | None:
    """État de la dernière demande de synchronisation, si le schéma le permet."""
    if not schema.has_sync_jobs:
        return None
    row = connection.execute(
        """
        SELECT id, status, stage, include_details, expected_count, summary_count,
               attempts, error_code, created_at, updated_at, last_success_at
        FROM tcgdex_sync_jobs
        WHERE set_id = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (set_id,),
    ).fetchone()
    if not row:
        return None
    job = dict(row)
    if schema.has_sync_cards:
        job["completed_details"] = connection.execute(
            "SELECT COUNT(*) FROM tcgdex_sync_cards"
            " WHERE job_id = ? AND status = 'completed'",
            (job["id"],),
        ).fetchone()[0]
    else:
        job["completed_details"] = None
    job.pop("id", None)
    return job


def _assess_coverage(local_cards: int, announced: int | None) -> dict[str, str]:
    """Classe la situation d'une extension sans conclure abusivement."""
    if local_cards == 0:
        return {
            "status": "extension_connue_sans_cartes",
            "conclusion": "faite",
            "explication": "extension présente au répertoire mais aucune carte locale",
        }
    if announced is None:
        return {
            "status": "information_insuffisante",
            "conclusion": "indisponible",
            "explication": "aucun effectif annoncé enregistré : impossible de conclure",
        }
    if local_cards == announced:
        return {
            "status": "effectif_conforme",
            "conclusion": "faite",
            "explication": "effectif local égal à l'effectif annoncé",
        }
    return {
        "status": "effectif_different_a_verifier",
        "conclusion": "a_verifier",
        "explication": MEANING_COUNT_GAP,
    }


def build_set_inventory(connection: sqlite3.Connection, schema: SchemaInfo) -> list[dict[str, Any]]:
    language_select = (
        ", (SELECT GROUP_CONCAT(reference_language || '=' || n, ', ')"
        "   FROM (SELECT reference_language, COUNT(*) AS n FROM pokemon_reference_cards"
        "         WHERE set_id = s.id GROUP BY reference_language ORDER BY reference_language))"
        "   AS languages"
        if schema.has_languages
        else ", NULL AS languages"
    )
    rows = connection.execute(
        f"""
        SELECT s.id, s.name, s.series, s.card_count_total, s.card_count_official,
               s.release_date, s.logo_url, s.symbol_url, s.updated_at,
               (SELECT COUNT(*) FROM pokemon_reference_cards c WHERE c.set_id = s.id)
                   AS local_cards,
               (SELECT COUNT(*) FROM pokemon_reference_cards c
                WHERE c.set_id = s.id AND c.image_url IS NOT NULL AND c.image_url <> '')
                   AS image_urls
               {language_select}
        FROM pokemon_reference_sets s
        ORDER BY s.id ASC
        """
    ).fetchall()

    inventory = []
    for row in rows:
        local_cards = row["local_cards"]
        announced = row["card_count_total"] if row["card_count_total"] is not None else row["card_count_official"]
        sync = _latest_sync_job(connection, schema, row["id"])

        detail_level: dict[str, Any]
        if sync is None and not schema.has_sync_jobs:
            detail_level = {
                "status": "information_indisponible",
                "explication": "table tcgdex_sync_jobs absente de cette sauvegarde",
            }
        elif sync is None:
            detail_level = {
                "status": "aucune_demande_de_synchronisation",
                "explication": "aucune tâche enregistrée pour cette extension",
            }
        else:
            completed = sync.get("completed_details")
            if completed is None:
                detail_level = {
                    "status": "a_verifier",
                    "explication": "progression des fiches détaillées indisponible",
                    "stage": sync["stage"],
                }
            else:
                expected = sync["expected_count"]
                detail_level = {
                    "status": "etabli",
                    "stage": sync["stage"],
                    "fiches_completees": completed,
                    "fiches_attendues": expected,
                    "manifeste_entrees": sync["summary_count"],
                }

        inventory.append(
            {
                "set_id": row["id"],
                "name": row["name"],
                "series": row["series"],
                "release_date": row["release_date"],
                "updated_at": row["updated_at"],
                "local_cards": local_cards,
                "cards_with_image_url": row["image_urls"],
                "languages": row["languages"],
                "announced": {
                    "card_count_total": row["card_count_total"],
                    "card_count_official": row["card_count_official"],
                    "signification_total": MEANING_ANNOUNCED_TOTAL,
                    "signification_official": MEANING_ANNOUNCED_OFFICIAL,
                },
                "coverage": _assess_coverage(local_cards, announced),
                "detail_level": detail_level,
                "sync_job": sync,
            }
        )
    return inventory


# ---------------------------------------------------------------------------
# 3. Recherche ciblée (diagnostic, pas identification d'annonce)
# ---------------------------------------------------------------------------


def search_cards(
    connection: sqlite3.Connection,
    schema: SchemaInfo,
    *,
    set_query: str | None = None,
    card_name: str | None = None,
    local_id: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Retourne toutes les correspondances, triées déterministement, sans en
    privilégier une. Ne fabrique aucun alias : une expression sans
    correspondance (par exemple « gempack 2 ») est simplement absente."""
    clauses: list[str] = []
    params: list[Any] = []

    if set_query:
        if schema.has_normalized_set_name:
            clauses.append(
                "(c.set_id = ? OR c.normalized_set_name LIKE ?)"
            )
            params.extend([set_query, f"%{normalize_text(set_query)}%"])
        else:
            clauses.append("(c.set_id = ? OR lower(c.set_name) LIKE ?)")
            params.extend([set_query, f"%{normalize_text(set_query)}%"])
    if card_name:
        if schema.has_normalized_name:
            clauses.append("c.normalized_name LIKE ?")
            params.append(f"%{normalize_text(card_name)}%")
        else:
            clauses.append("lower(c.name) LIKE ?")
            params.append(f"%{normalize_text(card_name)}%")
    if local_id:
        if schema.has_canonical_ids:
            clauses.append("c.canonical_local_id = ?")
            params.append(canonical_local_id(local_id))
        else:
            clauses.append("c.local_id = ?")
            params.append(local_id)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    order_id = "c.canonical_local_id" if schema.has_canonical_ids else "c.local_id"
    language_select = ", c.reference_language" if schema.has_languages else ", NULL AS reference_language"

    rows = connection.execute(
        f"""
        SELECT c.id, c.tcgdex_id, c.local_id, c.name, c.set_id, c.set_name,
               c.image_url IS NOT NULL AND c.image_url <> '' AS has_image
               {language_select}
        FROM pokemon_reference_cards c
        {where}
        ORDER BY c.name COLLATE NOCASE ASC, c.set_id ASC, {order_id} ASC, c.id ASC
        LIMIT ?
        """,
        [*params, max(1, min(limit, 500))],
    ).fetchall()

    matches = [
        {
            "tcgdex_id": row["tcgdex_id"],
            "name": row["name"],
            "local_id": row["local_id"],
            "set_id": row["set_id"],
            "set_name": row["set_name"],
            "reference_language": row["reference_language"],
            "has_image_url": bool(row["has_image"]),
        }
        for row in rows
    ]

    result: dict[str, Any] = {
        "criteria": {
            "set": set_query,
            "card_name": card_name,
            "local_id": local_id,
        },
        "match_count": len(matches),
        "matches": matches,
        "note": (
            "Aucune correspondance dans ce référentiel figé ; cela ne démontre "
            "pas une absence chez TCGdex ni dans le monde."
            if not matches
            else "Toutes les correspondances sont retournées ; aucune n'est choisie arbitrairement."
        ),
    }
    return result


# ---------------------------------------------------------------------------
# 4. Anomalies et limites
# ---------------------------------------------------------------------------


def _bounded_examples(
    connection: sqlite3.Connection, query: str, params: tuple[Any, ...] = ()
) -> tuple[int, list[dict[str, Any]]]:
    """Effectif total + exemples bornés pour un diagnostic lisible."""
    count = connection.execute(f"SELECT COUNT(*) FROM ({query})").fetchone()[0]
    rows = connection.execute(f"{query} LIMIT {MAX_EXAMPLES}", params).fetchall()
    return count, [dict(row) for row in rows]


def detect_anomalies(connection: sqlite3.Connection, schema: SchemaInfo) -> list[dict[str, Any]]:
    anomalies: list[dict[str, Any]] = []

    orphan_query = """
        SELECT c.id, c.tcgdex_id, c.name, c.set_id
        FROM pokemon_reference_cards c
        LEFT JOIN pokemon_reference_sets s ON s.id = c.set_id
        WHERE s.id IS NULL
        ORDER BY c.id
    """
    count, examples = _bounded_examples(connection, orphan_query)
    if count:
        anomalies.append(
            {
                "kind": "references_orphelines",
                "severity": "probleme_confirme",
                "count": count,
                "examples": examples,
                "explication": "cartes rattachées à une extension absente du répertoire",
            }
        )

    missing_number_query = """
        SELECT c.id, c.tcgdex_id, c.name, c.set_id
        FROM pokemon_reference_cards c
        WHERE c.local_id IS NULL OR c.local_id = ''
        ORDER BY c.id
    """
    count, examples = _bounded_examples(connection, missing_number_query)
    if count:
        anomalies.append(
            {
                "kind": "numeros_manquants",
                "severity": "probleme_confirme",
                "count": count,
                "examples": examples,
                "explication": "cartes sans numéro local exploitable",
            }
        )

    mismatch_query = """
        SELECT c.id, c.tcgdex_id, c.name, c.set_id, c.set_name, s.name AS repertoire_name
        FROM pokemon_reference_cards c
        JOIN pokemon_reference_sets s ON s.id = c.set_id
        WHERE c.set_name <> s.name
        ORDER BY c.id
    """
    count, examples = _bounded_examples(connection, mismatch_query)
    if count:
        anomalies.append(
            {
                "kind": "noms_extension_incoherents",
                "severity": "point_a_verifier",
                "count": count,
                "examples": examples,
                "explication": (
                    "nom d'extension de la carte différent du répertoire : "
                    "possible reprise du nom depuis la locale de synchronisation"
                ),
            }
        )

    if schema.has_canonical_ids:
        duplicate_query = """
            SELECT c.set_id, c.canonical_local_id, COUNT(*) AS occurrences,
                   GROUP_CONCAT(DISTINCT c.name) AS noms
            FROM pokemon_reference_cards c
            GROUP BY c.set_id, c.canonical_local_id
            HAVING COUNT(*) > 1
            ORDER BY c.set_id, c.canonical_local_id
        """
        count, examples = _bounded_examples(connection, duplicate_query)
        if count:
            anomalies.append(
                {
                    "kind": "numeros_partages_dans_une_extension",
                    "severity": "point_a_verifier",
                    "count": count,
                    "examples": examples,
                    "explication": (
                        "même numéro canonique sur plusieurs cartes d'une "
                        "extension : variantes légitimes possibles, à vérifier"
                    ),
                }
            )

        shared_query = """
            SELECT canonical_local_id, COUNT(DISTINCT set_id) AS extensions
            FROM pokemon_reference_cards
            GROUP BY canonical_local_id
            HAVING COUNT(DISTINCT set_id) > 1
            ORDER BY canonical_local_id
        """
        count, _ = _bounded_examples(connection, shared_query)
        anomalies.append(
            {
                "kind": "numeros_partages_entre_extensions",
                "severity": "information",
                "count": count,
                "examples": [],
                "explication": (
                    "numéros identiques entre extensions/langues : ce n'est "
                    "pas automatiquement des doublons erronés"
                ),
            }
        )

    if schema.has_languages:
        language_rows = connection.execute(
            "SELECT reference_language, COUNT(*) FROM pokemon_reference_cards"
            " GROUP BY reference_language ORDER BY reference_language"
        ).fetchall()
        anomalies.append(
            {
                "kind": "repartition_des_langues",
                "severity": "point_a_verifier",
                "count": len(language_rows),
                "examples": [
                    {"reference_language": row[0], "count": row[1]} for row in language_rows
                ],
                "explication": (
                    "une langue enregistrée par défaut n'est pas une preuve de "
                    "la langue d'un exemplaire vendu"
                ),
            }
        )
    else:
        anomalies.append(
            {
                "kind": "langues",
                "severity": "information_indisponible",
                "count": 0,
                "examples": [],
                "explication": "colonne reference_language absente de cette sauvegarde",
            }
        )

    anomalies.sort(key=lambda item: item["kind"])
    return anomalies


# ---------------------------------------------------------------------------
# Assemblage, rendu et export
# ---------------------------------------------------------------------------


def build_report(
    database_path: Path,
    *,
    set_query: str | None = None,
    card_name: str | None = None,
    local_id: str | None = None,
    search_limit: int = 50,
) -> dict[str, Any]:
    """Construit le rapport complet depuis une sauvegarde, sans rien modifier."""
    connection = open_backup(database_path)
    try:
        check_integrity(connection)
        schema = inspect_schema(connection)
        mode = journal_mode(connection)
        report: dict[str, Any] = {
            "report_version": REPORT_VERSION,
            "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "database": database_path.name,
            "journal_mode": mode,
            "method_warnings": list(METHOD_WARNINGS),
            "global": build_global_inventory(connection, schema),
            "sets": build_set_inventory(connection, schema),
            "anomalies": detect_anomalies(connection, schema),
            "limits": list(DIAGNOSTIC_LIMITS),
        }
        if set_query or card_name or local_id:
            report["search"] = search_cards(
                connection,
                schema,
                set_query=set_query,
                card_name=card_name,
                local_id=local_id,
                limit=search_limit,
            )
        if mode == "wal":
            report["limits"] = [
                *report["limits"],
                "Fichier encore en mode journal WAL : s'il a été copié hors du "
                "mécanisme de sauvegarde, les données les plus récentes peuvent "
                "manquer.",
            ]
        return report
    finally:
        connection.close()


def _format_languages(languages: list[dict[str, Any]] | None) -> str:
    if languages is None:
        return "information indisponible (colonne absente)"
    return ", ".join(f"{entry['language']}={entry['count']}" for entry in languages) or "aucune"


def render_text(report: dict[str, Any]) -> str:
    """Rendu lisible du rapport, sections numérotées comme la mission."""
    lines: list[str] = []
    global_info = report["global"]

    lines.append(f"RAPPORT DE COUVERTURE DU RÉFÉRENTIEL TCGDEX (version {report['report_version']})")
    lines.append(f"Base : {report['database']} · généré le {report['generated_at']}")
    lines.append("")
    lines.append("AVERTISSEMENTS MÉTHODOLOGIQUES")
    for warning in report["method_warnings"]:
        lines.append(f"  - {warning}")
    lines.append("")
    lines.append("1. INVENTAIRE GLOBAL")
    schema_version = global_info["schema_version"] or "information indisponible"
    lines.append(f"  Version de schéma : {schema_version}")
    if global_info["migrations_applied"] is not None:
        lines.append(f"  Migrations enregistrées : {global_info['migrations_applied']}")
    lines.append(f"  Extensions : {global_info['sets_count']}")
    lines.append(f"  Cartes : {global_info['cards_count']}")
    lines.append(
        f"  Cartes avec URL d'image : {global_info['cards_with_image_url']}"
        f" / {global_info['cards_count']} (URL renseignée ≠ image vérifiée)"
    )
    lines.append(f"  Langues de référence enregistrées : {_format_languages(global_info['languages'])}")
    if global_info["missing_optional_fields"]:
        lines.append(
            "  Champs absents de cette sauvegarde : "
            + ", ".join(global_info["missing_optional_fields"])
        )
    lines.append("")
    lines.append("2. INVENTAIRE PAR EXTENSION")
    if not report["sets"]:
        lines.append("  (aucune extension connue)")
    for entry in report["sets"]:
        coverage = entry["coverage"]
        lines.append(f"  [{entry['set_id']}] {entry['name']}")
        lines.append(f"      série={entry['series'] or '—'} sortie={entry['release_date'] or '—'}")
        lines.append(f"      cartes locales={entry['local_cards']} URL images={entry['cards_with_image_url']}")
        lines.append(f"      langues enregistrées : {entry['languages'] or '—'}")
        announced = entry["announced"]
        lines.append(
            f"      effectif annoncé total={announced['card_count_total']}"
            f" officiel={announced['card_count_official']} ({announced['signification_total']})"
        )
        lines.append(f"      statut : {coverage['status']} — {coverage['explication']}")
        detail = entry["detail_level"]
        lines.append(f"      détail : {detail['status']} — {detail.get('explication', '')}")
        sync = entry["sync_job"]
        if sync is None:
            lines.append("      synchronisation : aucune demande enregistrée")
        else:
            lines.append(
                f"      synchronisation : {sync['status']} (étape {sync['stage']},"
                f" tentatives {sync['attempts']}, dernière réussite {sync['last_success_at'] or '—'})"
            )
    lines.append("")
    if "search" in report:
        lines.append("3. RECHERCHE CIBLÉE")
        criteria = report["search"]["criteria"]
        lines.append(
            f"  critères : extension={criteria['set']!r} nom={criteria['card_name']!r}"
            f" numéro={criteria['local_id']!r}"
        )
        lines.append(f"  correspondances : {report['search']['match_count']}")
        for match in report["search"]["matches"]:
            lines.append(
                f"    - {match['name']} n°{match['local_id']}"
                f" · [{match['set_id']}] {match['set_name']}"
                f" · langue réf={match['reference_language'] or '—'}"
                f" · image={'oui' if match['has_image_url'] else 'non'}"
            )
        lines.append(f"  {report['search']['note']}")
        lines.append("")
    lines.append("4. ANOMALIES ET LIMITES")
    for anomaly in report["anomalies"]:
        lines.append(f"  [{anomaly['severity']}] {anomaly['kind']} : {anomaly['count']} occurrence(s)")
        lines.append(f"      {anomaly['explication']}")
        for example in anomaly["examples"]:
            lines.append(f"      ex. {example}")
    lines.append("")
    lines.append("LIMITES DU DIAGNOSTIC")
    for limit_note in report["limits"]:
        lines.append(f"  - {limit_note}")
    return "\n".join(lines)


def export_json(report: dict[str, Any], output_path: Path) -> Path:
    """Export JSON versionné ; refuse d'écraser un fichier existant."""
    if output_path.exists():
        raise ReportError(f"Refus d'écraser le fichier existant : {output_path}")
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    output_path.write_text(payload, encoding="utf-8")
    return output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.reference_coverage_report",
        description=(
            "Diagnostic hors ligne, en lecture seule, du référentiel TCGdex "
            "local contenu dans une sauvegarde SQLite cohérente (de préférence "
            "produite par pokemon-arbitrage backup). Aucune migration, seed, "
            "écriture, worker ou appel réseau."
        ),
    )
    parser.add_argument("database", type=Path, help="chemin d'une sauvegarde SQLite cohérente")
    parser.add_argument(
        "--set",
        dest="set_query",
        default=None,
        help="filtre de recherche : identifiant ou nom d'extension",
    )
    parser.add_argument("--card-name", default=None, help="filtre de recherche : nom de carte")
    parser.add_argument("--local-id", default=None, help="filtre de recherche : numéro local")
    parser.add_argument(
        "--search-limit",
        type=int,
        default=50,
        help="borne de correspondances retournées par la recherche (défaut 50)",
    )
    parser.add_argument(
        "--json",
        dest="json_path",
        type=Path,
        default=None,
        help="export JSON versionné (refuse d'écraser un fichier existant)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = build_report(
            args.database,
            set_query=args.set_query,
            card_name=args.card_name,
            local_id=args.local_id,
            search_limit=args.search_limit,
        )
        print(render_text(report))
        if args.json_path is not None:
            export_json(report, args.json_path)
            print(f"\nExport JSON écrit : {args.json_path}")
    except ReportError as error:
        print(f"Erreur : {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
