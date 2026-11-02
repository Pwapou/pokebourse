"""Modèles Pydantic pour le module Tendances (Lot 3)."""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class PriceVariation(BaseModel):
    """Variation de prix Cardmarket pour un produit / carte."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    product_id: int = Field(ge=0)
    card_name: str = Field(min_length=1)
    expansion_name: str | None = None
    tcg_dex_id: str | None = None
    reference_card_id: int | None = None
    current_price_cents: int = Field(ge=0)
    reference_price_cents: int = Field(gt=0)
    delta_cents: int
    delta_bps: int
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    source: str = Field(default="Cardmarket")
    fetched_at: str
    period: Literal["7_30", "1_7"] = "7_30"
    match_status: Literal["certifie", "partiel", "ambigu", "non_lie"] = "partiel"
    attachment_limits: str


class ListingActivityItem(BaseModel):
    """Activité des annonces observées sur 30 jours pour une carte du référentiel."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    reference_card_id: int = Field(ge=1)
    tcgdex_id: str | None = None
    card_name: str = Field(min_length=1)
    set_name: str = Field(min_length=1)
    local_id: str | None = None
    rarity: str | None = None
    image_url: str | None = None
    distinct_listings_count: int = Field(ge=0)
    new_listings_count: int = Field(ge=0)
    active_listings_count: int = Field(ge=0)
    min_price_cents: int | None = None
    max_price_cents: int | None = None
    currency: str = Field(default="EUR", min_length=3, max_length=3)


class BestOpportunityItem(BaseModel):
    """Meilleure affaire active pour une carte unitaire identifiée."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    listing_id: int = Field(ge=1)
    external_id: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    name: str = Field(min_length=1)
    set_name: str = Field(min_length=1)
    card_number: str | None = None
    condition: str | None = None
    language: str | None = None
    reference_card_id: int | None = None
    purchase_price_cents: int = Field(ge=0)
    buyer_shipping_cents: int = Field(ge=0)
    total_cost_cents: int = Field(ge=0)
    estimated_resale_cents: int = Field(gt=0)
    net_profit_cents: int
    roi_bps: int
    margin_bps: int | None = None
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    reference_source: str
    reference_source_name: str | None = None
    quote_freshness_date: str | None = None
    quote_age_days: int | None = None
    url: str | None = None
    image_url: str | None = None
    verdict: str = "opportunite"
    verdict_label: str = "Opportunité"
    comparables: dict[str, Any] | None = None


class TrendsFilters(BaseModel):
    """Filtres pour la page des tendances."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    period: str = Field(default="7_30")
    set_name: str = Field(default="", max_length=200)
    rarity: str = Field(default="", max_length=100)
    language: str = Field(default="", max_length=20)
    min_observations: int = Field(default=1, ge=1, le=1000)
    max_quote_age_days: int = Field(default=30, ge=1, le=365)
    limit: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="before")
    @classmethod
    def normalize_incoming(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        copied = dict(data)
        period = str(copied.get("period") or "").strip()
        if period not in ("7_30", "1_7"):
            copied["period"] = "7_30"
        for str_key in ("set_name", "rarity", "language"):
            val = copied.get(str_key)
            copied[str_key] = "" if val is None else str(val).strip()
        for int_key in ("min_observations", "max_quote_age_days", "limit"):
            val = copied.get(int_key)
            if val is not None and str(val).strip():
                try:
                    copied[int_key] = int(val)
                except (ValueError, TypeError):
                    pass
        return copied


class TrendsPageData(BaseModel):
    """Agrégation complète pour l'affichage de /trends."""

    model_config = ConfigDict(extra="ignore")

    computed_at: str
    last_cardmarket_sync_at: str | None = None
    filters: TrendsFilters
    hausses: list[PriceVariation] = Field(default_factory=list)
    baisses: list[PriceVariation] = Field(default_factory=list)
    total_price_compared: int = 0
    listing_activity: list[ListingActivityItem] = Field(default_factory=list)
    best_opportunities: list[BestOpportunityItem] = Field(default_factory=list)
    available_sets: list[str] = Field(default_factory=list)
    available_rarities: list[str] = Field(default_factory=list)
    available_languages: list[str] = Field(default_factory=list)
    has_data: bool = False
    is_empty: bool = True
    is_partial: bool = False
    partial_reason: str | None = None
