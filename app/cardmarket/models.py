"""Modèles de données du référentiel Cardmarket."""

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class CardmarketPrice(BaseModel):
    """Snapshot de prix de marché Cardmarket pour un produit (carte)."""

    product_id: int = Field(ge=0)
    card_name: str = Field(min_length=1, max_length=300)
    expansion_name: str | None = Field(default=None, max_length=300)
    language: str = Field(default="en", min_length=2, max_length=8)
    trend_price_cents: int | None = Field(default=None, ge=0)
    avg1_price_cents: int | None = Field(default=None, ge=0)
    avg7_price_cents: int | None = Field(default=None, ge=0)
    avg30_price_cents: int | None = Field(default=None, ge=0)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    tcg_dex_id: str | None = Field(default=None, max_length=100)
    fetched_at: str = Field(default_factory=lambda: _utc_now())

    @property
    def best_known_price_cents(self) -> int | None:
        """Meilleure estimation disponible : tendance, sinon moyenne 7 jours."""
        for value in (self.trend_price_cents, self.avg7_price_cents, self.avg30_price_cents):
            if value is not None:
                return value
        return None


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
