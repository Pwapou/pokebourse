from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
import sqlite3
from typing import cast
from urllib.parse import quote

from fastapi import FastAPI, File, Form, Query, Request, UploadFile
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from app.backups import (
    backup_file,
    create_backup,
    list_backups,
    restore_backup,
)
from app.catalog import (
    MAX_IMPORT_BYTES,
    CATALOG_IDENT_STATUSES,
    CATALOG_SORTS,
    CATALOG_SOURCES,
    CatalogImportError,
    catalog_data,
    catalog_export_rows,
    catalog_item_detail,
    dashboard_data,
    delete_import_batch,
    import_batch_detail,
    import_failures_report,
    import_jsonl,
    import_listings_from_extension,
    recent_import_failures,
    record_import_failure,
    reidentify_catalog_item,
)
from app.catalog_export import CSV_FILENAME, build_catalog_csv
from app.collectors.models import CollectorError
from app.config import Settings
from app.identification.models import IDENTIFICATION_STATUS_LABELS
from app.monitoring.models import WatchInput, WatchNotFoundError, WatchValidationError
from app.monitoring.service import WatchService
from app.profitability import (
    REFERENCE_KIND_LABELS,
    VERDICT_LABELS,
    FeeProfileUpdate,
    ProfitabilityError,
    ReferenceInput,
    SortOrder,
    delete_reference,
    build_market_index,
    enrich_catalog_items,
    evaluate_listing,
    get_active_fee_profile,
    import_references_jsonl,
    parse_euros_to_cents,
    parse_percent_to_bps,
    profitability_dashboard_summary,
    profitability_page_data,
    update_active_fee_profile,
    upsert_reference,
)
from app.storage.database import connect
from app.storage.migration_runner import apply_migrations, check_database
from app.sellers import repository as seller_repository
from app.sellers.models import (
    ReliabilityRating,
    SellerProfile,
    profile_from_row,
    reliability_rating,
)
from app.sellers.service import SellerService
from app.supervision.models import (
    AGENT_STATES,
    ERROR_CODE_LABELS,
    STATE_LABELS,
    SupervisionThresholds,
)
from app.supervision.service import SupervisionService

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

VALID_SORTS: set[str] = {"profit_desc", "roi_desc", "price_asc"}
VALID_VERDICTS: set[str] = {"all", *VERDICT_LABELS.keys()}


def format_money(cents: int | None, currency: str = "EUR") -> str:
    if cents is None:
        return "—"
    amount = f"{cents / 100:,.2f}".replace(",", " ").replace(".", ",")
    return f"{amount} €" if currency == "EUR" else f"{amount} {currency}"


def format_signed_money(cents: int | None, currency: str = "EUR") -> str:
    if cents is None:
        return "—"
    prefix = "+" if cents > 0 else ""
    return f"{prefix}{format_money(cents, currency)}"


def format_bps_percent(bps: int | None, signed: bool = False) -> str:
    if bps is None:
        return "—"
    prefix = "+" if signed and bps > 0 else ""
    amount = f"{bps / 100:.1f}".replace(".", ",")
    return f"{prefix}{amount} %"


def format_cents_input(cents: int | None) -> str:
    if cents is None:
        return ""
    return f"{cents / 100:.2f}".replace(".", ",")


def format_bps_input(bps: int | None) -> str:
    if bps is None:
        return ""
    if bps % 100 == 0:
        return str(bps // 100)
    return f"{bps / 100:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def format_date(value: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").strftime("%d/%m/%Y · %H:%M")
    except ValueError:
        return value


def format_filesize(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} o"
    value = float(size_bytes)
    for unit in ("Kio", "Mio", "Gio"):
        value /= 1024
        if value < 1024:
            return f"{value:.1f}".replace(".", ",") + f" {unit}"
    return f"{value:.1f} Tio".replace(".", ",")


templates.env.filters["money"] = format_money
templates.env.filters["signed_money"] = format_signed_money
templates.env.filters["bps_percent"] = format_bps_percent
templates.env.filters["cents_input"] = format_cents_input
templates.env.filters["bps_input"] = format_bps_input
templates.env.filters["date"] = format_date
templates.env.filters["filesize"] = format_filesize


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings = Settings.from_env()
    application.state.settings = settings
    with connect(settings.database_path) as connection:
        apply_migrations(connection)
    yield


