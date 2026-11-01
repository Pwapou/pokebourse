"""Collecte des profils vendeur sur les plateformes.

Extraction en liste blanche stricte : la réponse brute des plateformes
contient des données personnelles qui ne sont jamais propagées hors de ce
module et jamais persistées.
"""

import logging
from typing import Any

from app.collectors.models import CollectorError
from app.collectors.retry import call_with_backoff
from app.sellers.models import MAX_REPUTATION_BPS, SellerProfile
from app.supervision.models import utc_now

logger = logging.getLogger(__name__)

VINTED_DOMAIN = "https://www.vinted.fr"

# Champs de réputation Vinted autorisés (liste blanche). Tout le reste de la
# réponse — e-mail, nom réel, ville, date de naissance… — est ignoré.
_VINTED_FEEDBACK_FIELDS = (
    "login",
    "feedback_count",
    "positive_feedback_count",
    "neutral_feedback_count",
    "negative_feedback_count",
    "feedback_reputation",
    "item_count",
    "followers_count",
    "business",
    "business_account",
    "is_account_banned",
    "account_status",
    "profile_url",
)


def _as_non_negative_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _as_reputation_bps(value: Any) -> int | None:
    """Normalise une réputation 0..1 en points de base 0..10 000."""

    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if not 0.0 <= score <= 1.0:
        return None
    return round(score * MAX_REPUTATION_BPS)


def fetch_vinted_seller_profile(seller_id: str) -> SellerProfile:
    """Récupère la réputation publique d'un vendeur Vinted (lecture seule)."""

    try:
        from vinted_scraper import VintedScraper
    except ImportError as error:
        raise CollectorError(
            "Le connecteur Vinted n'est pas installé dans l'environnement."
        ) from error

    if not seller_id or not seller_id.isdigit():
        raise CollectorError("Identifiant vendeur Vinted invalide.")

    def request() -> Any:
        scraper = VintedScraper(VINTED_DOMAIN)
        return scraper.curl(f"/api/v2/users/{seller_id}")

    try:
        payload = call_with_backoff(request, operation_name="Profil vendeur Vinted")
    except CollectorError:
        raise
    except Exception as error:
        raise CollectorError("Profil vendeur Vinted indisponible.") from error

    raw = (getattr(payload, "json_data", None) or {}).get("user") or {}
    profile = {key: raw.get(key) for key in _VINTED_FEEDBACK_FIELDS}
    business = bool(profile.get("business") or profile.get("business_account"))
    is_banned = bool(profile.get("is_account_banned")) or profile.get("account_status") not in (None, "active", "ok")
    return SellerProfile(
        platform="vinted",
        seller_external_id=seller_id,
        login=profile.get("login"),
        feedback_count=_as_non_negative_int(profile.get("feedback_count")),
        positive_count=_as_non_negative_int(profile.get("positive_feedback_count")),
        neutral_count=_as_non_negative_int(profile.get("neutral_feedback_count")),
        negative_count=_as_non_negative_int(profile.get("negative_feedback_count")),
        reputation_bps=_as_reputation_bps(profile.get("feedback_reputation")),
        item_count=_as_non_negative_int(profile.get("item_count")),
        account_type="business" if business else "private",
        is_banned=is_banned,
        profile_url=profile.get("profile_url"),
        fetched_at=utc_now(),
    )


def fetch_leboncoin_seller_profile(seller_id: str) -> SellerProfile:
    """Récupère la réputation publique d'un vendeur Leboncoin (lecture seule)."""

    try:
        import lbc
    except ImportError as error:
        raise CollectorError(
            "Le connecteur Leboncoin n'est pas installé dans l'environnement."
        ) from error

    if not seller_id or len(seller_id) > 100:
        raise CollectorError("Identifiant vendeur Leboncoin invalide.")

    def request() -> Any:
        return lbc.Client().get_user(seller_id)

    try:
        user = call_with_backoff(request, operation_name="Profil vendeur Leboncoin")
    except CollectorError:
        raise
    except Exception as error:
        raise CollectorError("Profil vendeur Leboncoin indisponible.") from error

    feedback = getattr(user, "feedback", None)
    category_scores = [
        float(score)
        for score in (
            getattr(feedback, attr, None)
            for attr in (
                "conformity",
                "package",
                "product",
                "recommendation",
                "respect",
                "transaction",
                "user_attention",
            )
        )
        if score is not None
    ]
    reputation_bps = (
        round(sum(category_scores) / len(category_scores) * MAX_REPUTATION_BPS)
        if category_scores
        else None
    )
    reply = getattr(user, "reply", None)
    reply_rate = getattr(reply, "rate", None)
    return SellerProfile(
        platform="leboncoin",
        seller_external_id=seller_id,
        login=getattr(user, "name", None),
        feedback_count=_as_non_negative_int(
            getattr(feedback, "received_count", None)
        ),
        reputation_bps=reputation_bps,
        item_count=_as_non_negative_int(getattr(user, "total_ads", None)),
        response_rate_percent=_as_non_negative_int(reply_rate),
        account_type=str(getattr(user, "account_type", None) or None),
        is_banned=False,
        profile_url=None,
        fetched_at=utc_now(),
    )


def fetch_ebay_seller_profile(seller_id: str) -> SellerProfile:
    return SellerProfile(
        platform="ebay",
        seller_external_id=seller_id,
        login=seller_id,
        profile_url=f"https://www.ebay.fr/usr/{seller_id}",
        fetched_at=utc_now(),
    )


def fetch_wallapop_seller_profile(seller_id: str) -> SellerProfile:
    return SellerProfile(
        platform="wallapop",
        seller_external_id=seller_id,
        login=seller_id,
        profile_url=f"https://fr.wallapop.com/user/{seller_id}",
        fetched_at=utc_now(),
    )


PLATFORM_FETCHERS = {
    "vinted": fetch_vinted_seller_profile,
    "leboncoin": fetch_leboncoin_seller_profile,
    "ebay": fetch_ebay_seller_profile,
    "wallapop": fetch_wallapop_seller_profile,
}

__all__ = [
    "PLATFORM_FETCHERS",
    "fetch_ebay_seller_profile",
    "fetch_leboncoin_seller_profile",
    "fetch_vinted_seller_profile",
    "fetch_wallapop_seller_profile",
]
