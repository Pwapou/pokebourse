from dataclasses import dataclass, field
from typing import Literal

from app.tcgdex.models import ReferenceCardRecord

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


@dataclass(frozen=True)
class CandidateMatch:
    card_id: int
    tcgdex_id: str
    name: str
    set_name: str
    local_id: str
    confidence: int
    match_reason: str


@dataclass(frozen=True)
class IdentificationResult:
    status: IdentificationStatus
    confidence: int
    reason: str
    features: ExtractedFeatures
    matched_card: ReferenceCardRecord | None = None
    candidates: list[CandidateMatch] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    uncertain_fields: list[str] = field(default_factory=list)
