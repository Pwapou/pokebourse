"""Lecture Tesseract avec positions (T06.2) : passe bornée, parsing TSV, lignes, reprojection.

La commande cible est `tesseract stdin stdout -l fra+eng --psm <n> tsv`, exécutée
sans shell. Les pipes sont lus de manière bornée : une sortie excessive tue le
processus et est signalée, jamais tronquée silencieusement. Aucun TSV ni texte
brut n'est journalisé ni persisté.
"""

from __future__ import annotations

import csv
import io
from typing import Literal

from app.identification.ocr_geometry import project_quad
from app.identification.ocr_runner import (
    CancellationToken,
    OcrOutputLimitError,
    run_tesseract_tsv as _run_tesseract_tsv,
)
from app.identification.ocr_types import (
    MAX_TESSERACT_PASSES,
    Deadline,
    OcrConfig,
    OcrError,
    OcrLine,
    OcrToken,
    RectifiedCard,
)

# La sélection de langue fra+eng ne détecte PAS la langue de l'exemplaire (T06.4) :
# elle couvre les deux locales installées localement, sans appel externe.
TESSERACT_LANGUAGES = "fra+eng"
DEFAULT_PSM = 11

# Régions relatives de la carte orientée (procédure §6.2, version PASS_CONFIG_VERSION).
REGION_BANDS: dict[str, tuple[float, float]] = {
    "name": (0.0, 0.35),
    "number": (0.70, 1.0),
}


class TesseractUnavailableError(OcrError):
    """Le binaire Tesseract est absent de l'image."""


class TsvTruncatedError(OcrError):
    """Sortie TSV excessive ou invalide : aucune identité ne doit en découler."""


def run_tesseract_tsv(
    image_png: bytes,
    *,
    psm: int = DEFAULT_PSM,
    timeout_seconds: float,
    max_bytes: int,
    token: CancellationToken | None = None,
) -> str:
    """Adapte le contrat historique au superviseur de processus renforcé."""
    try:
        return _run_tesseract_tsv(
            image_png,
            psm=psm,
            deadline=Deadline(timeout_seconds),
            token=token,
            max_output_bytes=max_bytes,
        )
    except OcrOutputLimitError as error:
        raise TsvTruncatedError("Sortie OCR excessive : analyse refusée.") from error


def parse_tsv(payload: str, *, pass_id: str, raster_width: int, raster_height: int,
              config: OcrConfig | None = None) -> tuple[OcrToken, ...]:
    """Parse les mots (level 5) : boîtes invalides rejetées, scores négatifs inconnus.

    Le plafond de mots est strict : le dépasser lève TsvTruncatedError afin qu'aucun
    candidat ne soit produit depuis une sortie partielle.
    """
    config = config or OcrConfig()
    tokens: list[OcrToken] = []
    reader = csv.DictReader(io.StringIO(payload), delimiter="\t")
    token_index = 0
    for row in reader:
        if row.get("level") != "5":
            continue
        text = (row.get("text") or "").strip()
        if not text:
            continue
        try:
            left, top = int(row["left"]), int(row["top"])
            width, height = int(row["width"]), int(row["height"])
        except (KeyError, TypeError, ValueError):
            continue  # boîte invalide : rejetée, la passe continue
        if left < 0 or top < 0 or width <= 0 or height <= 0:
            continue
        if len(tokens) >= config.max_words_per_analysis:
            raise TsvTruncatedError("Sortie OCR trop riche : plafond de mots dépassé.")
        confidence: float | None
        try:
            raw_confidence = float(row.get("conf") or -1)
            confidence = raw_confidence if raw_confidence >= 0 else None
        except ValueError:
            confidence = None
        norm_box = (left / raster_width, top / raster_height,
                    (left + width) / raster_width, (top + height) / raster_height)
        tokens.append(OcrToken(
            pass_id=pass_id, token_index=token_index, text=text[:100],
            box=(left, top, width, height), norm_box=norm_box, photo_quad=None,
            group=(_group_value(row, "page_num", 1), _group_value(row, "block_num", 0),
                   _group_value(row, "par_num", 0), _group_value(row, "line_num", 0)),
            confidence=confidence,
        ))
        token_index += 1
    return tuple(tokens)


