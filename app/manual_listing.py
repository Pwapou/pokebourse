"""Ajout d'une annonce depuis une URL : récupération si autorisée, extraction, OCR."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit, urlunsplit

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.catalog import CatalogImportError, CatalogItem, import_jsonl, validate_public_image_url
from app.collectors.page_extract import extract_html
from app.collectors.page_fetch import PageFetchError, fetch_listing_image, fetch_listing_page, fetch_policy_for_url
from app.listing_preview import prefill_identity_fields, preview_listing, preview_form
from app.profitability import ProfitabilityError, parse_euros_to_cents
from app.storage.database import connect
from app.identification.evidence import form_evidence

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _money(cents: int | None, currency: str = "EUR") -> str:
    """Présente un montant entier sans conversion flottante."""
    if cents is None:
        return "Inconnu"
    sign = "−" if cents < 0 else ""
    absolute = abs(cents)
    return f"{sign}{absolute // 100},{absolute % 100:02d} {'€' if currency == 'EUR' else currency}"


def _percent(bps: int | None) -> str:
    """Présente des points de base en pourcentage."""
    if bps is None:
        return "Inconnu"
    sign = "−" if bps < 0 else ""
    value = abs(bps)
    return f"{sign}{value // 100},{value % 100:02d} %"


templates.env.filters["preview_money"] = _money
templates.env.filters["preview_percent"] = _percent
_DOMAINS = {
    "www.ebay.fr": "ebay", "ebay.fr": "ebay", "www.ebay.com": "ebay", "ebay.com": "ebay",
    "www.vinted.fr": "vinted", "vinted.fr": "vinted",
    "www.leboncoin.fr": "leboncoin", "leboncoin.fr": "leboncoin",
    "fr.wallapop.com": "wallapop", "es.wallapop.com": "wallapop",
    "it.wallapop.com": "wallapop", "www.wallapop.com": "wallapop", "wallapop.com": "wallapop",
}
_NAMES = {"ebay": "eBay", "vinted": "Vinted", "leboncoin": "Leboncoin", "wallapop": "Wallapop"}


def parse_listing_url(raw: str) -> dict[str, str]:
    """Reconnaît une URL officielle et propose seulement les éléments visibles dans son chemin.

    Aucun accès réseau ni redirection n'est effectué. Le titre issu d'un slug
    est une suggestion non vérifiée, jamais une preuve d'identité.
    """
    if len(raw) > 2048:
        raise ValueError("L’adresse est trop longue.")
    try:
        parts = urlsplit(raw.strip())
        host = (parts.hostname or "").lower()
        if parts.scheme.lower() != "https" or host not in _DOMAINS or parts.username or parts.password or parts.port not in (None, 443):
            raise ValueError
    except ValueError as error:
        raise ValueError("Saisissez une URL HTTPS d’annonce eBay, Vinted, Leboncoin ou Wallapop reconnue.") from error
    platform = _DOMAINS[host]
    path = unquote(parts.path)
    if platform == "ebay":
        match = re.fullmatch(r"/itm/(?:([^/]+)/)?(\d{9,15})/?", path)
        slug = match.group(1) if match else None
        external_id = match.group(2) if match else None
    elif platform == "vinted":
        match = re.fullmatch(r"/items/(\d+)(?:-([^/]+))?/?", path)
        external_id = match.group(1) if match else None
        slug = match.group(2) if match else None
    elif platform == "leboncoin":
        match = re.fullmatch(r"/ad/[^/]+/(\d+)/?", path)
        external_id = match.group(1) if match else None
        slug = None
    else:
        match = re.fullmatch(r"/item/([A-Za-z0-9][A-Za-z0-9-]{1,160})/?", path)
        external_id = match.group(1) if match else None
        slug = None
    if not external_id:
        raise ValueError("Adresse d’annonce non reconnue. Ouvrez l’annonce et copiez son URL complète, sans lien raccourci.")
    return {
        "url": urlunsplit(("https", host, parts.path, "", "")),
        "platform": platform,
        "platform_label": _NAMES[platform],
        "external_id": external_id,
        "name": re.sub(r"[-_]+", " ", slug or "").strip()[:200],
    }


_EXTRACTION_LABELS = {
    "title": "Titre de l’annonce",
    "description": "Description",
    "price_cents": "Prix affiché",
    "shipping_cents": "Frais de port",
    "currency": "Devise",
    "condition": "État déclaré",
    "image_url": "Image principale",
    "published_at": "Date de publication",
}

_SOURCE_LABELS = {
    "jsonld": "métadonnées structurées (JSON-LD)",
    "opengraph": "métadonnées Open Graph",
}

_FORM_FIELDS = (
    "url", "title", "description", "name", "set_name", "card_number", "language",
    "condition", "seller", "price", "shipping", "currency", "image_url",
    "ocr_names", "ocr_numbers",
    "captured_title", "captured_description", "captured_price", "captured_shipping",
    "captured_currency", "captured_condition", "captured_image_url",
    "proposed_name", "proposed_set_name", "proposed_card_number", "ocr_status", "proposal_source_name", "proposal_source_set_name", "proposal_source_card_number",
)

# Correspondance champs du formulaire ↔ champs extraits de la page.
_PROVENANCE_MAP = {
    "title": "title",
    "description": "description",
    "price": "price_cents",
    "shipping": "shipping_cents",
    "currency": "currency",
    "condition": "condition",
}
_PROVENANCE_BADGES = {"extraite": "green", "saisie": "neutral", "corrigée": "amber", "manquante": "red"}


def _provenance_view(values: dict[str, str], extraction: list[dict[str, Any]]) -> dict[str, Any]:
    """Provenance affichée de chaque champ : extraite, saisie, corrigée ou manquante."""
    view = {"show": False, "badge": {}, "label": {}}
    if not extraction and not any(values.get(f"captured_{key}") for key in _PROVENANCE_MAP):
        return view
    for field in _PROVENANCE_MAP:
        current = str(values.get(field) or "")
        captured = str(values.get(f"captured_{field}") or "")
        if captured and current != captured:
            label = "corrigée"
        elif captured:
            label = "extraite"
        elif current:
            label = "saisie"
        else:
            label = "manquante"
        view["label"][field] = label
        view["badge"][field] = _PROVENANCE_BADGES[label]
    view["show"] = True
    return view


def _euros(cents: int) -> str:
    """Convertit des centimes entiers en saisie « 83,25 » sans flottant."""
    return f"{cents // 100},{cents % 100:02d}"


def _retrieve_listing(request: Request, parsed: dict[str, str]) -> tuple[dict[str, str], list[dict[str, Any]], dict[str, Any] | None, str]:
    """Récupère la page autorisée, extrait les champs et lance l'OCR sur l'image.

    Retourne (valeurs préremplies, extraction avec statuts, résultat OCR, avis).
    Une valeur absente n'est jamais inventée : le champ reste « manquant ».
    Aucune annonce n'est créée ni modifiée ici.
    """
    allowed = tuple(getattr(request.app.state.settings, "page_fetch_allowed_hosts", ()) or ())
    values: dict[str, str] = {}
    extraction: list[dict[str, Any]] = []
    ocr_view: dict[str, Any] | None = None
    try:
        page = fetch_listing_page(parsed["url"], allowed_hosts=allowed)
        result = extract_html(page.content, page.final_url)
    except PageFetchError as error:
        return values, extraction, None, f"La page n’a pas pu être récupérée : {error}"
    except ValueError as error:
        return values, extraction, None, f"La page a été récupérée mais son contenu n’a pas pu être analysé : {error}"
    fields = result["fields"]
    title = str(fields.get("title", {}).get("value") or "")
    for key, label in _EXTRACTION_LABELS.items():
        entry = fields.get(key)
        if entry is not None:
            value = str(entry["value"])
            if key in {"price_cents", "shipping_cents"}:
                value = _euros(int(entry["value"]))
            extraction.append({
                "field": key, "label": label, "value": value[:300],
                "status": "proposé" if entry.get("status") == "propose" else "trouvé",
                "source": _SOURCE_LABELS.get(str(entry.get("source")), "page d’annonce"),
                "note": str(entry.get("note") or ""),
            })
        else:
            extraction.append({"field": key, "label": label, "value": "", "status": "manquant", "source": "", "note": ""})
    # Préremplissage strict : seuls les champs effectivement extraits sont proposés.
    if title:
        values["title"] = title
    description = fields.get("description")
    if description:
        values["description"] = str(description["value"])
    price = fields.get("price_cents")
    if price:
        values["price"] = _euros(int(price["value"]))
    currency = fields.get("currency")
    if currency:
        values["currency"] = str(currency["value"])
    shipping = fields.get("shipping_cents")
    if shipping:
        values["shipping"] = _euros(int(shipping["value"]))
    condition = fields.get("condition")
    if condition:
        values["condition"] = str(condition["value"])
    image = fields.get("image_url")
    if image:
        values["image_url"] = str(image["value"])
    # Le titre et la description priment : l'image n'est lue que si elle peut
    # apporter une information complémentaire à une identité encore incertaine.
    from app.identification.detector import extract_features
    from app.identification.matcher import CardMatcher
    from app.identification.ocr import analyze_image
    from app.tcgdex.cache import TcgdexCache

    lot_hint = extract_features(title or parsed.get("name") or "").is_lot
    with connect(request.app.state.settings.database_path) as connection:
        text_result = CardMatcher(TcgdexCache(connection), seed_if_empty=False, repair_index=False).identify(
            title or parsed.get("name") or "", values.get("description", "")
        )
    if lot_hint:
        ocr_view = {"status": "lot", "detail": "Annonce détectée comme lot ou produit scellé : aucune OCR unitaire lancée.", "names": [], "numbers": [], "candidates": []}
    elif text_result.status == "identified":
        ocr_view = {"status": "inutile", "detail": "Le titre et la description suffisent : OCR non lancé.", "names": [], "numbers": [], "candidates": []}
    elif not image:
        ocr_view = {"status": "absent", "detail": "Aucune image principale extraite : OCR non lancé.", "names": [], "numbers": [], "candidates": []}
    else:
        try:
            validate_public_image_url(str(image["value"]))
            fetched = fetch_listing_image(str(image["value"]), allowed_hosts=allowed)
            with connect(request.app.state.settings.database_path) as connection:
                suggestions = analyze_image(connection, fetched.content)
            ocr_view = {
                "status": "candidates" if suggestions.get("candidates") else "aucun_résultat",
                "detail": str(suggestions.get("message") or ""),
                "names": list(suggestions.get("recognized", {}).get("names", [])),
                "numbers": list(suggestions.get("recognized", {}).get("numbers", [])),
                "candidates": list(suggestions.get("candidates", [])),
            }
        except PageFetchError as error:
            ocr_view = {"status": "indisponible", "detail": f"Image principale inaccessible : {error}", "names": [], "numbers": [], "candidates": []}
        except ValueError as error:
            ocr_view = {"status": "indisponible", "detail": f"Image principale non analysable : {error}", "names": [], "numbers": [], "candidates": []}
        except RuntimeError as error:
            ocr_view = {"status": "indisponible", "detail": f"OCR indisponible : {error}", "names": [], "numbers": [], "candidates": []}
    return values, extraction, ocr_view, ""


def _read_form_values(form: Any, *, limit: int) -> dict[str, str]:
    return {key: str(form.get(key, ""))[:limit].strip() for key in _FORM_FIELDS}


def _render(
    request: Request,
    *,
    values: dict[str, str] | None = None,
    error: str = "",
    stage: str = "url",
    preview: dict | None = None,
    extraction: list[dict[str, Any]] | None = None,
    fetch_notice: str = "",
    ocr: dict[str, Any] | None = None,
) -> HTMLResponse:
    """Affiche l'étape courante sans enregistrer de données."""
    all_values = values or {}
    return templates.TemplateResponse(request=request, name="manual_listing.html", context={
        "page": "catalog", "values": all_values, "error": error, "stage": stage, "preview": preview,
        "extraction": extraction or [], "fetch_notice": fetch_notice, "ocr": ocr,
        "provenance": _provenance_view(all_values, extraction or []),
    })


