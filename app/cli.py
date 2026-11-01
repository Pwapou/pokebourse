import argparse
from collections.abc import Sequence
import json
import logging
from pathlib import Path
import sqlite3
import sys

from pydantic import ValidationError

from app.backups import create_backup, restore_backup
from app.catalog import (
    CatalogImportError,
    import_jsonl,
    record_import_failure,
)
from app.collectors.models import CollectorError
from app.config import Settings
from app.monitoring.models import (
    WatchAlreadyRunningError,
    WatchInput,
    WatchNotFoundError,
    WatchValidationError,
)
from app.monitoring.service import WatchService
from app.profitability import (
    FeeProfileUpdate,
    ProfitabilityError,
    evaluate_catalog,
    get_active_fee_profile,
    import_references_jsonl,
    update_active_fee_profile,
)
from app.storage.database import connect
from app.storage.migration_runner import apply_migrations, check_database


def _format_cents(cents: int | None, currency: str = "EUR", signed: bool = False) -> str:
    if cents is None:
        return "—"
    prefix = "+" if signed and cents > 0 else ""
    amount = f"{cents / 100:,.2f}".replace(",", " ").replace(".", ",")
    unit = "€" if currency == "EUR" else currency
    return f"{prefix}{amount} {unit}"


def _format_bps(bps: int | None, signed: bool = False) -> str:
    if bps is None:
        return "—"
    prefix = "+" if signed and bps > 0 else ""
    pct = f"{bps / 100:.1f}".replace(".", ",")
    return f"{prefix}{pct} %"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pokemon-arbitrage")
    parser.add_argument("--database", type=Path, help="Chemin de la base SQLite")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("migrate", help="Appliquer les migrations SQLite")
    subparsers.add_parser("check", help="Vérifier l'intégrité et les migrations")
    export_labels = subparsers.add_parser("export-labels", help="Exporter les validations humaines ML en JSONL")
    export_labels.add_argument("--output", required=True, type=Path, help="Fichier JSONL à créer (sans écrasement)")
    diagnostic = subparsers.add_parser("diagnose-identification", help="Diagnostiquer les annonces non résolues, en lecture seule")
    diagnostic.add_argument("--limit", type=int, choices=range(1, 501), default=100, metavar="1..500")
    diagnostic.add_argument("--status", choices=("unidentified", "ambiguous", "all"), default="unidentified")
    diagnostic.add_argument("--json", action="store_true", dest="as_json")

    import_cat = subparsers.add_parser(
        "import-catalog", help="Importer un fichier JSONL d'annonces"
    )
    import_cat.add_argument("file", type=Path, help="Chemin du fichier JSONL")
    import_cat.add_argument(
        "--source", default="import-cli", help="Nom de la source d'import"
    )

    import_refs = subparsers.add_parser(
        "import-references", help="Importer ou mettre à jour des cotes JSONL"
    )
    import_refs.add_argument("file", type=Path, help="Chemin du fichier JSONL de cotes")

    fees = subparsers.add_parser(
        "configure-fees",
        help="Afficher ou modifier les paramètres du moteur de rentabilité",
    )
    fees.add_argument("--buyer-shipping-cents", type=int, help="Port aller en centimes")
    fees.add_argument(
        "--platform-fee-bps",
        type=int,
        help="Commission plateforme en points de base (500 = 5,00 %%)",
    )
    fees.add_argument(
        "--seller-fixed-fee-cents", type=int, help="Frais fixes vendeur en centimes"
    )
    fees.add_argument(
        "--shipping-packaging-cents",
        type=int,
        help="Expédition et emballage en centimes",
    )
    fees.add_argument(
        "--min-net-profit-cents",
        type=int,
        help="Seuil de gain net minimum en centimes",
    )
    fees.add_argument(
        "--min-roi-bps",
        type=int,
        help="Seuil de ROI minimum en points de base (1500 = 15,00 %%)",
    )
    fees.add_argument(
        "--min-catalog-samples",
        type=int,
        help="Nombre minimum d'autres annonces comparables pour la médiane",
    )

    analyze = subparsers.add_parser(
        "analyze", help="Exécuter le moteur de rentabilité sur le catalogue"
    )
    analyze.add_argument(
        "--only-opportunities",
        action="store_true",
        help="Afficher uniquement les opportunités qualifiées",
    )
    analyze.add_argument("--query", default="", help="Filtrer par texte")
    analyze.add_argument("--set-name", default="", help="Filtrer par extension")
    analyze.add_argument(
        "--limit", type=int, default=25, help="Nombre maximal de lignes affichées"
    )
    analyze.add_argument(
        "--json", action="store_true", dest="as_json", help="Sortie au format JSON"
    )

    backup_parser = subparsers.add_parser(
        "backup", help="Créer une sauvegarde cohérente de la base SQLite"
    )
    backup_parser.add_argument(
        "--output",
        type=Path,
        help="Chemin de destination (défaut : <dossier de la base>/backups/pokebourse-<horodatage>.sqlite)",
    )

    restore_parser = subparsers.add_parser(
        "restore", help="Restaurer la base depuis un fichier de sauvegarde"
    )
    restore_parser.add_argument("file", type=Path, help="Chemin du fichier .sqlite")
    restore_parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirmer explicitement la restauration (remplace la base courante)",
    )

    subparsers.add_parser("list-watches", help="Lister les veilles marketplace")

    add_watch = subparsers.add_parser(
        "add-watch", help="Créer et activer une veille marketplace"
    )
    add_watch.add_argument("platform", choices=("vinted", "leboncoin", "ebay", "wallapop"))
    add_watch.add_argument("name", help="Nom de la veille")
    add_watch.add_argument("keywords", help="Mots-clés de recherche")
    add_watch.add_argument(
        "--price-from-cents", type=int, help="Prix minimum en centimes"
    )
    add_watch.add_argument(
        "--price-to-cents", type=int, help="Prix maximum en centimes"
    )
    add_watch.add_argument(
        "--interval-seconds", type=int, default=120, help="Intervalle entre deux contrôles"
    )
    add_watch.add_argument(
        "--category", help="Catégorie Leboncoin (ignorée par Vinted)"
    )

    pause_watch = subparsers.add_parser("pause-watch", help="Mettre une veille en pause")
    pause_watch.add_argument("watch_id", type=int, help="Identifiant de la veille")
    resume_watch = subparsers.add_parser(
        "resume-watch", help="Réactiver une veille en pause"
    )
    resume_watch.add_argument("watch_id", type=int, help="Identifiant de la veille")
    run_watch = subparsers.add_parser(
        "run-watch", help="Exécuter manuellement une veille une seule fois"
    )
    run_watch.add_argument("watch_id", type=int, help="Identifiant de la veille")
    return parser


