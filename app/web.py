from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
import json
import logging
import sqlite3
from typing import Annotated, Any, Literal
from urllib.parse import quote, urlencode

logger = logging.getLogger(__name__)

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
from pydantic import BeforeValidator, ValidationError

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
    CATALOG_VERDICTS,
    PROFITABILITY_SORT_KEYS,
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
    reidentify_catalog,
    reidentify_catalog_item,
    validate_public_image_url,
)
from app.catalog_export import CSV_FILENAME, build_catalog_csv
from app.cardmarket import aliases as cardmarket_aliases
from app.cardmarket import guide as cardmarket_guide
from app.cardmarket import service as cardmarket_service
from app.cardmarket.client import (
    CardmarketError,
    CardmarketNotConfiguredError,
    CardmarketNotFoundError,
    CardmarketRateLimitError,
)
from app.collectors.models import CollectorError
from app.config import Settings
from app.identification.models import IDENTIFICATION_STATUS_LABELS
from app.identification.ocr import router as ocr_router
from app.identification.normalization import canonical_local_id
from app.identification.annotation_pilot import (
    AnnotationAccessError, assignment, assignment_stage, pilot_dashboard, sample_pilot,
)
from app.identification.reviews import OUTCOMES, ReviewInput, review_context, save_review
from app.identification.research import enqueue_search, get_search_for_item, latest_search_for_item
from app.identification.resolution import (
    IdentificationConflictError, confirm_card, reclassify_unit, resolve_listing,
    revoke_confirmation,
)
from app.gestion import gestion_page_data
from app.tasking import tasking_data
from app.validation_history import get_validation_run, list_validation_runs, validation_image_path
from app.monitoring.models import WatchInput, WatchNotFoundError, WatchValidationError
from app.purchases import purchases_page_data
from app.monitoring.service import WatchService
from app.manual_listing import router as manual_listing_router
from app.capture_preview import router as capture_preview_router
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
    find_price_comparables,
    get_active_fee_profile,
    import_references_jsonl,
    list_references,
    parse_euros_to_cents,
    parse_percent_to_bps,
    profitability_dashboard_summary,
    update_active_fee_profile,
    upsert_reference,
)
from app.search.external import (
    ExternalSearchItem,
    ExternalSearchSummary,
    execute_external_search,
    import_external_listing,
)
from app.search.models import (
    CARD_SORTS,
    DEFAULT_CARD_SORT,
    DEFAULT_LISTING_SORT,
    LISTING_SORTS,
    LOT_FILTERS,
    SEARCH_IDENT_STATUSES,
    SEARCH_SCOPES,
    SEARCH_SOURCES,
    SearchFilters,
)
from app.search.service import (
    SEARCH_CSV_FILENAME,
    build_search_csv,
    get_search_filter_options,
    search_all,
    search_listings_export_rows,
)
from app.trends import TrendsFilters, get_trends_page_data
from app.storage.database import connect
from app.storage.migration_runner import apply_migrations, check_database
from app.sellers import repository as seller_repository
from app.sellers.models import (
    ReliabilityRating,
    SellerProfile,
    profile_from_row,
    reliability_rating,
    seller_platform_from_source,
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

# Tris unifiés du catalogue : tris SQL existants + tris de rentabilité.
CATALOG_SORT_OPTIONS: dict[str, str] = {
    **CATALOG_SORTS,
    **{key: "" for key in PROFITABILITY_SORT_KEYS},
}


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


def candidate_number_conflicts(listing_number: str | None, candidate_number: str | None) -> bool:
    """Signale deux numéros locaux différents sans déduire un numéro manquant."""
    listing = canonical_local_id((listing_number or "").split("/", 1)[0])
    candidate = canonical_local_id(candidate_number)
    return bool(listing and candidate and listing != candidate)


templates.env.globals["candidate_number_conflicts"] = candidate_number_conflicts
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
app.include_router(manual_listing_router)
app.include_router(capture_preview_router)
app.include_router(ocr_router)
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
    verdict: str = Query(default="all", max_length=30),
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
            verdict=verdict,
            sort=sort,
            page=page,
        )
        if data["evaluated"]:
            # Le service a déjà évalué toutes les lignes filtrées : la page
            # courante porte gain net, ROI et verdict exacts.
            from app.profitability import get_active_fee_profile

            enriched_items = data["items"]
            fee_profile = get_active_fee_profile(connection)
        else:
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
            "verdict_options": CATALOG_VERDICTS,
            "selected_verdict": data["verdict"],
            "verdict_labels": VERDICT_LABELS,
            "sort_options": CATALOG_SORT_OPTIONS,
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
    verdict: str = Query(default="all", max_length=30),
) -> Response:
    with connect(settings_from(request).database_path) as connection:
        rows = catalog_export_rows(
            connection,
            query=q.strip(),
            set_name=set_name,
            source=source,
            ident_status=ident,
            verdict=verdict,
        )
    return Response(
        content=build_catalog_csv(rows),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{CSV_FILENAME}"'},
    )


def _empty_query_to_none(value: Any) -> Any:
    """Traite les champs numériques optionnels vides envoyés par les formulaires."""
    return None if isinstance(value, str) and not value.strip() else value


OptionalQueryInt = Annotated[int | None, Query(), BeforeValidator(_empty_query_to_none)]


