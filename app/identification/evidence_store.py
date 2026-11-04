"""Conservation explicite et contrôlée des preuves visuelles (T04).

L'analyse OCR reste éphémère par défaut : aucune photo n'est conservée sans
un appel explicite à ce magasin. Les octets archivés sont dépourvus de
métadonnées EXIF (Pillow ré-encode un PNG propre) ; l'orientation d'origine
et une référence stable des pixels orientés sont conservées comme repères
pour le futur OCR spatial (T06). Une empreinte seule ne prouve pas la
conservation : la vérification contrôle les octets présents sur disque.

Garanties :
- écriture atomique (fichier temporaire puis renommage) dans l'espace de
  preuves uniquement ; aucun chemin fourni par l'appelant n'est accepté ;
- déduplication par empreinte des octets conservés ;
- quotas, rétention et purge explicites ;
- traitement explicite des fichiers manquants, corrompus ou supprimés.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import secrets
import sqlite3
from pathlib import Path
from typing import Any

from PIL import Image

from app.identification.ocr import _prepare_image
from app.identification.resolution import utc_now

IMAGE_STORE_VERSION = "image-store-v1"
TRANSFORM_VERSION = "transforms-v1"
READING_FIELDS = ("name", "card_number", "set_name", "language", "condition", "variant", "edition", "grading_company", "grade")
READING_SOURCES = ("ocr", "manual", "prefill")
EVIDENCE_PURPOSES = ("benchmark", "annotation", "confirmation")
DEFAULT_MAX_EVIDENCE_BYTES = 512 * 1024 * 1024


def evidence_root(database_path: Path) -> Path:
    """Racine contrôlée et persistante de l'espace de preuves."""
    return Path(database_path).resolve().parent / "evidence"


def _evidence_file(database_path: Path, storage_path: str) -> Path:
    """Résout un chemin stocké en base, en refusant toute sortie de l'espace."""
    root = evidence_root(database_path)
    path = (root / storage_path).resolve()
    if path != root and root not in path.parents:
        raise ValueError("Chemin de preuve hors de l'espace de stockage.")
    return path


def _pixel_reference(clean_png: bytes) -> tuple[str, int, int]:
    """Référence stable des pixels orientés : empreinte RGB + dimensions."""
    with Image.open(io.BytesIO(clean_png)) as prepared:
        rgb = prepared.convert("RGB")
        return hashlib.sha256(rgb.tobytes()).hexdigest(), rgb.width, rgb.height


def _original_orientation(content: bytes) -> int | None:
    """Orientation EXIF d'origine, gardée comme repère sans métadonnées."""
    try:
        with Image.open(io.BytesIO(content)) as image:
            exif = image.getexif()
            orientation = exif.get(0x0112) if exif else None
            if isinstance(orientation, int) and 1 <= orientation <= 8:
                return orientation
    except Exception:
        pass
    return None


def active_evidence_bytes(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        "SELECT COALESCE(SUM(byte_size), 0) FROM listing_image_evidence WHERE deleted_at IS NULL"
    ).fetchone()
    return int(row[0] if row else 0)


