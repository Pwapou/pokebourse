"""Orchestration du moteur OCR spatial (T06/T07) : budget global, passes, enveloppe.

Respecte le workflow W03–W04 : préparer la photo, redresser la région, lire avec
positions, produire lectures/hypothèses/indices de langue. Aucune écriture SQLite,
aucun appel réseau, aucune identité effective : la décision revient au matcher
commun et à la décision commune. Le budget global de 20 s couvre décodage,
géométrie, OCR et recherche ; Tesseract s'exécute dans un sous-processus récolté.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Literal

from app.identification.ocr_geometry import (
    auto_detect_regions,
    full_image_region,
    manual_region,
    prepare_image,
    rectify_region,
)
from app.identification.ocr_language import suggest_language
from app.identification.ocr_numbers import (
    extract_name_readings,
    extract_number_readings,
    generate_number_hypotheses,
    search_hypotheses,
)
from app.identification.ocr_text import (
    TsvTruncatedError,
    attach_photo_positions,
    band_raster,
    enhance_fallback,
    parse_tsv,
    reconstruct_lines,
    run_tesseract_tsv,
)
from app.identification.ocr_types import (
    OCR_SCHEMA_VERSION,
    CropSelection,
    Deadline,
    HypothesisSearch,
    OcrAnalysis,
    OcrConfig,
    OcrError,
    OcrLine,
    OcrReading,
    OcrToken,
    RectifiedCard,
)

Localization = Literal["manual", "auto", "full"]


def _resolve_regions(prepared: object, localization: Localization,
                     selection: CropSelection | None, config: OcrConfig) -> tuple[tuple, tuple[str, ...]]:
    """Choisit la/les région(s) analysées ; le repli est explicite, jamais un succès."""
    diagnostics: list[str] = []
    if localization == "full" or (localization == "manual" and selection is None):
        if localization == "manual":
            diagnostics.append("manual_without_selection: photo entière analysée sans cadrage.")
        return (full_image_region(prepared),), tuple(diagnostics)  # type: ignore[arg-type]
    if localization == "manual":
        return (manual_region(prepared, selection),), tuple(diagnostics)  # type: ignore[arg-type]
    regions, auto_diagnostics = auto_detect_regions(prepared, config)  # type: ignore[arg-type]
    diagnostics.extend(auto_diagnostics)
    if not regions:
        diagnostics.append("auto_fallback_full_image: localisation automatique impossible ; photo entière analysée.")
        regions = (full_image_region(prepared),)  # type: ignore[arg-type]
    return tuple(regions[: config.max_regions]), tuple(diagnostics)


def analyze_image_spatial(content: bytes, *, selection: CropSelection | None = None,
                          localization: Localization = "manual", rotation: int = 0,
                          catalog_names: tuple[str, ...] | None = None,
                          config: OcrConfig | None = None,
                          clock: Callable[[], float] = time.monotonic) -> OcrAnalysis:
    """Analyse une image dans le budget global : lectures, hypothèses, indices de langue.

    Une échéance atteinte avec des lectures déjà valides produit un résultat partiel
    diagnostiqué ; avant toute lecture exploitable, l'erreur est remontée (503 selon
    le contrat HTTP existant). Le chemin historique (`ocr.analyze_image`) reste la
    baseline : cette fonction est la stratégie `spatial` explicite et versionnée.
    """
    config = config or OcrConfig()
    deadline = Deadline(config.global_deadline_seconds, clock)
    timings: dict[str, float] = {}
    diagnostics: list[str] = []
    truncated: list[str] = []

    started = clock()
    prepared = prepare_image(content, config)
    timings["prepare_seconds"] = round(clock() - started, 4)
    deadline.check()

    started = clock()
    regions, region_diagnostics = _resolve_regions(prepared, localization, selection, config)
    diagnostics.extend(region_diagnostics)
    # Le recadrage manuel porte sa rotation ; l'automatique la déduit plus tard (passe rot180).
    effective_rotation = selection.rotation if (localization == "manual" and selection is not None) else rotation
    cards: list[RectifiedCard] = []
    for region in regions:
        deadline.check()
        cards.append(rectify_region(prepared, region, config, rotation=effective_rotation))
    timings["geometry_seconds"] = round(clock() - started, 4)

    passes_used = 0
    readings: list[OcrReading] = []
    language_fragments: list[str] = []
    passes_started = clock()

    def run_pass(card: RectifiedCard, role: str, psm: int, raster: bytes, suffix: str) -> tuple[tuple[OcrToken, ...], tuple[OcrLine, ...]]:
        nonlocal passes_used
        if passes_used >= config.max_tesseract_passes:
            raise TsvTruncatedError("Budget de passes Tesseract épuisé.")
        deadline.check()
        pass_id = f"{card.region.object_id}-{role}{suffix}"
        # Dimensions du raster décodé, sans le réécrire : lecture via PNG header.
        raster_width, raster_height = _png_size(raster)
        tsv = run_tesseract_tsv(
            raster, psm=psm, timeout_seconds=deadline.pass_timeout(config.global_deadline_seconds),
            max_bytes=config.max_tsv_bytes_per_pass,
        )
        passes_used += 1
        tokens = parse_tsv(tsv, pass_id=pass_id, raster_width=raster_width,
                           raster_height=raster_height, config=config)
        tokens = attach_photo_positions(tokens, card)
        return tokens, reconstruct_lines(tokens, pass_id=pass_id)

    for card in cards:
        object_id = card.region.object_id
        try:
            tokens, lines = run_pass(card, "full", 11, card.pixels, "")
        except (OcrError, TsvTruncatedError):
            raise  # première passe : aucune lecture exploitable, erreur remontée
        number_readings = list(extract_number_readings(
            tokens, lines, object_id=object_id, pass_role="full", config=config))
        name_readings = list(extract_name_readings(
            lines, object_id=object_id, pass_role="full", catalog_names=catalog_names, tokens=tokens))
        if card.region.kind != "label":
            language_fragments.extend(line.text[:100] for line in lines[:20])

        # Passes ciblées (§6.2) : uniquement pour compléter/lever une ambiguïté, dans le budget.
        try:
            if not number_readings:
                band = band_raster(card, "number", config)
                band_tokens, band_lines = run_pass(card, "number", 11, band, "-band")
                number_readings.extend(extract_number_readings(
                    band_tokens, band_lines, object_id=object_id, pass_role="number", config=config))
                if not number_readings:
                    isolated_raster = _isolated_line_raster(band, band_lines)
                    if isolated_raster is not None:
                        line_tokens, line_lines = run_pass(card, "number", 7, isolated_raster, "-line")
                        number_readings.extend(extract_number_readings(
                            line_tokens, line_lines, object_id=object_id, pass_role="number",
                            config=config))
                if not number_readings:
                    enhanced_tokens, enhanced_lines = run_pass(
                        card, "number", 11, enhance_fallback(band, config), "-enhanced")
                    number_readings.extend(extract_number_readings(
                        enhanced_tokens, enhanced_lines, object_id=object_id, pass_role="number",
                        config=config))
            if not name_readings:
                name_tokens, name_lines = run_pass(card, "name", 6, band_raster(card, "name", config), "-band")
                name_readings.extend(extract_name_readings(
                    name_tokens, name_lines, object_id=object_id, pass_role="name",
                    catalog_names=catalog_names, tokens=name_tokens))
            if (not number_readings and not name_readings and card.region.method == "auto"
                    and card.extra_rotation == 0):
                # Orientation incertaine : comparer les deux orientations portrait opposées.
                flipped = rectify_region(prepared, card.region, config, rotation=180)
                flip_tokens, flip_lines = run_pass(flipped, "full", 11, flipped.pixels, "-rot180")
                number_readings.extend(extract_number_readings(
                    flip_tokens, flip_lines, object_id=object_id, pass_role="full", config=config))
                name_readings.extend(extract_name_readings(
                    flip_lines, object_id=object_id, pass_role="full",
                    catalog_names=catalog_names, tokens=flip_tokens))
        except (OcrError, TsvTruncatedError) as error:
            if number_readings or name_readings:
                diagnostics.append(f"deadline_partial: passe de secours interrompue ({type(error).__name__}).")
                truncated.append("passes")
            else:
                raise
        readings.extend(number_readings)
        readings.extend(name_readings)

    timings["ocr_seconds"] = round(clock() - passes_started, 4)
    # Déduplication des lectures identiques (même objet, même rôle, même brut).
    unique: dict[tuple[str, str, str], OcrReading] = {}
    for reading in readings:
        unique.setdefault((reading.object_id, reading.role, reading.raw_text), reading)
    readings = list(unique.values())

    started = clock()
    hypotheses, hypotheses_truncated = generate_number_hypotheses(readings, config)
    if hypotheses_truncated:
        truncated.append("search_values")
        diagnostics.append("hypotheses_truncated: plafond de valeurs de recherche atteint.")
    language = suggest_language(language_fragments, config=config)
    timings["extraction_seconds"] = round(clock() - started, 4)

    return OcrAnalysis(
        schema_version=OCR_SCHEMA_VERSION,
        config_versions=config.versions(),
        image_ref=prepared.image_ref,
        width=prepared.width,
        height=prepared.height,
        regions=tuple(card.region for card in cards),
        readings=tuple(readings),
        number_hypotheses=hypotheses,
        language_hypotheses=(language,) if language.language or language.reason else (),
        diagnostics=tuple(diagnostics),
        timings=timings,
        truncated=tuple(truncated),
    )


def _png_size(png: bytes) -> tuple[int, int]:
    """Lit l'en-tête PNG (bytes 16–24) sans réécrire le raster."""
    if len(png) < 24 or png[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Raster PNG interne invalide.")
    return int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")


def _isolated_line_raster(band_png: bytes, lines: tuple[OcrLine, ...]) -> bytes | None:
    """Raster d'une ligne isolée (PSM 7 uniquement dans ce cas), sans traitement destructeur."""
    if len(lines) != 1:
        return None
    import io

    from PIL import Image
    line = lines[0]
    with Image.open(io.BytesIO(band_png)) as image:
        source = image.convert("RGB")
    left = max(0, line.box[0] - 4)
    top = max(0, line.box[1] - 2)
    right = min(source.width, line.box[0] + line.box[2] + 4)
    bottom = min(source.height, line.box[1] + line.box[3] + 2)
    if right - left < 2 or bottom - top < 2:
        return None
    output = io.BytesIO()
    source.crop((left, top, right, bottom)).save(output, format="PNG")
    return output.getvalue()


def verify_hypotheses(matcher: object, analysis: OcrAnalysis, *,
                      config: OcrConfig | None = None,
                      deadline: Deadline | None = None) -> HypothesisSearch:
    """Vérifie les hypothèses dans le catalogue local via la récupération commune.

    Les noms départagent depuis le MÊME objet que la lecture du numéro ; la recherche
    utilise une connexion de lecture courte hors de toute transaction (règle T09) :
    l'appelant fournit un matcher déjà construit et ne garde aucun BEGIN ouvert.
    """
    config = config or OcrConfig()
    names_by_object: dict[str, tuple[str, ...]] = {}
    for reading in analysis.readings:
        if reading.role == "name":
            names_by_object.setdefault(reading.object_id, ())
            names_by_object[reading.object_id] = (
                *names_by_object[reading.object_id], reading.raw_text
            )
    names_by_reading = {
        reading.reading_id: names_by_object.get(reading.object_id, ())
        for reading in analysis.readings
        if reading.role == "number"
    }
    return search_hypotheses(
        matcher, analysis.number_hypotheses, names_by_reading,  # type: ignore[arg-type]
        config=config, deadline=deadline,
    )


def legacy_recognized(analysis: OcrAnalysis) -> dict[str, list[str]]:
    """Valeurs du contrat historique `recognized` : lectures ORIGINALES uniquement.

    Jamais de réparation projetée comme si elle avait été lue ; une valeur par
    groupe alternatif, lectures distinctes conservées concurrentes (≤ 6 de chaque).
    """
    names: list[str] = []
    numbers: list[str] = []
    for reading in analysis.readings:
        target = names if reading.role == "name" else numbers if reading.role == "number" else None
        if target is None or len(target) >= 6 or reading.raw_text in target:
            continue
        target.append(reading.raw_text)
    return {"names": names, "numbers": numbers}


def build_ocr_evidence(analysis: OcrAnalysis, search: HypothesisSearch | None = None) -> dict:
    """Enveloppe versionnée et bornée `ocr_evidence` pour l'intégration T03/T08.

    Les détails géométriques et les groupes d'alternatives vivent ici, pas dans une
    liste plate d'assertions : les variantes d'une même lecture ne deviennent pas
    des observations simultanées soumises aux conflits. Aucun `verified`, aucune
    autorité humaine fournie par le client.
    """
    from app.identification.ocr_types import analysis_to_transport

    envelope = analysis_to_transport(analysis)
    if search is not None:
        envelope["suggestions"] = [
            {
                "tcgdex_id": candidate.tcgdex_id,
                "name": candidate.name,
                "set_name": candidate.set_name,
                "local_id": candidate.local_id,
                "confidence": candidate.confidence,
                "name_match_kind": candidate.name_match_kind,
                "contradictions": list(candidate.contradictions),
                "hypothesis_ids": list(candidate.hypothesis_ids),
                "literal_support": candidate.literal_support,
                "alternatives": list(candidate.alternatives),
            }
            for candidate in search.suggestions
        ]
        envelope["search"] = {
            "combos_used": search.combos_used,
            "values_examined": search.values_examined,
            "truncated": search.truncated,
            "diagnostics": list(search.diagnostics),
        }
    return envelope