app = FastAPI(title="Pokébourse", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


def settings_from(request: Request) -> Settings:
    return request.app.state.settings


def watch_service_from(request: Request) -> WatchService:
    settings = settings_from(request)
    return WatchService(min_interval_seconds=settings.min_watch_interval_seconds)


def supervision_service_from(request: Request) -> SupervisionService:
    settings = settings_from(request)
    return SupervisionService(
        settings.database_path,
        thresholds=settings.supervision_thresholds(),
        agent_key=settings.agent_key,
        ip_probe_url=settings.supervision_ip_probe_url,
    )


def seller_service_from(request: Request) -> SellerService:
    settings = settings_from(request)
    return SellerService(
        per_tick=settings.seller_enrichment_per_tick,
        cache_seconds=settings.seller_cache_seconds,
    )


def _seller_rating_for_item(
    connection: sqlite3.Connection, service: SellerService, item: object
) -> ReliabilityRating:
    def getter(key: str) -> object:
        try:
            return item[key]  # type: ignore[index]
        except (KeyError, IndexError, TypeError):
            return getattr(item, key, None)

    row = service.profile_for_item(
        connection,
        platform=getter("source_name"),
        seller_profile_id=getter("seller_profile_id"),
        seller_external_id=getter("seller_external_id"),
    )
    if row is None:
        return reliability_rating(None)
    return reliability_rating(profile_from_row(row))


STATE_BADGE_CLASSES: dict[str, str] = {
    "starting": "blue",
    "operational": "green",
    "degraded": "amber",
    "blocked": "red",
    "offline": "neutral",
    "stopped": "neutral",
}


def _supervision_authorized(request: Request) -> bool:
    """Restreint l'API de supervision lorsqu'un jeton est configuré."""

    settings = settings_from(request)
    if not settings.supervision_token:
        return True
    header = request.headers.get("X-Supervision-Token", "")
    authorization = request.headers.get("Authorization", "")
    expected = settings.supervision_token
    return header == expected or authorization == f"Bearer {expected}"


def _validation_details(error: ValidationError) -> str:
    labels = {
        "platform": "plateforme",
        "name": "nom",
        "search_text": "mots-clés",
        "price_from": "prix minimum",
        "price_to": "prix maximum",
        "interval_seconds": "intervalle",
        "category": "catégorie",
    }
    issues = []
    for issue in error.errors()[:3]:
        field = next((str(part) for part in issue.get("loc", ()) if str(part) != "value"), "")
        label = labels.get(field, field or "paramètre")
        issues.append(f"{label} : {issue.get('msg', 'valeur invalide')}")
    return "; ".join(issues) or "Paramètres invalides."


def _optional_euros_to_cents(value: str, label: str) -> int | None:
    if not value.strip():
        return None
    return parse_euros_to_cents(value, label)


@app.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    imported: int | None = Query(default=None, ge=0),
    error: str | None = Query(default=None, max_length=600),
    notice: str | None = Query(default=None, max_length=300),
) -> HTMLResponse:
    with connect(settings_from(request).database_path) as connection:
        check_database(connection)
        data = dashboard_data(connection)
        failures = recent_import_failures(connection)
        profit_data = profitability_dashboard_summary(connection)
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "page": "dashboard",
            "imported": imported,
            "error": error,
            "notice": notice,
            "failures": failures,
            **data,
            **profit_data,
        },
    )


@app.get("/catalog", response_class=HTMLResponse)
def catalog(
    request: Request,
    q: str = Query(default="", max_length=100),
    set_name: str = Query(default="", max_length=200),
    source: str = Query(default="all", max_length=20),
    ident: str = Query(default="all", max_length=20),
    sort: str = Query(default="", max_length=30),
    page: int = Query(default=1),
) -> HTMLResponse:
    with connect(settings_from(request).database_path) as connection:
        data = catalog_data(
            connection,
            query=q.strip(),
            set_name=set_name,
            source=source,
            ident_status=ident,
            sort=sort,
            page=page,
        )
        enriched_items, fee_profile = enrich_catalog_items(connection, data["items"])
        seller_service = seller_service_from(request)
        seller_ratings = {
            int(item["id"]): _seller_rating_for_item(connection, seller_service, item)
            for item in data["items"]
        }
    return templates.TemplateResponse(
        request=request,
        name="catalog.html",
        context={
            "page": "catalog",
            "query": q,
            "selected_set": set_name,
            "source_options": CATALOG_SOURCES,
            "selected_source": data["source"],
            "ident_status_options": CATALOG_IDENT_STATUSES,
            "selected_ident": data["ident_status"],
            "ident_labels": IDENTIFICATION_STATUS_LABELS,
            "sort_options": CATALOG_SORTS,
            "selected_sort": data["sort"],
            "total": data["total"],
            "sets": data["sets"],
            "items": enriched_items,
            "seller_ratings": seller_ratings,
            "fee_profile": fee_profile,
            "current_page": data["page"],
            "total_pages": data["total_pages"],
            "range_start": data["range_start"],
            "range_end": data["range_end"],
        },
    )


@app.get("/catalog/export.csv")
def catalog_export(
    request: Request,
    q: str = Query(default="", max_length=100),
    set_name: str = Query(default="", max_length=200),
    source: str = Query(default="all", max_length=20),
    ident: str = Query(default="all", max_length=20),
) -> Response:
    with connect(settings_from(request).database_path) as connection:
        rows = catalog_export_rows(
            connection,
            query=q.strip(),
            set_name=set_name,
            source=source,
            ident_status=ident,
        )
    return Response(
        content=build_catalog_csv(rows),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{CSV_FILENAME}"'},
    )


@app.post("/catalog/{item_id}/reidentify")
def reidentify_item(request: Request, item_id: int) -> RedirectResponse:
    with connect(settings_from(request).database_path) as connection:
        result = reidentify_catalog_item(connection, item_id)
        if not result:
            return RedirectResponse(url="/catalog?error=Annonce+introuvable", status_code=303)
    return RedirectResponse(
        url=f"/catalog/{item_id}?notice=Identification+r%C3%A9examin%C3%A9e",
        status_code=303,
    )


