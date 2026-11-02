import hashlib
import ipaddress
import json
import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast
from urllib.parse import urlsplit

from app.radar.repository import record_observation
from app.listing_identity import find_existing_listing_url, listing_url_identity
from app.identification.evidence import ObservationInput, validate_observations

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

MAX_IMPORT_BYTES = 2 * 1024 * 1024


class CatalogImportError(ValueError):
    pass


def validate_public_image_url(raw: str) -> str:
    """Valide une URL d'image destinée au navigateur, sans requête réseau.

    Empêche notamment les schémas actifs, les identifiants intégrés et les
    adresses locales littérales ; ne garantit pas la résolution DNS future.
    """
    try:
        parts = urlsplit(raw)
        host = (parts.hostname or "").lower().rstrip(".")
        if (parts.scheme.lower() != "https" or not host or parts.username is not None
                or parts.password is not None or parts.port not in (None, 443)
                or "." not in host or host.endswith((".localhost", ".local", ".internal"))):
            raise ValueError
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            raise ValueError
    except ValueError as error:
        raise ValueError("URL d’image HTTPS publique requise, sans identifiants intégrés.") from error
    return raw


class CatalogItem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    external_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    set_name: str = Field(min_length=1, max_length=200)
    card_number: str | None = Field(default=None, max_length=50)
    language: str = Field(default="fr", min_length=2, max_length=20)
    condition: str | None = Field(default=None, max_length=100)
    variant: str | None = Field(default=None, max_length=100)
    edition: str | None = Field(default=None, max_length=100)
    grading_company: str | None = Field(default=None, max_length=30)
    grade: str | None = Field(default=None, max_length=30)
    certification_number: str | None = Field(default=None, max_length=100)
    price_cents: int = Field(ge=0, le=1_000_000_000)
    shipping_cents: int | None = Field(default=None, ge=0, le=1_000_000_000)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    seller: str | None = Field(default=None, max_length=200)
    url: AnyHttpUrl | None = Field(default=None, max_length=2048)
    image_url: AnyHttpUrl | None = Field(default=None, max_length=2048)
    description: str | None = Field(default=None, max_length=10000)
    raw_data: dict[str, Any] | None = Field(default=None)
    identity_evidence: list[ObservationInput] | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def nested_observations(self) -> "CatalogItem":
        """Accepte le même contrat dans le brut collecteur, sans champ de confiance."""
        nested = (self.raw_data or {}).get("identity_evidence")
        if nested is not None:
            validated = validate_observations(nested)
            if self.identity_evidence is not None and self.identity_evidence != validated:
                raise ValueError("Deux listes d'observations contradictoires ont été fournies.")
            self.identity_evidence = validated
        return self

    @field_validator("identity_evidence")
    @classmethod
    def validate_identity_evidence(cls, value: list[ObservationInput] | None) -> list[ObservationInput] | None:
        """Valide les observations optionnelles sans autorité de confirmation."""
        return validate_observations(value) if value is not None else None

    @field_validator(
        "card_number",
        "condition",
        "variant",
        "edition",
        "grading_company",
        "grade",
        "certification_number",
        mode="before",
    )
    @classmethod
    def empty_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        value = value.upper()
        if not value.isascii() or not value.isalpha():
            raise ValueError("devise composée de trois lettres attendue")
        return value

    @field_validator("image_url")
    @classmethod
    def validate_image_url(cls, value: AnyHttpUrl | None) -> AnyHttpUrl | None:
        if value is not None:
            validate_public_image_url(str(value))
        return value


def parse_jsonl(content: bytes) -> list[CatalogItem]:
    if len(content) > MAX_IMPORT_BYTES:
        raise CatalogImportError("Le fichier dépasse la limite de 2 Mo.")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CatalogImportError("Le fichier doit être encodé en UTF-8.") from error

    items: list[CatalogItem] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError("un objet JSON est attendu")
            items.append(CatalogItem.model_validate(payload))
        except json.JSONDecodeError as error:
            raise CatalogImportError(
                f"Ligne {line_number} : JSON invalide ({error.msg})."
            ) from error
        except ValidationError as error:
            details = "; ".join(
                f"{'.'.join(str(part) for part in issue['loc']) or 'ligne'} : "
                f"{'champ obligatoire' if issue['type'] == 'missing' else issue['msg']}"
                for issue in error.errors()[:3]
            )
            raise CatalogImportError(f"Ligne {line_number} : {details}") from error
        except ValueError as error:
            raise CatalogImportError(f"Ligne {line_number} : {error}.") from error

    if not items:
        raise CatalogImportError("Le fichier ne contient aucune annonce.")
    return items


