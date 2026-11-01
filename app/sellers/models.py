"""Profils vendeur et évaluation de fiabilité.

Les profils ne stockent que des champs de réputation en liste blanche :
aucune donnée personnelle (nom réel, e-mail, ville, date de naissance) n'est
conservée, même si la plateforme la renvoie dans sa réponse brute.
"""

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SellerPlatform = Literal["vinted", "leboncoin"]

MAX_REPUTATION_BPS = 10_000


class SellerProfile(BaseModel):
    """Réputation publique d'un vendeur, telle que publiée par la plateforme."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    platform: SellerPlatform
    seller_external_id: str = Field(min_length=1, max_length=100)
    login: str | None = Field(default=None, max_length=200)
    feedback_count: int | None = Field(default=None, ge=0)
    positive_count: int | None = Field(default=None, ge=0)
    neutral_count: int | None = Field(default=None, ge=0)
    negative_count: int | None = Field(default=None, ge=0)
    reputation_bps: int | None = Field(default=None, ge=0, le=MAX_REPUTATION_BPS)
    item_count: int | None = Field(default=None, ge=0)
    response_rate_percent: int | None = Field(default=None, ge=0, le=100)
    account_type: str | None = Field(default=None, max_length=30)
    is_banned: bool = False
    profile_url: str | None = Field(default=None, max_length=2048)
    fetched_at: str = Field(min_length=10, max_length=40)
    is_favorite: bool = False
    user_notes: str | None = None

    @field_validator("profile_url")
    @classmethod
    def validate_profile_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not (value.startswith("https://www.vinted.") or value.startswith("https://www.leboncoin.fr")):
            raise ValueError("URL de profil hors domaine officiel")
        return value


@dataclass(frozen=True)
class ReliabilityRating:
    """Évaluation de fiabilité affichée en étoiles.

    Règle volontairement simple et lisible : aucune heuristique opaque. Les
    notes expliquent chaque ajustement pour que l'utilisateur puisse vérifier
    le calcul à la main.
    """

    stars: int | None
    label: str
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def known(self) -> bool:
        return self.stars is not None

    def stars_text(self) -> str:
        if self.stars is None:
            return "—"
        return "★" * self.stars + "☆" * (5 - self.stars)


UNKNOWN_RATING = ReliabilityRating(stars=None, label="Vendeur non évalué")
INSUFFICIENT_DATA_RATING = ReliabilityRating(
    stars=None, label="Données insuffisantes"
)

PROFILE_ROW_FIELDS = (
    "platform",
    "seller_external_id",
    "login",
    "feedback_count",
    "positive_count",
    "neutral_count",
    "negative_count",
    "reputation_bps",
    "item_count",
    "response_rate_percent",
    "account_type",
    "is_banned",
    "profile_url",
    "fetched_at",
    "is_favorite",
    "user_notes",
)


class Purchase(BaseModel):
    """Enregistrement d'un achat réel conclu auprès d'un vendeur."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: int | None = None
    catalog_item_id: int | None = None
    seller_profile_id: int | None = None
    seller_name: str = Field(min_length=1, max_length=200)
    card_name: str = Field(min_length=1, max_length=200)
    set_name: str | None = Field(default=None, max_length=200)
    card_number: str | None = Field(default=None, max_length=50)
    condition: str | None = Field(default=None, max_length=50)
    price_paid_cents: int = Field(ge=0)
    shipping_paid_cents: int = Field(default=0, ge=0)
    currency: str = "EUR"
    platform: str | None = None
    status: Literal["commande", "recu", "en_vente", "vendu"] = "recu"
    notes: str | None = None
    purchased_at: str | None = None


@dataclass
class SellerSummary:
    """Synthèse d'un vendeur avec indicateurs de fiabilité, sourcing et achats."""

    id: int
    platform: str
    seller_external_id: str
    login: str | None
    is_favorite: bool
    user_notes: str | None
    profile_url: str | None
    rating: ReliabilityRating
    feedback_count: int | None
    positive_count: int | None
    reputation_bps: int | None
    total_listings: int = 0
    opportunities_count: int = 0
    watches_count: int = 0
    purchases_count: int = 0
    total_spent_cents: int = 0


def profile_from_row(row: object) -> SellerProfile | None:
    """Reconstruit un profil depuis une ligne SQLite (champs en liste blanche)."""

    if row is None:
        return None

    def getter(key: str) -> object:
        try:
            return row[key]  # type: ignore[index]
        except (KeyError, IndexError, TypeError):
            return getattr(row, key, None)

    values = {key: getter(key) for key in PROFILE_ROW_FIELDS}
    values["is_banned"] = bool(values.get("is_banned"))
    values["is_favorite"] = bool(values.get("is_favorite"))
    if not values.get("seller_external_id"):
        return None
    return SellerProfile.model_validate(values)


def rating_from_profile_row(row: object) -> ReliabilityRating:
    return reliability_rating(profile_from_row(row))

_LABEL_BY_STARS = {
    5: "Fiable",
    4: "Fiable",
    3: "Correct",
    2: "À vérifier",
    1: "Risqué",
    0: "Risqué",
}

MIN_FEEDBACK_FOR_RATING = 3
HIGH_NEGATIVE_RATIO = 0.10
LOW_FEEDBACK_CAP = 3
LOW_FEEDBACK_THRESHOLD = 5


def reliability_rating(profile: SellerProfile | None) -> ReliabilityRating:
    """Calcule l'évaluation en étoiles à partir du profil publié.

    Le score de base est la réputation de la plateforme ramenée sur 5
    étoiles. Deux garde-fous bornent ensuite le résultat : peu d'avis, et
    une part d'avis négatifs supérieure à 10 %.
    """

    if profile is None:
        return UNKNOWN_RATING
    if profile.is_banned:
        return ReliabilityRating(stars=0, label="Compte banni")
    if (
        profile.feedback_count is None
        or profile.feedback_count < MIN_FEEDBACK_FOR_RATING
        or profile.reputation_bps is None
    ):
        return INSUFFICIENT_DATA_RATING

    notes: list[str] = []
    stars = round(profile.reputation_bps / MAX_REPUTATION_BPS * 5)

    if profile.feedback_count < LOW_FEEDBACK_THRESHOLD:
        stars = min(stars, LOW_FEEDBACK_CAP)
        notes.append(
            f"Seulement {profile.feedback_count} avis : note plafonnée à {LOW_FEEDBACK_CAP} étoiles."
        )

    if profile.negative_count is not None and profile.feedback_count > 0:
        negative_ratio = profile.negative_count / profile.feedback_count
        if negative_ratio > HIGH_NEGATIVE_RATIO:
            stars = min(stars, 2)
            notes.append(
                f"{profile.negative_count} avis négatif(s) sur {profile.feedback_count} "
                f"({negative_ratio:.0%}) : note plafonnée à 2 étoiles."
            )

    stars = max(0, min(5, stars))
    return ReliabilityRating(
        stars=stars, label=_LABEL_BY_STARS[stars], notes=tuple(notes)
    )