@app.get("/catalog/{item_id}", response_class=HTMLResponse)
def catalog_item(
    request: Request,
    item_id: int,
    notice: str | None = Query(default=None, max_length=200),
) -> HTMLResponse:
    with connect(settings_from(request).database_path) as connection:
        item = catalog_item_detail(connection, item_id)
        seller_profile_row = None
        if item is not None:
            fee_profile = get_active_fee_profile(connection)
            market_index = build_market_index(
                connection, fee_profile.min_catalog_samples
            )
            evaluation = evaluate_listing(item, fee_profile, market_index)
            seller_profile_row = seller_service_from(request).profile_for_item(
                connection,
                platform=item["source_name"],
                seller_profile_id=item["seller_profile_id"],
                seller_external_id=item["seller_external_id"],
            )
    if item is None:
        return templates.TemplateResponse(
            request=request,
            name="404.html",
            context={"page": "", "message": "Cette annonce n'existe pas ou a été retirée du catalogue."},
            status_code=404,
        )
    seller_profile = profile_from_row(seller_profile_row)
    return templates.TemplateResponse(
        request=request,
        name="catalog_detail.html",
        context={
            "page": "catalog",
            "item": item,
            "evaluation": evaluation,
            "fee_profile": fee_profile,
            "seller_profile": seller_profile,
            "seller_rating": reliability_rating(seller_profile),
            "notice": notice,
            "ident_labels": IDENTIFICATION_STATUS_LABELS,
        },
    )


@app.post("/catalog/{item_id}/purchase")
def catalog_item_purchase(
    request: Request,
    item_id: int,
    price_paid: float = Form(..., ge=0),
    shipping_paid: float = Form(default=0.0, ge=0),
    status: str = Form(default="recu"),
    notes: str | None = Form(default=None),
) -> RedirectResponse:
    with connect(settings_from(request).database_path) as connection:
        item = catalog_item_detail(connection, item_id)
        if item is None:
            return templates.TemplateResponse(
                request=request,
                name="404.html",
                context={"page": "catalog", "message": "Cette annonce n'existe pas."},
                status_code=404,
            )

        seller_profile_id = item["seller_profile_id"]
        if seller_profile_id is None and item["seller"]:
            platform = item["source_name"] if item["source_name"] in ("vinted", "leboncoin") else "vinted"
            ext_id = item["seller_external_id"] or f"seller-{item['seller']}"
            existing_pid = seller_repository.find_profile_id(
                connection, platform=platform, seller_external_id=ext_id
            )
            if existing_pid is not None:
                seller_profile_id = existing_pid
            else:
                seller_profile_id = seller_repository.upsert_profile(
                    connection,
                    SellerProfile(
                        platform=platform,
                        seller_external_id=ext_id,
                        login=item["seller"],
                        fetched_at=datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                    ),
                )
            seller_repository.link_catalog_item(connection, item_id=item_id, profile_id=seller_profile_id)

        seller_repository.record_purchase(
            connection,
            catalog_item_id=item_id,
            seller_profile_id=seller_profile_id,
            seller_name=item["seller"] or "Vendeur",
            card_name=item["name"],
            set_name=item["set_name"],
            card_number=item["card_number"],
            condition=item["condition"],
            price_paid_cents=round(price_paid * 100),
            shipping_paid_cents=round(shipping_paid * 100),
            currency=item["currency"] or "EUR",
            platform=item["source_name"],
            status=status if status in ("commande", "recu", "en_vente", "vendu") else "recu",
            notes=notes.strip() if notes and notes.strip() else None,
        )

    msg = quote("Achat enregistré avec succès ! Vos statistiques et l'historique vendeur ont été actualisés.")
    return RedirectResponse(
        url=f"/catalog/{item_id}?notice={msg}",
        status_code=303,
    )


@app.get("/sellers", response_class=HTMLResponse)
def sellers_directory(
    request: Request,
    platform: str = Query(default="all", max_length=20),
    sort: str = Query(default="reputation", max_length=30),
    favorites: int = Query(default=0),
    q: str = Query(default="", max_length=100),
    notice: str | None = Query(default=None, max_length=200),
) -> HTMLResponse:
    with connect(settings_from(request).database_path) as connection:
        service = seller_service_from(request)
        sellers = service.list_sellers_directory(
            connection,
            platform=platform if platform in ("vinted", "leboncoin") else None,
            sort=sort if sort in ("reputation", "opportunities", "purchases", "name") else "reputation",
            only_favorites=bool(favorites),
            query=q.strip(),
        )
    return templates.TemplateResponse(
        request=request,
        name="sellers.html",
        context={
            "page": "sellers",
            "sellers": sellers,
            "total": len(sellers),
            "selected_platform": platform,
            "selected_sort": sort,
            "only_favorites": bool(favorites),
            "query": q,
            "notice": notice,
        },
    )


@app.get("/sellers/{seller_id}", response_class=HTMLResponse)
def seller_detail(
    request: Request,
    seller_id: int,
    notice: str | None = Query(default=None, max_length=200),
) -> HTMLResponse:
    with connect(settings_from(request).database_path) as connection:
        service = seller_service_from(request)
        summary = service.get_seller_summary(connection, seller_id)
        if summary is None:
            return templates.TemplateResponse(
                request=request,
                name="404.html",
                context={"page": "sellers", "message": "Ce profil vendeur n'existe pas."},
                status_code=404,
            )
    return templates.TemplateResponse(
        request=request,
        name="seller_detail.html",
        context={
            "page": "sellers",
            "notice": notice,
            **summary,
        },
    )


