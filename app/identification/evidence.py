"""Observations locales bornées : une provenance cliente n'est jamais une validation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.identification.normalization import normalize_text

PIPELINE_VERSION = "evidence-rules-v1"
OBSERVATION_VERSION = "observations-v1"
IDENTITY_FIELDS = ("name", "card_number", "set_name", "language", "variant", "condition", "edition", "grading_company", "grade")
EvidenceField = Literal["title", "description", "name", "card_number", "set_name", "language", "variant", "condition", "edition", "grading_company", "grade"]
EvidenceSource = Literal["title", "description", "structured", "manual", "prefill", "ocr"]


class ObservationInput(BaseModel):
    """Ajout JSON/JSONL compatible, sans statut « vérifié » ni rôle humain libre."""

    model_config = ConfigDict(extra="forbid", strict=True)
    field: EvidenceField
    value: str = Field(min_length=1, max_length=20000)
    source: EvidenceSource = "structured"
    excerpt: str | None = Field(default=None, max_length=10000)
    image_ref: str | None = Field(default=None, max_length=200)
    region: tuple[int, int, int, int] | None = None
    extractor_version: str = Field(default=OBSERVATION_VERSION, min_length=1, max_length=80)

    @field_validator("region", mode="before")
    @classmethod
    def json_region(cls, value: object) -> object:
        """Accepte les coordonnées JSON tout en gardant les entiers stricts."""
        return tuple(value) if isinstance(value, list) else value


@dataclass(frozen=True)
class Observation:
    """Valeur brute et normalisée ; la qualité est déterminée par le backend."""

    field: str
    value: str
    source: str
    normalized_value: str
    excerpt: str | None
    image_ref: str | None
    region: tuple[int, int, int, int] | None
    extractor_version: str
    quality: str
    normalization_version: str = OBSERVATION_VERSION

    def transport(self) -> dict[str, Any]:
        """Exporte seulement les champs admissibles en entrée, jamais une autorité."""
        return {key: value for key, value in asdict(self).items()
                if key not in {"normalized_value", "quality", "normalization_version"} and value is not None}


@dataclass(frozen=True)
class ListingEvidence:
    """Bundle transitoire, réutilisable par les lectures et les écritures."""

    title: str
    description: str | None
    observations: tuple[Observation, ...]
    ocr_unavailable: bool = False

    def transport(self) -> list[dict[str, Any]]:
        """Sérialise les observations sans les textes OCR bruts ni les images."""
        return [observation.transport() for observation in self.observations]


def validate_observations(value: object) -> list[ObservationInput]:
    """Valide intégralement les ajouts optionnels avant toute écriture."""
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 64:
        raise ValueError("Au plus 64 observations d'identité sont autorisées.")
    result = [item if isinstance(item, ObservationInput) else ObservationInput.model_validate(item) for item in value]
    for item in result:
        if item.region is not None and (any(coordinate < 0 or coordinate > 1_000_000 for coordinate in item.region)
                                        or item.region[2] <= item.region[0] or item.region[3] <= item.region[1]):
            raise ValueError("Région de preuve invalide.")
        if item.source == "ocr" and item.field not in {"name", "card_number"}:
            raise ValueError("L'OCR transmet des indices de nom/numéro, jamais un texte d'annonce substitué.")
        if item.source == "ocr" and len(item.value) > (200 if item.field == "name" else 50):
            raise ValueError("Indice OCR trop long pour un nom ou un numéro.")
    return result


def build_evidence(title: str, description: str | None = None, *, attributes: Mapping[str, Any] | None = None) -> ListingEvidence:
    """Fusionne les observations sans perdre les origines concurrentes."""
    attributes = attributes or {}
    supplied = validate_observations(attributes.get("identity_evidence"))
    # Une observation explicite décrit la valeur du champ, y compris lorsqu'elle
    # provient d'un préremplissage. Ne pas la recréer comme preuve structurée.
    covered = {(item.field, item.value) for item in supplied}
    inputs = list(supplied)
    for field, value, source in (("title", title, "title"), ("description", description, "description"),
                                 *((field, attributes.get(field), "structured") for field in IDENTITY_FIELDS)):
        if isinstance(value, str) and value.strip() and (field, value) not in covered:
            inputs.append(ObservationInput(field=field, value=value, source=source))
    for field, key in (("name", "ocr_names"), ("card_number", "ocr_numbers")):
        values = attributes.get(key, ())
        if isinstance(values, str):
            values = values.splitlines()
        if not isinstance(values, (list, tuple)):
            raise ValueError("Liste d'indices OCR invalide.")
        for value in values[:6]:
            if isinstance(value, str) and value.strip():
                inputs.append(ObservationInput(field=field, value=value.strip(), source="ocr"))
    observations = []
    seen = set()
    for item in inputs:
        key = (item.field, item.value, item.source, item.image_ref, item.region)
        if key in seen:
            continue
        seen.add(key)
        observations.append(Observation(item.field, item.value, item.source, normalize_text(item.value),
                                        item.excerpt, item.image_ref, item.region, item.extractor_version,
                                        "indicative" if item.source in {"ocr", "prefill"} else "declared"))
    if len(observations) > 64:
        raise ValueError("Au plus 64 observations d'identité sont autorisées après fusion.")
    return ListingEvidence(title, description, tuple(observations), attributes.get("ocr_status") == "unavailable")


def form_evidence(values: Mapping[str, Any], captured: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """Distingue saisie, extraction et préremplissage au passage d'un formulaire."""
    captured = captured or {}
    observations = []
    for field in ("title", "description", *IDENTITY_FIELDS):
        value = values.get(field)
        if not isinstance(value, str) or not value.strip():
            continue
        original = captured.get(field) or values.get(f"captured_{field}")
        proposed = values.get(f"proposed_{field}")
        source = "prefill" if proposed == value else "structured" if original == value else "manual"
        observations.append({"field": field, "value": value, "source": source})
        if original and original != value:
            observations.append({"field": field, "value": original,
                                 "source": field if field in {"title", "description"} else "structured"})
    for field, key in (("name", "ocr_names"), ("card_number", "ocr_numbers")):
        hints = values.get(key, ())
        if isinstance(hints, str):
            hints = hints.splitlines()
        if hints is None:
            hints = ()
        for hint in hints:
            if isinstance(hint, str) and hint.strip():
                observations.append({"field": field, "value": hint.strip(), "source": "ocr"})
    return [item.model_dump(exclude_none=True) for item in validate_observations(observations)]