def import_jsonl(
    connection: sqlite3.Connection,
    content: bytes,
    source_name: str = "import-web",
) -> int:
    items = parse_jsonl(content)
    checksum = hashlib.sha256(content).hexdigest()
    try:
        with connection:
            if not connection.in_transaction:
                connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO sources (name, kind, enabled)
                VALUES (?, 'manual_jsonl', 1)
                ON CONFLICT(name) DO UPDATE SET enabled = 1
                """,
                (source_name,),
            )
            source_id = connection.execute(
                "SELECT id FROM sources WHERE name = ?", (source_name,)
            ).fetchone()[0]
            duplicate = connection.execute(
                "SELECT 1 FROM import_batches WHERE source_id = ? AND input_checksum = ?",
                (source_id, checksum),
            ).fetchone()
            if duplicate:
                raise CatalogImportError("Ce fichier a déjà été importé.")

            identities: set[tuple[str, str]] = set()
            for item in items:
                url = str(item.url) if item.url else None
                identity = listing_url_identity(source_name, url)
                if identity is not None:
                    if identity in identities or find_existing_listing_url(connection, source_name, url) is not None:
                        raise CatalogImportError("Cette annonce existe déjà pour cette plateforme. Aucun changement n’a été enregistré.")
                    identities.add(identity)

            batch_cursor = connection.execute(
                "INSERT INTO import_batches (source_id, input_checksum) VALUES (?, ?)",
                (source_id, checksum),
            )
            batch_id = batch_cursor.lastrowid
            connection.executemany(
                """
                INSERT INTO catalog_items (
                    source_id, import_batch_id, external_id, name, set_name,
                    card_number, language, condition, variant, edition,
                    grading_company, grade, certification_number,
                    price_cents, currency, seller, url, shipping_cents, image_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        source_id,
                        batch_id,
                        item.external_id,
                        item.name,
                        item.set_name,
                        item.card_number,
                        item.language,
                        item.condition,
                        item.variant,
                        item.edition,
                        item.grading_company,
                        item.grade,
                        item.certification_number,
                        item.price_cents,
                        item.currency,
                        item.seller,
                        str(item.url) if item.url else None,
                        item.shipping_cents,
                        str(item.image_url) if item.image_url else None,
                    )
                    for item in items
                ],
            )
            from app.identification.pipeline import resolve_and_apply
            rows = connection.execute("SELECT id FROM catalog_items WHERE import_batch_id = ? ORDER BY id", (batch_id,)).fetchall()
            for row, item in zip(rows, items, strict=True):
                # Les champs corrigés ne doivent jamais devenir les entrées d'apprentissage.
                raw_input = item.raw_data or {}
                raw_title = raw_input.get("title")
                original_title = (raw_title if isinstance(raw_title, str) and raw_title.strip() else
                                  next((observation.value for observation in item.identity_evidence if observation.field == "title"), "")
                                  if item.identity_evidence is not None else item.name)
                observed = {key: getattr(item, key) for key in ("name", "set_name", "card_number", "variant", "condition", "edition")}
                if "language" in item.model_fields_set:
                    observed["language"] = item.language
                observed["description"] = item.description if "description" in item.model_fields_set else raw_input.get("description", raw_input.get("body"))
                observed["_identity_input_origin"] = "original_text" if isinstance(raw_title, str) and raw_title.strip() else "structured_import"
                if item.identity_evidence is not None:
                    observed["identity_evidence"] = [observation.model_dump(exclude_none=True) for observation in item.identity_evidence]
                if isinstance(raw_input.get("ocr_status"), str) and raw_input["ocr_status"] in {"available", "unavailable"}:
                    observed["ocr_status"] = raw_input["ocr_status"]
                connection.execute(
                    "UPDATE catalog_items SET original_title=?, raw_data=? WHERE id=?",
                    (original_title, json.dumps(observed, ensure_ascii=False), row["id"]),
                )
                record_observation(
                    connection, int(row["id"]), price_cents=item.price_cents,
                    shipping_cents=item.shipping_cents, currency=item.currency, available=None,
                    observed_at=connection.execute("SELECT imported_at FROM catalog_items WHERE id=?", (row["id"],)).fetchone()[0],
                    origin="import",
                )
                resolve_and_apply(connection, int(row["id"]))
            connection.execute(
                "UPDATE import_batches SET status = 'completed' WHERE id = ?",
                (batch_id,),
            )
    except sqlite3.IntegrityError as error:
        raise CatalogImportError(
            "Import annulé : un identifiant externe existe déjà pour cette source."
        ) from error
    return len(items)