@app.post("/sellers/{seller_id}/favorite")
def seller_favorite_toggle(
    request: Request,
    seller_id: int,
    is_favorite: int = Form(default=1),
) -> RedirectResponse:
    with connect(settings_from(request).database_path) as connection:
        seller_repository.set_favorite(connection, seller_id, is_favorite == 1)
    msg = quote("Vendeur ajouté à vos favoris ❤️" if is_favorite == 1 else "Vendeur retiré de vos favoris.")
    return RedirectResponse(
        url=f"/sellers/{seller_id}?notice={msg}",
        status_code=303,
    )


@app.post("/sellers/{seller_id}/notes")
def seller_notes_save(
    request: Request,
    seller_id: int,
    notes: str = Form(default=""),
) -> RedirectResponse:
    with connect(settings_from(request).database_path) as connection:
        seller_repository.set_user_notes(connection, seller_id, notes)
    msg = quote("Notes personnelles enregistrées.")
    return RedirectResponse(
        url=f"/sellers/{seller_id}?notice={msg}",
        status_code=303,
    )


@app.post("/sellers/{seller_id}/purchase")
def seller_add_purchase(
    request: Request,
    seller_id: int,
    card_name: str = Form(..., min_length=1, max_length=200),
    set_name: str | None = Form(default=None, max_length=200),
    card_number: str | None = Form(default=None, max_length=50),
    condition: str | None = Form(default=None, max_length=50),
    price_paid: float = Form(..., ge=0),
    shipping_paid: float = Form(default=0.0, ge=0),
    status: str = Form(default="recu"),
    notes: str | None = Form(default=None),
) -> RedirectResponse:
    with connect(settings_from(request).database_path) as connection:
        raw_seller = seller_repository.get_profile(connection, seller_id)
        if raw_seller is None:
            return templates.TemplateResponse(
                request=request,
                name="404.html",
                context={"page": "sellers", "message": "Vendeur introuvable."},
                status_code=404,
            )

        seller_name = raw_seller.get("login") or raw_seller.get("seller_external_id") or "Vendeur"
        platform = raw_seller.get("platform")
        seller_repository.record_purchase(
            connection,
            seller_profile_id=seller_id,
            seller_name=seller_name,
            card_name=card_name.strip(),
            set_name=set_name.strip() if set_name else None,
            card_number=card_number.strip() if card_number else None,
            condition=condition.strip() if condition else None,
            price_paid_cents=round(price_paid * 100),
            shipping_paid_cents=round(shipping_paid * 100),
            platform=platform,
            status=status if status in ("commande", "recu", "en_vente", "vendu") else "recu",
            notes=notes.strip() if notes and notes.strip() else None,
        )
    msg = quote("Achat enregistré avec succès auprès de ce vendeur !")
    return RedirectResponse(
        url=f"/sellers/{seller_id}?notice={msg}",
        status_code=303,
    )


@app.get("/profitability", response_class=HTMLResponse)
def profitability(
    request: Request,
    q: str = Query(default="", max_length=100),
    set_name: str = Query(default="", max_length=200),
    verdict: str = Query(default="all", max_length=30),
    sort: str = Query(default="profit_desc", max_length=30),
    notice: str | None = Query(default=None, max_length=300),
    error: str | None = Query(default=None, max_length=600),
    prefill_name: str = Query(default="", max_length=200),
    prefill_set: str = Query(default="", max_length=200),
    prefill_number: str = Query(default="", max_length=50),
    prefill_lang: str = Query(default="fr", max_length=20),
    prefill_condition: str = Query(default="", max_length=100),
    prefill_variant: str = Query(default="", max_length=100),
    prefill_edition: str = Query(default="", max_length=100),
    prefill_grading_company: str = Query(default="", max_length=30),
    prefill_grade: str = Query(default="", max_length=30),
    prefill_certification_number: str = Query(default="", max_length=100),
    prefill_price: str = Query(default="", max_length=30),
    prefill_source_name: str = Query(default="", max_length=100),
    prefill_reference_kind: str = Query(default="", max_length=30),
    prefill_observed_at: str = Query(default="", max_length=10),
    prefill_source_url: str = Query(default="", max_length=2048),
    prefill_sample_size: str = Query(default="", max_length=10),
    prefill_note: str = Query(default="", max_length=300),
) -> HTMLResponse:
    active_verdict = verdict if verdict in VALID_VERDICTS else "all"
    active_sort = cast(SortOrder, sort if sort in VALID_SORTS else "profit_desc")
    with connect(settings_from(request).database_path) as connection:
        check_database(connection)
        data = profitability_page_data(
            connection,
            query=q.strip(),
            set_name=set_name,
            verdict=active_verdict,
            sort=active_sort,
        )
    return templates.TemplateResponse(
        request=request,
        name="profitability.html",
        context={
            "page": "profitability",
            "query": q,
            "selected_set": set_name,
            "selected_verdict": active_verdict,
            "selected_sort": active_sort,
            "notice": notice,
            "error": error,
            "reference_kind_labels": REFERENCE_KIND_LABELS,
            "prefill": {
                "name": prefill_name,
                "set_name": prefill_set,
                "card_number": prefill_number,
                "language": prefill_lang or "fr",
                "condition": prefill_condition,
                "variant": prefill_variant,
                "edition": prefill_edition,
                "grading_company": prefill_grading_company,
                "grade": prefill_grade,
                "certification_number": prefill_certification_number,
                "price": prefill_price,
                "source_name": prefill_source_name,
                "reference_kind": prefill_reference_kind,
                "observed_at": prefill_observed_at,
                "source_url": prefill_source_url,
                "sample_size": prefill_sample_size,
                "note": prefill_note,
            },
            **data,
        },
    )


