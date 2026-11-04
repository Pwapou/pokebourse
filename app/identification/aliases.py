"""Alias contrôlés du référentiel et localisations (T05).

Un alias n'est jamais fabriqué automatiquement : il porte une cible
vérifiable localement, une langue/périmètre, une provenance explicite et une
version. Les collisions (un même libellé pointant vers plusieurs cartes) et
les correspondances approximatives sont conservées comme suggestions ;
aucune d'elles n'est promue en équivalence d'impression. La langue d'une
fiche TCGdex ne prouve pas celle de l'exemplaire vendu.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from app.identification.normalization import normalize_text
from app.identification.resolution import utc_now

ALIAS_VERSION = "aliases-v1"
ALIAS_SCOPES = ("card", "set")
ALIAS_PROVENANCES = ("manual", "tcgdex", "cardmarket", "import")
ALIAS_STATUSES = ("active", "suggestion")
MAX_SUGGESTION_SCAN = 5000


@dataclass(frozen=True)
class AliasResolution:
    """Résultat borné d'une recherche d'alias, sans autorité implicite."""

    status: str  # "exact" | "collision" | "suggestion" | "none"
    matches: tuple[dict[str, Any], ...]

    @property
    def approximate(self) -> bool:
        return self.status in {"collision", "suggestion"}


def normalize_alias_value(value: str) -> str:
    """Normalisation partagée à l'écriture et à la lecture des alias."""
    return " ".join(normalize_text(value).split())


def _validate_locale(locale: str | None) -> str | None:
    if locale is None:
        return None
    if not isinstance(locale, str) or not (2 <= len(locale) <= 20) or not locale.isascii():
        raise ValueError("Locale d'alias invalide.")
    return locale.lower()


def register_alias(
    connection: sqlite3.Connection,
    raw_alias: str,
    target_card_id: int,
    *,
    locale: str | None = None,
    scope: str = "card",
    provenance: str = "manual",
    note: str | None = None,
    operator: str = "local",
    version: str = ALIAS_VERSION,
) -> dict[str, Any]:
    """Enregistre ou actualise un alias contrôlé, après vérification locale.

    La cible doit exister dans le référentiel local ; aucun identifiant n'est
    deviné. Une collision avec un alias actif existant dégrade toutes les
    occurrences en suggestions : aucune cible ne gagne d'autorité par
    accumulation. Pour « gempack 2 » ou tout cas non vérifié, ne rien
    enregistrer : la recherche conserve le cas non résolu.
    """
    if not isinstance(raw_alias, str) or not raw_alias.strip() or len(raw_alias) > 200:
        raise ValueError("Alias invalide.")
    if scope not in ALIAS_SCOPES or provenance not in ALIAS_PROVENANCES:
        raise ValueError("Périmètre ou provenance d'alias invalide.")
    if not operator.strip() or len(operator) > 100:
        raise ValueError("Identifiant opérateur local invalide.")
    locale = _validate_locale(locale)
    target = connection.execute(
        "SELECT id FROM pokemon_reference_cards WHERE id=?", (target_card_id,)
    ).fetchone()
    if target is None:
        raise LookupError("Cible d'alias introuvable dans le référentiel local.")
    alias = normalize_alias_value(raw_alias)
    collisions = connection.execute(
        """SELECT id, target_card_id FROM reference_aliases
        WHERE alias=? AND status='active' AND target_card_id<>?""",
        (alias, target_card_id),
    ).fetchall()
    status = "suggestion" if collisions else "active"
    now = utc_now()
    with connection:
        if not connection.in_transaction:
            connection.execute("BEGIN IMMEDIATE")
        for collision in collisions:
            # La collision est conservée comme suggestion, jamais effacée.
            connection.execute(
                "UPDATE reference_aliases SET status='suggestion', updated_at=? WHERE id=?",
                (now, collision["id"]),
            )
        connection.execute(
            """INSERT INTO reference_aliases
            (alias, raw_alias, target_card_id, locale, scope, provenance, status, version, note, created_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(alias, target_card_id, locale, scope) DO UPDATE SET
                raw_alias=excluded.raw_alias,
                provenance=excluded.provenance,
                status=excluded.status,
                version=excluded.version,
                note=excluded.note,
                updated_at=excluded.updated_at""",
            (alias, raw_alias.strip(), target_card_id, locale, scope, provenance,
             status, version, note, operator, now, now),
        )
    row = connection.execute(
        "SELECT * FROM reference_aliases WHERE alias=? AND target_card_id=? AND locale IS ? AND scope=?",
        (alias, target_card_id, locale, scope),
    ).fetchone()
    return dict(row)


def _match_rows(connection: sqlite3.Connection, alias: str, *, locale: str | None) -> list[sqlite3.Row]:
    return connection.execute(
        """SELECT a.*, c.tcgdex_id, c.name, c.set_name, c.reference_language FROM reference_aliases a
        JOIN pokemon_reference_cards c ON c.id=a.target_card_id
        WHERE a.alias=? AND (a.locale IS NULL OR a.locale=?)
        ORDER BY a.status='active' DESC, a.id""",
        (alias, locale or ""),
    ).fetchall()


