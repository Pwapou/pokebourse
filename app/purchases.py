"""Vue centralisée des achats et de leurs montants par devise."""

import sqlite3
from typing import Any

from app.sellers import repository as seller_repository

PURCHASE_STATUSES = ("all", "commande", "recu", "en_vente", "vendu")
DEFAULT_PURCHASE_STATUS = "all"

PURCHASE_STATUS_LABELS: dict[str, str] = {
    "commande": "Commandé",
    "recu": "Reçu",
    "en_vente": "En vente",
    "vendu": "Vendu",
}


def normalize_purchase_status(status: str) -> str:
    return status if status in PURCHASE_STATUSES else DEFAULT_PURCHASE_STATUS


def purchases_page_data(
    connection: sqlite3.Connection, *, status: str = DEFAULT_PURCHASE_STATUS
) -> dict[str, Any]:
    """Achats filtrés par statut, compteurs et coûts en centimes entiers."""
    active_status = normalize_purchase_status(status)
    rows = seller_repository.list_purchases(connection, limit=None)

    counts = {key: 0 for key in PURCHASE_STATUS_LABELS}
    totals_by_currency: dict[str, int] = {}
    ongoing_count = 0
    for row in rows:
        row_status = str(row["status"])
        if row_status in counts:
            counts[row_status] += 1
        currency = str(row["currency"])
        totals_by_currency[currency] = totals_by_currency.get(currency, 0) + int(
            row["price_paid_cents"]
        ) + int(row["shipping_paid_cents"])
        if row_status != "vendu":
            ongoing_count += 1

    filtered = [
        row
        for row in rows
        if active_status == DEFAULT_PURCHASE_STATUS or row["status"] == active_status
    ]
    return {
        "status": active_status,
        "status_options": PURCHASE_STATUSES,
        "status_labels": PURCHASE_STATUS_LABELS,
        "counts": counts,
        "total_count": len(rows),
        "ongoing_count": ongoing_count,
        "totals_by_currency": dict(sorted(totals_by_currency.items())),
        "purchases": filtered,
    }