@app.get("/search", response_class=HTMLResponse)
def search_page(
    request: Request,
    q: str = Query(default="", max_length=200),
    scope: str = Query(default="all", max_length=20),
    set_name: str = Query(default="", max_length=200),
    year_min: OptionalQueryInt = None,
    year_max: OptionalQueryInt = None,
    rarity: str = Query(default="", max_length=100),
    condition: str = Query(default="", max_length=100),
    language: str = Query(default="", max_length=20),
    variant: str = Query(default="", max_length=100),
    edition: str = Query(default="", max_length=100),
    grading_company: str = Query(default="", max_length=50),
    grade: str = Query(default="", max_length=30),
    source: str = Query(default="all", max_length=20),
    price_min: str = Query(default="", max_length=20),
    price_max: str = Query(default="", max_length=20),
    ident_status: str = Query(default="all", max_length=20),
    lot_filter: str = Query(default="all", max_length=20),
    sort: str = Query(default="", max_length=30),
    page: int = Query(default=1, ge=1),
    external: bool = Query(default=False),
    error: str = Query(default="", max_length=500),
) -> HTMLResponse:
    price_min_cents: int | None = None
    price_max_cents: int | None = None
    validation_error: str | None = None

    if price_min.strip():
        try:
            price_min_cents = parse_euros_to_cents(price_min, "Prix minimum")
        except ValueError as exc:
            validation_error = str(exc)
    if price_max.strip():
        try:
            price_max_cents = parse_euros_to_cents(price_max, "Prix maximum")
        except ValueError as exc:
            validation_error = str(exc)

    try:
        filters = SearchFilters(
            q=q,
            scope=scope,
            set_name=set_name,
            year_min=year_min,
            year_max=year_max,
            rarity=rarity,
            condition=condition,
            language=language,
            variant=variant,
            edition=edition,
            grading_company=grading_company,
            grade=grade,
            source=source,
            price_min_cents=price_min_cents,
            price_max_cents=price_max_cents,
            ident_status=ident_status,
            lot_filter=lot_filter,
            sort=sort,
            page=page,
        )
    except ValueError as exc:
        validation_error = str(exc)
        filters = SearchFilters(q=q, scope=scope)

    has_active_filters = bool(
        q.strip() or set_name.strip() or year_min is not None or year_max is not None
        or rarity.strip() or condition.strip() or language.strip() or variant.strip()
        or edition.strip() or grading_company.strip() or grade.strip()
        or source != "all" or price_min.strip() or price_max.strip()
        or ident_status != "all" or lot_filter != "all" or sort
    )
    has_advanced_filters = bool(
        set_name.strip() or year_min is not None or year_max is not None
        or rarity.strip() or condition.strip() or language.strip() or variant.strip()
        or edition.strip() or grading_company.strip() or grade.strip()
        or source != "all" or price_min.strip() or price_max.strip()
        or ident_status != "all" or lot_filter != "all"
    )

    external_summary: ExternalSearchSummary | None = None
    with connect(settings_from(request).database_path) as connection:
        filter_options = get_search_filter_options(connection)
        results = None
        if validation_error is None and has_active_filters:
            results = search_all(connection, filters)
            if external:
                external_summary = execute_external_search(connection, filters)

    export_query_params = filters.to_query_params()
    export_query_params.pop("page", None)
    export_query_string = urlencode(export_query_params)

    return templates.TemplateResponse(
        request=request,
        name="search.html",
        context={
            "page": "search",
            "filters": filters,
            "filter_options": filter_options,
            "results": results,
            "external_summary": external_summary,
            "external_active": external,
            "validation_error": validation_error,
            "import_error": error,
            "has_active_filters": has_active_filters,
            "has_advanced_filters": has_advanced_filters,
            "price_min_input": price_min,
            "price_max_input": price_max,
            "export_query_string": export_query_string,
        },
    )


@app.post("/search/external/import")
def search_external_import(
    request: Request,
    source: str = Form(...),
    external_id: str = Form(...),
    title: str = Form(...),
    price_cents: int = Form(...),
    currency: str = Form(default="EUR"),
    shipping_cents: int | None = Form(default=None),
    seller: str | None = Form(default=None),
    seller_external_id: str | None = Form(default=None),
    url: str | None = Form(default=None),
    image_url: str | None = Form(default=None),
    raw_data_json: str | None = Form(default=None),
) -> RedirectResponse:
    raw_data: dict[str, Any] = {}
    if raw_data_json:
        try:
            raw_data = json.loads(raw_data_json)
        except Exception:
            raw_data = {}

    item = ExternalSearchItem(
        source=source,
        external_id=external_id,
        title=title,
        price_cents=price_cents,
        currency=currency,
        shipping_cents=shipping_cents,
        seller=seller,
        seller_external_id=seller_external_id,
        url=url,
        image_url=image_url,
        raw_data=raw_data,
    )
    try:
        with connect(settings_from(request).database_path) as connection:
            listing_id = import_external_listing(connection, item)
        return RedirectResponse(
            f"/catalog/{listing_id}",
            status_code=303,
        )
    except Exception as exc:
        logger.warning("Échec de l'import externe : %s", exc)
        return RedirectResponse(
            f"/search?error={quote(str(exc))}",
            status_code=303,
        )


@app.get("/search/export.csv")
def search_export(
    request: Request,
    q: str = Query(default="", max_length=200),
    set_name: str = Query(default="", max_length=200),
    year_min: OptionalQueryInt = None,
    year_max: OptionalQueryInt = None,
    rarity: str = Query(default="", max_length=100),
    condition: str = Query(default="", max_length=100),
    language: str = Query(default="", max_length=20),
    variant: str = Query(default="", max_length=100),
    edition: str = Query(default="", max_length=100),
    grading_company: str = Query(default="", max_length=50),
    grade: str = Query(default="", max_length=30),
    source: str = Query(default="all", max_length=20),
    price_min: str = Query(default="", max_length=20),
    price_max: str = Query(default="", max_length=20),
    ident_status: str = Query(default="all", max_length=20),
    lot_filter: str = Query(default="all", max_length=20),
    sort: str = Query(default="", max_length=30),
) -> Response:
    price_min_cents: int | None = None
    price_max_cents: int | None = None

    try:
        if price_min.strip():
            price_min_cents = parse_euros_to_cents(price_min, "Prix minimum")
        if price_max.strip():
            price_max_cents = parse_euros_to_cents(price_max, "Prix maximum")
        filters = SearchFilters(
            q=q,
            scope="listings",
            set_name=set_name,
            year_min=year_min,
            year_max=year_max,
            rarity=rarity,
            condition=condition,
            language=language,
            variant=variant,
            edition=edition,
            grading_company=grading_company,
            grade=grade,
            source=source,
            price_min_cents=price_min_cents,
            price_max_cents=price_max_cents,
            ident_status=ident_status,
            lot_filter=lot_filter,
            sort=sort,
        )
    except ValueError as exc:
        return PlainTextResponse(f"Critères d’export invalides : {exc}", status_code=400)

    with connect(settings_from(request).database_path) as connection:
        rows = search_listings_export_rows(connection, filters)

    return Response(
        content=build_search_csv(rows),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{SEARCH_CSV_FILENAME}"'},
    )


@app.get("/trends", response_class=HTMLResponse)
def trends_page(
    request: Request,
    period: str = Query(default="7_30", max_length=10),
    set_name: str = Query(default="", max_length=200),
    rarity: str = Query(default="", max_length=100),
    language: str = Query(default="", max_length=20),
    min_observations: int = Query(default=1, ge=1, le=1000),
    max_quote_age_days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=20, ge=1, le=100),
    page: int = Query(default=1, ge=1, le=100_000),
) -> HTMLResponse:
    filters = TrendsFilters(
        period=period,
        set_name=set_name,
        rarity=rarity,
        language=language,
        min_observations=min_observations,
        max_quote_age_days=max_quote_age_days,
        limit=limit,
        page=page,
    )
    with connect(settings_from(request).database_path) as connection:
        trends_data = get_trends_page_data(connection, filters)

    return templates.TemplateResponse(
        request=request,
        name="trends.html",
        context={
            "page": "trends",
            "trends": trends_data,
        },
    )



@app.get("/catalog/labels.jsonl")
def identification_labels_export(request: Request) -> Response:
    """Télécharge un jeu pilote humain sans données structurées de vendeur."""
    from app.identification.dataset import build_dataset
    database_path = settings_from(request).database_path
    with connect(database_path) as connection:
        payload = build_dataset(connection, database_path)
    return Response(payload, media_type="application/x-ndjson", headers={
        "Content-Disposition": 'attachment; filename="pokebourse-labels.jsonl"',
    })


