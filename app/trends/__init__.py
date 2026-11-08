"""Module Tendances de marché — Variations de prix, activité des annonces et meilleures affaires."""

from app.trends.models import (
    BestOpportunityItem,
    ListingActivityItem,
    ListingActivityPage,
    OpportunitiesPage,
    PriceMovementsPage,
    PriceVariation,
    TrendsFilters,
    TrendsPageData,
)
from app.trends.opportunities import get_best_opportunities
from app.trends.service import (
    compute_price_variation,
    get_listing_activity,
    get_price_movements,
    get_trends_page_data,
)

__all__ = [
    "BestOpportunityItem",
    "ListingActivityItem",
    "ListingActivityPage",
    "OpportunitiesPage",
    "PriceMovementsPage",
    "PriceVariation",
    "TrendsFilters",
    "TrendsPageData",
    "compute_price_variation",
    "get_best_opportunities",
    "get_listing_activity",
    "get_price_movements",
    "get_trends_page_data",
]
