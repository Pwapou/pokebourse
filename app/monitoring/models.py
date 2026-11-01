from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

WatchPlatform = Literal["vinted", "leboncoin", "ebay", "wallapop"]


class WatchInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    platform: WatchPlatform
    name: str = Field(min_length=1, max_length=120)
    search_text: str = Field(min_length=1, max_length=200)
    price_from: int | None = Field(default=None, ge=0, le=1_000_000_000)
    price_to: int | None = Field(default=None, ge=0, le=1_000_000_000)
    interval_seconds: int = Field(ge=1, le=86_400)
    category: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def validate_prices(self) -> "WatchInput":
        if (
            self.price_from is not None
            and self.price_to is not None
            and self.price_from > self.price_to
        ):
            raise ValueError("Le prix minimum ne peut pas dépasser le prix maximum.")
        return self

    def search_params(self) -> dict[str, object]:
        params: dict[str, object] = {"search_text": self.search_text}
        if self.price_from is not None:
            params["price_from"] = self.price_from
        if self.price_to is not None:
            params["price_to"] = self.price_to
        if self.category:
            params["category"] = self.category
        return params


class WatchNotFoundError(LookupError):
    pass


class WatchValidationError(ValueError):
    pass


class WatchAlreadyRunningError(RuntimeError):
    pass