@app.get("/annotations", response_class=HTMLResponse)
def annotation_dashboard_page(
    request: Request, notice: str | None = Query(default=None, max_length=200),
    error: str | None = Query(default=None, max_length=300),
    view: str = Query(default="all", max_length=20), queue_page: int = Query(default=1, ge=1),
) -> HTMLResponse:
    """Suit le pilote sans dévoiler de décision sur les lectures en attente."""
    operator = settings_from(request).review_operator
    with connect(settings_from(request).database_path) as connection:
        data = pilot_dashboard(connection, operator)
    next_item = next((item for item in data.get("items", []) if item["stage"] in ("first", "second")), None)
    view = view if view in ("all", "available", "waiting", "final") else "all"
    visible = [item for item in data.get("items", []) if view == "all"
               or (view == "available" and item["stage"] in ("first", "second"))
               or (view == "waiting" and item["current"] and item["blocked"])
               or (view == "final" and item["stage"] == "adjudication")]
    pages = max(1, (len(visible) + 24) // 25)
    queue_page = min(queue_page, pages)
    return templates.TemplateResponse(request=request, name="annotation_dashboard.html", context={
        "page": "annotations", "operator": operator, "notice": notice, "error": error,
        "next_item": next_item, "ident_labels": IDENTIFICATION_STATUS_LABELS,
        "queue_items": visible[(queue_page - 1) * 25:queue_page * 25], "view": view,
        "queue_page": queue_page, "queue_pages": pages, "queue_total": len(visible), **data,
    })


@app.get("/tcgdex", response_class=HTMLResponse)
def tcgdex_catalog_page(
    request: Request, q: str = Query(default="", max_length=100), page: int = Query(default=1, ge=1),
    follow: int | None = Query(default=None, ge=1), notice: str | None = Query(default=None, max_length=200),
    error: str | None = Query(default=None, max_length=300),
) -> HTMLResponse:
    """Inventaire et suivi persistants ; aucun accès distant pendant l'affichage."""
    from app.tcgdex.sync import sync_dashboard
    with connect(settings_from(request).database_path) as connection:
        data = sync_dashboard(connection, query=q.strip(), page=page)
    following = next((job for job in data["jobs"] if job["id"] == follow and job["status"] in ("queued", "running")), None)
    return templates.TemplateResponse(request=request, name="tcgdex_sync.html", context={
        "page": "tcgdex", "notice": notice, "error": error, "following": following, **data,
    })


@app.post("/tcgdex/sync")
def tcgdex_enqueue(
    request: Request, set_ids: list[str] = Form(default=[]), manual_set_id: str = Form(default="", max_length=50),
    include_details: bool = Form(default=False),
) -> RedirectResponse:
    """Enregistre les extensions explicitement choisies pour le worker."""
    from app.tcgdex.sync import enqueue_sync, validate_set_selection
    selected = list(dict.fromkeys([*set_ids, *([manual_set_id.strip()] if manual_set_id.strip() else [])]))
    try:
        selected = validate_set_selection(selected)
        with connect(settings_from(request).database_path) as connection:
            ids = [enqueue_sync(connection, set_id, include_details=include_details) for set_id in selected]
    except ValueError as exc:
        return RedirectResponse(f"/tcgdex?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(f"/tcgdex?follow={ids[0]}&notice={quote('Demande enregistrée. Le worker avance la file ; les données récentes sont réutilisées.')}#jobs-title", status_code=303)


@app.post("/tcgdex/directory")
def tcgdex_refresh_directory(request: Request) -> RedirectResponse:
    """Demande une liste officielle d'extensions sans charger toutes leurs cartes."""
    from app.tcgdex.sync import enqueue_sync
    with connect(settings_from(request).database_path) as connection:
        job_id = enqueue_sync(connection)
    return RedirectResponse(f"/tcgdex?follow={job_id}&notice={quote('Liste des extensions demandée au worker.')}#jobs-title", status_code=303)


@app.post("/tcgdex/jobs/{job_id}/{action}")
def tcgdex_control_job(request: Request, job_id: int, action: Literal["pause", "resume"]) -> Response:
    """Contrôle une tâche sans retirer les cartes déjà disponibles dans le cache."""
    from app.tcgdex.sync import control_job
    try:
        with connect(settings_from(request).database_path) as connection:
            control_job(connection, job_id, action)
    except LookupError:
        return HTMLResponse("Synchronisation introuvable.", status_code=404)
    return RedirectResponse(f"/tcgdex?follow={job_id}#jobs-title", status_code=303)


@app.get("/identification/diagnostics")
def identification_diagnostic_page(
    request: Request, limit: int = Query(default=100, ge=1, le=500),
    status: Literal["unidentified", "ambiguous", "all"] = "unidentified", download: bool = False,
) -> Response:
    """Présente les constats locaux, sans modifier les annonces ou leurs validations."""
    from app.identification.diagnostics import identification_diagnostics
    with connect(settings_from(request).database_path) as connection:
        report = identification_diagnostics(connection, limit=limit, status=status)
    if download:
        return JSONResponse(report, headers={"Content-Disposition": 'attachment; filename="identification-diagnostics.json"'})
    return templates.TemplateResponse(request=request, name="identification_diagnostics.html", context={
        "page": "annotations", "report": report,
    })


@app.post("/annotations/sample")
def annotation_sample(request: Request) -> RedirectResponse:
    """Constitue ou complète le pilote à partir des seules données locales."""
    with connect(settings_from(request).database_path) as connection:
        added = sample_pilot(connection)
    message = f"{added} annonce(s) ajoutée(s) à la file." if added else "Aucune nouvelle annonce admissible : importez des annonces ou terminez les lectures en attente."
    return RedirectResponse(f"/annotations?notice={quote(message)}", status_code=303)


@app.get("/annotations/items/{assignment_id}", response_class=HTMLResponse)
def annotation_assignment_page(
    request: Request, assignment_id: int, q: str = Query(default="", max_length=100),
    offset: int = Query(default=0, ge=0), error: str | None = Query(default=None, max_length=300),
) -> Response:
    """Impose une lecture aveugle jusqu'à la fin des lectures indépendantes."""
    from app.identification.resolution import capture_evidence
    try:
        with connect(settings_from(request).database_path) as connection:
            with connection:
                item = assignment(connection, assignment_id)
                if item["listing_id"] is not None:
                    capture_evidence(connection, item["listing_id"])
                    item = assignment(connection, assignment_id)
                stage = assignment_stage(connection, item, settings_from(request).review_operator)
                if stage == "done":
                    return RedirectResponse("/annotations", status_code=303)
                blind = stage != "adjudication"
                data = review_context(connection, item["listing_id"], q, offset, blind=blind)
                annotation_ids = [item["first_review_id"]] + ([item["second_review_id"]] if item["second_review_id"] else [])
                compared = [] if blind else [connection.execute(
                    "SELECT outcome, validated_tcgdex_id, text_sufficient FROM listing_identification_reviews WHERE id=?", (review_id,)
                ).fetchone() for review_id in annotation_ids]
        return templates.TemplateResponse(request=request, name="identification_review.html", context={
            "page": "annotations", "item_id": item["listing_id"], "query": q, "offset": offset,
            "blind": blind, "error": error, "outcomes": OUTCOMES, "pilot_assignment": item,
            "assignment_stage": stage, "annotation_ids": ",".join(map(str, annotation_ids)) if not blind else "",
            "compared_annotations": compared, **data,
        })
    except (AnnotationAccessError, LookupError) as exc:
        return templates.TemplateResponse(request=request, name="annotation_blocked.html",
            status_code=403 if isinstance(exc, AnnotationAccessError) else 404,
            context={"page": "annotations", "message": str(exc)})


@app.get("/catalog/{item_id}/review", response_class=HTMLResponse)
def identification_review_page(
    request: Request, item_id: int,
    q: str = Query(default="", max_length=100),
    offset: int = Query(default=0, ge=0),
    blind: bool = Query(default=True),
    notice: str | None = Query(default=None, max_length=200),
    error: str | None = Query(default=None, max_length=300),
) -> HTMLResponse:
    """Lecture indépendante par défaut, sans suggestion ni historique visible."""
    with connect(settings_from(request).database_path) as connection:
        if not connection.execute("SELECT id FROM catalog_items WHERE id=?", (item_id,)).fetchone():
            return templates.TemplateResponse(request=request, name="404.html", status_code=404,
                context={"page": "catalog", "message": "Annonce introuvable."})
        with connection:
            data = review_context(connection, item_id, q, offset, blind=blind)
    return templates.TemplateResponse(request=request, name="identification_review.html", context={
        "page": "catalog", "item_id": item_id, "query": q, "offset": offset,
        "blind": blind, "notice": notice, "error": error, "outcomes": OUTCOMES, **data,
    })


@app.post("/catalog/{item_id}/review")
def identification_review_submit(
    request: Request, item_id: int, evidence_hash: str = Form(...), revision: int = Form(...),
    outcome: str = Form(...), review_kind: str = Form(default="decision"),
    reference_card_id: int | None = Form(default=None), text_sufficient: bool = Form(default=False),
    comment: str | None = Form(default=None, max_length=2000),
    annotation_ids: str = Form(default="", max_length=1000),
    verified_language: str = Form(default="", max_length=100),
    verified_variant: str = Form(default="", max_length=100),
    verified_edition: str = Form(default="", max_length=100),
    verified_condition: str = Form(default="", max_length=100),
    assignment_id: int | None = Form(default=None), assignment_stage: str | None = Form(default=None),
    evidence_basis: str = Form(default="text"), image_evidence_id: int | None = Form(default=None),
) -> Response:
    """Enregistre une révision avec identité locale fixe et contrôle du snapshot."""
    try:
        review = ReviewInput.model_validate({
            "outcome": outcome, "review_kind": review_kind, "validated_card_id": reference_card_id,
            "text_sufficient": text_sufficient, "comment": comment,
            "evidence_basis": evidence_basis, "image_evidence_id": image_evidence_id,
            "reviewed_annotation_ids": [int(value.strip()) for value in annotation_ids.split(",") if value.strip()],
            "verified_attributes": {key: {"status": "verified" if value.strip() else "unknown", "value": value.strip() or None}
                for key, value in (("language", verified_language), ("variant", verified_variant),
                                   ("edition", verified_edition), ("condition", verified_condition))},
        })
        database_path = settings_from(request).database_path
        with connect(database_path) as connection:
            save_review(connection, item_id, review, expected_hash=evidence_hash, expected_revision=revision,
                        operator=settings_from(request).review_operator,
                        assignment_id=assignment_id, assignment_stage=assignment_stage,
                        database_path=database_path)
    except IdentificationConflictError as exc:
        path = f"/annotations/items/{assignment_id}" if assignment_id is not None else f"/catalog/{item_id}/review"
        return HTMLResponse(f"<p>{str(exc)}</p><a href='{path}'>Recharger la fiche</a>", status_code=409)
    except LookupError:
        return HTMLResponse("Annonce introuvable.", status_code=404)
    except AnnotationAccessError as exc:
        return templates.TemplateResponse(request=request, name="annotation_blocked.html", status_code=403,
            context={"page": "annotations", "message": str(exc)})
    except (ValueError, ValidationError) as exc:
        message = str(exc) if not isinstance(exc, ValidationError) else "Validation invalide : vérifiez le résultat, la carte choisie et la suffisance du texte."
        path = f"/annotations/items/{assignment_id}" if assignment_id is not None else f"/catalog/{item_id}/review"
        return RedirectResponse(f"{path}?error={quote(message[:300])}", status_code=303)
    if assignment_id is not None:
        return RedirectResponse("/annotations?notice=Lecture+enregistr%C3%A9e", status_code=303)
    return RedirectResponse(f"/catalog/{item_id}/review?notice=Lecture+enregistr%C3%A9e", status_code=303)


@app.post("/catalog/reidentify-all")
def reidentify_catalog_all(request: Request) -> RedirectResponse:
    """Réexamine toutes les annonces non identifiées avec le référentiel courant."""
    with connect(settings_from(request).database_path) as connection:
        report = reidentify_catalog(connection)
    labels = {
        "identified": "identifiée(s)",
        "ambiguous": "à vérifier",
        "lot": "lot(s)",
        "unidentified": "non identifiée(s)",
    }
    details = ", ".join(
        f"{labels.get(status, status)} {count}"
        for status, count in report.items()
        if status != "examined"
    )
    msg = f"Réexamen terminé : {report['examined']} annonce(s) réexaminée(s)."
    if details:
        msg += f" Résultat : {details}."
    return RedirectResponse(url=f"/catalog?notice={quote(msg)}", status_code=303)


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


@app.post("/catalog/{item_id}/preuves-visuelles")
def store_listing_visual_evidence(
    request: Request, item_id: int,
    file: UploadFile = File(...), purpose: str = Form(default="confirmation"),
) -> RedirectResponse:
    """Conserve explicitement une photo dans l'espace de preuves contrôlé (T04).

    Distinct de l'analyse OCR, qui reste éphémère : aucune photo n'est
    conservée sans cette action explicite, et la conservation ne confirme
    aucune identité.
    """
    from urllib.parse import quote

    from app.identification.evidence_store import store_image_evidence
    from app.identification.ocr import MAX_IMAGE_BYTES

    database_path = settings_from(request).database_path
    content = file.file.read(MAX_IMAGE_BYTES + 1)
    try:
        with connect(database_path) as connection:
            store_image_evidence(connection, database_path, content, purpose=purpose, listing_id=item_id)
    except ValueError as exc:
        return RedirectResponse(url=f"/catalog/{item_id}?error={quote(str(exc))}", status_code=303)
    except LookupError:
        return RedirectResponse(url="/catalog?error=Annonce+introuvable", status_code=303)
    return RedirectResponse(
        url=f"/catalog/{item_id}?notice=Preuve+visuelle+conserv%C3%A9e",
        status_code=303,
    )


@app.get("/catalog/{item_id}", response_class=HTMLResponse)
def catalog_item(
    request: Request,
    item_id: int,
    notice: str | None = Query(default=None, max_length=200),
    error: str | None = Query(default=None, max_length=300),
) -> HTMLResponse:
    with connect(settings_from(request).database_path) as connection:
        item = catalog_item_detail(connection, item_id)
        seller_profile_row = None
        cardmarket_view = None
        visual_evidence: list[dict[str, Any]] = []
        database_path = settings_from(request).database_path
        comparables: dict[str, list[dict[str, Any]]] = {
            "listings": [],
            "sales": [],
            "references": [],
        }
        cardmarket_ready = cardmarket_service.credentials_configured(
            settings_from(request)
        )
        if item is not None:
            fee_profile = get_active_fee_profile(connection)
            market_index = build_market_index(
                connection, fee_profile.min_catalog_samples
            )
            evaluation = evaluate_listing(item, fee_profile, market_index)
            comparables = find_price_comparables(
                connection, item, evaluation["reference_price_cents"]
            )
            identification = resolve_listing(connection, item_id)
            identification_candidates = identification.result.candidates[:5]
            identification_search = latest_search_for_item(connection, item_id)
            cardmarket_rows = cardmarket_service.prices_for_item(connection, item)
            cardmarket_view = _cardmarket_view(cardmarket_rows)
            cardmarket_guide_count = connection.execute(
                "SELECT COUNT(*) FROM cardmarket_prices"
            ).fetchone()[0]
            seller_profile_row = seller_service_from(request).profile_for_item(
                connection,
                platform=item["source_name"],
                seller_profile_id=item["seller_profile_id"],
                seller_external_id=item["seller_external_id"],
            )
            from app.identification.evidence_store import evidence_file_status

            for evidence_row in connection.execute(
                "SELECT id, sha256, width, height, byte_size, purpose, created_at "
                "FROM listing_image_evidence WHERE listing_id=? ORDER BY id DESC LIMIT 20",
                (item_id,),
            ):
                evidence_dict = dict(evidence_row)
                evidence_dict["status"] = evidence_file_status(connection, database_path, evidence_row["id"])
                visual_evidence.append(evidence_dict)
    if item is None:
        return templates.TemplateResponse(
            request=request,
            name="404.html",
            context={"page": "", "message": "Cette annonce n'existe pas ou a été retirée du catalogue."},
            status_code=404,
        )
    seller_profile = profile_from_row(seller_profile_row)
    try:
        listing_image_url = validate_public_image_url(str(item["image_url"])) if item["image_url"] else None
    except ValueError:
        listing_image_url = None
    return templates.TemplateResponse(
        request=request,
        name="catalog_detail.html",
        context={
            "page": "catalog",
            "item": item,
            "listing_image_url": listing_image_url,
            "evaluation": evaluation,
            "fee_profile": fee_profile,
            "seller_profile": seller_profile,
            "seller_rating": reliability_rating(seller_profile),
            "notice": notice,
            "ident_labels": IDENTIFICATION_STATUS_LABELS,
            "cardmarket": cardmarket_view,
            "cardmarket_ready": cardmarket_ready,
            "cardmarket_guide_count": cardmarket_guide_count,
            "comparables": comparables,
            "identification": identification,
            "identification_candidates": identification_candidates,
            "identification_search": identification_search,
            "visual_evidence": visual_evidence,
            "error": error,
        },
    )


def _reference_payload(card: object) -> dict[str, object]:
    return {
        "id": card.id, "tcgdex_id": card.tcgdex_id, "name": card.name,
        "set_name": card.set_name, "local_id": card.local_id,
        "image_url": card.image_url, "rarity": card.rarity, "language": "fr",
    }


@app.get("/catalog/{item_id}/identification")
def catalog_identification_candidates(
    request: Request, item_id: int, name: str = Query(default="", max_length=200),
    local_id: str = Query(default="", max_length=50), set_name: str = Query(default="", max_length=200),
    tcgdex_id: str = Query(default="", max_length=100), page: int = Query(default=1, ge=1),
) -> JSONResponse:
    from app.tcgdex.cache import TcgdexCache
    from app.identification.reference_search import search_references
    with connect(settings_from(request).database_path) as connection:
        if not catalog_item_detail(connection, item_id):
            return JSONResponse({"detail": "Annonce introuvable"}, status_code=404)
        cache = TcgdexCache(connection)
        search = search_references(cache, name=name, local_id=local_id or None, set_name=set_name or None,
                                   tcgdex_id=tcgdex_id or None, limit=21, offset=(page - 1) * 20)
        cards = search.cards
    return JSONResponse({"items": [_reference_payload(card) for card in cards[:20]], "page": page,
                         "has_next": len(cards) > 20, "approximate": search.approximate})


@app.post("/catalog/{item_id}/identification/search")
def catalog_identification_search(
    request: Request, item_id: int, name: str = Form(default=""), local_id: str = Form(default=""),
    set_name: str = Form(default=""), tcgdex_id: str = Form(default=""), force: int = Form(default=0),
) -> RedirectResponse:
    try:
        with connect(settings_from(request).database_path) as connection:
            with connection:
                search_id = enqueue_search(connection, item_id, {"name": name, "local_id": local_id, "set_name": set_name, "tcgdex_id": tcgdex_id}, force=bool(force))
        return RedirectResponse(f"/catalog/{item_id}?notice={quote(f'Recherche {search_id} en attente du worker.')}", status_code=303)
    except (ValueError, LookupError) as error:
        return RedirectResponse(f"/catalog/{item_id}?error={quote(str(error))}", status_code=303)


@app.get("/catalog/{item_id}/identification/search/{search_id}")
def catalog_identification_search_status(request: Request, item_id: int, search_id: int) -> JSONResponse:
    with connect(settings_from(request).database_path) as connection:
        search = get_search_for_item(connection, item_id, search_id)
        if search is None:
            return JSONResponse({"detail": "Recherche introuvable pour cette annonce"}, status_code=404)
        return JSONResponse({"id": search["id"], "status": search["status"], "attempts": search["attempts"], "partial": bool(search["partial"]), "error_code": search["error_code"], "result_card_ids": json.loads(search["result_card_ids_json"])})


@app.post("/catalog/{item_id}/identification/confirm")
def catalog_identification_confirm(
    request: Request, item_id: int, reference_card_id: int = Form(...),
    evidence_hash: str = Form(...), revision: int = Form(...), reason: str = Form(default=""),
) -> RedirectResponse:
    try:
        with connect(settings_from(request).database_path) as connection:
            with connection:
                confirm_card(connection, item_id, reference_card_id, evidence_hash, revision, reason or None)
        return RedirectResponse(f"/catalog/{item_id}?notice={quote('Carte confirmée manuellement.')}", status_code=303)
    except (ValueError, LookupError) as error:
        return RedirectResponse(f"/catalog/{item_id}?error={quote(str(error))}", status_code=303)


@app.post("/catalog/{item_id}/identification/revoke")
def catalog_identification_revoke(request: Request, item_id: int, evidence_hash: str = Form(...), revision: int = Form(...)) -> RedirectResponse:
    try:
        with connect(settings_from(request).database_path) as connection:
            with connection:
                revoke_confirmation(connection, item_id, evidence_hash, revision)
        return RedirectResponse(f"/catalog/{item_id}?notice={quote('Confirmation retirée ; résolution automatique réactivée.')}", status_code=303)
    except ValueError as error:
        return RedirectResponse(f"/catalog/{item_id}?error={quote(str(error))}", status_code=303)


@app.post("/catalog/{item_id}/identification/reclassify-unit")
def catalog_identification_reclassify(request: Request, item_id: int, evidence_hash: str = Form(...), revision: int = Form(...), reason: str = Form(...)) -> RedirectResponse:
    try:
        with connect(settings_from(request).database_path) as connection:
            with connection:
                reclassify_unit(connection, item_id, evidence_hash, revision, reason)
        return RedirectResponse(f"/catalog/{item_id}?notice={quote('Classement lot corrigé et historisé.')}", status_code=303)
    except ValueError as error:
        return RedirectResponse(f"/catalog/{item_id}?error={quote(str(error))}", status_code=303)


@app.post("/catalog/{item_id}/cardmarket/refresh")
def catalog_item_cardmarket_refresh(request: Request, item_id: int) -> RedirectResponse:
    settings = settings_from(request)
    with connect(settings.database_path) as connection:
        item = catalog_item_detail(connection, item_id)
        if item is None:
            return RedirectResponse(url="/catalog?error=Annonce+introuvable", status_code=303)
        try:
            snapshot = cardmarket_service.refresh_price_for_item(
                connection, item, settings
            )
        except CardmarketNotConfiguredError:
            return RedirectResponse(
                url=f"/catalog/{item_id}?error={quote('API Cardmarket non configurée : renseignez les 4 variables CARDMARKET_* (voir documentation).')}",
                status_code=303,
            )
        except CardmarketNotFoundError as error:
            return RedirectResponse(
                url=f"/catalog/{item_id}?error={quote(str(error))}",
                status_code=303,
            )
        except CardmarketRateLimitError:
            return RedirectResponse(
                url=f"/catalog/{item_id}?error={quote('Limite de requêtes Cardmarket atteinte — réessayez dans quelques minutes.')}",
                status_code=303,
            )
        except CardmarketError as error:
            return RedirectResponse(
                url=f"/catalog/{item_id}?error={quote(f'Erreur Cardmarket : {error}')}",
                status_code=303,
            )
    if snapshot is not None and snapshot.best_known_price_cents is not None:
        euros, cents = divmod(snapshot.best_known_price_cents, 100)
        msg = quote(
            f"Prix Cardmarket actualisé : {snapshot.card_name} "
            f"({euros},{cents:02d} {snapshot.currency})."
        )
    else:
        msg = quote("Prix Cardmarket actualisé, mais aucun prix de vente disponible.")
    return RedirectResponse(url=f"/catalog/{item_id}?notice={msg}", status_code=303)


def _cardmarket_view(rows: list[Any]) -> dict[str, Any] | None:
    """Construit la vue d'affichage : produit unique ou fourchette multi-produits."""
    if not rows:
        return None
    trends = [
        int(row["trend_price_cents"])
        for row in rows
        if row["trend_price_cents"] is not None
    ]
    return {
        "rows": rows,
        "count": len(rows),
        "single": rows[0] if len(rows) == 1 else None,
        "currency": rows[0]["currency"],
        "trend_min": min(trends) if trends else None,
        "trend_max": max(trends) if trends else None,
    }


@app.post("/cardmarket/sync")
def cardmarket_sync(request: Request) -> RedirectResponse:
    """Télécharge le price guide officiel Cardmarket et synchronise les cotes."""
    with connect(settings_from(request).database_path) as connection:
        try:
            result = cardmarket_guide.sync_price_guide(connection)
        except Exception as error:  # Réseau, JSON invalide, fichier indisponible…
            return RedirectResponse(
                url=f"/reglages?error={quote(f'Synchronisation Cardmarket impossible : {error}')}",
                status_code=303,
            )
    guide_date = (result["created_at"] or "")[:10]
    msg = (
        f"Cotes Cardmarket synchronisées : {result['synced']} cartes "
        f"(price guide officiel du {guide_date}"
        + (f", {result['skipped']} produits sans nom ignorés" if result["skipped"] else "")
        + ")."
    )
    return RedirectResponse(url=f"/reglages?notice={quote(msg)}", status_code=303)


@app.post("/cardmarket/aliases/sync")
def cardmarket_aliases_sync(request: Request) -> RedirectResponse:
    """Synchronise les noms de cartes multilingues (TCGdex → card_name_aliases)."""
    with connect(settings_from(request).database_path) as connection:
        try:
            result = cardmarket_aliases.sync_name_aliases(connection)
        except Exception as error:
            return RedirectResponse(
                url=f"/reglages?error={quote(f'Synchronisation des noms impossible : {error}')}",
                status_code=303,
            )
    total = sum(result["per_locale"].values())
    locales = " · ".join(
        f"{locale.upper()} {count}" for locale, count in result["per_locale"].items()
    )
    msg = f"Noms multilingues synchronisés : {total} alias ({locales})."
    if result["skipped"]:
        msg += f" Locales ignorées (API indisponible) : {', '.join(result['skipped'])}."
    return RedirectResponse(url=f"/reglages?notice={quote(msg)}", status_code=303)


@app.post("/cardmarket/sync-all")
def cardmarket_sync_all(request: Request) -> RedirectResponse:
    """Synchronise cotes + noms en une seule action (« Tout synchroniser »)."""
    from app.cardmarket import daily as cardmarket_daily

    with connect(settings_from(request).database_path) as connection:
        try:
            result = cardmarket_daily.run_daily_sync(connection)
            cardmarket_daily.mark_success(connection, "manuel · " + cardmarket_daily.summarize(result))
        except Exception as error:
            cardmarket_daily.mark_attempt(connection, f"manuel en échec : {error}")
            return RedirectResponse(
                url=f"/reglages?error={quote(f'Synchronisation impossible : {error}')}",
                status_code=303,
            )
    guide_date = (result["guide"]["created_at"] or "")[:10]
    alias_total = sum(result["aliases"]["per_locale"].values())
    msg = (
        f"Cotes + noms synchronisés : {result['guide']['synced']} cotes Cardmarket "
        f"(price guide du {guide_date}) et {alias_total} alias multilingues."
    )
    if result["aliases"]["skipped"]:
        msg += f" Locales ignorées (API indisponible) : {', '.join(result['aliases']['skipped'])}."
    return RedirectResponse(url=f"/reglages?notice={quote(msg)}", status_code=303)


@app.post("/catalog/{item_id}/purchase")
def catalog_item_purchase(
    request: Request,
    item_id: int,
    price_paid: str = Form(...),
    shipping_paid: str = Form(...),
    status: str = Form(...),
    notes: str | None = Form(default=None),
) -> RedirectResponse:
    try:
        price_cents = parse_euros_to_cents(price_paid, "Prix payé")
        shipping_cents = parse_euros_to_cents(shipping_paid, "Frais de port")
        if status not in ("commande", "recu", "en_vente", "vendu"):
            raise ProfitabilityError("Choisissez un statut d'achat valide.")
    except ProfitabilityError as error:
        return RedirectResponse(f"/catalog/{item_id}?error={quote(str(error))}#purchase", status_code=303)
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
        platform = seller_platform_from_source(item["source_name"], item["url"])
        if seller_profile_id is None and item["seller"] and platform is not None:
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
            price_paid_cents=price_cents,
            shipping_paid_cents=shipping_cents,
            currency=item["currency"] or "EUR",
            platform=platform,
            status=status,
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
            platform=platform if platform in ("vinted", "leboncoin", "ebay", "wallapop") else None,
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
    price_paid: str = Form(...),
    shipping_paid: str = Form(...),
    status: str = Form(...),
    notes: str | None = Form(default=None),
) -> RedirectResponse:
    try:
        price_cents = parse_euros_to_cents(price_paid, "Prix payé")
        shipping_cents = parse_euros_to_cents(shipping_paid, "Frais de port")
        if status not in ("commande", "recu", "en_vente", "vendu"):
            raise ProfitabilityError("Choisissez un statut d'achat valide.")
    except ProfitabilityError as error:
        return RedirectResponse(f"/sellers/{seller_id}?error={quote(str(error))}#purchase", status_code=303)
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
            price_paid_cents=price_cents,
            shipping_paid_cents=shipping_cents,
            platform=platform,
            status=status,
            notes=notes.strip() if notes and notes.strip() else None,
        )
    msg = quote("Achat enregistré avec succès auprès de ce vendeur !")
    return RedirectResponse(
        url=f"/sellers/{seller_id}?notice={msg}",
        status_code=303,
    )