@router.get("/ajouter-annonce", response_class=HTMLResponse)
def add_listing_page(request: Request) -> HTMLResponse:
    """Présente l'ajout assisté d'une annonce par URL."""
    return _render(request)


@router.post("/ajouter-annonce/preparer", response_class=HTMLResponse)
async def prepare_listing(request: Request) -> HTMLResponse:
    """Analyse l'adresse, récupère la page si autorisée, et demande la vérification."""
    form = await request.form()
    raw_url = str(form.get("url", ""))
    try:
        parsed = parse_listing_url(raw_url)
    except ValueError as error:
        return _render(request, values={"url": raw_url[:2048]}, error=str(error))
    values = dict(parsed)
    if values.get("name"):
        values["proposed_name"] = values["name"]
    extraction: list[dict[str, Any]] = []
    ocr_view: dict[str, Any] | None = None
    fetch_notice = ""
    allowed = tuple(getattr(request.app.state.settings, "page_fetch_allowed_hosts", ()) or ())
    policy = fetch_policy_for_url(parsed["url"], allowed)
    if policy["status"] == "allowed":
        retrieved, extraction, ocr_view, fetch_notice = await run_in_threadpool(_retrieve_listing, request, parsed)
        values.update(retrieved)
        # Les valeurs extraites d'origine sont conservées pour afficher la
        # provenance (extraite / corrigée) sans jamais écraser une correction.
        for key in _PROVENANCE_MAP:
            if key in retrieved:
                values[f"captured_{key}"] = retrieved[key]
        if "image_url" in retrieved:
            values["captured_image_url"] = retrieved["image_url"]
        if ocr_view:
            values["ocr_status"] = "unavailable" if ocr_view.get("status") == "indisponible" else "available"
            values["ocr_names"] = "\n".join(ocr_view.get("names", []))
            values["ocr_numbers"] = "\n".join(ocr_view.get("numbers", []))
    else:
        fetch_notice = policy["message"]
    preview = None
    if extraction:
        from app.listing_preview import preview_listing
        try:
            with connect(request.app.state.settings.database_path) as connection:
                preview = preview_form(connection, values)
            prefill_identity_fields(values, preview)
        except (ValueError, ProfitabilityError):
            fetch_notice = (fetch_notice + " Identification ou prix indisponible : vérifiez les champs et relancez l’analyse.").strip()
    return _render(request, values=values, stage="review", extraction=extraction,
                   fetch_notice=fetch_notice, ocr=ocr_view, preview=preview)