@app.post("/profitability/settings")
def save_profitability_settings(
    request: Request,
    buyer_shipping_euros: str = Form(...),
    platform_fee_percent: str = Form(...),
    seller_fixed_fee_euros: str = Form(...),
    shipping_packaging_euros: str = Form(...),
    min_net_profit_euros: str = Form(...),
    min_roi_percent: str = Form(...),
    min_catalog_samples: str = Form(default="2"),
) -> RedirectResponse:
    try:
        try:
            samples = int(min_catalog_samples.strip())
        except ValueError as error:
            raise ProfitabilityError(
                "L'échantillon minimum doit être un entier compris entre 2 et 100."
            ) from error
        if not 2 <= samples <= 100:
            raise ProfitabilityError(
                "L'échantillon minimum doit être compris entre 2 et 100."
            )
        update = FeeProfileUpdate(
            buyer_shipping_cents=(
                parse_euros_to_cents(buyer_shipping_euros, "Port aller")
                if buyer_shipping_euros.strip()
                else None
            ),
            platform_fee_bps=(
                parse_percent_to_bps(
                    platform_fee_percent, "Commission plateforme", max_bps=10_000
                )
                if platform_fee_percent.strip()
                else None
            ),
            seller_fixed_fee_cents=(
                parse_euros_to_cents(seller_fixed_fee_euros, "Frais fixes vendeur")
                if seller_fixed_fee_euros.strip()
                else None
            ),
            shipping_packaging_cents=(
                parse_euros_to_cents(
                    shipping_packaging_euros, "Expédition et emballage"
                )
                if shipping_packaging_euros.strip()
                else None
            ),
            min_net_profit_cents=parse_euros_to_cents(
                min_net_profit_euros, "Gain net minimum"
            ),
            min_roi_bps=parse_percent_to_bps(
                min_roi_percent, "ROI minimum", max_bps=100_000
            ),
            min_catalog_samples=samples,
        )
        with connect(settings_from(request).database_path) as connection:
            update_active_fee_profile(connection, update)
    except (ProfitabilityError, ValidationError) as error:
        message = (
            error.errors()[0]["msg"]
            if isinstance(error, ValidationError)
            else str(error)
        )
        return RedirectResponse(
            f"/profitability?error={quote(message)}#parametres", status_code=303
        )
    return RedirectResponse(
        f"/profitability?notice={quote('Paramètres de rentabilité enregistrés.')}#parametres",
        status_code=303,
    )


@app.post("/profitability/references")
def save_reference_cote(
    request: Request,
    name: str = Form(...),
    set_name: str = Form(...),
    card_number: str = Form(default=""),
    language: str = Form(default="fr"),
    condition: str = Form(default=""),
    variant: str = Form(default=""),
    edition: str = Form(default=""),
    grading_company: str = Form(default=""),
    grade: str = Form(default=""),
    certification_number: str = Form(default=""),
    reference_price_euros: str = Form(...),
    currency: str = Form(default="EUR"),
    source_name: str = Form(default=""),
    reference_kind: str = Form(default=""),
    observed_at: str = Form(default=""),
    source_url: str = Form(default=""),
    sample_size: str = Form(default=""),
    note: str = Form(default=""),
) -> RedirectResponse:
    try:
        price_cents = parse_euros_to_cents(reference_price_euros, "Prix de référence")
        try:
            parsed_sample_size = int(sample_size) if sample_size.strip() else None
        except ValueError as error:
            raise ProfitabilityError(
                "La taille de l’échantillon doit être un entier positif."
            ) from error
        reference = ReferenceInput(
            name=name,
            set_name=set_name,
            card_number=card_number or None,
            language=language or "fr",
            condition=condition or None,
            variant=variant or None,
            edition=edition or None,
            grading_company=grading_company or None,
            grade=grade or None,
            certification_number=certification_number or None,
            reference_price_cents=price_cents,
            currency=currency or "EUR",
            source_name=source_name or None,
            reference_kind=reference_kind or None,
            observed_at=observed_at or None,
            source_url=source_url or None,
            sample_size=parsed_sample_size,
            note=note or None,
        )
        with connect(settings_from(request).database_path) as connection:
            upsert_reference(connection, reference, source_kind="manual")
    except (ProfitabilityError, ValidationError) as error:
        if isinstance(error, ValidationError):
            details = "; ".join(
                f"{'.'.join(str(part) for part in issue['loc'])} : {issue['msg']}"
                for issue in error.errors()[:2]
            )
        else:
            details = str(error)
        return RedirectResponse(
            f"/profitability?error={quote(details)}#cotes", status_code=303
        )
    return RedirectResponse(
        f"/profitability?notice={quote(f'Cote enregistrée pour {reference.name}.')}#cotes",
        status_code=303,
    )