# Paramètres de préremplissage de la section « Références de prix ».
REGAGES_PREFILL_QUERY = [
    ("prefill_name", "name", 200),
    ("prefill_set", "set_name", 200),
    ("prefill_number", "card_number", 50),
    ("prefill_lang", "language", 20),
    ("prefill_condition", "condition", 100),
    ("prefill_variant", "variant", 100),
    ("prefill_edition", "edition", 100),
    ("prefill_grading_company", "grading_company", 30),
    ("prefill_grade", "grade", 30),
    ("prefill_certification_number", "certification_number", 100),
    ("prefill_price", "price", 30),
    ("prefill_source_name", "source_name", 100),
    ("prefill_reference_kind", "reference_kind", 30),
    ("prefill_observed_at", "observed_at", 10),
    ("prefill_source_url", "source_url", 2048),
    ("prefill_sample_size", "sample_size", 10),
    ("prefill_note", "note", 300),
]


def _reglages_context(
    connection: sqlite3.Connection,
    *,
    prefill: dict[str, str],
    notice: str | None,
    error: str | None,
    compat_banner: bool = False,
) -> dict[str, Any]:
    from app.cardmarket import daily as cardmarket_daily

    profile = get_active_fee_profile(connection)
    reference_count = connection.execute(
        "SELECT COUNT(*) FROM market_references"
    ).fetchone()[0]
    cardmarket_count = connection.execute(
        "SELECT COUNT(*) AS n FROM cardmarket_prices"
    ).fetchone()["n"]
    cardmarket_guide_at = connection.execute(
        "SELECT MAX(fetched_at) AS fetched_at FROM cardmarket_prices"
    ).fetchone()["fetched_at"]
    catalog_count = connection.execute(
        "SELECT COUNT(*) AS n FROM catalog_items"
    ).fetchone()["n"]
    fee_fields = (
        ("buyer_shipping_cents", "Port aller à l’achat"),
        ("platform_fee_bps", "Commission plateforme"),
        ("seller_fixed_fee_cents", "Frais fixes par vente"),
        ("shipping_packaging_cents", "Expédition & emballage"),
    )
    missing_fee_labels = [
        label for field, label in fee_fields if getattr(profile, field) is None
    ]
    return {
        "page": "reglages",
        "profile": profile,
        "prefill": prefill,
        "notice": notice,
        "error": error,
        "compat_banner": compat_banner,
        "reference_kind_labels": REFERENCE_KIND_LABELS,
        "reference_count": reference_count,
        "cardmarket_count": cardmarket_count,
        "cardmarket_guide_at": cardmarket_guide_at,
        "catalog_count": catalog_count,
        "missing_fee_labels": missing_fee_labels,
        "saved_references": list_references(connection, limit=50),
        "cardmarket_sync": cardmarket_daily.load_state(connection),
    }