def dashboard_data(connection: sqlite3.Connection) -> dict[str, Any]:
    stats = {
        "item_count": connection.execute("SELECT COUNT(*) FROM catalog_items").fetchone()[0],
        "sets": connection.execute(
            "SELECT COUNT(DISTINCT set_name) FROM catalog_items"
        ).fetchone()[0],
        "imports": connection.execute(
            "SELECT COUNT(*) FROM import_batches WHERE status = 'completed'"
        ).fetchone()[0],
        "sources": connection.execute(
            "SELECT COUNT(*) FROM sources WHERE enabled = 1"
        ).fetchone()[0],
        "ambiguous_count": connection.execute(
            "SELECT COUNT(*) FROM catalog_items WHERE identification_status = 'ambiguous'"
        ).fetchone()[0],
        # Achats en cours = tous statuts sauf « vendu ».
        "purchases_ongoing": connection.execute(
            "SELECT COUNT(*) FROM purchases WHERE status != 'vendu'"
        ).fetchone()[0],
    }
    recent_imports = connection.execute(
        """
        SELECT b.id, b.status, b.imported_at, s.name AS source_name,
               COUNT(c.id) AS item_count
        FROM import_batches b
        JOIN sources s ON s.id = b.source_id
        LEFT JOIN catalog_items c ON c.import_batch_id = b.id
        GROUP BY b.id
        ORDER BY b.imported_at DESC, b.id DESC
        LIMIT 6
        """
    ).fetchall()
    latest_items = connection.execute(
        """
        SELECT id, name, set_name, card_number, price_cents, currency, condition, imported_at
        FROM catalog_items
        ORDER BY imported_at DESC, id DESC
        LIMIT 5
        """
    ).fetchall()
    return {"stats": stats, "recent_imports": recent_imports, "latest_items": latest_items}


CATALOG_PER_PAGE = 25

# Liste blanche des tris autorisés : aucune expression SQL ne provient de
# l'utilisateur, seules ces clés sont acceptées.
CATALOG_SORTS: dict[str, str] = {
    "import_desc": "c.imported_at DESC, c.id DESC",
    "import_asc": "c.imported_at ASC, c.id ASC",
    "name_asc": "c.name COLLATE NOCASE ASC, c.id ASC",
    "price_asc": "c.price_cents ASC, c.id ASC",
    "price_desc": "c.price_cents DESC, c.id ASC",
    # Fiabilité vendeur : réputation sur 5 étoiles ; comptes bannis et
    # profils inconnus ou insuffisants passent en dernier.
    "seller_reliability": (
        "CASE "
        "WHEN sp.id IS NULL THEN -1 "
        "WHEN sp.is_banned = 1 THEN -0.5 "
        "WHEN sp.feedback_count < 3 OR sp.reputation_bps IS NULL THEN 0 "
        "ELSE ROUND(sp.reputation_bps / 10000.0 * 5) "
        "END DESC, c.id ASC"
    ),
}
DEFAULT_CATALOG_SORT = "import_desc"
CATALOG_SOURCES = ("all", "vinted", "leboncoin", "ebay", "wallapop", "manual")
DEFAULT_CATALOG_SOURCE = "all"
CATALOG_IDENT_STATUSES = ("all", "identified", "ambiguous", "lot", "unidentified")
DEFAULT_CATALOG_IDENT_STATUS = "all"
# Verdicts de rentabilité (mêmes valeurs que le moteur de rentabilité).
CATALOG_VERDICTS = ("all", "opportunite", "surveiller", "non_rentable", "sans_cote")
DEFAULT_CATALOG_VERDICT = "all"
# Tris exécutés après évaluation complète (gain net, ROI). « price_asc » est
# partagé avec les tris SQL du catalogue (même sémantique : prix d'achat).
PROFITABILITY_SORT_KEYS = ("profit_desc", "roi_desc")

CATALOG_LISTING_COLUMNS = (
    "c.id, c.external_id, c.name, c.set_name, c.card_number, c.language, "
    "c.condition, c.variant, c.edition, c.grading_company, c.grade, "
    "c.certification_number, c.price_cents, c.shipping_cents, c.currency, c.seller, c.url, "
    "c.imported_at, s.name AS source_name, s.kind AS source_kind, "
    "c.identification_status, c.reference_card_id, c.identification_confidence, "
    "c.identification_reason, c.is_lot, c.seller_profile_id, c.seller_external_id"
)


def normalize_catalog_sort(sort: str) -> str:
    # Les tris de rentabilité (gain net, ROI) sont conservés : ils empruntent
    # le chemin d'évaluation complet, jamais la requête SQL du catalogue.
    if sort in CATALOG_SORTS or sort in PROFITABILITY_SORT_KEYS:
        return sort
    return DEFAULT_CATALOG_SORT


def normalize_catalog_source(source: str) -> str:
    return source if source in CATALOG_SOURCES else DEFAULT_CATALOG_SOURCE


