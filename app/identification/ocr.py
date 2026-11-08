"""Lecture locale et éphémère d'une photo : indices et candidats à vérifier."""

from __future__ import annotations

import io
import os
import sqlite3
import subprocess
import threading
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from PIL import Image, ImageOps, UnidentifiedImageError

from app.identification.detector import extract_features
from app.storage.database import connect

router = APIRouter()
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 12_000_000
OCR_TIMEOUT_SECONDS = 20
_OCR_SLOTS = threading.BoundedSemaphore(2)


def _prepare_image(content: bytes) -> bytes:
    """Décode uniquement une image bornée et la convertit en PNG sans métadonnées."""
    if not content or len(content) > MAX_IMAGE_BYTES:
        raise ValueError("Image vide ou supérieure à 8 Mo.")
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.format not in {"PNG", "JPEG", "WEBP"}:
                raise ValueError("Formats acceptés : JPEG, PNG et WebP.")
            width, height = image.size
            if width <= 0 or height <= 0 or width * height > MAX_PIXELS:
                raise ValueError("Image trop grande : maximum 12 millions de pixels.")
            # Une seule image est analysée, et les métadonnées ne sont pas conservées.
            image.seek(0)
            image.load()
            clean = ImageOps.exif_transpose(image).convert("RGB")
            output = io.BytesIO()
            clean.save(output, format="PNG")
            return output.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise ValueError("Image illisible ou format non pris en charge.") from error


def _run_tesseract(image: bytes, psm: int = 11) -> str:
    """Exécute Tesseract sans fichier temporaire ni écriture des résultats."""
    environment = dict(os.environ, OMP_THREAD_LIMIT="1")
    try:
        result = subprocess.run(
            ["tesseract", "stdin", "stdout", "-l", "fra+eng", "--psm", str(psm)],
            input=image, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=OCR_TIMEOUT_SECONDS, check=True, env=environment,
        )
    except FileNotFoundError as error:
        raise RuntimeError("Moteur OCR indisponible. Reconstruisez l'image Docker de l'application.") from error
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("Analyse trop longue. Essayez une image plus lisible et recadrée.") from error
    except subprocess.CalledProcessError as error:
        raise RuntimeError("Analyse OCR impossible pour cette image.") from error
    return result.stdout.decode("utf-8", errors="replace")[:20_000]


def extract_suggestions(connection: sqlite3.Connection, text: str) -> dict[str, Any]:
    """Réutilise l'extraction et le classement communs, sans conserver le texte brut."""
    from app.identification.matcher import CardMatcher
    from app.tcgdex.cache import TcgdexCache

    result = CardMatcher(TcgdexCache(connection), seed_if_empty=False, repair_index=False).identify(text[:20_000])
    features = result.features
    names = [features.name] if features.name else []
    numbers = [features.card_number] if features.card_number else []
    candidates: list[dict[str, Any]] = []
    cards = {card.id: card for card in TcgdexCache(connection).get_cards_by_ids(
        [candidate.card_id for candidate in result.candidates[:20]]
    )}
    for candidate in result.candidates[:20]:
        if candidate.contradictions:
            continue
        card = cards[candidate.card_id]
        candidates.append({
            **asdict(candidate), "image_url": card.image_url,
        })
    status = "lot" if result.status == "lot" else "candidates" if candidates else "no_match"
    return {
        "status": status,
        "recognized": {"names": names, "numbers": numbers},
        "candidates": candidates,
        "message": (
            "Cette image semble montrer un lot : aucune carte unitaire n'est proposée."
            if status == "lot" else
            "Suggestions à vérifier : le texte lu peut être incomplet ou concerner plusieurs cartes. "
            "La photo ne prouve ni authenticité, ni état, ni prix."
            if candidates else "Aucun candidat fiable trouvé. Essayez une photo nette, recadrée sur une seule carte."
        ),
    }