def _prefill_params(**values: str) -> dict[str, str]:
    """Normalise les préremplissages : langue « fr » par défaut, jamais None."""
    prefill = {key: value for key, value in values.items()}
    prefill["language"] = prefill.get("language") or "fr"
    return prefill


@app.get("/reglages", response_class=HTMLResponse)
def reglages_page(
    request: Request,
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
    """Frais, seuils, références de prix et synchronisations de marché."""
    prefill = _prefill_params(
        name=prefill_name,
        set_name=prefill_set,
        card_number=prefill_number,
        language=prefill_lang,
        condition=prefill_condition,
        variant=prefill_variant,
        edition=prefill_edition,
        grading_company=prefill_grading_company,
        grade=prefill_grade,
        certification_number=prefill_certification_number,
        price=prefill_price,
        source_name=prefill_source_name,
        reference_kind=prefill_reference_kind,
        observed_at=prefill_observed_at,
        source_url=prefill_source_url,
        sample_size=prefill_sample_size,
        note=prefill_note,
    )
    with connect(settings_from(request).database_path) as connection:
        check_database(connection)
        context = _reglages_context(
            connection, prefill=prefill, notice=notice, error=error
        )
    return templates.TemplateResponse(
        request=request, name="reglages.html", context=context
    )


@app.get("/achats", response_class=HTMLResponse)
def achats_page(
    request: Request, status: str = Query(default="all", max_length=20),
    notice: str | None = Query(default=None), error: str | None = Query(default=None),
) -> HTMLResponse:
    """Affiche le portefeuille et les messages de mise à jour."""
    with connect(settings_from(request).database_path) as connection:
        check_database(connection)
        data = purchases_page_data(connection, status=status)
    return templates.TemplateResponse(
        request=request, name="achats.html", context={"page": "achats", "notice": notice, "error": error, **data}
    )


@app.post("/achats/{purchase_id}/update")
def update_purchase(
    request: Request, purchase_id: int, status: str = Form(...),
    sale_price: str = Form(default=""),
) -> Response:
    """Enregistre le statut et le prix de vente réel facultatif d'un achat."""
    try:
        if status not in ("commande", "recu", "en_vente", "vendu"):
            raise ProfitabilityError("Choisissez un statut d'achat valide.")
        sale_cents = parse_euros_to_cents(sale_price, "Prix de vente réel") if sale_price.strip() else None
    except ProfitabilityError as error:
        return RedirectResponse(f"/achats?error={quote(str(error))}", status_code=303)
    with connect(settings_from(request).database_path) as connection:
        updated = seller_repository.update_purchase_status(
            connection, purchase_id, status=status, sale_price_cents=sale_cents,
        )
    if not updated:
        return HTMLResponse("Achat introuvable.", status_code=404)
    return RedirectResponse(f"/achats?notice={quote('Achat mis à jour.')}", status_code=303)


@app.get("/tasking", response_class=HTMLResponse)
def tasking_page(request: Request) -> HTMLResponse:
    """Afficher les plans et l’état Git disponibles en lecture seule."""
    return templates.TemplateResponse(request=request, name="tasking.html", context={"page": "tasking", **tasking_data()})


@app.get("/gestion", response_class=HTMLResponse)
def gestion_page(request: Request) -> HTMLResponse:
    """Index de gestion avancée : états réels des modules secondaires."""
    database_path = settings_from(request).database_path
    with connect(database_path) as connection:
        check_database(connection)
        data = gestion_page_data(connection, database_path)
    return templates.TemplateResponse(
        request=request, name="gestion.html", context={"page": "gestion", **data}
    )


@app.get("/validations/ocr", response_class=HTMLResponse)
def validation_ocr_page(request: Request) -> HTMLResponse:
    """Affiche la campagne réelle la plus récente et l'historique conservé."""
    runs = list_validation_runs()
    report = get_validation_run(runs[0]["id"]) if runs else None
    return templates.TemplateResponse(
        request=request, name="validation_ocr.html", context={"page": "gestion", "runs": runs, "report": report}
    )


@app.get("/validations/ocr/{run_id}", response_class=HTMLResponse)
def validation_ocr_detail(request: Request, run_id: str) -> HTMLResponse:
    """Compare les trois lectures d'une campagne sans toucher au catalogue."""
    report = get_validation_run(run_id)
    if report is None:
        return templates.TemplateResponse(request=request, name="404.html", status_code=404)
    return templates.TemplateResponse(
        request=request, name="validation_ocr.html",
        context={"page": "gestion", "runs": list_validation_runs(), "report": report},
    )


@app.get("/validations/ocr/{run_id}/images/{filename}")
def validation_ocr_image(run_id: str, filename: str) -> Response:
    """Sert uniquement une photo référencée par le rapport local."""
    path = validation_image_path(run_id, filename)
    if path is None:
        return Response(status_code=404)
    return FileResponse(path, media_type="image/webp")


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
    """Compatibilité des anciens liens vers la page d'analyse.

    - les préremplissages de références sont redirigés vers /reglages#cotes ;
    - les filtres d'analyse (verdict, q, set_name, sort) sont redirigés vers
      le catalogue unifié /catalog ;
    - les liens sans paramètres (y compris les anciennes ancres #parametres et
      #cotes) affichent la page de compatibilité : mêmes formulaires que
      /reglages, avec un bandeau d'orientation vers le catalogue.
    """
    raw_params = request.query_params
    prefill = _prefill_params(
        name=prefill_name,
        set_name=prefill_set,
        card_number=prefill_number,
        language=prefill_lang,
        condition=prefill_condition,
        variant=prefill_variant,
        edition=prefill_edition,
        grading_company=prefill_grading_company,
        grade=prefill_grade,
        certification_number=prefill_certification_number,
        price=prefill_price,
        source_name=prefill_source_name,
        reference_kind=prefill_reference_kind,
        observed_at=prefill_observed_at,
        source_url=prefill_source_url,
        sample_size=prefill_sample_size,
        note=prefill_note,
    )
    if any(value for key, value in prefill.items() if key != "language"):
        forward = {
            f"prefill_{key}": value
            for key, value in prefill.items()
            if value and not (key == "language" and value == "fr")
        }
        return RedirectResponse(
            f"/reglages?{urlencode(forward)}#cotes", status_code=303
        )
    wants_analysis = (
        ("q" in raw_params and q.strip() != "")
        or ("set_name" in raw_params and set_name != "")
        or ("verdict" in raw_params and verdict in VERDICT_LABELS)
        or ("sort" in raw_params and sort in VALID_SORTS)
    )
    if wants_analysis:
        target: dict[str, str] = {}
        if q.strip():
            target["q"] = q.strip()
        if set_name:
            target["set_name"] = set_name
        if verdict in VERDICT_LABELS:
            target["verdict"] = verdict
        if sort in VALID_SORTS:
            target["sort"] = sort
        if notice:
            target["notice"] = notice
        if error:
            target["error"] = error
        return RedirectResponse(f"/catalog?{urlencode(target)}", status_code=303)
    with connect(settings_from(request).database_path) as connection:
        check_database(connection)
        context = _reglages_context(
            connection,
            prefill=prefill,
            notice=notice,
            error=error,
            compat_banner=True,
        )
    return templates.TemplateResponse(
        request=request, name="reglages.html", context=context
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
            f"/reglages?error={quote(message)}#parametres", status_code=303
        )
    return RedirectResponse(
        f"/reglages?notice={quote('Paramètres de rentabilité enregistrés.')}#parametres",
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
            f"/reglages?error={quote(details)}#cotes", status_code=303
        )
    return RedirectResponse(
        f"/reglages?notice={quote(f'Cote enregistrée pour {reference.name}.')}#cotes",
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
            f"/reglages?error={quote(str(error))}#cotes", status_code=303
        )
    finally:
        await file.close()
    return RedirectResponse(
        f"/reglages?notice={quote(f'{count} cote(s) importée(s) ou mise(s) à jour.')}#cotes",
        status_code=303,
    )


@app.post("/profitability/references/{reference_id}/delete")
def remove_reference_cote(request: Request, reference_id: int) -> RedirectResponse:
    with connect(settings_from(request).database_path) as connection:
        deleted = delete_reference(connection, reference_id)
    if not deleted:
        return RedirectResponse(
            f"/reglages?error={quote('Cote introuvable.')}#cotes", status_code=303
        )
    return RedirectResponse(
        f"/reglages?notice={quote('Cote supprimée.')}#cotes", status_code=303
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
