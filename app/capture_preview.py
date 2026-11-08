"""Prévisualisation d'une annonce capturée par l'extension Chrome.

Le parcours est strictement en lecture jusqu'à la confirmation explicite de
l'utilisateur : la prévisualisation propose une identification et une
rentabilité indicatives, présente la provenance de chaque champ (extrait,
proposé, saisi/corrigé, manquant) puis, sur « Confirmer et ajouter l'annonce »,
enregistre via le flux transactionnel existant (``app.catalog.import_jsonl``)
avec sa déduplication et la préservation de ``first_seen_at``.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from app.catalog import CatalogImportError, CatalogItem, import_jsonl, validate_public_image_url
from app.listing_preview import LANGUAGES, prefill_identity_fields, preview_form
from app.manual_listing import _money, _percent
from app.profitability import ProfitabilityError, parse_euros_to_cents
from app.storage.database import connect
from app.identification.evidence import form_evidence

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.filters["preview_money"] = _money
templates.env.filters["preview_percent"] = _percent

# Champs éditables d'une annonce capturée. « platform » et « external_id » ne sont
# jamais modifiables : ils identifient la source et servent à la déduplication.
_FIELDS = (
    "title", "description", "name", "set_name", "card_number", "language",
    "condition", "seller", "price", "shipping", "currency", "image_url",
)
# Plateformes officielles reconnues ; toute autre origine de capture (nom d'hôte
# d'une boutique TCG, « web » générique) reste utilisable en prévisualisation.
_SOURCES_RECONNUES = {"vinted", "leboncoin", "ebay", "wallapop"}
_SOURCE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9.-]{1,59}$")


def _clean(raw: Any) -> str:
    return str(raw or "")[:10000].strip()


def _provenance(captured: str, current: str) -> str:
    """Origine d'un champ : extraite, saisie, corrigée ou manquante.

    Compare la valeur capturée d'origine à la valeur actuellement affichée.
    """
    if not current and not captured:
        return "manquante"
    if current and not captured:
        return "saisie"
    if captured and current != captured:
        return "corrigée"
    return "extraite"


def _read_form(form: Any) -> tuple[dict[str, str], dict[str, str]]:
    """Retourne (valeurs affichées, valeurs capturées d'origine) du formulaire."""
    values = {key: _clean(form.get(key, "")) for key in (*_FIELDS, "proposed_name", "proposed_set_name", "proposed_card_number", "ocr_status", "proposal_source_name", "proposal_source_set_name", "proposal_source_card_number")}
    captured = {key: _clean(form.get(f"captured_{key}", "")) for key in _FIELDS}
    return values, captured


def _provenances(values: dict[str, str], captured: dict[str, str]) -> dict[str, str]:
    return {key: "proposée" if values.get(key) and values.get(f"proposed_{key}") == values[key]
            else _provenance(captured.get(key, ""), values.get(key, "")) for key in _FIELDS}


def _read_ocr_hints(form: Any) -> dict[str, Any] | None:
    """Recharge uniquement les indices nécessaires, jamais le texte OCR brut."""
    names = [_clean(value)[:100] for value in form.getlist("ocr_names") if _clean(value)]
    numbers = [_clean(value)[:40] for value in form.getlist("ocr_numbers") if _clean(value)]
    # Les formulaires HTML historiques utilisent une liste séparée par des retours.
    if not names:
        names = [_clean(value)[:100] for value in _clean(form.get("ocr_names", "")).split("\n") if _clean(value)]
    if not numbers:
        numbers = [_clean(value)[:40] for value in _clean(form.get("ocr_numbers", "")).split("\n") if _clean(value)]
    if not names and not numbers and form.get("ocr_status") != "unavailable":
        return None
    return {"message": "Indices conservés depuis la première lecture de l’image.", "names": names[:6], "numbers": numbers[:6], "status": _clean(form.get("ocr_status", ""))}


def _analyse(
    connection: Any, values: dict[str, str], captured: dict[str, str],
    ocr_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Analyse le texte d’abord et transmet les compléments OCR séparément."""
    return preview_form(connection, {
        **values,
        "identity_evidence": form_evidence({**values, "ocr_names": (ocr_result or {}).get("names", ()), "ocr_numbers": (ocr_result or {}).get("numbers", ())}, captured),
        "ocr_status": (ocr_result or {}).get("status"),
        "title": values["title"],
        "description": values["description"],
        "name": values["name"],
        "set_name": values["set_name"],
        "card_number": values["card_number"],
        "language": values["language"],
        "condition": values["condition"],
        "ocr_names": (ocr_result or {}).get("names", ()),
        "ocr_numbers": (ocr_result or {}).get("numbers", ()),
        "currency": values["currency"],
    })


def _render(
    request: Request,
    *,
    platform: str,
    external_id: str,
    url: str,
    values: dict[str, str],
    captured: dict[str, str],
    preview: dict[str, Any] | None = None,
    error: str = "",
    ocr_result: dict[str, Any] | None = None,
) -> HTMLResponse:
    image_url = values.get("image_url", "")
    try:
        preview_image_url = validate_public_image_url(image_url) if image_url else None
    except ValueError:
        preview_image_url = None
    context = {
        "page": "catalog",
        "platform": platform,
        "external_id": external_id,
        "listing_url": url,
        "values": values,
        "captured": captured,
        "provenance": _provenances(values, captured),
        "preview": preview,
        "preview_image_url": preview_image_url,
        "error": error,
        "ocr_result": ocr_result,
    }
    return templates.TemplateResponse(request=request, name="capture_preview.html", context=context)


def _source_parts(form: Any) -> tuple[str, str, str]:
    """Valide la plateforme et les identifiants transmis par l'extension."""
    platform = _clean(form.get("platform", "")).lower()
    external_id = _clean(form.get("external_id", ""))[:100]
    url = _clean(form.get("url", ""))[:2048]
    if not _SOURCE_PATTERN.fullmatch(platform):
        raise ValueError("Plateforme d'annonce non reconnue.")
    if not external_id:
        raise ValueError("Identifiant d'annonce manquant.")
    if not url:
        raise ValueError("Adresse de l'annonce manquante.")
    return platform, external_id, url


@router.post("/previsualiser-capture", response_class=HTMLResponse)
async def capture_preview_page(request: Request) -> HTMLResponse:
    """Affiche la prévisualisation d'une capture transmise par l'extension.

    Aucune annonce n'est créée : la capture est analysée telle quelle et chaque
    champ est présenté avec sa provenance (extraite ou manquante).
    """
    form = await request.form()
    try:
        platform, external_id, url = _source_parts(form)
    except ValueError as error:
        return _render(request, platform="", external_id="", url="", values={}, captured={}, error=str(error))
    # La soumission initiale EST la capture : elle sert de référence pour la provenance.
    values, _ = _read_form(form)
    captured = dict(values)
    ocr_result: dict[str, Any] | None = None
    try:
        parsed = json.loads(_clean(form.get("ocr_result", "")))
        if isinstance(parsed, dict):
            recognized = parsed.get("recognized") if isinstance(parsed.get("recognized"), dict) else {}
            names = recognized.get("names") if isinstance(recognized.get("names"), list) else []
            numbers = recognized.get("numbers") if isinstance(recognized.get("numbers"), list) else []
            ocr_result = {
                "message": _clean(parsed.get("message", ""))[:500],
                "names": [_clean(x)[:100] for x in names[:6] if isinstance(x, str)],
                "numbers": [_clean(x)[:40] for x in numbers[:6] if isinstance(x, str)],
                "status": "unavailable" if parsed.get("status") == "unavailable" else "available",
            }
            values["ocr_status"] = ocr_result["status"]
    except (ValueError, TypeError):
        pass
    preview: dict[str, Any] | None = None
    error = ""
    try:
        with connect(request.app.state.settings.database_path) as connection:
            preview = _analyse(connection, values, captured, ocr_result)
            if preview:
                prefill_identity_fields(values, preview)
    except (ValueError, ProfitabilityError) as exc:
        error = str(exc)
    return _render(request, platform=platform, external_id=external_id, url=url,
                   values=values, captured=captured, preview=preview, error=error, ocr_result=ocr_result)


@router.post("/previsualiser-capture/analyser", response_class=HTMLResponse)
async def reanalyse_capture(request: Request) -> HTMLResponse:
    """Relance l'analyse en conservant corrections et indices OCR structurés."""
    form = await request.form()
    try:
        platform, external_id, url = _source_parts(form)
    except ValueError as error:
        return _render(request, platform="", external_id="", url="", values={}, captured={}, error=str(error))
    values, captured = _read_form(form)
    ocr_result = _read_ocr_hints(form)
    preview: dict[str, Any] | None = None
    error = ""
    try:
        with connect(request.app.state.settings.database_path) as connection:
            preview = _analyse(connection, values, captured, ocr_result)
            if preview:
                prefill_identity_fields(values, preview)
    except (ValueError, ProfitabilityError) as exc:
        error = str(exc)
    return _render(request, platform=platform, external_id=external_id, url=url,
                   values=values, captured=captured, preview=preview, error=error, ocr_result=ocr_result)


@router.post("/previsualiser-capture/confirmer")
async def confirm_capture(request: Request) -> Response:
    """Enregistre l'annonce confirmée via le flux transactionnel existant.

    Aucune écriture n’a lieu avant ce point. Une langue absente reste inconnue ;
    le pseudonyme vendeur est limité aux champs publics autorisés.
    """
    form = await request.form()
    try:
        platform, external_id, url = _source_parts(form)
    except ValueError as error:
        return _render(request, platform="", external_id="", url="", values={}, captured={}, error=str(error))
    values, captured = _read_form(form)
    preview = None
    try:
        values["language"] = values["language"] or "und"
        with connect(request.app.state.settings.database_path) as connection:
            preview = _analyse(connection, values, captured, _read_ocr_hints(form))
        if values["language"] not in LANGUAGES:
            raise ValueError("Langue non admise : choisissez une langue ou Inconnue.")
        if preview["field_checks"]["card_number"]["status"] == "invalid":
            raise ValueError(preview["field_checks"]["card_number"]["message"])
        if preview["identification"]["reason_code"] == "contradiction":
            raise ValueError("Preuves contradictoires : vérifiez les champs et les candidats du diagnostic avant l’ajout.")
        if not re.fullmatch(r"[A-Za-z]{3}", values["currency"]):
            raise ValueError("Indiquez la devise de l'annonce avec son code à trois lettres, par exemple EUR.")
        if "@" in values["seller"] or re.search(r"(?<!\d)(?:\+?\d[\s.()-]*){9,}(?!\d)", values["seller"]):
            raise ValueError("Indiquez uniquement un pseudonyme public, sans adresse e-mail ni numéro de téléphone.")
        price_cents = parse_euros_to_cents(values["price"], "Prix affiché")
        shipping_cents = parse_euros_to_cents(values["shipping"], "Port") if values["shipping"] else None
        raw_data: dict[str, Any] = {}
        if captured.get("title") or values["title"]:
            raw_data["title"] = captured.get("title") or values["title"]
            raw_data["edited_title"] = values["title"]
        if values["description"]:
            raw_data["description"] = values["description"]
        if values["ocr_status"] in {"available", "unavailable"}:
            raw_data["ocr_status"] = values["ocr_status"]
        data = {
            "identity_evidence": form_evidence({**values, "ocr_names": (_read_ocr_hints(form) or {}).get("names", ()), "ocr_numbers": (_read_ocr_hints(form) or {}).get("numbers", ())}, captured),
            "external_id": external_id,
            "url": url,
            "image_url": values["image_url"] or None,
            "name": values["name"] or "Annonce capturée",
            "set_name": values["set_name"] or "Non identifiée",
            "card_number": values["card_number"] or None,
            "language": values["language"],
            "condition": values["condition"] or None,
            "seller": values["seller"] or None,
            "price_cents": price_cents,
            "shipping_cents": shipping_cents,
            "currency": values["currency"].upper(),
            "description": values["description"] or None,
            "raw_data": raw_data or None,
        }
        item = CatalogItem.model_validate(data)
        content = json.dumps(item.model_dump(mode="json", exclude_none=True), ensure_ascii=False).encode("utf-8")
        with connect(request.app.state.settings.database_path) as connection:
            import_jsonl(connection, content, source_name=platform)
            row = connection.execute(
                "SELECT c.id FROM catalog_items c JOIN sources s ON s.id = c.source_id "
                "WHERE s.name = ? AND c.external_id = ?",
                (platform, external_id),
            ).fetchone()
        return RedirectResponse(f"/catalog/{row['id']}?notice=Annonce+ajout%C3%A9e", status_code=303)
    except (ValueError, ProfitabilityError, CatalogImportError, ValidationError) as error:
        message = str(error)
        if isinstance(error, CatalogImportError) and "déjà" in message:
            message = "Cette annonce existe déjà pour cette plateforme. Aucun changement n’a été enregistré."
        if isinstance(error, ValidationError):
            message = ("Adresse de l’image invalide : une URL HTTPS publique est requise."
                       if any(issue.get("loc", (None,))[0] == "image_url" for issue in error.errors())
                       else "Vérifiez le nom, l’extension, la langue et les autres champs saisis.")
        return _render(request, platform=platform, external_id=external_id, url=url,
                       values=values, captured=captured, preview=preview, error=message, ocr_result=_read_ocr_hints(form))
