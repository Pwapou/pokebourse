from __future__ import annotations

import json
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, model_validator

SEARCH_SCOPES = ("all", "cards", "listings")
DEFAULT_SCOPE = "all"

LOT_FILTERS = ("all", "exclude", "only")
DEFAULT_LOT_FILTER = "all"

SEARCH_SOURCES = ("all", "vinted", "leboncoin", "ebay", "wallapop", "manual")
DEFAULT_SOURCE = "all"

SEARCH_IDENT_STATUSES = ("all", "identified", "ambiguous", "lot", "unidentified")
DEFAULT_IDENT_STATUS = "all"

CARD_SORTS: dict[str, str] = {
    "relevance": "Pertinence",
    "name_asc": "Nom (A → Z)",
    "name_desc": "Nom (Z → A)",
    "release_desc": "Date de sortie (récente)",
    "release_asc": "Date de sortie (ancienne)",
    "local_id_asc": "Numéro de carte",
}
DEFAULT_CARD_SORT = "relevance"

LISTING_SORTS: dict[str, str] = {
    "relevance": "Pertinence",
    "import_desc": "Import récent",
    "import_asc": "Import ancien",
    "price_asc": "Prix croissant",
    "price_desc": "Prix décroissant",
    "name_asc": "Nom (A → Z)",
    "name_desc": "Nom (Z → A)",
    "net_profit_desc": "Gain net (décroissant)",
    "roi_desc": "ROI (décroissant)",
}
DEFAULT_LISTING_SORT = "relevance"

# Tris de rentabilité calculés par le moteur de rentabilité (hors SQL) :
# le tri s'effectue en Python sur l'ensemble des annonces filtrées, puis la
# pagination est appliquée en mémoire pour conserver un ordre stable.
PROFITABILITY_LISTING_SORTS = ("net_profit_desc", "roi_desc")


