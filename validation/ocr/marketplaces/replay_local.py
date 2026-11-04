"""Rejeu strictement local d'une campagne figée ; ne fait pas partie de pytest.

Ce script rejoue l'identification des 30 annonces à partir des artefacts locaux
conservés par une campagne précédente (``jeu-30-liens.json`` et photos
téléchargées) ouverte sur une **sauvegarde SQLite figée**, en lecture seule.
Il ne télécharge rien : tout artefact manquant est une erreur explicite, jamais
une acquisition implicite. Le résultat est un nouveau rapport compatible avec
``scripts.evaluate_identification.py`` (variantes ``title_only``, ``ocr_only``,
``combined``), marqué ``decision_origin: automatic`` avec les versions de
pipeline et de normalisation courantes, afin de pouvoir comparer, à labels
humains égaux, un « avant » et un « après ».

Différences volontaires avec l'acquisition historique ``run_30_liens.py`` :

- aucun accès réseau (la résolution DNS est désactivée pour le processus) ;
- la base ouverte est une sauvegarde cohérente explicite, jamais la base
  opérationnelle, et uniquement en URI ``mode=ro`` ;
- les photos absentes rendent la variante ``ocr_only`` indisponible
  (``null``), sans être fabriquées ;
- les empreintes SHA-256 des photos sont contrôlées contre le manifeste de
  campagne lorsqu'il en fournit.

Usage (dans le conteneur, depuis la racine du dépôt) :

    python validation/ocr/marketplaces/replay_local.py \
        --backup /data/backups/pokebourse-YYYYMMDD-HHMMSS-ffffff.sqlite

Codes de retour : 0 succès ; 2 artefacts manquants, sauvegarde invalide ou
tentative réseau détectée.
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).parent
EVALUATION_DIR = ROOT.parent / "evaluation"
MANIFEST_PATH = EVALUATION_DIR / "manifest.json"

sys.path.insert(0, str(ROOT))
from run_30_liens import identity  # noqa: E402  (même logique d'identification que l'acquisition)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _ban_network() -> None:
    """Bloque toute résolution DNS : un appel réseau devient une erreur nette."""

    def _blocked(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("Accès réseau interdit pendant le rejeu local")

    socket.getaddrinfo = _blocked  # type: ignore[assignment]


def _git_commit() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10, check=True
        ).stdout.strip()
    except Exception:
        return None


def _load_manifest_images() -> dict[str, str]:
    """Empreintes attendues {chemin relatif: sha256} depuis le manifeste figé."""
    if not MANIFEST_PATH.exists():
        return {}
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {entry["path"]: entry["sha256"] for entry in manifest.get("images", [])}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run-id", default="2026-11-02-30-liens", help="Campagne figée à rejouer")
    parser.add_argument("--backup", required=True, help="Chemin d'une sauvegarde SQLite cohérente (jamais la base opérationnelle)")
    parser.add_argument("--output-dir", default=None, help="Sortie (défaut : runs/<run-id>-rejeu/)")
    args = parser.parse_args()

    source_run = ROOT / "runs" / args.run_id
    output_dir = Path(args.output_dir) if args.output_dir else ROOT / "runs" / f"{args.run_id}-rejeu"
    output_dir.mkdir(parents=True, exist_ok=True)

    dataset_path = ROOT / "jeu-30-liens.json"
    errors: list[str] = []
    if not dataset_path.exists():
        errors.append(f"Jeu de campagne manquant : {dataset_path}")
        dataset = []
    else:
        dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
        if len(dataset) != 30 or len({item["url"] for item in dataset}) != 30:
            errors.append("Le jeu doit contenir exactement 30 liens distincts")

    backup_path = Path(args.backup)
    if not backup_path.exists():
        errors.append(f"Sauvegarde absente : {backup_path}")
        backup_sha256 = None
    else:
        probe = sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True)
        try:
            tables = {row[0] for row in probe.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"pokemon_reference_cards", "pokemon_reference_sets"} <= tables:
                errors.append("La sauvegarde ne contient pas les tables du référentiel")
        except sqlite3.DatabaseError:
            errors.append(f"Fichier invalide (non SQLite) : {backup_path}")
        finally:
            probe.close()
        backup_sha256 = _sha256(backup_path)

    expected_images = _load_manifest_images()
    images_dir = source_run / "images"
    for index, item in enumerate(dataset, start=1):
        if not item.get("image_url"):
            continue
        image_path = images_dir / f"{index:02d}.webp"
        if not image_path.exists():
            errors.append(f"Photo manquante pour l'annonce {index:02d} (aucun téléchargement implicite)")
            continue
        expected = expected_images.get(str(image_path.relative_to(ROOT.parent.parent)))
        if expected and _sha256(image_path) != expected:
            errors.append(f"Empreinte de la photo {index:02d} différente du manifeste figé")

    if errors:
        for error in errors:
            print(f"REFUS : {error}", file=sys.stderr)
        return 2

    from app.identification.evidence import OBSERVATION_VERSION, PIPELINE_VERSION  # import local : après bannissement réseau
    from app.identification.ocr import analyze_image

    _ban_network()

    results = []
    connection = sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row  # même contrat d'accès que app.storage.database.connect
    try:
        for index, item in enumerate(dataset, start=1):
            result = dict(item)
            result["index"] = index
            result["image_status"] = "non fournie ; titre public seul testé"
            result["ocr"] = None
            result["ocr_only"] = None
            image_path = images_dir / f"{index:02d}.webp"
            if item.get("image_url") and image_path.exists():
                result["image"] = f"images/{image_path.name}"
                result["image_status"] = "analysée localement (rejeu)"
                ocr_result = analyze_image(connection, image_path.read_bytes())
                result["ocr"] = {"status": ocr_result["status"], "recognized": ocr_result["recognized"]}
                result["ocr_only"] = identity(connection, "", ocr_result["recognized"])
            result["title_only"] = identity(connection, item["title"])
            recognized = (result.get("ocr") or {}).get("recognized")
            result["combined"] = identity(connection, item["title"], recognized)
            results.append(result)
            print(f"{index:02d}/30 {item['platform']} {result['combined']['status']}", flush=True)
    finally:
        connection.close()

    report = {
        "id": f"{args.run_id}-rejeu",
        "label": "30 annonces Vinted et eBay — rejeu local hermétique",
        "created_at": datetime.now(UTC).isoformat(),
        "source": "Rejeu strictement local des artefacts figés ; aucun accès réseau ; sauvegarde SQLite en lecture seule.",
        "replay": {
            "source_run": args.run_id,
            "backup": str(backup_path),
            "backup_sha256": backup_sha256,
            "git_commit": _git_commit(),
            "network": "dns_banned",
        },
        "decision_origin": "automatic",
        "pipeline_version": PIPELINE_VERSION,
        "observation_version": OBSERVATION_VERSION,
        "note": "Rejeu hermétique : à comparer au rapport historique uniquement à labels humains égaux ; les statuts ne sont pas une mesure de justesse.",
        "items": results,
    }
    (output_dir / "resultats.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Rapport écrit : {output_dir / 'resultats.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