def _group_value(row: dict[str, str | None], key: str, default: int) -> int:
    """Numéro de groupe tolérant aux valeurs absentes ou corrompues."""
    try:
        return int(row.get(key) or default)
    except (TypeError, ValueError):
        return default


def attach_photo_positions(tokens: tuple[OcrToken, ...], card: RectifiedCard) -> tuple[OcrToken, ...]:
    """Reprojette chaque boîte vers la photo orientée (quadrilatère reprojeté)."""
    positioned = []
    for token in tokens:
        quad = project_quad(token.box, card.card_to_photo)
        positioned.append(token.__class__(
            pass_id=token.pass_id, token_index=token.token_index, text=token.text,
            box=token.box, norm_box=token.norm_box, photo_quad=quad,
            group=token.group, confidence=token.confidence,
        ))
    return tuple(positioned)


def reconstruct_lines(tokens: tuple[OcrToken, ...], *, pass_id: str) -> tuple[OcrLine, ...]:
    """Reconstitue les lignes par identifiants complets page/bloc/paragraphe/ligne.

    Deux blocs distincts portant le même numéro de ligne ne sont jamais joints.
    """
    grouped: dict[tuple[int, int, int, int], list[OcrToken]] = {}
    for token in tokens:
        grouped.setdefault(token.group, []).append(token)
    lines: list[OcrLine] = []
    for group in sorted(grouped):
        members = sorted(grouped[group], key=lambda token: (token.box[0], token.box[1]))
        left = min(token.box[0] for token in members)
        top = min(token.box[1] for token in members)
        right = max(token.box[0] + token.box[2] for token in members)
        bottom = max(token.box[1] + token.box[3] for token in members)
        lines.append(OcrLine(
            pass_id=pass_id, group=group, text=" ".join(token.text for token in members),
            box=(left, top, right - left, bottom - top),
            token_indexes=tuple(token.token_index for token in members),
        ))
    return tuple(lines)


def band_raster(card: RectifiedCard, role: Literal["name", "number"], config: OcrConfig | None = None) -> bytes:
    """Extrait la bande haute (nom) ou basse (numéro) de la carte redressée."""
    import io

    from PIL import Image, ImageOps

    config = config or OcrConfig()
    top_fraction, bottom_fraction = REGION_BANDS[role]
    with Image.open(io.BytesIO(card.pixels)) as image:
        source = image.convert("RGB")
    top = int(source.height * top_fraction)
    bottom = max(top + 1, int(source.height * bottom_fraction))
    band = source.crop((0, top, source.width, bottom))
    if band.width * band.height > config.max_derived_pixels:
        scale = (config.max_derived_pixels / (band.width * band.height)) ** 0.5
        band = band.resize((max(1, int(band.width * scale)), max(1, int(band.height * scale))))
    output = io.BytesIO()
    band.save(output, format="PNG")
    return output.getvalue()


def enhance_fallback(raster_png: bytes, config: OcrConfig | None = None) -> bytes:
    """Variante de secours : contraste puis agrandissement borné (facteur au plus 3)."""
    import io

    from PIL import Image, ImageOps

    config = config or OcrConfig()
    with Image.open(io.BytesIO(raster_png)) as image:
        source = image.convert("L")
    enhanced = ImageOps.autocontrast(source)
    if enhanced.width < 1600:
        ratio = min(config.fallback_enhance_factor, max(1, 1600 // max(1, enhanced.width)))
        target_width = enhanced.width * ratio
        target_height = enhanced.height * ratio
        if target_width * target_height <= config.max_derived_pixels:
            enhanced = enhanced.resize((target_width, target_height))
    output = io.BytesIO()
    enhanced.save(output, format="PNG")
    return output.getvalue()


PASS_BUDGET_TOTAL = MAX_TESSERACT_PASSES