@app.post("/profitability/references/import")
async def import_reference_cotes(
    request: Request, file: UploadFile = File(...)
) -> RedirectResponse:
    try:
        content = await file.read(MAX_IMPORT_BYTES + 1)
        with connect(settings_from(request).database_path) as connection:
            count = import_references_jsonl(connection, content)
    except ProfitabilityError as error:
        return RedirectResponse(
            f"/profitability?error={quote(str(error))}#cotes", status_code=303
        )
    finally:
        await file.close()
    return RedirectResponse(
        f"/profitability?notice={quote(f'{count} cote(s) importée(s) ou mise(s) à jour.')}#cotes",
        status_code=303,
    )


@app.post("/profitability/references/{reference_id}/delete")
def remove_reference_cote(request: Request, reference_id: int) -> RedirectResponse:
    with connect(settings_from(request).database_path) as connection:
        deleted = delete_reference(connection, reference_id)
    if not deleted:
        return RedirectResponse(
            f"/profitability?error={quote('Cote introuvable.')}#cotes", status_code=303
        )
    return RedirectResponse(
        f"/profitability?notice={quote('Cote supprimée.')}#cotes", status_code=303
    )


@app.get("/watches", response_class=HTMLResponse)
def watches_page(
    request: Request,
    notice: str | None = Query(default=None, max_length=300),
    error: str | None = Query(default=None, max_length=600),
) -> HTMLResponse:
    settings = settings_from(request)
    with connect(settings.database_path) as connection:
        check_database(connection)
        watches = watch_service_from(request).list_watches(connection)
    return templates.TemplateResponse(
        request=request,
        name="watches.html",
        context={
            "page": "watches",
            "watches": watches,
            "notice": notice,
            "error": error,
            "min_interval_seconds": settings.min_watch_interval_seconds,
            "default_interval_seconds": max(
                120, settings.min_watch_interval_seconds
            ),
        },
    )


@app.post("/watches")
def create_watch_web(
    request: Request,
    platform: str = Form(..., max_length=20),
    name: str = Form(..., max_length=120),
    search_text: str = Form(..., max_length=200),
    price_min_euros: str = Form(default="", max_length=30),
    price_max_euros: str = Form(default="", max_length=30),
    interval_seconds: str = Form(default="120", max_length=10),
    category: str = Form(default="", max_length=100),
) -> RedirectResponse:
    try:
        price_from = _optional_euros_to_cents(price_min_euros, "Prix minimum")
        price_to = _optional_euros_to_cents(price_max_euros, "Prix maximum")
        try:
            parsed_interval = int(interval_seconds.strip())
        except ValueError as error:
            raise WatchValidationError(
                "L'intervalle doit être un nombre entier de secondes."
            ) from error
        watch = WatchInput(
            platform=platform,  # type: ignore[arg-type]
            name=name,
            search_text=search_text,
            price_from=price_from,
            price_to=price_to,
            interval_seconds=parsed_interval,
            category=category.strip() or None,
        )
        with connect(settings_from(request).database_path) as connection:
            watch_id = watch_service_from(request).create_watch(connection, watch)
    except ProfitabilityError as error:
        return RedirectResponse(f"/watches?error={quote(str(error))}", status_code=303)
    except WatchValidationError as error:
        return RedirectResponse(f"/watches?error={quote(str(error))}", status_code=303)
    except ValidationError as error:
        return RedirectResponse(
            f"/watches?error={quote(_validation_details(error))}", status_code=303
        )
    return RedirectResponse(
        f"/watches?notice={quote(f'Veille #{watch_id} créée et activée.')}",
        status_code=303,
    )


@app.post("/watches/{watch_id}/pause")
def pause_watch_web(request: Request, watch_id: int) -> RedirectResponse:
    try:
        with connect(settings_from(request).database_path) as connection:
            watch_service_from(request).pause_watch(connection, watch_id)
    except WatchNotFoundError:
        return RedirectResponse(
            f"/watches?error={quote('Veille introuvable.')}", status_code=303
        )
    return RedirectResponse(
        f"/watches?notice={quote(f'Veille #{watch_id} mise en pause.')}", status_code=303
    )


@app.post("/watches/{watch_id}/resume")
def resume_watch_web(request: Request, watch_id: int) -> RedirectResponse:
    try:
        with connect(settings_from(request).database_path) as connection:
            watch_service_from(request).resume_watch(connection, watch_id)
    except WatchNotFoundError:
        return RedirectResponse(
            f"/watches?error={quote('Veille introuvable.')}", status_code=303
        )
    return RedirectResponse(
        f"/watches?notice={quote(f'Veille #{watch_id} réactivée.')}", status_code=303
    )


@app.post("/watches/{watch_id}/run")
def run_watch_web(request: Request, watch_id: int) -> RedirectResponse:
    try:
        with connect(settings_from(request).database_path) as connection:
            summary = watch_service_from(request).run_watch_once(connection, watch_id)
    except WatchNotFoundError:
        return RedirectResponse(
            f"/watches?error={quote('Veille introuvable.')}", status_code=303
        )
    except (CollectorError, WatchValidationError) as error:
        return RedirectResponse(
            f"/watches?error={quote(str(error))}", status_code=303
        )
    message = (
        f"Contrôle exécuté : {summary['result_count']} résultat(s), "
        f"{summary['created_count']} nouveau(x), {summary['updated_count']} mis à jour."
    )
    return RedirectResponse(f"/watches?notice={quote(message)}", status_code=303)


