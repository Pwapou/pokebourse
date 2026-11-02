from dataclasses import dataclass, field
from typing import Literal

from app.tcgdex.models import ReferenceCardRecord
from app.identification.evidence import OBSERVATION_VERSION, PIPELINE_VERSION, Observation

IdentificationStatus = Literal["identified", "ambiguous", "unidentified", "lot"]

IDENTIFICATION_STATUS_LABELS: dict[IdentificationStatus, str] = {
    "identified": "Identifiée",
    "ambiguous": "À vérifier",
    "unidentified": "Non identifiée",
    "lot": "Lot / Coffret",
}


@dataclass(frozen=True)
class ExtractedFeatures:
    name: str | None = None
    card_number: str | None = None
    local_id: str | None = None
    set_card_count: str | None = None
    set_name: str | None = None
    language: str | None = None
    variant: str | None = None
    condition: str | None = None
    grading_company: str | None = None
    grade: str | None = None
    is_lot: bool = False
    lot_reason: str | None = None
    selection_reason: str | None = None
    languages: tuple[str, ...] = ()
    condition_raw: str | None = None


@dataclass(frozen=True)
class CandidateMatch:
    card_id: int
    tcgdex_id: str
    name: str
    set_name: str
    local_id: str
    confidence: int
    match_reason: str
    name_match_kind: Literal["exact", "partial", "fuzzy", "absent"] = "absent"
    contradictions: tuple[str, ...] = ()
    score_criteria: tuple[str, ...] = ()
    confidence_level: Literal["élevé", "moyen", "faible"] = "faible"


@dataclass(frozen=True)
class IdentificationResult:
    status: IdentificationStatus
    confidence: int | None
    reason: str
    features: ExtractedFeatures
    matched_card: ReferenceCardRecord | None = None
    candidates: list[CandidateMatch] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    uncertain_fields: list[str] = field(default_factory=list)
    diagnostic_candidates: list[CandidateMatch] = field(default_factory=list)
    observations: tuple[Observation, ...] = ()
    evidence_conflicts: tuple[str, ...] = ()
    reason_code: str = "insufficient_evidence"
    decision_source: str = "automatic"
    pipeline_version: str = PIPELINE_VERSION
    normalization_version: str = OBSERVATION_VERSION