class SearchFilters(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    q: str = Field(default="", max_length=200)
    scope: str = Field(default=DEFAULT_SCOPE)
    set_name: str = Field(default="", max_length=200)
    year_min: int | None = Field(default=None, ge=1990, le=2050)
    year_max: int | None = Field(default=None, ge=1990, le=2050)
    rarity: str = Field(default="", max_length=100)
    condition: str = Field(default="", max_length=100)
    language: str = Field(default="", max_length=20)
    variant: str = Field(default="", max_length=100)
    edition: str = Field(default="", max_length=100)
    grading_company: str = Field(default="", max_length=50)
    grade: str = Field(default="", max_length=30)
    source: str = Field(default=DEFAULT_SOURCE)
    price_min_cents: int | None = Field(default=None, ge=0, le=1_000_000_000)
    price_max_cents: int | None = Field(default=None, ge=0, le=1_000_000_000)
    ident_status: str = Field(default=DEFAULT_IDENT_STATUS)
    lot_filter: str = Field(default=DEFAULT_LOT_FILTER)
    sort: str = Field(default="")
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=25, ge=1, le=100)

    @model_validator(mode="before")
    @classmethod
    def normalize_incoming(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        copied = dict(data)

        # Normalisation des chaînes vides
        for str_key in (
            "q", "set_name", "rarity", "condition", "language", "variant",
            "edition", "grading_company", "grade", "sort",
        ):
            val = copied.get(str_key)
            if val is None or not str(val).strip():
                copied[str_key] = ""
            else:
                copied[str_key] = str(val).strip()

        # Normalisation des entiers d'années
        for yr_key in ("year_min", "year_max"):
            val = copied.get(yr_key)
            if val is None or str(val).strip() == "":
                copied[yr_key] = None
            else:
                try:
                    copied[yr_key] = int(val)
                except (ValueError, TypeError):
                    copied[yr_key] = None

        # Normalisation des prix en centimes
        for pr_key in ("price_min_cents", "price_max_cents"):
            val = copied.get(pr_key)
            if val is None or str(val).strip() == "":
                copied[pr_key] = None
            else:
                try:
                    copied[pr_key] = int(val)
                except (ValueError, TypeError):
                    copied[pr_key] = None

        # Scope
        scope = copied.get("scope")
        if not scope or scope not in SEARCH_SCOPES:
            copied["scope"] = DEFAULT_SCOPE

        # Source
        source = copied.get("source")
        if not source or source not in SEARCH_SOURCES:
            copied["source"] = DEFAULT_SOURCE

        # Ident status
        ident = copied.get("ident_status")
        if not ident or ident not in SEARCH_IDENT_STATUSES:
            copied["ident_status"] = DEFAULT_IDENT_STATUS

        # Lot filter
        lot = copied.get("lot_filter")
        if not lot or lot not in LOT_FILTERS:
            copied["lot_filter"] = DEFAULT_LOT_FILTER

        return copied

    @model_validator(mode="after")
    def validate_ranges_and_sorts(self) -> SearchFilters:
        if self.year_min is not None and self.year_max is not None:
            if self.year_min > self.year_max:
                raise ValueError("L'année minimale ne peut pas être supérieure à l'année maximale.")

        if self.price_min_cents is not None and self.price_max_cents is not None:
            if self.price_min_cents > self.price_max_cents:
                raise ValueError("Le prix minimal ne peut pas être supérieur au prix maximal.")

        # Normalisation du tri
        if self.scope == "cards":
            if self.sort not in CARD_SORTS:
                self.sort = DEFAULT_CARD_SORT if self.q else "name_asc"
        elif self.scope == "listings":
            if self.sort not in LISTING_SORTS:
                self.sort = DEFAULT_LISTING_SORT if self.q else "import_desc"
        else:
            # scope == "all"
            valid_any = set(CARD_SORTS) | set(LISTING_SORTS)
            if self.sort not in valid_any:
                self.sort = "relevance" if self.q else "name_asc"

        return self

    def to_query_params(self, **overrides: Any) -> dict[str, str]:
        """Convertit les filtres actuels en dictionnaire de query params pour l'URL."""
        params: dict[str, str] = {}
        target = {**self.model_dump(), **overrides}

        if target.get("q"):
            params["q"] = str(target["q"])
        if target.get("scope") and target["scope"] != DEFAULT_SCOPE:
            params["scope"] = str(target["scope"])
        if target.get("set_name"):
            params["set_name"] = str(target["set_name"])
        if target.get("year_min") is not None:
            params["year_min"] = str(target["year_min"])
        if target.get("year_max") is not None:
            params["year_max"] = str(target["year_max"])
        if target.get("rarity"):
            params["rarity"] = str(target["rarity"])
        if target.get("condition"):
            params["condition"] = str(target["condition"])
        if target.get("language"):
            params["language"] = str(target["language"])
        if target.get("variant"):
            params["variant"] = str(target["variant"])
        if target.get("edition"):
            params["edition"] = str(target["edition"])
        if target.get("grading_company"):
            params["grading_company"] = str(target["grading_company"])
        if target.get("grade"):
            params["grade"] = str(target["grade"])
        if target.get("source") and target["source"] != DEFAULT_SOURCE:
            params["source"] = str(target["source"])
        if target.get("price_min_cents") is not None:
            cents = target["price_min_cents"]
            params["price_min"] = f"{cents // 100}.{cents % 100:02d}"
        if target.get("price_max_cents") is not None:
            cents = target["price_max_cents"]
            params["price_max"] = f"{cents // 100}.{cents % 100:02d}"
        if target.get("ident_status") and target["ident_status"] != DEFAULT_IDENT_STATUS:
            params["ident_status"] = str(target["ident_status"])
        if target.get("lot_filter") and target["lot_filter"] != DEFAULT_LOT_FILTER:
            params["lot_filter"] = str(target["lot_filter"])
        if target.get("sort"):
            params["sort"] = str(target["sort"])
        if target.get("page") and target["page"] > 1:
            params["page"] = str(target["page"])

        # La recherche distante n'est lancée qu'à la suite d'une action explicite.
        if overrides.get("external"):
            params["external"] = "1"

        return params


class CardSearchResult(BaseModel):
    id: int
    tcgdex_id: str
    local_id: str
    name: str
    set_id: str
    set_name: str
    release_date: str | None = None
    release_year: int | None = None
    rarity: str | None = None
    category: str | None = None
    types: list[str] = Field(default_factory=list)
    hp: int | None = None
    stage: str | None = None
    illustrator: str | None = None
    image_url: str | None = None


class CardSearchSummary(BaseModel):
    items: list[CardSearchResult]
    total: int
    is_approximate: bool = False
    page: int = 1
    per_page: int = 25
    total_pages: int = 1
    range_start: int = 0
    range_end: int = 0
    missing_rarity_count: int = 0
    missing_year_count: int = 0
    metadata_diagnostic: str | None = None


class ListingSearchResult(BaseModel):
    id: int
    external_id: str
    name: str
    set_name: str
    card_number: str | None = None
    language: str
    condition: str | None = None
    variant: str | None = None
    edition: str | None = None
    grading_company: str | None = None
    grade: str | None = None
    certification_number: str | None = None
    price_cents: int
    currency: str
    seller: str | None = None
    url: str | None = None
    imported_at: str
    original_title: str | None = None
    source_name: str
    source_kind: str
    identification_status: str
    is_lot: int
    reference_card_id: int | None = None
    identification_confidence: int | None = None
    identification_reason: str | None = None
    seller_profile_id: int | None = None
    seller_external_id: str | None = None
    ref_name: str | None = None
    ref_tcgdex_id: str | None = None
    ref_rarity: str | None = None
    ref_image_url: str | None = None
    ref_local_id: str | None = None
    ref_set_name: str | None = None
    ref_release_date: str | None = None
    ref_release_year: int | None = None

    # Champs facultatifs enrichis de rentabilité
    total_cost_cents: int | None = None
    reference_price_cents: int | None = None
    reference_source: str | None = None
    sample_count: int | None = None
    net_profit_cents: int | None = None
    roi_bps: int | None = None
    verdict: str | None = None


class ListingSearchSummary(BaseModel):
    items: list[ListingSearchResult]
    total: int
    page: int = 1
    per_page: int = 25
    total_pages: int = 1
    range_start: int = 0
    range_end: int = 0
    missing_rarity_count: int = 0
    missing_year_count: int = 0
    metadata_diagnostic: str | None = None


class SearchResults(BaseModel):
    filters: SearchFilters
    cards: CardSearchSummary | None = None
    listings: ListingSearchSummary | None = None
    validation_error: str | None = None
