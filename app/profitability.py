from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
import sqlite3
from typing import Any, Literal
import unicodedata

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
)

from app.catalog import MAX_IMPORT_BYTES

Verdict = Literal["opportunite", "surveiller", "non_rentable", "sans_cote"]
SortOrder = Literal["profit_desc", "roi_desc", "price_asc"]
ReferenceKind = Literal["ventes_conclues", "annonces", "estimation_manuelle"]

VERDICT_LABELS: dict[Verdict, str] = {
    "opportunite": "Opportunité",
    "surveiller": "Marge faible",
    "non_rentable": "Non rentable",
    "sans_cote": "Données insuffisantes",
}

REFERENCE_KIND_LABELS: dict[str, str] = {
    "ventes_conclues": "Ventes conclues",
    "annonces": "Prix d’annonces",
    "estimation_manuelle": "Estimation manuelle",
}


class ProfitabilityError(ValueError):
    pass


def normalize_token(value: str | None) -> str:
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFKD", value)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(stripped.casefold().split())


def build_card_key(
    *,
    name: str,
    set_name: str,
    card_number: str | None = None,
    language: str = "fr",
    condition: str | None = None,
    currency: str = "EUR",
    variant: str | None = None,
    edition: str | None = None,
    grading_company: str | None = None,
    grade: str | None = None,
) -> str:
    parts = [
        normalize_token(name),
        normalize_token(set_name),
        normalize_token(card_number),
        normalize_token(language or "fr"),
        normalize_token(condition),
        currency.strip().upper(),
    ]
    if any((variant, edition, grading_company, grade)):
        parts.extend(
            [
                normalize_token(variant),
                normalize_token(edition),
                normalize_token(grading_company),
                normalize_token(grade),
            ]
        )
    return json.dumps(parts, ensure_ascii=False, separators=(",", ":"))