@app.post("/watches/{watch_id}/delete")
def delete_watch_web(
    request: Request, watch_id: int, confirm: str = Form(default="")
) -> RedirectResponse:
    if confirm != "yes":
        return RedirectResponse(
            f"/watches?error={quote('Suppression annulée : confirmation explicite requise.')}",
            status_code=303,
        )
    try:
        with connect(settings_from(request).database_path) as connection:
            watch_service_from(request).delete_watch(connection, watch_id)
    except WatchNotFoundError:
        return RedirectResponse(
            f"/watches?error={quote('Veille introuvable.')}", status_code=303
        )
    return RedirectResponse(
        f"/watches?notice={quote(f'Veille #{watch_id} supprimée.')}", status_code=303
    )


@app.post("/imports")
async def create_import(request: Request, file: UploadFile = File(...)) -> Response:
    filename = Path(file.filename or "import.jsonl").name
    is_json = "application/json" in request.headers.get("accept", "")
    try:
        content = await file.read(MAX_IMPORT_BYTES + 1)
        try:
            with connect(settings_from(request).database_path) as connection:
                if is_json:
                    evaluations = import_listings_from_extension(connection, content)
                    return JSONResponse(
                        {
                            "status": "ok",
                            "imported": len(evaluations),
                            "evaluations": evaluations,
                        }
                    )
                imported = import_jsonl(connection, content)
        except CatalogImportError as error:
            with connect(settings_from(request).database_path) as connection:
                record_import_failure(
                    connection,
                    source_name="import-web",
                    filename=filename,
                    content=content,
                    error_message=str(error),
                )
            if is_json:
                return JSONResponse(
                    status_code=400,
                    content={"status": "error", "detail": str(error)},
                )
            return RedirectResponse(f"/?error={quote(str(error))}", status_code=303)
    finally:
        await file.close()
    return RedirectResponse(f"/?imported={imported}", status_code=303)


@app.get("/imports/failures/report")
def download_import_failures_report(request: Request) -> PlainTextResponse:
    with connect(settings_from(request).database_path) as connection:
        report = import_failures_report(connection)
    return PlainTextResponse(
        report,
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="rapport-echecs-import.txt"'
        },
    )


@app.get("/imports/{batch_id}", response_class=HTMLResponse, response_model=None)
def import_batch_page(
    request: Request,
    batch_id: int,
    error: str | None = Query(default=None, max_length=600),
) -> HTMLResponse | RedirectResponse:
    with connect(settings_from(request).database_path) as connection:
        detail = import_batch_detail(connection, batch_id)
    if detail is None:
        return RedirectResponse(
            f"/?error={quote('Lot d’import introuvable.')}", status_code=303
        )
    return templates.TemplateResponse(
        request=request,
        name="import_detail.html",
        context={"page": "imports", "error": error, **detail},
    )


@app.post("/imports/{batch_id}/delete")
def remove_import_batch(
    request: Request, batch_id: int, confirm: str = Form(default="")
) -> RedirectResponse:
    if confirm != "yes":
        return RedirectResponse(
            f"/imports/{batch_id}?error={quote('Suppression annulée : confirmation explicite requise.')}",
            status_code=303,
        )
    with connect(settings_from(request).database_path) as connection:
        deleted = delete_import_batch(connection, batch_id)
    if not deleted:
        return RedirectResponse(
            f"/?error={quote('Lot d’import introuvable.')}", status_code=303
        )
    return RedirectResponse(
        f"/?notice={quote('Lot supprimé avec ses annonces associées.')}",
        status_code=303,
    )


@app.get("/backups", response_class=HTMLResponse)
def backups_page(
    request: Request,
    notice: str | None = Query(default=None, max_length=300),
    error: str | None = Query(default=None, max_length=600),
) -> HTMLResponse:
    settings = settings_from(request)
    return templates.TemplateResponse(
        request=request,
        name="backups.html",
        context={
            "page": "backups",
            "notice": notice,
            "error": error,
            "backups": list_backups(settings.database_path),
        },
    )


@app.post("/backups")
def create_backup_web(request: Request) -> RedirectResponse:
    try:
        destination = create_backup(settings_from(request).database_path)
    except (OSError, sqlite3.Error, RuntimeError) as error:
        return RedirectResponse(
            f"/backups?error={quote(str(error))}", status_code=303
        )
    return RedirectResponse(
        f"/backups?notice={quote(f'Sauvegarde créée : {destination.name}')}",
        status_code=303,
    )


@app.get("/backups/download", response_model=None)
def download_backup(
    request: Request, name: str = Query(..., max_length=200)
) -> FileResponse | RedirectResponse:
    try:
        path = backup_file(settings_from(request).database_path, name)
    except RuntimeError:
        return RedirectResponse(
            f"/backups?error={quote('Sauvegarde introuvable ou nom invalide.')}",
            status_code=303,
        )
    return FileResponse(path, media_type="application/octet-stream", filename=name)


