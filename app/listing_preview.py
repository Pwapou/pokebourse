"""Prévisualisation locale d'une annonce sans écriture ni appel réseau."""
from __future__ import annotations

from dataclasses import asdict
from collections.abc import Mapping
import sqlite3
import re
from typing import Any

from app.identification.matcher import CardMatcher
from app.profitability import build_market_index, evaluate_listing, get_active_fee_profile
from app.tcgdex.cache import TcgdexCache
from app.identification.evidence import form_evidence
from app.identification.normalization import normalize_text, valid_card_number
from app.profitability import parse_euros_to_cents, ProfitabilityError


def prefill_identity_fields(values: dict[str, str], preview: Mapping[str, Any]) -> None:
    """Projette une seule proposition admissible, sans modifier les observations."""
    identification = preview.get("identification", {})
    if identification.get("status") == "lot" or identification.get("evidence_conflicts"):
        return
    candidates = identification.get("candidates", [])
    card = identification.get("matched_card") or (candidates[0] if candidates and (
        len(candidates) == 1 or candidates[0]["confidence"] > candidates[1]["confidence"]) else {})
    features = identification.get("features", {})
    for field in ("name", "set_name", "card_number"):
        current = values.get(field, "")
        original_title = values.get("captured_title", values.get("title", ""))
        fallback = field == "name" and current == original_title
        if current and not fallback and current != values.get(f"proposed_{field}"):
            continue
        proposed = str(card.get("local_id" if field == "card_number" else field) or "")
        # Conserver une fraction effectivement lue ; ne jamais fabriquer son total.
        if field == "card_number" and proposed and features.get("card_number"):
            proposed = features["card_number"]
        values[field] = proposed
        values[f"proposed_{field}"] = proposed
        source = "référentiel"
        if field == "card_number" and any(observation.get("source") == "ocr" and observation.get("field") == field
                                          and observation.get("value") == proposed for observation in identification.get("observations", [])):
            source = "OCR"
        values[f"proposal_source_{field}"] = source if proposed else ""
        if proposed and isinstance(preview.get("field_checks"), dict):
            preview["field_checks"][field] = {"status": "proposed", "message": f"Proposée depuis {'l’OCR' if source == 'OCR' else 'le référentiel'} — à vérifier, sans confirmation humaine."}


LANGUAGES = {"fr", "en", "ja", "de", "es", "it", "ko", "zh", "und"}


def identity_checks(matcher: CardMatcher, fields: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    """Décrit séparément les critères ; une absence ne bloque pas la recherche partielle."""
    from app.identification.aliases import resolve_alias

    checks = {}
    for field, label in (("name", "Nom"), ("set_name", "Extension"), ("card_number", "Numéro"), ("language", "Langue")):
        value = str(fields.get(field) or "").strip()
        normalized = normalize_text(value)
        status, message = "used", f"{label} : critère exploitable, à vérifier avec les autres champs."
        if not value or (field == "language" and value == "und"):
            status, message = "missing", f"{label} inconnu : recherche partielle disponible."
        elif field == "name" and value == fields.get("title"):
            status, message = "ignored", "Titre vendeur conservé ; il ne constitue pas un nom canonique."
        elif field == "name" and normalized not in matcher._name_ids:
            alias = resolve_alias(matcher.cache.connection, value)
            status, message = ("used", "Alias local reconnu ; référence à vérifier.") if alias.status == "exact" else (
                "unresolved", "Nom non reconnu : recherche lexicale indicative, sans filtre exact.")
        elif field == "set_name" and normalized not in {normalize_text(name) for name in matcher._sets}:
            status, message = "unresolved", "Extension non reconnue : écartée des filtres exacts, valeur conservée."
        elif field == "card_number" and not valid_card_number(value, matcher._number_ids):
            status, message = "invalid", "Numéro invalide : chiffres ou identifiant attesté requis ; valeur écartée de la recherche."
        elif field == "language" and value not in LANGUAGES:
            status, message = "invalid", "Langue non admise : choisissez une langue ou Inconnue."
        if value and value == fields.get(f"proposed_{field}") and status != "invalid":
            status = "proposed"
            source = "l’OCR" if fields.get(f"proposal_source_{field}") == "OCR" else "le référentiel"
            message = f"Proposée depuis {source} — à vérifier, sans confirmation humaine."
        checks[field] = {"status": status, "message": message}
    return checks


def preview_form(connection: sqlite3.Connection, fields: Mapping[str, Any]) -> dict[str, Any]:
    """Analyse un formulaire même si ses montants sont invalides, sans OCR ni écriture."""
    values = dict(fields)
    errors = {}
    for field, label in (("price", "Prix affiché"), ("shipping", "Port")):
        try:
            values[field + "_cents"] = parse_euros_to_cents(str(values[field]), label) if values.get(field) else None
        except (ValueError, ProfitabilityError) as error:
            values[field + "_cents"] = None
            errors[field] = str(error)
    if not values.get("currency"):
        errors["currency"] = "Devise de l’annonce inconnue : renseignez le code indiqué sur l’annonce avant l’enregistrement."
    elif not re.fullmatch(r"[A-Za-z]{3}", str(values["currency"])):
        errors["currency"] = "Devise invalide : code à trois lettres requis."
    response = preview_listing(connection, values)
    response["financial_errors"] = errors
    if errors:
        response.update(evaluation=None, evaluation_reason="Corrigez les champs financiers pour calculer la rentabilité.")
    return response


def preview_listing(
    connection: sqlite3.Connection,
    fields: Mapping[str, Any],
    *,
    assert_fields: set[str] | None = None,
) -> dict[str, Any]:
    """Propose une identité et une rentabilité, sans créer ni modifier d'annonce.

    Les champs fournis sont des observations ou corrections explicites. Une cote
    n'est cherchée que pour une identité unitaire retenue et une langue connue.
    ``assert_fields`` est conservé pour compatibilité des anciens appelants ;
    les observations et leur provenance gouvernent désormais la décision.
    """
    title = str((fields.get("title") if "title" in fields else fields.get("name")) or "").strip()
    description = str(fields.get("description") or "").strip()
    matcher = CardMatcher(TcgdexCache(connection), seed_if_empty=False, repair_index=False)
    checks = identity_checks(matcher, fields)
    attributes = dict(fields)
    if "identity_evidence" not in attributes:
        attributes["identity_evidence"] = form_evidence(fields)
    result = matcher.identify(title, description, raw_data=attributes)
    identity = asdict(result)
    response: dict[str, Any] = {"identification": identity, "evaluation": None, "evaluation_reason": None, "field_checks": checks}
    price = fields.get("price_cents")
    currency = str(fields.get("currency") or "").strip().upper()
    # Le détecteur ne fournit une langue que lorsqu'elle est explicitement lue.
    language = str(fields.get("language") or result.features.language or "").strip().lower()
    if any(check["status"] == "invalid" for check in checks.values()):
        response["evaluation_reason"] = "Champs d’identité invalides : vérifiez les diagnostics. Candidats indicatifs uniquement."
    elif price is None:
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