def store_image_evidence(
    connection: sqlite3.Connection,
    database_path: Path,
    content: bytes,
    *,
    purpose: str = "benchmark",
    listing_id: int | None = None,
    max_bytes: int = DEFAULT_MAX_EVIDENCE_BYTES,
) -> sqlite3.Row:
    """Conserve explicitement les octets d'une photo dans l'espace de preuves.

    Déduplique par empreinte : stocker deux fois les mêmes octets réutilise
    l'enregistrement existant. Re-conserver les octets d'une preuve supprimée
    réactive cet enregistrement (identité et décisions rattachées conservées).
    Ne déclenche aucune analyse et ne confirme aucune identité. Lève
    ValueError pour tout contenu invalide ou dépassement de quota ; ne
    conserve rien en cas d'échec.

    La fonction valide sa propre transaction : l'INSERT reste persisté même si
    l'appelant ne commit jamais (cas des routes web, qui ne commitent pas).
    """
    if purpose not in EVIDENCE_PURPOSES:
        raise ValueError("Périmètre de conservation inconnu.")
    if type(max_bytes) is not int or max_bytes <= 0:
        raise ValueError("Quota de preuves invalide.")
    if listing_id is not None:
        if connection.execute("SELECT 1 FROM catalog_items WHERE id=?", (listing_id,)).fetchone() is None:
            raise LookupError("Annonce introuvable.")
    # Mêmes bornes et même nettoyage que l'analyse éphémère : pas de métadonnées.
    clean = _prepare_image(content)
    sha256 = hashlib.sha256(clean).hexdigest()
    stored: Path | None = None
    try:
        with connection:
            if not connection.in_transaction:
                connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM listing_image_evidence WHERE sha256=?", (sha256,)
            ).fetchone()
            if existing is not None and existing["deleted_at"] is None:
                if listing_id is not None and existing["listing_id"] is None:
                    connection.execute(
                        "UPDATE listing_image_evidence SET listing_id=? WHERE id=? AND listing_id IS NULL",
                        (listing_id, existing["id"]),
                    )
                return connection.execute(
                    "SELECT * FROM listing_image_evidence WHERE id=?", (existing["id"],)
                ).fetchone()
            if active_evidence_bytes(connection) + len(clean) > max_bytes:
                raise ValueError("Quota de stockage des preuves atteint : purgez avant de conserver davantage.")
            pixel_sha256, width, height = _pixel_reference(clean)
            if existing is not None:
                # Réactivation d'une preuve supprimée : l'unicité de l'empreinte
                # interdit un nouvel enregistrement ; on réécrit les octets et
                # on rétablit la preuve, en conservant son identité et les
                # décisions qui la référencent.
                destination = _evidence_file(Path(database_path), existing["storage_path"])
                temporary = destination.with_name(f".tmp-{secrets.token_hex(8)}")
                try:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    temporary.write_bytes(clean)
                    os.replace(temporary, destination)
                    stored = destination
                    connection.execute(
                        """UPDATE listing_image_evidence SET deleted_at=NULL, purpose=?,
                           listing_id=COALESCE(listing_id, ?), byte_size=?, width=?, height=?,
                           pixel_sha256=?, exif_orientation=?, created_at=?, mime_type='image/png'
                           WHERE id=?""",
                        (purpose, listing_id, len(clean), width, height, pixel_sha256,
                         _original_orientation(content), utc_now(), existing["id"]),
                    )
                except BaseException:
                    temporary.unlink(missing_ok=True)
                    destination.unlink(missing_ok=True)
                    stored = None
                    raise
                return connection.execute(
                    "SELECT * FROM listing_image_evidence WHERE id=?", (existing["id"],)
                ).fetchone()
            storage_path = f"images/{sha256[:2]}/{sha256}.png"
            destination = _evidence_file(Path(database_path), storage_path)
            temporary = destination.with_name(f".tmp-{secrets.token_hex(8)}")
            try:
                destination.parent.mkdir(parents=True, exist_ok=True)
                temporary.write_bytes(clean)
                os.replace(temporary, destination)
                stored = destination
                connection.execute(
                    """INSERT INTO listing_image_evidence
                    (sha256, pixel_sha256, storage_path, byte_size, mime_type, width, height,
                     exif_orientation, purpose, listing_id, created_at)
                    VALUES (?, ?, ?, ?, 'image/png', ?, ?, ?, ?, ?, ?)""",
                    (sha256, pixel_sha256, storage_path, len(clean), width, height,
                     _original_orientation(content), purpose, listing_id, utc_now()),
                )
            except sqlite3.IntegrityError:
                # Déduplication concurrente : réutiliser l'enregistrement existant.
                temporary.unlink(missing_ok=True)
                stored = None
            except BaseException:
                temporary.unlink(missing_ok=True)
                destination.unlink(missing_ok=True)
                stored = None
                raise
    except BaseException:
        # Un échec au commit ne doit laisser ni ligne orpheline ni octet orphelin.
        if stored is not None:
            stored.unlink(missing_ok=True)
        raise
    return connection.execute(
        "SELECT * FROM listing_image_evidence WHERE sha256=? AND deleted_at IS NULL", (sha256,)
    ).fetchone()


def evidence_file_status(connection: sqlite3.Connection, database_path: Path, evidence_id: int) -> str:
    """État explicite des octets : present, deleted, missing, corrupted."""
    row = connection.execute(
        "SELECT * FROM listing_image_evidence WHERE id=?", (evidence_id,)
    ).fetchone()
    if row is None:
        raise LookupError("Preuve visuelle introuvable.")
    if row["deleted_at"] is not None:
        return "deleted"
    try:
        path = _evidence_file(Path(database_path), row["storage_path"])
    except ValueError:
        return "corrupted"
    if not path.is_file():
        return "missing"
    if hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
        return "corrupted"
    return "present"


def verify_evidence_store(connection: sqlite3.Connection, evidence_dir: Path) -> dict[str, Any]:
    """Contrôle les octets d'un espace de preuves donné, sans rien modifier.

    Fonctionne pour l'espace courant (à côté de la base) et pour le sidecar
    d'une sauvegarde : les chemins stockés sont toujours résolus relativement
    à la racine fournie et refusés hors de celle-ci.
    """
    root = Path(evidence_dir).resolve()
    statuses: dict[str, list[int]] = {"present": [], "deleted": [], "missing": [], "corrupted": []}
    for row in connection.execute(
        "SELECT id, sha256, storage_path, deleted_at FROM listing_image_evidence ORDER BY id"
    ):
        if row["deleted_at"] is not None:
            statuses["deleted"].append(row["id"])
            continue
        path = (root / row["storage_path"]).resolve()
        if not (path != root and root in path.parents) or not path.is_file():
            statuses["missing"].append(row["id"])
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            statuses["corrupted"].append(row["id"])
            continue
        statuses["present"].append(row["id"])
    return {
        "store_version": IMAGE_STORE_VERSION,
        "total": sum(len(ids) for ids in statuses.values()),
        "present": len(statuses["present"]),
        "missing": statuses["missing"],
        "corrupted": statuses["corrupted"],
        "deleted": len(statuses["deleted"]),
        "ok": not statuses["missing"] and not statuses["corrupted"],
    }