def normalize_catalog_ident_status(status: str) -> str:
    return status if status in CATALOG_IDENT_STATUSES else DEFAULT_CATALOG_IDENT_STATUS


def normalize_catalog_verdict(verdict: str) -> str:
    return verdict if verdict in CATALOG_VERDICTS else DEFAULT_CATALOG_VERDICT


def _catalog_filters(
    query: str,
    set_name: str,
    source: str = DEFAULT_CATALOG_SOURCE,
    ident_status: str = DEFAULT_CATALOG_IDENT_STATUS,
) -> tuple[str, list[str]]:
    filters: list[str] = []
    parameters: list[str] = []
    if query:
        filters.append(
            "(c.name LIKE ? OR c.set_name LIKE ? OR c.card_number LIKE ? "
            "OR c.seller LIKE ? OR c.external_id LIKE ? OR c.original_title LIKE ?)"
        )
        parameters.extend([f"%{query}%"] * 6)
    if set_name:
        filters.append("c.set_name = ?")
        parameters.append(set_name)
    active_source = normalize_catalog_source(source)
    if active_source in ("vinted", "leboncoin", "ebay", "wallapop"):
        filters.append("s.name = ?")
        parameters.append(active_source)
    elif active_source == "manual":
        filters.append("s.kind = 'manual_jsonl'")

    active_ident = normalize_catalog_ident_status(ident_status)
    if active_ident != "all":
        filters.append("c.identification_status = ?")
        parameters.append(active_ident)

    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    return where, parameters


def _evaluation_path_required(verdict: str, sort: str) -> bool:
    """Le filtre verdict et les tris de rentabilité exigent une évaluation
    complète des annonces avant filtrage et pagination (compteurs exacts)."""
    return verdict != DEFAULT_CATALOG_VERDICT or sort in PROFITABILITY_SORT_KEYS


def _sort_evaluated_rows(
    evaluations: list[dict[str, Any]], sort: str
) -> list[dict[str, Any]]:
    """Réplique en mémoire les tris SQL du catalogue sur des lignes évaluées,
    pour les combinaisons « filtre verdict + tri catalogue ». Les clés de tri
    sont déjà normalisées (liste blanche)."""
    if sort == "name_asc":
        return sorted(
            evaluations, key=lambda row: (str(row["name"]).casefold(), int(row["id"]))
        )
    if sort == "price_asc":
        return sorted(
            evaluations, key=lambda row: (int(row["price_cents"]), int(row["id"]))
        )
    if sort == "price_desc":
        return sorted(
            evaluations, key=lambda row: (-int(row["price_cents"]), int(row["id"]))
        )
    if sort == "import_asc":
        return sorted(
            evaluations, key=lambda row: (str(row["imported_at"]), int(row["id"]))
        )
    if sort == "import_desc":
        return sorted(
            evaluations,
            key=lambda row: (str(row["imported_at"]), int(row["id"])),
            reverse=True,
        )
    if sort == "seller_reliability":

        def reliability_rank(row: Mapping[str, Any]) -> float:
            reputation = row.get("sp_reputation_bps")
            feedback_count = row.get("sp_feedback_count")
            if row.get("sp_is_banned") is None and reputation is None:
                return -1.0
            if row.get("sp_is_banned") == 1:
                return -0.5
            if feedback_count is None or feedback_count < 3 or reputation is None:
                return 0.0
            return round(int(reputation) / 10_000.0 * 5)

        return sorted(
            evaluations,
            key=lambda row: (-reliability_rank(row), int(row["id"])),
        )
    # Tri inconnu : comportement du tri par défaut (import récent).
    return _sort_evaluated_rows(evaluations, "import_desc")