def parse_euros_to_cents(raw: str | int | float, field_label: str) -> int:
    text = str(raw).strip().replace(" ", "").replace("\u00a0", "").replace(",", ".")
    if not text:
        raise ProfitabilityError(f"Le champ « {field_label} » est obligatoire.")
    try:
        amount = Decimal(text)
    except InvalidOperation as error:
        raise ProfitabilityError(
            f"Le champ « {field_label} » doit être un montant valide (ex. 5,00)."
        ) from error
    if not amount.is_finite() or amount < 0:
        raise ProfitabilityError(
            f"Le champ « {field_label} » doit être supérieur ou égal à 0."
        )
    exponent = amount.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -2:
        raise ProfitabilityError(
            f"Le champ « {field_label} » accepte au maximum deux décimales."
        )
    cents = int((amount * Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if cents > 1_000_000_000:
        raise ProfitabilityError(f"Le montant « {field_label} » dépasse la limite autorisée.")
    return cents


def parse_percent_to_bps(
    raw: str | int | float, field_label: str, *, max_bps: int = 10_000
) -> int:
    text = str(raw).strip().replace(" ", "").replace("\u00a0", "").replace(",", ".")
    if not text:
        raise ProfitabilityError(f"Le champ « {field_label} » est obligatoire.")
    try:
        percent = Decimal(text)
    except InvalidOperation as error:
        raise ProfitabilityError(
            f"Le champ « {field_label} » doit être un pourcentage valide (ex. 5 ou 12,5)."
        ) from error
    if not percent.is_finite() or percent < 0:
        raise ProfitabilityError(
            f"Le champ « {field_label} » doit être supérieur ou égal à 0."
        )
    exponent = percent.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -2:
        raise ProfitabilityError(
            f"Le champ « {field_label} » accepte au maximum deux décimales."
        )
    bps = int((percent * Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if bps > max_bps:
        max_pct = max_bps // 100
        raise ProfitabilityError(
            f"Le champ « {field_label} » ne peut pas dépasser {max_pct} %."
        )
    return bps


def median_cents(prices: Sequence[int]) -> int:
    if not prices:
        raise ValueError("impossible de calculer une médiane sur une liste vide")
    ordered = sorted(prices)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle] + 1) // 2


def round_ratio_bps(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        raise ValueError("le dénominateur doit être strictement positif")
    ratio = (Decimal(numerator) * Decimal(10_000)) / Decimal(denominator)
    return int(ratio.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class FeeProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: int = 1
    name: str = Field(default="Standard", min_length=1, max_length=100)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    buyer_shipping_cents: int | None = Field(default=None, ge=0, le=1_000_000_000)
    platform_fee_bps: int | None = Field(default=None, ge=0, le=10_000)
    seller_fixed_fee_cents: int | None = Field(default=None, ge=0, le=1_000_000_000)
    shipping_packaging_cents: int | None = Field(default=None, ge=0, le=1_000_000_000)
    min_net_profit_cents: int = Field(default=500, ge=0, le=1_000_000_000)
    min_roi_bps: int = Field(default=1500, ge=0, le=100_000)
    min_catalog_samples: int = Field(default=2, ge=2, le=100)
    updated_at: str | None = None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        value = value.upper()
        if not value.isascii() or not value.isalpha():
            raise ValueError("devise composée de trois lettres attendue")
        return value


class FeeProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    buyer_shipping_cents: int | None = Field(default=None, ge=0, le=1_000_000_000)
    platform_fee_bps: int | None = Field(default=None, ge=0, le=10_000)
    seller_fixed_fee_cents: int | None = Field(default=None, ge=0, le=1_000_000_000)
    shipping_packaging_cents: int | None = Field(default=None, ge=0, le=1_000_000_000)
    min_net_profit_cents: int = Field(ge=0, le=1_000_000_000)
    min_roi_bps: int = Field(ge=0, le=100_000)
    min_catalog_samples: int = Field(default=2, ge=2, le=100)


class ReferenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

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
    reference_price_cents: int = Field(ge=0, le=1_000_000_000)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    source_name: str | None = Field(default=None, max_length=100)
    reference_kind: ReferenceKind | None = None
    observed_at: date | None = None
    source_url: AnyHttpUrl | None = Field(default=None, max_length=2048)
    sample_size: int | None = Field(default=None, ge=1, le=1_000_000)
    note: str | None = Field(default=None, max_length=300)

    @field_validator(
        "card_number",
        "condition",
        "variant",
        "edition",
        "grading_company",
        "grade",
        "certification_number",
        "source_name",
        "note",
        mode="before",
    )
    @classmethod
    def empty_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("language")
    @classmethod
    def normalize_language(cls, value: str) -> str:
        return value.lower()

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        value = value.upper()
        if not value.isascii() or not value.isalpha():
            raise ValueError("devise composée de trois lettres attendue")
        return value

    def card_key(self) -> str:
        return build_card_key(
            name=self.name,
            set_name=self.set_name,
            card_number=self.card_number,
            language=self.language,
            condition=self.condition,
            currency=self.currency,
            variant=self.variant,
            edition=self.edition,
            grading_company=self.grading_company,
            grade=self.grade,
        )


def get_active_fee_profile(connection: sqlite3.Connection) -> FeeProfile:
    row = connection.execute(
        """
        SELECT id, name, currency, buyer_shipping_cents, platform_fee_bps,
               seller_fixed_fee_cents, shipping_packaging_cents,
               min_net_profit_cents, min_roi_bps, min_catalog_samples, updated_at
        FROM fee_profiles
        WHERE is_active = 1
        ORDER BY id ASC
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        return FeeProfile()
    return FeeProfile.model_validate(dict(row))


def update_active_fee_profile(
    connection: sqlite3.Connection, update: FeeProfileUpdate
) -> FeeProfile:
    current = get_active_fee_profile(connection)
    with connection:
        connection.execute(
            """
            INSERT INTO fee_profiles (
                id, name, currency, buyer_shipping_cents, platform_fee_bps,
                seller_fixed_fee_cents, shipping_packaging_cents,
                min_net_profit_cents, min_roi_bps, min_catalog_samples, is_active, updated_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            )
            ON CONFLICT(id) DO UPDATE SET
                buyer_shipping_cents = excluded.buyer_shipping_cents,
                platform_fee_bps = excluded.platform_fee_bps,
                seller_fixed_fee_cents = excluded.seller_fixed_fee_cents,
                shipping_packaging_cents = excluded.shipping_packaging_cents,
                min_net_profit_cents = excluded.min_net_profit_cents,
                min_roi_bps = excluded.min_roi_bps,
                min_catalog_samples = excluded.min_catalog_samples,
                is_active = 1,
                updated_at = excluded.updated_at
            """,
            (
                current.id,
                current.name,
                current.currency,
                update.buyer_shipping_cents,
                update.platform_fee_bps,
                update.seller_fixed_fee_cents,
                update.shipping_packaging_cents,
                update.min_net_profit_cents,
                update.min_roi_bps,
                update.min_catalog_samples,
            ),
        )
    return get_active_fee_profile(connection)


def parse_references_jsonl(content: bytes) -> list[ReferenceInput]:
    if len(content) > MAX_IMPORT_BYTES:
        raise ProfitabilityError("Le fichier de cotes dépasse la limite de 2 Mo.")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ProfitabilityError("Le fichier de cotes doit être encodé en UTF-8.") from error

    references: list[ReferenceInput] = []
    seen_keys: set[str] = set()
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError("un objet JSON est attendu")
            reference = ReferenceInput.model_validate(payload)
        except json.JSONDecodeError as error:
            raise ProfitabilityError(
                f"Ligne {line_number} : JSON invalide ({error.msg})."
            ) from error
        except ValidationError as error:
            details = "; ".join(
                f"{'.'.join(str(part) for part in issue['loc']) or 'ligne'} : {issue['msg']}"
                for issue in error.errors()[:3]
            )
            raise ProfitabilityError(f"Ligne {line_number} : {details}") from error
        except ValueError as error:
            raise ProfitabilityError(f"Ligne {line_number} : {error}.") from error

        key = reference.card_key()
        if key in seen_keys:
            raise ProfitabilityError(
                f"Ligne {line_number} : cote en doublon pour « {reference.name} » ({reference.set_name})."
            )
        seen_keys.add(key)
        references.append(reference)

    if not references:
        raise ProfitabilityError("Le fichier ne contient aucune cote de référence.")
    return references


REFERENCE_UPSERT_SQL = """
    INSERT INTO market_references (
        card_key, name, set_name, card_number, language, condition,
        variant, edition, grading_company, grade, certification_number,
        reference_price_cents, currency, source_kind, source_name,
        reference_kind, observed_at, source_url, sample_size, note, updated_at
    ) VALUES (
        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    )
    ON CONFLICT(card_key) DO UPDATE SET
        name = excluded.name,
        set_name = excluded.set_name,
        card_number = excluded.card_number,
        language = excluded.language,
        condition = excluded.condition,
        variant = excluded.variant,
        edition = excluded.edition,
        grading_company = excluded.grading_company,
        grade = excluded.grade,
        certification_number = excluded.certification_number,
        reference_price_cents = excluded.reference_price_cents,
        currency = excluded.currency,
        source_kind = excluded.source_kind,
        source_name = excluded.source_name,
        reference_kind = excluded.reference_kind,
        observed_at = excluded.observed_at,
        source_url = excluded.source_url,
        sample_size = excluded.sample_size,
        note = excluded.note,
        updated_at = excluded.updated_at
"""


def reference_values(
    reference: ReferenceInput, source_kind: Literal["manual", "jsonl"]
) -> tuple[Any, ...]:
    return (
        reference.card_key(),
        reference.name,
        reference.set_name,
        reference.card_number,
        reference.language,
        reference.condition,
        reference.variant,
        reference.edition,
        reference.grading_company,
        reference.grade,
        reference.certification_number,
        reference.reference_price_cents,
        reference.currency,
        source_kind,
        reference.source_name,
        reference.reference_kind,
        reference.observed_at.isoformat() if reference.observed_at else None,
        str(reference.source_url) if reference.source_url else None,
        reference.sample_size,
        reference.note,
    )


def upsert_reference(
    connection: sqlite3.Connection,
    reference: ReferenceInput,
    source_kind: Literal["manual", "jsonl"] = "manual",
) -> int:
    key = reference.card_key()
    with connection:
        connection.execute(
            REFERENCE_UPSERT_SQL, reference_values(reference, source_kind)
        )
        row = connection.execute(
            "SELECT id FROM market_references WHERE card_key = ?", (key,)
        ).fetchone()
    return int(row[0])


def import_references_jsonl(connection: sqlite3.Connection, content: bytes) -> int:
    references = parse_references_jsonl(content)
    with connection:
        connection.executemany(
            REFERENCE_UPSERT_SQL,
            [reference_values(reference, "jsonl") for reference in references],
        )
    return len(references)


def delete_reference(connection: sqlite3.Connection, reference_id: int) -> bool:
    with connection:
        cursor = connection.execute(
            "DELETE FROM market_references WHERE id = ?", (reference_id,)
        )
    return cursor.rowcount > 0


def list_references(
    connection: sqlite3.Connection, limit: int = 100
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT id, name, set_name, card_number, language, condition,
               variant, edition, grading_company, grade, certification_number,
               reference_price_cents, currency, source_kind, source_name,
               reference_kind, observed_at, source_url, sample_size, note, updated_at
        FROM market_references
        ORDER BY updated_at DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


class MarketIndex:
    def __init__(
        self,
        references_by_key: Mapping[str, Mapping[str, Any]],
        strict_catalog_prices: Mapping[str, list[tuple[int, int]]],
        min_catalog_samples: int,
    ) -> None:
        self._references = references_by_key
        self._strict_prices = strict_catalog_prices
        self._min_samples = min_catalog_samples

    def resolve(
        self, item: Mapping[str, Any], target_currency: str
    ) -> tuple[int | None, str | None, int, dict[str, Any] | None]:
        currency = str(item["currency"]).upper()
        if currency != target_currency.upper():
            return None, "devise_differente", 0, None

        identity = {
            "name": str(item["name"]),
            "set_name": str(item["set_name"]),
            "language": str(item.get("language") or "fr"),
            "currency": currency,
            "variant": item.get("variant"),
            "edition": item.get("edition"),
            "grading_company": item.get("grading_company"),
            "grade": item.get("grade"),
        }
        card_number = item.get("card_number") or ""
        condition = item.get("condition") or ""
        candidates = [
            (
                "exacte",
                build_card_key(
                    **identity, card_number=card_number, condition=condition
                ),
            ),
            (
                "etat_generique",
                build_card_key(**identity, card_number=card_number, condition=""),
            ),
            (
                "numero_generique",
                build_card_key(**identity, card_number="", condition=condition),
            ),
            (
                "generique",
                build_card_key(**identity, card_number="", condition=""),
            ),
        ]
        seen_keys: set[str] = set()
        for match_scope, key in candidates:
            if key in seen_keys:
                continue
            seen_keys.add(key)
            ref = self._references.get(key)
            if ref is not None:
                sample_size = ref.get("sample_size")
                return (
                    int(ref["reference_price_cents"]),
                    "reference",
                    int(sample_size) if sample_size is not None else 0,
                    {**dict(ref), "match_scope": match_scope},
                )

        if normalize_token(condition):
            strict_key = candidates[0][1]
            item_id = item.get("id")
            strict_group = [
                price
                for row_id, price in self._strict_prices.get(strict_key, [])
                if row_id != item_id
            ]
            if len(strict_group) >= self._min_samples:
                return (
                    median_cents(strict_group),
                    "catalog_median",
                    len(strict_group),
                    None,
                )

        return None, None, 0, None


def build_market_index(
    connection: sqlite3.Connection, min_catalog_samples: int
) -> MarketIndex:
    ref_rows = connection.execute(
        """
        SELECT card_key, reference_price_cents, currency, source_name,
               reference_kind, observed_at, source_url, sample_size, note, updated_at
        FROM market_references
        """
    ).fetchall()
    references_by_key = {row["card_key"]: dict(row) for row in ref_rows}

    strict_prices: dict[str, list[tuple[int, int]]] = defaultdict(list)
    item_rows = connection.execute(
        """
        SELECT id, name, set_name, card_number, language, condition,
               variant, edition, grading_company, grade, price_cents, currency
        FROM catalog_items
        """
    ).fetchall()
    for row in item_rows:
        condition = row["condition"] or ""
        if not normalize_token(condition):
            continue
        strict_key = build_card_key(
            name=row["name"],
            set_name=row["set_name"],
            card_number=row["card_number"] or "",
            language=row["language"] or "fr",
            condition=condition,
            currency=row["currency"],
            variant=row["variant"],
            edition=row["edition"],
            grading_company=row["grading_company"],
            grade=row["grade"],
        )
        strict_prices[strict_key].append((int(row["id"]), int(row["price_cents"])))

    return MarketIndex(
        references_by_key=references_by_key,
        strict_catalog_prices=strict_prices,
        min_catalog_samples=min_catalog_samples,
    )


def evaluate_listing(
    item: Mapping[str, Any], profile: FeeProfile, market_index: MarketIndex
) -> dict[str, Any]:
    row = dict(item)
    purchase_price_cents = int(row["price_cents"])
    missing_fee_fields = [
        field
        for field in (
            "buyer_shipping_cents",
            "platform_fee_bps",
            "seller_fixed_fee_cents",
            "shipping_packaging_cents",
        )
        if getattr(profile, field) is None
    ]
    total_cost_cents = (
        purchase_price_cents + profile.buyer_shipping_cents
        if profile.buyer_shipping_cents is not None
        else None
    )
    reference_price_cents, reference_source, sample_count, reference_metadata = (
        market_index.resolve(row, profile.currency)
    )
    metadata = reference_metadata or {}
    result = {
        **row,
        "total_cost_cents": total_cost_cents,
        "reference_price_cents": reference_price_cents,
        "reference_source": reference_source,
        "sample_count": sample_count,
        "reference_note": metadata.get("note"),
        "reference_source_name": metadata.get("source_name"),
        "reference_kind": metadata.get("reference_kind"),
        "reference_kind_label": REFERENCE_KIND_LABELS.get(
            metadata.get("reference_kind") or ""
        ),
        "reference_observed_at": metadata.get("observed_at"),
        "reference_source_url": metadata.get("source_url"),
        "reference_updated_at": metadata.get("updated_at"),
        "reference_match_scope": metadata.get("match_scope"),
        "missing_fee_fields": missing_fee_fields,
        "platform_fee_cents": None,
        "total_selling_fees_cents": None,
        "net_proceeds_cents": None,
        "net_profit_cents": None,
        "roi_bps": None,
        "margin_bps": None,
        "verdict": "sans_cote",
        "verdict_label": VERDICT_LABELS["sans_cote"],
    }
    if reference_price_cents is None or missing_fee_fields:
        return result

    assert total_cost_cents is not None
    assert profile.platform_fee_bps is not None
    assert profile.seller_fixed_fee_cents is not None
    assert profile.shipping_packaging_cents is not None
    platform_fee_cents = (
        reference_price_cents * profile.platform_fee_bps + 5_000
    ) // 10_000
    total_selling_fees_cents = (
        platform_fee_cents
        + profile.seller_fixed_fee_cents
        + profile.shipping_packaging_cents
    )
    net_proceeds_cents = reference_price_cents - total_selling_fees_cents
    net_profit_cents = net_proceeds_cents - total_cost_cents
    roi_bps = (
        round_ratio_bps(net_profit_cents, total_cost_cents)
        if total_cost_cents > 0
        else None
    )
    margin_bps = (
        round_ratio_bps(net_profit_cents, reference_price_cents)
        if reference_price_cents > 0
        else None
    )

    if total_cost_cents == 0:
        verdict: Verdict = "sans_cote"
    elif net_profit_cents < 0:
        verdict = "non_rentable"
    else:
        meets_profit = net_profit_cents >= profile.min_net_profit_cents
        meets_roi = (
            net_profit_cents * 10_000
            >= profile.min_roi_bps * total_cost_cents
        )
        verdict = "opportunite" if (meets_profit and meets_roi) else "surveiller"

    return {
        **result,
        "platform_fee_cents": platform_fee_cents,
        "total_selling_fees_cents": total_selling_fees_cents,
        "net_proceeds_cents": net_proceeds_cents,
        "net_profit_cents": net_profit_cents,
        "roi_bps": roi_bps,
        "margin_bps": margin_bps,
        "verdict": verdict,
        "verdict_label": VERDICT_LABELS[verdict],
    }


def _sort_evaluations(
    evaluations: list[dict[str, Any]], sort: SortOrder
) -> list[dict[str, Any]]:
    verdict_rank = {
        "opportunite": 0,
        "surveiller": 1,
        "non_rentable": 2,
        "sans_cote": 3,
    }
    if sort == "roi_desc":
        return sorted(
            evaluations,
            key=lambda item: (
                item["reference_price_cents"] is None,
                verdict_rank[item["verdict"]],
                -(item["roi_bps"] if item["roi_bps"] is not None else -10_000_000),
                -(item["net_profit_cents"] if item["net_profit_cents"] is not None else -10_000_000_000),
            ),
        )
    if sort == "price_asc":
        return sorted(
            evaluations,
            key=lambda item: (
                int(item["price_cents"]),
                verdict_rank[item["verdict"]],
            ),
        )
    return sorted(
        evaluations,
        key=lambda item: (
            item["reference_price_cents"] is None,
            verdict_rank[item["verdict"]],
            -(item["net_profit_cents"] if item["net_profit_cents"] is not None else -10_000_000_000),
            -(item["roi_bps"] if item["roi_bps"] is not None else -10_000_000),
        ),
    )


def summarize_evaluations(evaluations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    opportunities = [row for row in evaluations if row["verdict"] == "opportunite"]
    evaluated = [row for row in evaluations if row["reference_price_cents"] is not None]
    by_reference = sum(1 for row in evaluated if row["reference_source"] == "reference")
    by_median = sum(
        1 for row in evaluated if row["reference_source"] == "catalog_median"
    )
    roi_candidates = [
        int(row["roi_bps"]) for row in opportunities if row["roi_bps"] is not None
    ]
    return {
        "catalog_count": len(evaluations),
        "evaluated_count": len(evaluated),
        "reference_match_count": by_reference,
        "median_match_count": by_median,
        "missing_count": sum(1 for row in evaluations if row["verdict"] == "sans_cote"),
        "opportunity_count": len(opportunities),
        "watch_count": sum(1 for row in evaluations if row["verdict"] == "surveiller"),
        "unprofitable_count": sum(
            1 for row in evaluations if row["verdict"] == "non_rentable"
        ),
        "potential_profit_cents": sum(
            int(row["net_profit_cents"]) for row in opportunities
        ),
        "best_roi_bps": max(roi_candidates) if roi_candidates else None,
    }


def evaluate_catalog(
    connection: sqlite3.Connection,
    *,
    query: str = "",
    set_name: str = "",
    verdict: str = "all",
    sort: SortOrder = "profit_desc",
) -> tuple[list[dict[str, Any]], dict[str, Any], FeeProfile]:
    profile = get_active_fee_profile(connection)
    market_index = build_market_index(connection, profile.min_catalog_samples)

    all_rows = connection.execute(
        """
        SELECT id, external_id, name, set_name, card_number, language, condition,
               variant, edition, grading_company, grade, certification_number,
               price_cents, currency, seller, url, imported_at
        FROM catalog_items
        ORDER BY imported_at DESC, id DESC
        """
    ).fetchall()
    all_evaluations = [
        evaluate_listing(row, profile, market_index) for row in all_rows
    ]
    summary = summarize_evaluations(all_evaluations)

    filtered = all_evaluations
    if query:
        needle = query.casefold()
        filtered = [
            row
            for row in filtered
            if needle in str(row["name"]).casefold()
            or needle in str(row["set_name"]).casefold()
            or needle in str(row["card_number"] or "").casefold()
            or needle in str(row["seller"] or "").casefold()
            or needle in str(row["external_id"]).casefold()
        ]
    if set_name:
        filtered = [row for row in filtered if row["set_name"] == set_name]
    if verdict in VERDICT_LABELS:
        filtered = [row for row in filtered if row["verdict"] == verdict]

    return _sort_evaluations(filtered, sort), summary, profile


def profitability_page_data(
    connection: sqlite3.Connection,
    *,
    query: str = "",
    set_name: str = "",
    verdict: str = "all",
    sort: SortOrder = "profit_desc",
    limit: int = 200,
) -> dict[str, Any]:
    filtered, summary, profile = evaluate_catalog(
        connection, query=query, set_name=set_name, verdict=verdict, sort=sort
    )
    sets = connection.execute(
        "SELECT DISTINCT set_name FROM catalog_items ORDER BY set_name"
    ).fetchall()
    reference_count = connection.execute(
        "SELECT COUNT(*) FROM market_references"
    ).fetchone()[0]
    return {
        "profile": profile,
        "summary": summary,
        "evaluations": filtered[:limit],
        "filtered_total": len(filtered),
        "sets": sets,
        "saved_references": list_references(connection, limit=50),
        "reference_count": reference_count,
    }


def profitability_dashboard_summary(
    connection: sqlite3.Connection, *, top_limit: int = 5
) -> dict[str, Any]:
    filtered, summary, profile = evaluate_catalog(
        connection, verdict="opportunite", sort="profit_desc"
    )
    return {
        "fee_profile": profile,
        "profit_summary": summary,
        "top_opportunities": filtered[:top_limit],
    }


def enrich_catalog_items(
    connection: sqlite3.Connection, rows: Sequence[Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], FeeProfile]:
    profile = get_active_fee_profile(connection)
    market_index = build_market_index(connection, profile.min_catalog_samples)
    return [evaluate_listing(row, profile, market_index) for row in rows], profile
