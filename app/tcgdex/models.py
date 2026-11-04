from dataclasses import dataclass
from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class TcgdexSet(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=200)
    series: str | None = Field(default=None, max_length=100)
    card_count_total: int | None = Field(default=None, ge=0)
    card_count_official: int | None = Field(default=None, ge=0)
    release_date: str | None = None
    logo_url: str | None = None
    symbol_url: str | None = None


class TcgdexCard(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=100)  # tcgdex_id (ex: swsh3-136, base1-4)
    local_id: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=200)
    set_id: str = Field(min_length=1, max_length=50)
    set_name: str = Field(min_length=1, max_length=200)
    # Locale de la fiche : une même identité TCGdex peut exister en plusieurs
    # localisations (fr, en, ja…) sans écrasement (T05). La langue d'une fiche
    # ne prouve pas celle de l'exemplaire vendu.
    reference_language: str = Field(default="fr", min_length=1, max_length=20)
    rarity: str | None = Field(default=None, max_length=100)
    category: str | None = Field(default=None, max_length=50)
    types: list[str] = Field(default_factory=list)
    hp: int | None = Field(default=None, ge=0)
    stage: str | None = Field(default=None, max_length=50)
    illustrator: str | None = Field(default=None, max_length=200)
    image_url: str | None = None
    raw_data: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class ReferenceCardRecord:
    id: int
    tcgdex_id: str
    local_id: str
    name: str
    set_id: str
    set_name: str
    rarity: str | None
    category: str | None
    types: str | None
    hp: int | None
    stage: str | None
    illustrator: str | None
    image_url: str | None
    raw_data: dict[str, Any]
    updated_at: str
    # Locale de la fiche de référence ; distincte de la langue d'un exemplaire.
    reference_language: str = "fr"
