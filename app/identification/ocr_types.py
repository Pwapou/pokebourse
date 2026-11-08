"""Contrats internes du moteur OCR spatial (T06/T07) : types, versions et budgets.

Ces types sont volontairement indépendants de HTTP et de SQLite : l'orchestrateur
reçoit une configuration et une horloge, les fonctions géométriques et de parsing
restent pures. Les nombres réels servent uniquement à la géométrie ; aucun calcul
monétaire n'a lieu ici.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, field_validator

OCR_SCHEMA_VERSION = "ocr-spatial-v1"
GEOMETRY_VERSION = "ocr-geometry-v1"
PASS_CONFIG_VERSION = "ocr-passes-v1"
EXTRACTION_VERSION = "ocr-extraction-v1"
HYPOTHESES_VERSION = "ocr-hypotheses-v1"
LANGUAGE_CLUES_VERSION = "ocr-language-clues-v1"
PREPARED_REF_METHOD = "prepared-sha256-v1"

Point = tuple[float, float]
Matrix = tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]

RegionKind = Literal["card", "label", "unknown"]
RegionMethod = Literal["manual", "auto", "full_image"]
PassRole = Literal["full", "name", "number"]
ReadingRole = Literal["name", "number", "language", "unknown"]
HypothesisState = Literal["pending", "catalog_match", "no_catalog_match", "not_searchable"]

MAX_TESSERACT_PASSES = 6
GLOBAL_DEADLINE_SECONDS = 20.0


class OcrError(RuntimeError):
    """Échec d'une étape du traitement OCR, avec motif utile pour le repli."""


class OcrDeadlineExceeded(OcrError):
    """L'échéance globale est atteinte : aucun nouvel essai n'est autorisé."""


class GeometryError(ValueError):
    """Cadrage, quadrilatère ou transformation géométrique invalide."""


class AutoLocateUnavailable(OcrError):
    """Le backend automatique (OpenCV headless) n'est pas installé."""


@dataclass(frozen=True)
class OcrConfig:
    """Budgets et réglages versionnés ; valeurs initiales expérimentales de la procédure T06/T07."""

    max_image_bytes: int = 8 * 1024 * 1024
    max_input_pixels: int = 12_000_000
    max_derived_pixels: int = 12_000_000
    max_card_long_side: int = 2000
    max_tesseract_passes: int = MAX_TESSERACT_PASSES
    global_deadline_seconds: float = GLOBAL_DEADLINE_SECONDS
    max_tsv_bytes_per_pass: int = 2_000_000
    max_words_per_analysis: int = 4096
    max_number_readings: int = 24
    max_variants_per_reading: int = 4  # lecture originale comprise
    max_search_values: int = 12
    max_name_number_combos: int = 36
    max_suggestions: int = 20
    max_regions: int = 4
    max_language_proposals: int = 3
    max_clue_fragments: int = 6
    auto_detect_long_side: int = 1600
    fallback_enhance_factor: int = 3

    def versions(self) -> dict[str, str]:
        """Expose les versions associées à chaque étape pour le manifeste de benchmark."""
        return {
            "schema": OCR_SCHEMA_VERSION,
            "geometry": GEOMETRY_VERSION,
            "passes": PASS_CONFIG_VERSION,
            "extraction": EXTRACTION_VERSION,
            "hypotheses": HYPOTHESES_VERSION,
            "language_clues": LANGUAGE_CLUES_VERSION,
        }