@app.post("/backups/restore")
def restore_backup_web(
    request: Request, name: str = Form(...), confirm: str = Form(default="")
) -> RedirectResponse:
    if confirm != "yes":
        return RedirectResponse(
            f"/backups?error={quote('Restauration annulée : confirmation explicite requise.')}",
            status_code=303,
        )
    settings = settings_from(request)
    try:
        path = backup_file(settings.database_path, name)
        safety_backup = restore_backup(settings.database_path, path)
    except (OSError, sqlite3.Error, RuntimeError) as error:
        return RedirectResponse(
            f"/backups?error={quote(str(error))}", status_code=303
        )
    notice = f"Base restaurée depuis {name}."
    if safety_backup is not None:
        notice += f" Sauvegarde de sécurité : {safety_backup.name}."
    return RedirectResponse(f"/backups?notice={quote(notice)}", status_code=303)


@app.get("/agents", response_class=HTMLResponse)
def agents_page(
    request: Request,
    site: str = Query(default="all", max_length=50),
    state: str = Query(default="all", max_length=20),
    notice: str | None = Query(default=None, max_length=300),
    error: str | None = Query(default=None, max_length=600),
) -> HTMLResponse:
    settings = settings_from(request)
    service = supervision_service_from(request)
    with connect(settings.database_path) as connection:
        check_database(connection)
        agents = service.list_agents(connection)
    active_state = state if state in AGENT_STATES else "all"
    known_sites = sorted(
        {collector["site"] for agent in agents for collector in agent["collectors"]}
    )
    active_site = site if site in known_sites else "all"
    rows: list[dict[str, object]] = []
    for agent in agents:
        for collector in agent["collectors"]:
            if active_site != "all" and collector["site"] != active_site:
                continue
            if active_state != "all" and collector["state"] != active_state:
                continue
            rows.append({"agent": agent, "collector": collector})
    return templates.TemplateResponse(
        request=request,
        name="agents.html",
        context={
            "page": "agents",
            "agents": agents,
            "rows": rows,
            "sites": known_sites,
            "states": [(key, STATE_LABELS[key]) for key in AGENT_STATES],
            "selected_site": active_site,
            "selected_state": active_state,
            "state_labels": STATE_LABELS,
            "error_code_labels": ERROR_CODE_LABELS,
            "state_badge_classes": STATE_BADGE_CLASSES,
            "notice": notice,
            "error": error,
            "refresh_seconds": int(
                service.thresholds.heartbeat_interval_seconds
            ),
        },
    )


@app.get("/agents/{agent_id}", response_class=HTMLResponse)
def agent_detail_page(
    request: Request,
    agent_id: int,
    notice: str | None = Query(default=None, max_length=300),
    error: str | None = Query(default=None, max_length=600),
) -> HTMLResponse:
    settings = settings_from(request)
    with connect(settings.database_path) as connection:
        check_database(connection)
        detail = supervision_service_from(request).agent_detail(connection, agent_id)
    if detail is None:
        return templates.TemplateResponse(
            request=request,
            name="404.html",
            context={"page": "agents", "message": "Cet agent n'existe pas ou a été retiré."},
            status_code=404,
        )
    return templates.TemplateResponse(
        request=request,
        name="agent_detail.html",
        context={
            "page": "agents",
            "agent": detail,
            "state_labels": STATE_LABELS,
            "error_code_labels": ERROR_CODE_LABELS,
            "state_badge_classes": STATE_BADGE_CLASSES,
            "notice": notice,
            "error": error,
            "refresh_seconds": 30,
        },
    )


@app.post("/agents/{agent_id}/collectors/{collector_key}/resume")
def resume_collector_web(
    request: Request, agent_id: int, collector_key: str
) -> RedirectResponse:
    settings = settings_from(request)
    service = supervision_service_from(request)
    try:
        with connect(settings.database_path) as connection:
            service.agent_id = agent_id
            service.resume_collector(connection, collector_key=collector_key)
    except LookupError:
        return RedirectResponse(
            f"/agents/{agent_id}?error={quote('Collecteur introuvable.')}",
            status_code=303,
        )
    except RuntimeError as exc:
        return RedirectResponse(
            f"/agents/{agent_id}?error={quote(str(exc))}", status_code=303
        )
    return RedirectResponse(
        f"/agents/{agent_id}?notice={quote(f'Collecteur {collector_key} repris.')}",
        status_code=303,
    )


@app.get("/api/agents")
def api_agents(request: Request) -> JSONResponse:
    if not _supervision_authorized(request):
        return JSONResponse(status_code=401, content={"detail": "non autorisé"})
    settings = settings_from(request)
    with connect(settings.database_path) as connection:
        agents = supervision_service_from(request).list_agents(connection)
    return JSONResponse({"agents": agents})


@app.get("/api/agents/{agent_id}")
def api_agent_detail(request: Request, agent_id: int) -> JSONResponse:
    if not _supervision_authorized(request):
        return JSONResponse(status_code=401, content={"detail": "non autorisé"})
    settings = settings_from(request)
    with connect(settings.database_path) as connection:
        detail = supervision_service_from(request).agent_detail(connection, agent_id)
    if detail is None:
        return JSONResponse(status_code=404, content={"detail": "agent introuvable"})
    return JSONResponse(detail)


@app.get("/health")
def health(request: Request) -> JSONResponse:
    try:
        with connect(settings_from(request).database_path) as connection:
            check_database(connection)
    except (OSError, sqlite3.Error, RuntimeError) as error:
        return JSONResponse(
            status_code=503, content={"status": "error", "detail": str(error)}
        )
    return JSONResponse({"status": "ok", "database": "ok"})