@router.post("/ajouter-annonce/analyser", response_class=HTMLResponse)
async def preview_manual_listing(request: Request) -> HTMLResponse:
    """Analyse les champs présents sans enregistrer ni modifier les corrections."""
    from app.listing_preview import preview_listing

    values = _read_form_values(await request.form(), limit=10000)
    try:
        parsed = parse_listing_url(values["url"])
        values.update({key: parsed[key] for key in ("url", "platform", "platform_label", "external_id")})
        with connect(request.app.state.settings.database_path) as connection:
            preview = preview_form(connection, values)
        prefill_identity_fields(values, preview)
        return _render(request, values=values, stage="review", preview=preview)
    except (ValueError, ProfitabilityError) as error:
        return _render(request, values=values, error=str(error), stage="review")


@router.post("/ajouter-annonce/enregistrer")
async def save_listing(request: Request) -> Response:
    """Valide les champs confirmés et les importe via le flux transactionnel existant."""
    form = await request.form()
    values = _read_form_values(form, limit=2048)
    try:
        parsed = parse_listing_url(values["url"])
    except ValueError as error:
        return _render(request, values={"url": values["url"]}, error=str(error))
    values.update({key: parsed[key] for key in ("url", "platform", "platform_label", "external_id")})
    preview = None
    try:
        # Même une soumission finale sans JavaScript garde les candidats quand
        # les montants doivent être corrigés ; aucune écriture/OCR ici.
        with connect(request.app.state.settings.database_path) as connection:
            if connection.execute(
                "SELECT 1 FROM catalog_items c JOIN sources s ON s.id=c.source_id WHERE s.name=? AND c.external_id=?",
                (parsed["platform"], parsed["external_id"]),
            ).fetchone():
                raise CatalogImportError("Cette annonce existe déjà pour cette plateforme.")
            preview = preview_form(connection, values)
        if "@" in values["seller"] or re.search(r"(?<!\d)(?:\+?\d[\s.()-]*){9,}(?!\d)", values["seller"]):
            raise ValueError("Indiquez uniquement un pseudonyme public, sans adresse e-mail ni numéro de téléphone.")
        price = parse_euros_to_cents(values["price"], "Prix affiché")
        shipping = parse_euros_to_cents(values["shipping"], "Port") if values["shipping"] else None
        if not re.fullmatch(r"[A-Za-z]{3}", values["currency"]):
            raise ValueError("Indiquez la devise de l’annonce avec son code à trois lettres, par exemple EUR.")
        values["language"] = values["language"] or "und"
        if any(check["status"] == "invalid" for check in preview["field_checks"].values()):
            raise ValueError("Vérifiez les champs d’identité invalides avant l’ajout.")
        if preview["identification"]["reason_code"] == "contradiction":
            raise ValueError("Preuves contradictoires : vérifiez les champs avant l’ajout.")
        data = {
            "identity_evidence": form_evidence(values),
            "external_id": parsed["external_id"], "url": parsed["url"], "name": values["name"],
            "set_name": values["set_name"], "card_number": values["card_number"] or None,
            "language": values["language"], "condition": values["condition"] or None,
            "seller": values["seller"] or None, "price_cents": price,
            "shipping_cents": shipping, "currency": values["currency"].upper(),
            "image_url": values["image_url"] or None,
            "description": values["description"] or None,
            "raw_data": {"title": values["captured_title"] or values["title"],
                         "edited_title": values["title"], "ocr_status": values["ocr_status"]},
        }
        item = CatalogItem.model_validate(data)
        content = json.dumps(item.model_dump(mode="json", exclude_none=True), ensure_ascii=False).encode("utf-8")
        with connect(request.app.state.settings.database_path) as connection:
            import_jsonl(connection, content, source_name=parsed["platform"])
            row = connection.execute(
                "SELECT c.id FROM catalog_items c JOIN sources s ON s.id = c.source_id WHERE s.name = ? AND c.external_id = ?",
                (parsed["platform"], parsed["external_id"]),
            ).fetchone()
        return RedirectResponse(f"/catalog/{row['id']}?notice=Annonce+ajout%C3%A9e", status_code=303)
    except (ValueError, ProfitabilityError, CatalogImportError, ValidationError) as error:
        message = str(error)
        if isinstance(error, CatalogImportError) and ("déjà" in message or "identifiant externe" in message):
            message = "Cette annonce existe déjà pour cette plateforme. Aucun changement n’a été enregistré."
        if isinstance(error, ValidationError):
            message = ("Adresse de l’image invalide : une URL HTTPS publique est requise."
                       if any(issue.get("loc", (None,))[0] == "image_url" for issue in error.errors())
                       else "Vérifiez le nom, l’extension, la langue et les autres champs saisis.")
        return _render(request, values=values, error=message, stage="review", preview=preview)
