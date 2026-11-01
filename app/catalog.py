import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, ValidationError, field_validator

MAX_IMPORT_BYTES = 2 * 1024 * 1024


class CatalogImportError(ValueError):
    pass


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
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    seller: str | None = Field(default=None, max_length=200)
    url: AnyHttpUrl | None = Field(default=None, max_length=2048)
    description: str | None = Field(default=None, max_length=10000)
    raw_data: dict[str, Any] | None = Field(default=None)

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
                f"{'.'.join(str(part) for part in issue['loc']) or 'ligne'} : {issue['msg']}"
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
                    price_cents, currency, seller, url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    )
                    for item in items
                ],
            )
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
CATALOG_SOURCES = ("all", "vinted", "leboncoin", "manual")
DEFAULT_CATALOG_SOURCE = "all"
CATALOG_IDENT_STATUSES = ("all", "identified", "ambiguous", "lot", "unidentified")
DEFAULT_CATALOG_IDENT_STATUS = "all"

CATALOG_LISTING_COLUMNS = (
    "c.id, c.external_id, c.name, c.set_name, c.card_number, c.language, "
    "c.condition, c.variant, c.edition, c.grading_company, c.grade, "
    "c.certification_number, c.price_cents, c.currency, c.seller, c.url, "
    "c.imported_at, s.name AS source_name, s.kind AS source_kind, "
    "c.identification_status, c.reference_card_id, c.identification_confidence, "
    "c.identification_reason, c.is_lot, c.seller_profile_id, c.seller_external_id"
)


def normalize_catalog_sort(sort: str) -> str:
    return sort if sort in CATALOG_SORTS else DEFAULT_CATALOG_SORT


def normalize_catalog_source(source: str) -> str:
    return source if source in CATALOG_SOURCES else DEFAULT_CATALOG_SOURCE


def normalize_catalog_ident_status(status: str) -> str:
    return status if status in CATALOG_IDENT_STATUSES else DEFAULT_CATALOG_IDENT_STATUS


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
    if active_source == "vinted":
        filters.append("s.name = 'vinted'")
    elif active_source == "leboncoin":
        filters.append("s.name = 'leboncoin'")
    elif active_source == "manual":
        filters.append("s.kind = 'manual_jsonl'")

    active_ident = normalize_catalog_ident_status(ident_status)
    if active_ident != "all":
        filters.append("c.identification_status = ?")
        parameters.append(active_ident)

    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    return where, parameters


def catalog_data(
    connection: sqlite3.Connection,
    query: str = "",
    set_name: str = "",
    source: str = DEFAULT_CATALOG_SOURCE,
    ident_status: str = DEFAULT_CATALOG_IDENT_STATUS,
    sort: str = DEFAULT_CATALOG_SORT,
    page: int = 1,
    per_page: int = CATALOG_PER_PAGE,
) -> dict[str, Any]:
    active_sort = normalize_catalog_sort(sort)
    active_source = normalize_catalog_source(source)
    active_ident = normalize_catalog_ident_status(ident_status)
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
    }


def catalog_export_rows(
    connection: sqlite3.Connection,
    query: str = "",
    set_name: str = "",
    source: str = DEFAULT_CATALOG_SOURCE,
    ident_status: str = DEFAULT_CATALOG_IDENT_STATUS,
) -> list[sqlite3.Row]:
    active_source = normalize_catalog_source(source)
    active_ident = normalize_catalog_ident_status(ident_status)
    where, parameters = _catalog_filters(query, set_name, active_source, active_ident)
    return connection.execute(
        f"""
        SELECT {CATALOG_LISTING_COLUMNS}
        FROM catalog_items c
        JOIN sources s ON s.id = c.source_id
        {where}
        ORDER BY c.name COLLATE NOCASE ASC, c.id ASC
        """,
        parameters,
    ).fetchall()


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
    """Réexamine et met à jour l'identification d'une annonce du catalogue."""
    from app.identification.matcher import CardMatcher
    from app.tcgdex.cache import TcgdexCache

    item = catalog_item_detail(connection, item_id)
    if not item:
        return None

    raw_data = None
    title = item["original_title"] or item["name"]
    raw_row = connection.execute(
        "SELECT raw_data FROM catalog_items WHERE id = ?", (item_id,)
    ).fetchone()
    if raw_row and raw_row[0]:
        try:
            raw_data = json.loads(raw_row[0])
        except Exception:
            pass

    matcher = CardMatcher(TcgdexCache(connection))
    ident = matcher.identify(title, raw_data=raw_data)

    name = item["name"]
    set_name = item["set_name"]
    card_number = item["card_number"]
    ref_card_id = None
    is_lot = 1 if ident.features.is_lot else 0

    if ident.status == "identified" and ident.matched_card:
        name = ident.matched_card.name
        set_name = ident.matched_card.set_name
        card_number = ident.matched_card.local_id
        ref_card_id = ident.matched_card.id
    elif ident.status == "lot":
        name = title
        set_name = "Lot / Coffret"
        card_number = None
        is_lot = 1
    elif ident.status == "ambiguous":
        if ident.features.name:
            name = ident.features.name
        if ident.features.set_name:
            set_name = ident.features.set_name
        if ident.features.card_number:
            card_number = ident.features.card_number

    with connection:
        connection.execute(
            """
            UPDATE catalog_items SET
                name = ?, set_name = ?, card_number = ?,
                identification_status = ?, reference_card_id = ?,
                identification_confidence = ?, identification_reason = ?,
                is_lot = ?
            WHERE id = ?
            """,
            (
                name,
                set_name,
                card_number,
                ident.status,
                ref_card_id,
                ident.confidence,
                ident.reason,
                is_lot,
                item_id,
            ),
        )

    return {
        "item_id": item_id,
        "name": name,
        "set_name": set_name,
        "card_number": card_number,
        "status": ident.status,
        "confidence": ident.confidence,
        "reason": ident.reason,
        "reference_card_id": ref_card_id,
    }


def import_listings_from_extension(
    connection: sqlite3.Connection,
    content: bytes,
    source_name: str = "extension-chrome",
) -> list[dict[str, Any]]:
    """Importe et évalue immédiatement une liste d'annonces transmises par l'extension Chrome."""
    from app.profitability import enrich_catalog_items

    items = parse_jsonl(content)
    if not items:
        return []

    now = datetime.now(UTC).isoformat()
    with connection:
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
            if item.description and "description" not in raw_payload:
                raw_payload["description"] = item.description
            raw_json = json.dumps(raw_payload, ensure_ascii=False) if raw_payload else None

            existing = connection.execute(
                "SELECT id FROM catalog_items WHERE source_id = ? AND external_id = ?",
                (source_id, item.external_id),
            ).fetchone()

            if existing is not None:
                item_id = existing[0]
                connection.execute(
                    """
                    UPDATE catalog_items SET
                        price_cents = ?,
                        currency = ?,
                        seller = ?,
                        url = ?,
                        raw_data = COALESCE(?, raw_data),
                        last_seen_at = ?,
                        import_batch_id = ?
                    WHERE id = ?
                    """,
                    (
                        item.price_cents,
                        item.currency,
                        item.seller,
                        str(item.url) if item.url else None,
                        raw_json,
                        now,
                        batch_id,
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

            saved_item_ids.append(item_id)
            reidentify_catalog_item(connection, item_id)

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
                "url_detail": f"http://localhost:8000/catalog/{ev['id']}",
                "url_add_cote": "http://localhost:8000/profitability#cotes",
            }
        )

    return results