class Deadline:
    """Échéance monotone globale ; chaque sous-opération reçoit le temps restant."""

    def __init__(self, budget_seconds: float, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._start = clock()
        self._budget = float(budget_seconds)

    def elapsed(self) -> float:
        return self._clock() - self._start

    def remaining(self) -> float:
        return self._budget - self.elapsed()

    def check(self) -> None:
        """Lève OcrDeadlineExceeded lorsque plus aucun essai ne doit démarrer."""
        if self.remaining() <= 0:
            raise OcrDeadlineExceeded("Délai global d'analyse dépassé.")

    def pass_timeout(self, cap_seconds: float) -> float:
        """Borne le délai d'une passe par le temps restant, sans jamais l'étendre."""
        return max(0.1, min(cap_seconds, self.remaining()))


@dataclass(frozen=True)
class PreparedImage:
    """Pixels orientés EXIF (une seule fois), sans métadonnées, et leur empreinte."""

    image_ref: str
    width: int
    height: int
    exif_rotation_degrees: int
    pixels: bytes  # PNG RGB éphémère, jamais persisté ici


@dataclass(frozen=True)
class CropSelection:
    """Recadrage manuel : rectangle ou quadrilatère exclusifs, rotation en degrés."""

    rect: tuple[float, float, float, float] | None = None
    quad: tuple[Point, Point, Point, Point] | None = None
    rotation: int = 0
    contract_version: str = GEOMETRY_VERSION


@dataclass(frozen=True)
class CardRegion:
    """Objet/région dans la photo orientée ; les coordonnées sont des pixels photo."""

    region_id: str
    object_id: str
    kind: RegionKind
    quad: tuple[Point, Point, Point, Point]
    method: RegionMethod
    quality: str = "ok"
    motifs: tuple[str, ...] = ()


@dataclass(frozen=True)
class RectifiedCard:
    """Vue rectangulaire de la région et les matrices permettant le retour à la photo."""

    region: CardRegion
    width: int
    height: int
    card_to_photo: Matrix
    photo_to_card: Matrix
    extra_rotation: int
    pixels: bytes  # PNG RGB éphémère de la vue rectangulaire


@dataclass(frozen=True)
class OcrToken:
    """Mot lu dans une passe ; les boîtes sont exprimées dans le repère de la passe."""

    pass_id: str
    token_index: int
    text: str
    box: tuple[int, int, int, int]
    norm_box: tuple[float, float, float, float]
    photo_quad: tuple[Point, Point, Point, Point] | None
    group: tuple[int, int, int, int]  # page, bloc, paragraphe, ligne
    confidence: float | None


@dataclass(frozen=True)
class OcrLine:
    """Ligne reconstituée dans un même bloc d'une passe, jamais entre blocs."""

    pass_id: str
    group: tuple[int, int, int, int]
    text: str
    box: tuple[int, int, int, int]
    token_indexes: tuple[int, ...]


@dataclass(frozen=True)
class OcrReading:
    """Lecture assemblée (nom ou numéro) : texte brut conservé, jamais remplacé."""

    reading_id: str
    object_id: str
    role: ReadingRole
    raw_text: str
    token_refs: tuple[tuple[str, int], ...]
    pass_roles: tuple[PassRole, ...]
    operations: tuple[str, ...] = ()
    confidence: float | None = None
    version: str = EXTRACTION_VERSION
    photo_box: tuple[float, float, float, float] | None = None  # rectangle englobant en pixels photo


@dataclass(frozen=True)
class NumberComponents:
    """Structure d'un numéro : préfixe, numérateur, dénominateur, suffixe optionnels."""

    kind: Literal["fraction", "promo"]
    raw: str
    prefix: str | None
    numerator: str
    denominator: str | None
    suffix: str | None


@dataclass(frozen=True)
class NumberHypothesis:
    """Variante d'une même lecture : un groupe alternatif « ceci ou cela »."""

    hypothesis_id: str
    alternative_group_id: str  # == reading_id : les variantes d'un groupe s'excluent
    reading_id: str
    value: str
    components: NumberComponents
    operations: tuple[str, ...]
    rank: int = 0
    origins: tuple[str, ...] = ()
    search_state: HypothesisState = "pending"


@dataclass(frozen=True)
class LanguageHypothesis:
    """Suggestion de langue de l'exemplaire, jamais une confirmation ; abstention explicite."""

    language: str | None
    clue_fragments: tuple[str, ...]
    method_version: str = LANGUAGE_CLUES_VERSION
    reason: str | None = None
    conflict: str | None = None


@dataclass(frozen=True)
class RankedCandidate:
    """Candidat de catalogue adossé aux hypothèses qui le justifient."""

    card_id: int
    tcgdex_id: str
    name: str
    set_name: str
    local_id: str
    confidence: int
    name_match_kind: str
    contradictions: tuple[str, ...]
    hypothesis_ids: tuple[str, ...]
    literal_support: bool
    alternatives: tuple[str, ...]  # autres valeurs du même groupe alternatif


@dataclass(frozen=True)
class HypothesisSearch:
    """Résultat borné de la vérification des hypothèses dans le catalogue local."""

    suggestions: tuple[RankedCandidate, ...]
    diagnostics: tuple[str, ...]
    combos_used: int
    values_examined: int
    truncated: bool = False


@dataclass(frozen=True)
class OcrAnalysis:
    """Résultat complet d'une analyse spatiale : aucune autorité humaine, aucune écriture."""

    schema_version: str
    config_versions: dict[str, str]
    image_ref: str
    width: int
    height: int
    regions: tuple[CardRegion, ...]
    readings: tuple[OcrReading, ...]
    number_hypotheses: tuple[NumberHypothesis, ...]
    language_hypotheses: tuple[LanguageHypothesis, ...]
    diagnostics: tuple[str, ...]
    timings: dict[str, float] = field(default_factory=dict)
    truncated: tuple[str, ...] = ()


def is_finite_point(point: Point) -> bool:
    """Une coordonnée géométrique doit être finie ; NaN et infinis sont rejetés."""
    return math.isfinite(point[0]) and math.isfinite(point[1])


class SpatialSelectionInput(BaseModel):
    """Validation stricte à la frontière HTTP ; aucune matrice fournie par le client."""

    model_config = ConfigDict(extra="forbid", strict=True)

    crop: tuple[float, float, float, float] | None = None
    quad: list[tuple[float, float]] | None = None
    rotation: int = 0
    frame_width: int
    frame_height: int

    @field_validator("crop", "quad", mode="before")
    @classmethod
    def json_tuple(cls, value: object) -> object:
        """Accepte les listes JSON tout en gardant des nombres stricts."""
        if isinstance(value, list):
            return tuple(tuple(item) if isinstance(item, list) else item for item in value)
        return value

    def to_selection(self) -> CropSelection:
        """Produit la sélection interne ; la validation métier reste côté géométrie."""
        quad = tuple(self.quad) if self.quad is not None else None
        return CropSelection(rect=self.crop, quad=quad, rotation=self.rotation)

    def finite(self) -> bool:
        """Refuse NaN/inf, que Pydantic laisse passer pour les flottants."""
        values: list[float] = []
        if self.crop is not None:
            values.extend(self.crop)
        if self.quad is not None:
            for point in self.quad:
                values.extend(point)
        return all(math.isfinite(value) for value in values)


def analysis_to_transport(analysis: OcrAnalysis) -> dict[str, Any]:
    """Sérialise bornée pour l'enveloppe `ocr_evidence` : pas de TSV ni de texte brut entier."""
    return {
        "version": analysis.schema_version,
        "image_ref": analysis.image_ref,
        "frame": {"width": analysis.width, "height": analysis.height},
        "config_versions": analysis.config_versions,
        "regions": [
            {
                "region_id": region.region_id,
                "object_id": region.object_id,
                "kind": region.kind,
                "method": region.method,
                "quality": region.quality,
                "motifs": list(region.motifs),
                "quad": [[round(x, 2), round(y, 2)] for x, y in region.quad],
            }
            for region in analysis.regions
        ],
        "readings": [
            {
                "reading_id": reading.reading_id,
                "object_id": reading.object_id,
                "role": reading.role,
                "raw_text": reading.raw_text[:80],
                "operations": list(reading.operations),
                "confidence": reading.confidence,
                "version": reading.version,
            }
            for reading in analysis.readings
        ],
        "number_hypotheses": [
            {
                "hypothesis_id": hypothesis.hypothesis_id,
                "alternative_group_id": hypothesis.alternative_group_id,
                "value": hypothesis.value,
                "operations": list(hypothesis.operations),
                "rank": hypothesis.rank,
                "origins": list(hypothesis.origins),
                "search_state": hypothesis.search_state,
            }
            for hypothesis in analysis.number_hypotheses
        ],
        "language_hypotheses": [
            {
                "language": hypothesis.language,
                "clue_fragments": list(hypothesis.clue_fragments),
                "method_version": hypothesis.method_version,
                "reason": hypothesis.reason,
                "conflict": hypothesis.conflict,
            }
            for hypothesis in analysis.language_hypotheses
        ],
        "diagnostics": list(analysis.diagnostics),
        "timings": dict(analysis.timings),
        "truncated": list(analysis.truncated),
    }