def _run_backup(database_path: Path, output: Path | None) -> int:
    if not database_path.is_file():
        print(f"Erreur : base introuvable : {database_path}", file=sys.stderr)
        return 1
    try:
        destination = create_backup(database_path, output)
    except (OSError, sqlite3.Error, RuntimeError) as error:
        print(f"Erreur : {error}", file=sys.stderr)
        return 1
    print(f"Sauvegarde créée : {destination}")
    return 0


def _run_restore(database_path: Path, backup: Path, confirmed: bool) -> int:
    if not confirmed:
        print(
            "Restauration refusée : ajoutez --yes pour confirmer explicitement "
            "(la base courante sera remplacée).",
            file=sys.stderr,
        )
        return 2
    try:
        safety_backup = restore_backup(database_path, backup)
    except (OSError, sqlite3.Error, RuntimeError) as error:
        print(f"Erreur : {error}", file=sys.stderr)
        return 1
    print(f"Base restaurée depuis {backup}")
    if safety_backup is not None:
        print(f"Sauvegarde de sécurité : {safety_backup}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = Settings.from_env()
        logging.basicConfig(level=settings.log_level)
        database_path = args.database or settings.database_path
        if args.command == "backup":
            return _run_backup(database_path, args.output)
        if args.command == "restore":
            return _run_restore(database_path, args.file, args.yes)
        with connect(database_path) as connection:
            if args.command == "migrate":
                applied = apply_migrations(connection)
                if applied:
                    for version in applied:
                        print(f"Migration appliquée : {version}")
                else:
                    print("Aucune migration en attente")
            elif args.command == "check":
                check_database(connection)
                print(f"Base SQLite valide : {database_path}")
            elif args.command == "export-labels":
                from app.identification.dataset import build_dataset
                check_database(connection)
                payload = build_dataset(connection)
                with args.output.open("xb") as destination:
                    destination.write(payload)
                print(f"Validations humaines exportées : {args.output}")
            elif args.command == "diagnose-identification":
                from app.identification.diagnostics import identification_diagnostics
                check_database(connection)
                report = identification_diagnostics(connection, limit=args.limit, status=args.status)
                if args.as_json:
                    print(json.dumps(report, ensure_ascii=False, indent=2))
                else:
                    print(f"Catalogue : {report['catalog']['card_count']} cartes, {report['catalog']['set_count']} extensions")
                    print(f"Annonces analysées : {report['analyzed_count']} / {report['population']} ; {report['with_candidates']} avec candidats")
                    for key, count in report["counts"].items():
                        print(f"- {report['labels'][key]} : {count}")
            elif args.command == "list-watches":
                check_database(connection)
                service = WatchService(
                    min_interval_seconds=settings.min_watch_interval_seconds
                )
                watches = service.list_watches(connection)
                if not watches:
                    print("Aucune veille configurée.")
                for watch in watches:
                    state = "active" if watch["is_active"] else "pause"
                    last_status = watch["last_run_status"] or "jamais exécutée"
                    last_at = (
                        watch["last_run_started_at"]
                        or "—"
                    )
                    print(
                        f"#{watch['id']} [{watch['platform']}] {watch['name']} : "
                        f"{state}, intervalle {watch['interval_seconds']} s, "
                        f"dernier contrôle {last_status} ({last_at})"
                    )
            elif args.command == "add-watch":
                check_database(connection)
                watch = WatchInput(
                    platform=args.platform,
                    name=args.name,
                    search_text=args.keywords,
                    price_from=args.price_from_cents,
                    price_to=args.price_to_cents,
                    interval_seconds=args.interval_seconds,
                    category=args.category,
                )
                service = WatchService(
                    min_interval_seconds=settings.min_watch_interval_seconds
                )
                watch_id = service.create_watch(connection, watch)
                print(f"Veille créée et activée : #{watch_id}")
            elif args.command == "pause-watch":
                check_database(connection)
                WatchService(
                    min_interval_seconds=settings.min_watch_interval_seconds
                ).pause_watch(connection, args.watch_id)
                print(f"Veille mise en pause : #{args.watch_id}")
            elif args.command == "resume-watch":
                check_database(connection)
                WatchService(
                    min_interval_seconds=settings.min_watch_interval_seconds
                ).resume_watch(connection, args.watch_id)
                print(f"Veille réactivée : #{args.watch_id}")
            elif args.command == "run-watch":
                check_database(connection)
                summary = WatchService(
                    min_interval_seconds=settings.min_watch_interval_seconds
                ).run_watch_once(connection, args.watch_id)
                print(
                    f"Exécution réussie : {summary['result_count']} résultat(s), "
                    f"{summary['created_count']} nouvelle(s) annonce(s), "
                    f"{summary['updated_count']} mise(s) à jour."
                )
            elif args.command == "import-catalog":
                check_database(connection)
                content = args.file.read_bytes()
                try:
                    imported = import_jsonl(
                        connection, content, source_name=args.source
                    )
                except CatalogImportError as error:
                    record_import_failure(
                        connection,
                        source_name=args.source,
                        filename=args.file.name,
                        content=content,
                        error_message=str(error),
                    )
                    raise
                print(f"Annonces importées : {imported}")
            elif args.command == "import-references":
                check_database(connection)
                count = import_references_jsonl(connection, args.file.read_bytes())
                print(f"Cotes importées ou mises à jour : {count}")
            elif args.command == "configure-fees":
                check_database(connection)
                current = get_active_fee_profile(connection)
                updates = {
                    "buyer_shipping_cents": (
                        args.buyer_shipping_cents
                        if args.buyer_shipping_cents is not None
                        else current.buyer_shipping_cents
                    ),
                    "platform_fee_bps": (
                        args.platform_fee_bps
                        if args.platform_fee_bps is not None
                        else current.platform_fee_bps
                    ),
                    "seller_fixed_fee_cents": (
                        args.seller_fixed_fee_cents
                        if args.seller_fixed_fee_cents is not None
                        else current.seller_fixed_fee_cents
                    ),
                    "shipping_packaging_cents": (
                        args.shipping_packaging_cents
                        if args.shipping_packaging_cents is not None
                        else current.shipping_packaging_cents
                    ),
                    "min_net_profit_cents": (
                        args.min_net_profit_cents
                        if args.min_net_profit_cents is not None
                        else current.min_net_profit_cents
                    ),
                    "min_roi_bps": (
                        args.min_roi_bps
                        if args.min_roi_bps is not None
                        else current.min_roi_bps
                    ),
                    "min_catalog_samples": (
                        args.min_catalog_samples
                        if args.min_catalog_samples is not None
                        else current.min_catalog_samples
                    ),
                }
                has_change = any(
                    getattr(args, field) is not None for field in updates
                )
                profile = (
                    update_active_fee_profile(
                        connection, FeeProfileUpdate.model_validate(updates)
                    )
                    if has_change
                    else current
                )
                print(
                    f"Profil actif ({profile.name}) : "
                    f"port aller {_format_cents(profile.buyer_shipping_cents, profile.currency)}, "
                    f"commission {_format_bps(profile.platform_fee_bps)}, "
                    f"frais fixes {_format_cents(profile.seller_fixed_fee_cents, profile.currency)}, "
                    f"envoi {_format_cents(profile.shipping_packaging_cents, profile.currency)}, "
                    f"seuils {_format_cents(profile.min_net_profit_cents, profile.currency)} / "
                    f"{_format_bps(profile.min_roi_bps)}"
                )
            elif args.command == "analyze":
                check_database(connection)
                verdict_filter = "opportunite" if args.only_opportunities else "all"
                evaluations, summary, profile = evaluate_catalog(
                    connection,
                    query=args.query.strip(),
                    set_name=args.set_name,
                    verdict=verdict_filter,
                )
                displayed = evaluations[: max(args.limit, 0)]
                if args.as_json:
                    print(
                        json.dumps(
                            {
                                "profile": profile.model_dump(),
                                "summary": summary,
                                "results": displayed,
                            },
                            ensure_ascii=False,
                            indent=2,
                        )
                    )
                else:
                    print(
                        f"Opportunités : {summary['opportunity_count']} / "
                        f"{summary['catalog_count']} annonces "
                        f"(potentiel net : {_format_cents(summary['potential_profit_cents'], profile.currency, signed=True)})"
                    )
                    for row in displayed:
                        number = f" #{row['card_number']}" if row.get("card_number") else ""
                        print(
                            f"- [{row['verdict_label']}] {row['name']} ({row['set_name']}{number}) : "
                            f"achat {_format_cents(row['total_cost_cents'], row['currency'])} -> "
                            f"cote {_format_cents(row['reference_price_cents'], row['currency'])} | "
                            f"gain {_format_cents(row['net_profit_cents'], row['currency'], signed=True)} "
                            f"({_format_bps(row['roi_bps'], signed=True)})"
                        )
        return 0
    except (
        OSError,
        sqlite3.Error,
        RuntimeError,
        ValidationError,
        CatalogImportError,
        CollectorError,
        ProfitabilityError,
        WatchNotFoundError,
        WatchValidationError,
    ) as error:
        print(f"Erreur : {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