def resolve_alias(connection: sqlite3.Connection, value: str, *, locale: str | None = None) -> AliasResolution:
    """Résout un libellé : exact si une seule cible active, sinon suggestions."""
    if not isinstance(value, str) or not value.strip():
        return AliasResolution("none", ())
    locale = _validate_locale(locale)
    rows = _match_rows(connection, normalize_alias_value(value), locale=locale)
    if not rows:
        return AliasResolution("none", ())
    active = [row for row in rows if row["status"] == "active"]
    targets = {row["target_card_id"] for row in active}
    if len(active) == 1 and len(targets) == 1:
        status = "exact"
        selected: list[sqlite3.Row] = active
    else:
        # Collision ou seules des suggestions : aucune équivalence imposée.
        status = "collision" if active else "suggestion"
        selected = rows
    matches = tuple({
        "alias_id": row["id"], "alias": row["alias"], "target_card_id": row["target_card_id"],
        "tcgdex_id": row["tcgdex_id"], "name": row["name"], "set_name": row["set_name"],
        "locale": row["locale"], "scope": row["scope"], "provenance": row["provenance"],
        "status": row["status"], "version": row["version"],
    } for row in selected)
    return AliasResolution(status, matches)


def _edit_distance(left: str, right: str, *, maximum: int = 2) -> int:
    """Distance de Levenshtein bornée ; au-delà du plafond, la valeur importe peu."""
    if abs(len(left) - len(right)) > maximum:
        return maximum + 1
    previous = list(range(len(right) + 1))
    for i, a in enumerate(left, start=1):
        current = [i]
        best = current[0]
        for j, b in enumerate(right, start=1):
            cost = 0 if a == b else 1
            value = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost)
            current.append(value)
            best = min(best, value)
        if best > maximum:
            return maximum + 1
        previous = current
    return previous[-1]


def suggest_aliases(connection: sqlite3.Connection, value: str, *, locale: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
    """Correspondances approximatives conservées comme suggestions, sans écriture.

    Une correspondance floue n'est jamais une preuve exacte : chaque élément
    retourné porte le statut « suggestion » et sa provenance.
    """
    if not isinstance(value, str) or not value.strip():
        return []
    locale = _validate_locale(locale)
    alias = normalize_alias_value(value)
    rows = _match_rows(connection, alias, locale=locale)
    suggestions: list[dict[str, Any]] = []
    seen: set[int] = set()
    for row in rows:
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        suggestions.append({
            "alias_id": row["id"], "alias": row["alias"], "target_card_id": row["target_card_id"],
            "tcgdex_id": row["tcgdex_id"], "name": row["name"], "set_name": row["set_name"],
            "locale": row["locale"], "scope": row["scope"], "provenance": row["provenance"],
            "status": "suggestion", "version": row["version"], "distance": 0,
        })
    if len(suggestions) < limit:
        candidates = connection.execute(
            """SELECT DISTINCT a.alias FROM reference_aliases a
            WHERE a.alias<>? AND (a.locale IS NULL OR a.locale=?)
            ORDER BY a.alias LIMIT ?""",
            (alias, locale or "", MAX_SUGGESTION_SCAN),
        ).fetchall()
        for row in candidates:
            distance = _edit_distance(alias, row["alias"])
            if distance <= 2 and row["alias"] not in {item["alias"] for item in suggestions}:
                match = _match_rows(connection, row["alias"], locale=locale)
                for target in match[:1]:
                    suggestions.append({
                        "alias_id": target["id"], "alias": target["alias"], "target_card_id": target["target_card_id"],
                        "tcgdex_id": target["tcgdex_id"], "name": target["name"], "set_name": target["set_name"],
                        "locale": target["locale"], "scope": target["scope"], "provenance": target["provenance"],
                        "status": "suggestion", "version": target["version"], "distance": distance,
                    })
            if len(suggestions) >= limit:
                break
    return suggestions[:limit]


def set_alias_status(
    connection: sqlite3.Connection, alias_id: int, status: str, *, operator: str = "local",
) -> None:
    """Réactive ou classe une suggestion après une vérification humaine."""
    if status not in ALIAS_STATUSES:
        raise ValueError("Statut d'alias invalide.")
    if not operator.strip() or len(operator) > 100:
        raise ValueError("Identifiant opérateur local invalide.")
    row = connection.execute("SELECT id FROM reference_aliases WHERE id=?", (alias_id,)).fetchone()
    if row is None:
        raise LookupError("Alias introuvable.")
    connection.execute(
        "UPDATE reference_aliases SET status=?, updated_at=? WHERE id=?",
        (status, utc_now(), alias_id),
    )
