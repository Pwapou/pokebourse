"""Prévisualisation locale d'une annonce sans écriture ni appel réseau."""
from __future__ import annotations

from dataclasses import asdict
from collections.abc import Mapping
import sqlite3
from typing import Any

from app.identification.matcher import CardMatcher
from app.profitability import build_market_index, evaluate_listing, get_active_fee_profile
from app.tcgdex.cache import TcgdexCache
from app.identification.evidence import form_evidence


def prefill_identity_fields(values: dict[str, str], preview: Mapping[str, Any]) -> None:
    """Préremplit seulement les champs vides, sans écraser une saisie utilisateur."""
    identification = preview.get("identification", {})
    features = identification.get("features", {})
    card = identification.get("matched_card") or {}
    for field, feature in (("name", "name"), ("set_name", "set_name"), ("card_number", "card_number")):
        if not values.get(field):
            card_value = card.get("local_id" if field == "card_number" else field)
            feature_value = features.get(feature)
            values[field] = str((feature_value if field == "card_number" else card_value) or card_value or feature_value or "")
            if values[field]:
                values[f"proposed_{field}"] = values[field]


def preview_listing(
    connection: sqlite3.Connection,
    fields: Mapping[str, Any],
    *,
    assert_fields: set[str] | None = None,
) -> dict[str, Any]:
    """Propose une identité et une rentabilité, sans créer ni modifier d'annonce.

    Les champs fournis sont des observations ou corrections explicites. Une cote
    n'est cherchée que pour une identité unitaire retenue et une langue connue.
    Lorsque ``assert_fields`` est fourni, seuls ces champs d'identité
    (parmi « name », « set_name », « card_number ») déclenchent une
    contradiction lorsqu'ils contredisent la carte proposée ; les autres
    restent de simples indices de recherche. Par défaut, tout champ fourni
    est une assertion explicite (corrections de l'utilisateur).
    """
    title = str((fields.get("title") if "title" in fields else fields.get("name")) or "").strip()
    description = str(fields.get("description") or "").strip()
    matcher = CardMatcher(TcgdexCache(connection), seed_if_empty=False, repair_index=False)
    attributes = dict(fields)
    if "identity_evidence" not in attributes:
        attributes["identity_evidence"] = form_evidence(fields)
    result = matcher.identify(title, description, raw_data=attributes)
    identity = asdict(result)
    response: dict[str, Any] = {"identification": identity, "evaluation": None, "evaluation_reason": None}
    price = fields.get("price_cents")
    currency = str(fields.get("currency") or "").strip().upper()
    # Le détecteur ne fournit une langue que lorsqu'elle est explicitement lue.
    language = str(fields.get("language") or result.features.language or "").strip().lower()
    if price is None:
        response["evaluation_reason"] = "Prix d’achat inconnu."
    elif not currency:
        response["evaluation_reason"] = "Devise de l’annonce inconnue."
    elif identity["status"] != "identified" or result.matched_card is None:
        response["evaluation_reason"] = "Identité à vérifier avant de chercher une cote."
    elif not language or language != "fr":
        response["evaluation_reason"] = "Langue de l’annonce inconnue ou non couverte."
    else:
        card = result.matched_card
        row = {
            "id": None, "price_cents": price, "shipping_cents": fields.get("shipping_cents"),
            "currency": currency, "name": card.name, "set_name": card.set_name,
            "card_number": result.features.card_number or card.local_id,
            "condition": fields.get("condition") or result.features.condition,
            "language": language, "variant": fields.get("variant") or result.features.variant,
            "edition": fields.get("edition"), "grading_company": fields.get("grading_company") or result.features.grading_company,
            "grade": fields.get("grade") or result.features.grade,
            "reference_card_id": card.id, "identification_status": result.status,
        }
        profile = get_active_fee_profile(connection)
        response["evaluation"] = evaluate_listing(row, profile, build_market_index(connection, profile.min_catalog_samples))
    return response