def verify_image_evidence(connection: sqlite3.Connection, database_path: Path) -> dict[str, Any]:
    """Contrôle l'intégrité de toutes les preuves actives, sans rien modifier."""
    return verify_evidence_store(connection, evidence_root(database_path))


def delete_image_evidence(connection: sqlite3.Connection, database_path: Path, evidence_id: int) -> None:
    """Supprime explicitement les octets et marque la preuve (purge logique)."""
    row = connection.execute(
        "SELECT * FROM listing_image_evidence WHERE id=?", (evidence_id,)
    ).fetchone()
    if row is None:
        raise LookupError("Preuve visuelle introuvable.")
    try:
        _evidence_file(Path(database_path), row["storage_path"]).unlink(missing_ok=True)
    except ValueError:
        pass
    connection.execute(
        "UPDATE listing_image_evidence SET deleted_at=? WHERE id=? AND deleted_at IS NULL",
        (utc_now(), evidence_id),
    )


def purge_unreferenced_evidence(connection: sqlite3.Connection, database_path: Path) -> int:
    """Purge les preuves actives sans annonce, lecture ni décision rattachée."""
    rows = connection.execute(
        """SELECT e.id FROM listing_image_evidence e
        WHERE e.deleted_at IS NULL AND e.listing_id IS NULL
        AND NOT EXISTS (SELECT 1 FROM listing_image_evidence_readings r WHERE r.image_evidence_id=e.id)
        AND NOT EXISTS (SELECT 1 FROM listing_identification_reviews v WHERE v.image_evidence_id=e.id)
        ORDER BY e.id"""
    ).fetchall()
    for row in rows:
        delete_image_evidence(connection, database_path, row["id"])
    return len(rows)


def purge_expired_evidence(
    connection: sqlite3.Connection, database_path: Path, *, days: int,
) -> int:
    """Applique la rétention : purge les preuves non utilisées par une décision."""
    if type(days) is not int or not 1 <= days <= 3650:
        raise ValueError("Durée de rétention invalide.")
    from datetime import UTC, datetime, timedelta
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    rows = connection.execute(
        """SELECT e.id FROM listing_image_evidence e
        WHERE e.deleted_at IS NULL AND e.created_at < ?
        AND NOT EXISTS (SELECT 1 FROM listing_identification_reviews v WHERE v.image_evidence_id=e.id)
        ORDER BY e.id""",
        (cutoff,),
    ).fetchall()
    for row in rows:
        delete_image_evidence(connection, database_path, row["id"])
    return len(rows)


def attach_image_reading(
    connection: sqlite3.Connection,
    *,
    image_evidence_id: int,
    field: str,
    value: str,
    source: str,
    listing_id: int | None = None,
    snapshot_id: int | None = None,
    region: tuple[int, int, int, int] | None = None,
    extractor_version: str = IMAGE_STORE_VERSION,
) -> int:
    """Rattache une lecture à image → observation → région → version.

    Une lecture n'est jamais créée pour une preuve supprimée ; une région
    exige quatre entiers ordonnés dans le repère de l'image orientée.
    """
    if field not in READING_FIELDS or source not in READING_SOURCES:
        raise ValueError("Champ ou origine de lecture invalide.")
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise ValueError("Valeur de lecture invalide.")
    row = connection.execute(
        "SELECT id, deleted_at FROM listing_image_evidence WHERE id=?", (image_evidence_id,)
    ).fetchone()
    if row is None:
        raise LookupError("Preuve visuelle introuvable.")
    if row["deleted_at"] is not None:
        raise ValueError("Une preuve supprimée ne reçoit pas de nouvelle lecture.")
    if region is not None:
        coordinates = tuple(region)
        if (len(coordinates) != 4 or any(type(c) is not int for c in coordinates)
                or any(c < 0 or c > 1_000_000 for c in coordinates)
                or coordinates[2] <= coordinates[0] or coordinates[3] <= coordinates[1]):
            raise ValueError("Région de lecture invalide.")
    cursor = connection.execute(
        """INSERT INTO listing_image_evidence_readings
        (image_evidence_id, listing_id, snapshot_id, field, value, source,
         region_json, transform_version, extractor_version, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (image_evidence_id, listing_id, snapshot_id, field, value.strip(), source,
         json.dumps(list(region)) if region is not None else None,
         TRANSFORM_VERSION, extractor_version, utc_now()),
    )
    return int(cursor.lastrowid)