def _evaluated_catalog_data(
    connection: sqlite3.Connection,
    *,
    query: str,
    set_name: str,
    source: str,
    ident_status: str,
    verdict: str,
    sort: str,
    page: int,
    per_page: int,
) -> dict[str, Any]:
    """Évalue toutes les annonces correspondant aux filtres catalogue, puis
    applique le filtre verdict, le tri choisi et la pagination en mémoire.
    Réutilise le moteur de rentabilité : aucun calcul dupliqué."""
    from app.profitability import (
        SortOrder,
        build_market_index,
        evaluate_listing,
        get_active_fee_profile,
        sort_evaluations,
    )

    profile = get_active_fee_profile(connection)
    market_index = build_market_index(connection, profile.min_catalog_samples)
    where, parameters = _catalog_filters(query, set_name, source, ident_status)
    rows = connection.execute(
        f"""
        SELECT {CATALOG_LISTING_COLUMNS},
               sp.reputation_bps AS sp_reputation_bps,
               sp.is_banned AS sp_is_banned,
               sp.feedback_count AS sp_feedback_count
        FROM catalog_items c
        JOIN sources s ON s.id = c.source_id
        LEFT JOIN seller_profiles sp ON sp.id = c.seller_profile_id
        {where}
        """,
        parameters,
    ).fetchall()
    evaluations = [evaluate_listing(row, profile, market_index) for row in rows]
    if verdict != DEFAULT_CATALOG_VERDICT:
        evaluations = [row for row in evaluations if row["verdict"] == verdict]
    if sort in PROFITABILITY_SORT_KEYS or sort == "price_asc":
        # price_asc appartient aux deux mondes ; sur les lignes évaluées on
        # utilise le tri du moteur de rentabilité (identique au tri SQL).
        evaluations = sort_evaluations(evaluations, cast(SortOrder, sort))
    else:
        evaluations = _sort_evaluated_rows(evaluations, sort)

    total = len(evaluations)
    total_pages = max(1, (total + per_page - 1) // per_page)
    current_page = min(max(1, page), total_pages)
    offset = (current_page - 1) * per_page
    sets = connection.execute(
        "SELECT DISTINCT c.set_name FROM catalog_items c ORDER BY c.set_name"
    ).fetchall()
    return {
        "items": evaluations[offset : offset + per_page],
        "total": total,
        "sets": sets,
        "page": current_page,
        "per_page": per_page,
        "total_pages": total_pages,
        "range_start": offset + 1 if total else 0,
        "range_end": min(offset + per_page, total),
        "sort": sort,
        "source": source,
        "ident_status": ident_status,
        "verdict": verdict,
        "evaluated": True,
    }


def catalog_data(
    connection: sqlite3.Connection,
    query: str = "",
    set_name: str = "",
    source: str = DEFAULT_CATALOG_SOURCE,
    ident_status: str = DEFAULT_CATALOG_IDENT_STATUS,
    verdict: str = DEFAULT_CATALOG_VERDICT,
    sort: str = DEFAULT_CATALOG_SORT,
    page: int = 1,
    per_page: int = CATALOG_PER_PAGE,
) -> dict[str, Any]:
    active_sort = normalize_catalog_sort(sort)
    active_source = normalize_catalog_source(source)
    active_ident = normalize_catalog_ident_status(ident_status)
    active_verdict = normalize_catalog_verdict(verdict)
    if _evaluation_path_required(active_verdict, active_sort):
        return _evaluated_catalog_data(
            connection,
            query=query,
            set_name=set_name,
            source=active_source,
            ident_status=active_ident,
            verdict=active_verdict,
            sort=active_sort,
            page=page,
            per_page=per_page,
        )
    where, parameters = _catalog_filters(query, set_name, active_source, active_ident)
    total = connection.execute(
        f"""
        SELECT COUNT(*)
        FROM catalog_items c
        JOIN sources s ON s.id = c.source_id
        {where}
        """,
        parameters,
    ).fetchone()[0]
    total_pages = max(1, (total + per_page - 1) // per_page)
    # Les pages invalides ou négatives retombent sur la première page, les
    # pages au-delà de la dernière reviennent sur la dernière.
    current_page = min(max(1, page), total_pages)
    offset = (current_page - 1) * per_page
    items = connection.execute(
        f"""
        SELECT {CATALOG_LISTING_COLUMNS}
        FROM catalog_items c
        JOIN sources s ON s.id = c.source_id
        LEFT JOIN seller_profiles sp ON sp.id = c.seller_profile_id
        {where}
        ORDER BY {CATALOG_SORTS[active_sort]}
        LIMIT ? OFFSET ?
        """,
        [*parameters, per_page, offset],
    ).fetchall()
    sets = connection.execute(
        "SELECT DISTINCT c.set_name FROM catalog_items c ORDER BY c.set_name"
    ).fetchall()
    range_start = offset + 1 if total else 0
    range_end = min(offset + per_page, total)
    return {
        "items": items,
        "total": total,
        "sets": sets,
        "page": current_page,
        "per_page": per_page,
        "total_pages": total_pages,
        "range_start": range_start,
        "range_end": range_end,
        "sort": active_sort,
        "source": active_source,
        "ident_status": active_ident,
        "verdict": active_verdict,
        "evaluated": False,
    }


def catalog_export_rows(
    connection: sqlite3.Connection,
    query: str = "",
    set_name: str = "",
    source: str = DEFAULT_CATALOG_SOURCE,
    ident_status: str = DEFAULT_CATALOG_IDENT_STATUS,
    verdict: str = DEFAULT_CATALOG_VERDICT,
) -> list[Any]:
    active_source = normalize_catalog_source(source)
    active_ident = normalize_catalog_ident_status(ident_status)
    active_verdict = normalize_catalog_verdict(verdict)
    where, parameters = _catalog_filters(query, set_name, active_source, active_ident)
    rows: list[Any] = connection.execute(
        f"""
        SELECT {CATALOG_LISTING_COLUMNS}
        FROM catalog_items c
        JOIN sources s ON s.id = c.source_id
        {where}
        ORDER BY c.name COLLATE NOCASE ASC, c.id ASC
        """,
        parameters,
    ).fetchall()
    if active_verdict == DEFAULT_CATALOG_VERDICT:
        return rows
    # Filtre verdict : évaluation complète des lignes exportées, mêmes règles
    # que la vue unifiée du catalogue.
    from app.profitability import (
        build_market_index,
        evaluate_listing,
        get_active_fee_profile,
    )

    profile = get_active_fee_profile(connection)
    market_index = build_market_index(connection, profile.min_catalog_samples)
    evaluations = [evaluate_listing(row, profile, market_index) for row in rows]
    return [
        row
        for row in evaluations
        if row["verdict"] == active_verdict
    ]


def catalog_item_detail(
    connection: sqlite3.Connection, item_id: int
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT c.id, c.external_id, c.name, c.set_name, c.card_number,
               c.language, c.condition, c.variant, c.edition, c.grading_company,
               c.grade, c.certification_number, c.price_cents, c.currency, c.seller,
               c.url, c.imported_at, c.import_batch_id, c.original_title,
               c.first_seen_at, c.last_seen_at, c.published_at, c.image_url,
               c.shipping_cents, c.is_active,
               c.identification_status, c.reference_card_id,
               c.identification_confidence, c.identification_reason, c.is_lot,
               c.seller_profile_id, c.seller_external_id,
               s.name AS source_name, s.kind AS source_kind,
               r.name AS ref_card_name, r.set_name AS ref_set_name,
               r.rarity AS ref_rarity, r.image_url AS ref_image_url,
               r.tcgdex_id AS ref_tcgdex_id
        FROM catalog_items c
        JOIN sources s ON s.id = c.source_id
        LEFT JOIN pokemon_reference_cards r ON r.id = c.reference_card_id
        WHERE c.id = ?
        """,
        (item_id,),
    ).fetchone()


def import_batch_detail(
    connection: sqlite3.Connection, batch_id: int
) -> dict[str, Any] | None:
    batch = connection.execute(
        """
        SELECT b.id, b.status, b.imported_at, b.input_checksum, s.name AS source_name
        FROM import_batches b
        JOIN sources s ON s.id = b.source_id
        WHERE b.id = ?
        """,
        (batch_id,),
    ).fetchone()
    if batch is None:
        return None
    items = connection.execute(
        """
        SELECT id, external_id, name, set_name, card_number, language, condition,
               price_cents, currency, seller, url, imported_at
        FROM catalog_items
        WHERE import_batch_id = ?
        ORDER BY id
        """,
        (batch_id,),
    ).fetchall()
    return {"batch": batch, "items": items}


def delete_import_batch(connection: sqlite3.Connection, batch_id: int) -> bool:
    with connection:
        connection.execute(
            "DELETE FROM catalog_items WHERE import_batch_id = ?", (batch_id,)
        )
        cursor = connection.execute(
            "DELETE FROM import_batches WHERE id = ?", (batch_id,)
        )
        if cursor.rowcount == 0:
            return False
    return True


def record_import_failure(
    connection: sqlite3.Connection,
    *,
    source_name: str,
    filename: str,
    content: bytes,
    error_message: str,
) -> int:
    checksum = hashlib.sha256(content).hexdigest()
    with connection:
        cursor = connection.execute(
            """
            INSERT INTO import_failures (source_name, filename, input_checksum, error_message)
            VALUES (?, ?, ?, ?)
            """,
            (source_name, filename, checksum, error_message),
        )
    return cursor.lastrowid


def recent_import_failures(
    connection: sqlite3.Connection, limit: int = 8
) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT id, source_name, filename, input_checksum, error_message, failed_at
        FROM import_failures
        ORDER BY failed_at DESC, id DESC
        LIMIT ?
        """,
        (max(limit, 1),),
    ).fetchall()


def import_failures_report(connection: sqlite3.Connection, limit: int = 50) -> str:
    rows = recent_import_failures(connection, limit)
    lines = [
        "Pokébourse — Rapport des échecs d'import",
        f"Généré le {datetime.now(UTC):%Y-%m-%dT%H:%M:%SZ}",
        "",
    ]
    if not rows:
        lines.append("Aucun échec d'import enregistré.")
    for index, row in enumerate(rows, start=1):
        lines.append(f"{index}. {row['failed_at']} — {row['filename']}")
        lines.append(f"   Source : {row['source_name']}")
        lines.append(f"   Empreinte SHA-256 : {row['input_checksum']}")
        lines.append(f"   Erreur : {row['error_message']}")
        lines.append("")
    return "\n".join(lines)


def reidentify_catalog_item(
    connection: sqlite3.Connection, item_id: int
) -> dict[str, Any] | None:
    """Réexamine via le service commun, sans écraser une confirmation applicable."""
    from app.config import Settings
    from app.identification.pipeline import resolve_and_apply

    if not catalog_item_detail(connection, item_id):
        return None
    with connection:
        resolution = resolve_and_apply(
            connection, item_id, auto_enrich=Settings.from_env().tcgdex_auto_enrich
        )
    item = catalog_item_detail(connection, item_id)
    return {
        "item_id": item_id, "name": item["name"], "set_name": item["set_name"],
        "card_number": item["card_number"], "status": resolution.result.status,
        "confidence": resolution.result.confidence, "reason": resolution.result.reason,
        "reference_card_id": item["reference_card_id"],
    }


def reidentify_catalog(
    connection: sqlite3.Connection, *, only_pending: bool = True
) -> dict[str, int]:
    """Réexamine les annonces avec le référentiel courant.

    À lancer après une mise à jour complète du catalogue TCGdex : les annonces
    importées alors que le référentiel était incomplet (ex. données seed)
    obtiennent une nouvelle chance d'être identifiées. Les confirmations
    humaines restent prioritaires (le service commun les respecte).
    """
    from app.config import Settings
    from app.identification.pipeline import resolve_and_apply

    query = "SELECT id FROM catalog_items"
    if only_pending:
        query += " WHERE identification_status IN ('unidentified', 'ambiguous')"
    item_ids = [int(row["id"]) for row in connection.execute(query).fetchall()]
    auto_enrich = Settings.from_env().tcgdex_auto_enrich
    counts: dict[str, int] = {}
    for item_id in item_ids:
        with connection:
            resolution = resolve_and_apply(connection, item_id, auto_enrich=auto_enrich)
        status = resolution.result.status
        counts[status] = counts.get(status, 0) + 1
    counts["examined"] = len(item_ids)
    return counts


def import_listings_from_extension(
    connection: sqlite3.Connection,
    content: bytes,
    source_name: str = "extension-chrome",
) -> list[dict[str, Any]]:
    """Importe et évalue immédiatement une liste d'annonces transmises par l'extension Chrome."""
    from app.profitability import enrich_catalog_items
    from app.identification.resolution import resolve_listing

    items = parse_jsonl(content)
    if not items:
        return []

    now = datetime.now(UTC).isoformat()
    with connection:
        if not connection.in_transaction:
            connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            INSERT INTO sources (name, kind, enabled)
            VALUES (?, 'api', 1)
            ON CONFLICT(name) DO UPDATE SET enabled = 1
            """,
            (source_name,),
        )
        source_id = connection.execute(
            "SELECT id FROM sources WHERE name = ?", (source_name,)
        ).fetchone()[0]

        checksum = hashlib.sha256(content).hexdigest()
        connection.execute(
            """
            INSERT INTO import_batches (source_id, input_checksum, status)
            VALUES (?, ?, 'completed')
            ON CONFLICT(source_id, input_checksum) DO UPDATE SET status = 'completed'
            """,
            (source_id, checksum),
        )
        batch_id = connection.execute(
            "SELECT id FROM import_batches WHERE source_id = ? AND input_checksum = ?",
            (source_id, checksum),
        ).fetchone()[0]

        saved_item_ids: list[int] = []
        for item in items:
            raw_payload = dict(item.raw_data or {})
            for key in ("name", "set_name", "card_number", "variant", "condition", "edition"):
                raw_payload.setdefault(key, getattr(item, key))
            if "language" in item.model_fields_set:
                raw_payload["language"] = item.language
            if "description" in item.model_fields_set:
                raw_payload["description"] = item.description
            original_title = raw_payload.get("title") or item.name
            raw_payload["_identity_input_origin"] = "original_text" if raw_payload.get("title") else "structured_import"
            raw_payload.pop("_observed_title", None)

            existing = connection.execute(
                "SELECT id, price_cents, currency, original_title, url FROM catalog_items WHERE source_id = ? AND external_id = ?",
                (source_id, item.external_id),
            ).fetchone()

            if existing is not None:
                old_identity = listing_url_identity(source_name, existing["url"])
                new_identity = listing_url_identity(source_name, str(item.url) if item.url else None)
                if old_identity is not None and new_identity is not None and old_identity != new_identity:
                    raise CatalogImportError("Identifiant de capture déjà utilisé pour une autre annonce. Import annulé.")

            if existing is None:
                # Une capture d'une autre voie d'import doit conserver la ligne
                # et les corrections humaines déjà enregistrées.
                matched_id = find_existing_listing_url(
                    connection, source_name, str(item.url) if item.url else None
                )
                if matched_id is not None:
                    saved_item_ids.append(matched_id)
                    continue

            if existing is not None and original_title != existing["original_title"]:
                raw_payload["_observed_title"] = original_title
            raw_json = json.dumps(raw_payload, ensure_ascii=False) if raw_payload else None

            if existing is not None:
                item_id = existing[0]
                connection.execute(
                    """
                    UPDATE catalog_items SET
                        price_cents = ?,
                        url = ?,
                        raw_data = COALESCE(?, raw_data),
                        last_seen_at = ?
                    WHERE id = ?
                    """,
                    (
                        item.price_cents if item.currency == existing["currency"] else existing["price_cents"],
                        str(item.url) if item.url else None,
                        raw_json,
                        now,
                        item_id,
                    ),
                )
            else:
                cursor = connection.execute(
                    """
                    INSERT INTO catalog_items (
                        source_id, import_batch_id, external_id, name, set_name,
                        card_number, language, condition, variant, edition,
                        grading_company, grade, certification_number,
                        price_cents, currency, seller, url, raw_data, imported_at,
                        first_seen_at, last_seen_at
                    ) VALUES (
                        ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?,
                        ?, ?, ?,
                        ?, ?, ?, ?, ?, ?,
                        ?, ?
                    )
                    """,
                    (
                        source_id,
                        batch_id,
                        item.external_id,
                        item.name,
                        item.set_name,
                        item.card_number,
                        item.language,
                        item.condition,
                        item.variant,
                        item.edition,
                        item.grading_company,
                        item.grade,
                        item.certification_number,
                        item.price_cents,
                        item.currency,
                        item.seller,
                        str(item.url) if item.url else None,
                        raw_json,
                        now,
                        now,
                        now,
                    ),
                )
                item_id = cursor.lastrowid

            record_observation(connection, int(item_id), price_cents=item.price_cents,
                               shipping_cents=None, currency=item.currency, available=None,
                               observed_at=now, origin="extension")
            if existing is None:
                connection.execute("UPDATE catalog_items SET original_title=? WHERE id=?", (original_title, item_id))
            reidentify_catalog_item(connection, item_id)
            saved_item_ids.append(item_id)

    placeholders = ",".join("?" for _ in saved_item_ids)
    rows = connection.execute(
        f"SELECT * FROM catalog_items WHERE id IN ({placeholders})",
        saved_item_ids,
    ).fetchall()

    evaluations, profile = enrich_catalog_items(connection, rows)

    results: list[dict[str, Any]] = []
    for ev in evaluations:
        ref_price_cents = ev.get("reference_price_cents")
        has_ref = ref_price_cents is not None
        purchase_cents = ev["price_cents"]
        net_profit_cents = ev.get("net_profit_cents")
        roi_bps = ev.get("roi_bps")

        results.append(
            {
                "id": ev["id"],
                "external_id": ev["external_id"],
                "name": ev["name"],
                "set_name": ev["set_name"],
                "card_number": ev.get("card_number"),
                "purchase_price_cents": purchase_cents,
                "purchase_price_formatted": f"{(purchase_cents / 100):.2f}".replace(".", ",")
                + " €",
                "reference_price_cents": ref_price_cents,
                "reference_price_formatted": (
                    f"{(ref_price_cents / 100):.2f}".replace(".", ",") + " €"
                    if has_ref
                    else "Cote non renseignée dans Pokébourse"
                ),
                "has_reference_price": has_ref,
                "net_profit_cents": net_profit_cents,
                "net_profit_formatted": (
                    (
                        f"{'+' if net_profit_cents >= 0 else ''}{(net_profit_cents / 100):.2f}".replace(
                            ".", ","
                        )
                        + " €"
                    )
                    if net_profit_cents is not None
                    else None
                ),
                "roi_bps": roi_bps,
                "roi_percent": (
                    f"{'+' if roi_bps >= 0 else ''}{(roi_bps / 100):.1f}%"
                    if roi_bps is not None
                    else None
                ),
                "verdict": ev["verdict"],
                "verdict_label": ev["verdict_label"],
                "reference_source": ev.get("reference_source"),
                "reference_source_name": ev.get("reference_source_name"),
                "identification_status": ev.get("identification_status"),
                "identification_reason": ev.get("identification_reason"),
                "is_lot": bool(ev.get("is_lot")),
                "decision_source": resolve_listing(connection, int(ev["id"])).decision_source,
                "url_detail": f"http://localhost:8000/catalog/{ev['id']}",
                "url_identify": f"http://localhost:8000/catalog/{ev['id']}#ident-title",
                "url_add_cote": "http://localhost:8000/reglages#cotes",
            }
        )

    return results