def _targeted_images(image: bytes) -> list[tuple[bytes, int]]:
    """Prépare au plus deux recadrages contrastés, seulement en repli OCR."""
    with Image.open(io.BytesIO(image)) as source:
        clean = source.convert("RGB")
        width, height = clean.size
        regions = (
            clean.crop((0, 0, width, max(1, height * 20 // 100))),
            clean.crop((0, height * 85 // 100, width, height)),
        )
        prepared: list[tuple[bytes, int]] = []
        for region, psm in zip(regions, (6, 11), strict=True):
            enhanced = ImageOps.autocontrast(region.convert("L"))
            if enhanced.width < 1600:
                ratio = min(3, max(1, 1600 // max(1, enhanced.width)))
                enhanced = enhanced.resize((enhanced.width * ratio, enhanced.height * ratio))
            output = io.BytesIO()
            enhanced.save(output, format="PNG")
            prepared.append((output.getvalue(), psm))
        return prepared


def _crop_image(image: bytes, selection: tuple[int, int, int, int, int, int, int]) -> bytes:
    """Recadre dans le repère EXIF orienté, puis applique une rotation horaire."""
    x, y, width, height, image_width, image_height, rotation = selection
    with Image.open(io.BytesIO(image)) as source:
        if (source.width, source.height) != (image_width, image_height):
            raise ValueError("Dimensions de la photo incohérentes. Sélectionnez à nouveau la photo.")
        if x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > source.width or y + height > source.height:
            raise ValueError("La sélection doit être non vide et contenue dans la photo.")
        if rotation not in (0, 90, 180, 270):
            raise ValueError("Rotation invalide.")
        cropped = source.crop((x, y, x + width, y + height)).rotate(-rotation, expand=True)
        output = io.BytesIO()
        cropped.save(output, format="PNG")
        return output.getvalue()


def analyze_image(connection: sqlite3.Connection, content: bytes, selection: tuple[int, int, int, int, int, int, int] | None = None) -> dict[str, Any]:
    """Lance un OCR complet puis, si nécessaire, deux lectures ciblées au maximum."""
    if not _OCR_SLOTS.acquire(blocking=False):
        raise RuntimeError("Deux analyses OCR sont déjà en cours. Réessayez dans un instant.")
    try:
        image = _prepare_image(content)
        if selection is not None:
            image = _crop_image(image, selection)
        text = _run_tesseract(image)
        result = extract_suggestions(connection, text)
        recognized = result["recognized"]
        sufficient = result["status"] == "lot" or (
            result["candidates"] and recognized["names"] and recognized["numbers"]
        )
        if sufficient:
            return result
        best_name: str | None = None
        for targeted, psm in _targeted_images(image):
            targeted_text = _run_tesseract(targeted, psm)
            targeted_result = extract_suggestions(connection, targeted_text)
            targeted_recognized = targeted_result["recognized"]
            exact_target = bool(
                targeted_result["candidates"]
                and targeted_result["candidates"][0]["name_match_kind"] == "exact"
                and not targeted_result["candidates"][0]["contradictions"]
            )
            if exact_target and targeted_recognized["names"]:
                # Un nom exact du catalogue sur la bande haute est plus fiable
                # qu'une correspondance partielle dans le texte de l'image entière.
                best_name = targeted_recognized["names"][0]
                result = targeted_result
            if exact_target and targeted_recognized["names"] and targeted_recognized["numbers"]:
                return targeted_result
            if targeted_recognized["numbers"] and best_name:
                combined = extract_suggestions(connection, f"{best_name}\n{targeted_text}")
                if combined["candidates"]:
                    result = combined
                    if combined["recognized"]["names"] and combined["recognized"]["numbers"]:
                        return result
        return result
    finally:
        _OCR_SLOTS.release()


@router.post("/ocr/preview")
def ocr_preview(file: UploadFile = File(...)) -> Response:
    """Retourne la photo orientée de manière éphémère pour choisir une région."""
    try:
        image = _prepare_image(file.file.read(MAX_IMAGE_BYTES + 1))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return Response(image, media_type="image/png", headers={"Cache-Control": "no-store"})


@router.post("/ocr/suggestions")
def ocr_suggestions(
    request: Request, file: UploadFile = File(...), listing_id: int | None = Form(default=None, gt=0),
    title: str = Form(default="", max_length=500),
    crop_x: int | None = Form(default=None), crop_y: int | None = Form(default=None),
    crop_width: int | None = Form(default=None), crop_height: int | None = Form(default=None),
    image_width: int | None = Form(default=None), image_height: int | None = Form(default=None),
    crop_rotation: int | None = Form(default=None),
) -> dict[str, Any]:
    """Analyse une photo transmise explicitement sans écrire de données ni confirmer de carte."""
    with connect(request.app.state.settings.database_path) as connection:
        if listing_id is not None:
            listing = connection.execute(
                "SELECT identification_status, is_lot FROM catalog_items WHERE id = ?", (listing_id,)
            ).fetchone()
            if listing is None:
                raise HTTPException(status_code=404, detail="Annonce introuvable.")
            is_lot = listing[0] == "lot" or bool(listing[1])
        else:
            is_lot = extract_features(title).is_lot if title else False
        if is_lot:
            return {"status": "lot", "recognized": {"names": [], "numbers": []}, "candidates": [], "message": "Cette annonce est un lot ou un produit scellé : aucune carte unitaire n'est proposée."}
        content = file.file.read(MAX_IMAGE_BYTES + 1)
        try:
            parts = (crop_x, crop_y, crop_width, crop_height, image_width, image_height, crop_rotation)
            if any(part is not None for part in parts):
                if any(part is None for part in parts):
                    raise ValueError("Sélection incomplète.")
                return analyze_image(connection, content, parts)  # type: ignore[arg-type]
            return analyze_image(connection, content)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
