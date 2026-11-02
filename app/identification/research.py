"""File SQLite durable et orchestration bornée des recherches TCGdex."""

import hashlib
import json
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.identification.normalization import canonical_local_id, normalize_text
from app.identification.resolution import apply_resolution, resolve_listing, utc_now
from app.tcgdex.cache import TcgdexCache
from app.tcgdex.client import TcgdexError, TcgdexNotFoundError, TcgdexRateLimitError
from app.tcgdex.models import TcgdexCard, TcgdexSet

STRATEGY_VERSION = "targeted-fr-v1"


def normalize_criteria(criteria: dict[str, Any]) -> dict[str, str]:
    allowed = ("tcgdex_id", "name", "local_id", "set_id", "set_name")
    clean = {key: str(criteria.get(key)).strip() for key in allowed if criteria.get(key) and str(criteria.get(key)).strip()}
    if "local_id" in clean:
        clean["local_id"] = canonical_local_id(clean["local_id"])
    if not any(key in clean for key in ("tcgdex_id", "name", "local_id")):
        raise ValueError("Au moins un identifiant, nom ou numéro est requis.")
    return clean


def criteria_hash(criteria: dict[str, str], language: str = "fr") -> str:
    canonical = {key: normalize_text(value) for key, value in criteria.items()}
    payload = json.dumps({"criteria": canonical, "language": language, "strategy": STRATEGY_VERSION}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def enqueue_search(
    connection: sqlite3.Connection,
    item_id: int | None = None,
    criteria: dict[str, Any] | None = None,
    *,
    force: bool = False,
) -> int:
    clean = normalize_criteria(criteria or {})
    evidence_hash = None
    if item_id is not None:
        evidence = resolve_listing(connection, item_id)
        if evidence.result.status == "lot":
            raise ValueError("Aucune recherche unitaire automatique pour un lot actif.")
        evidence_hash = evidence.evidence_hash
    digest = criteria_hash(clean)
    now = datetime.now(UTC)
    row = connection.execute("SELECT * FROM identification_searches WHERE criteria_hash=?", (digest,)).fetchone()
    if row:
        if row["status"] in ("completed", "empty", "failed"):
            last = datetime.fromisoformat(row["updated_at"].replace("Z", "+00:00"))
            if (now - last).total_seconds() < 30 and not force:
                search_id = int(row["id"])
            else:
                connection.execute("UPDATE identification_searches SET status='queued', next_attempt_at=?, attempts=0, error_code=NULL, error_message=NULL, updated_at=? WHERE id=?", (now.isoformat(), utc_now(), row["id"]))
                search_id = int(row["id"])
        else:
            search_id = int(row["id"])
    else:
        cursor = connection.execute(
            """INSERT INTO identification_searches
            (criteria_hash, criteria_json, language, strategy_version, status,
             next_attempt_at, created_at, updated_at) VALUES (?, ?, 'fr', ?, 'queued', ?, ?, ?)""",
            (digest, json.dumps(clean, sort_keys=True), STRATEGY_VERSION, now.isoformat(), utc_now(), utc_now()),
        )
        search_id = int(cursor.lastrowid)
    if item_id is not None and evidence_hash is not None:
        connection.execute(
            "INSERT OR IGNORE INTO identification_search_listings(search_id, listing_id, evidence_hash, created_at) VALUES (?, ?, ?, ?)",
            (search_id, item_id, evidence_hash, utc_now()),
        )
    return search_id


def get_search_by_id(connection: sqlite3.Connection, search_id: int) -> sqlite3.Row | None:
    return connection.execute("SELECT * FROM identification_searches WHERE id=?", (search_id,)).fetchone()


def claim_search(connection: sqlite3.Connection, owner: str | None = None) -> sqlite3.Row | None:
    """Réservation atomique, avec reprise des baux expirés."""
    owner = owner or uuid.uuid4().hex
    now = datetime.now(UTC)
    connection.execute("BEGIN IMMEDIATE")
    try:
        row = connection.execute(
            """SELECT * FROM identification_searches
            WHERE attempts < 3 AND next_attempt_at <= ?
              AND (status='queued' OR (status='running' AND lease_expires_at <= ?))
            ORDER BY next_attempt_at, id LIMIT 1""",
            (now.isoformat(), now.isoformat()),
        ).fetchone()
        if row is None:
            connection.commit(); return None
        lease = (now + timedelta(seconds=60)).isoformat()
        connection.execute(
            "UPDATE identification_searches SET status='running', attempts=attempts+1, lease_owner=?, lease_expires_at=?, updated_at=? WHERE id=?",
            (owner, lease, utc_now(), row["id"]),
        )
        connection.commit()
        return connection.execute("SELECT * FROM identification_searches WHERE id=?", (row["id"],)).fetchone()
    except Exception:
        connection.rollback(); raise


def get_search_for_item(connection: sqlite3.Connection, item_id: int, search_id: int) -> sqlite3.Row | None:
    return connection.execute(
        """SELECT s.* FROM identification_searches s
        JOIN identification_search_listings a ON a.search_id=s.id
        WHERE s.id=? AND a.listing_id=?""", (search_id, item_id)
    ).fetchone()


def latest_search_for_item(connection: sqlite3.Connection, item_id: int) -> sqlite3.Row | None:
    return connection.execute(
        """SELECT s.* FROM identification_searches s JOIN identification_search_listings a ON a.search_id=s.id
        WHERE a.listing_id=? ORDER BY s.id DESC LIMIT 1""", (item_id,)
    ).fetchone()


def process_claimed_search(connection: sqlite3.Connection, search: sqlite3.Row, client: Any) -> None:
    """Le réseau s'exécute hors transaction ; la publication est courte et contrôlée."""
    criteria = json.loads(search["criteria_json"])
    try:
        raw_cards = client.search_cards(**criteria)
        cache = TcgdexCache(connection)
        ids: list[int] = []
        for raw in raw_cards[:50]:
            card_id = _import_summary(cache, raw)
            if card_id:
                ids.append(card_id)
        with connection:
            connection.execute(
                "UPDATE identification_searches SET status=?, result_card_ids_json=?, partial=?, completed_at=?, lease_owner=NULL, lease_expires_at=NULL, error_code=NULL, error_message=NULL, updated_at=? WHERE id=?",
                ("completed" if ids else "empty", json.dumps(ids), int(len(raw_cards) > 50), utc_now(), utc_now(), search["id"]),
            )
            _publish_results(connection, int(search["id"]))
    except TcgdexRateLimitError as error:
        delay = max(1, int(error.retry_after or 60))
        _schedule_retry(connection, int(search["id"]), "rate_limited", str(error), delay)
    except TcgdexNotFoundError as error:
        with connection:
            connection.execute("UPDATE identification_searches SET status='empty', error_code='not_found', error_message=?, lease_owner=NULL, lease_expires_at=NULL, updated_at=? WHERE id=?", (str(error), utc_now(), search["id"]))
    except (TcgdexError, ValueError, TypeError, KeyError) as error:
        _schedule_retry(connection, int(search["id"]), "invalid_response" if isinstance(error, (ValueError, TypeError, KeyError)) else "network_error", str(error), min(60 * int(search["attempts"]), 300))


def _schedule_retry(connection: sqlite3.Connection, search_id: int, code: str, message: str, delay: int) -> None:
    with connection:
        row = connection.execute("SELECT attempts FROM identification_searches WHERE id=?", (search_id,)).fetchone()
        status = "failed" if row and row["attempts"] >= 3 else "queued"
        connection.execute(
            "UPDATE identification_searches SET status=?, next_attempt_at=?, error_code=?, error_message=?, lease_owner=NULL, lease_expires_at=NULL, updated_at=? WHERE id=?",
            (status, (datetime.now(UTC) + timedelta(seconds=delay)).isoformat(), code, message[:500], utc_now(), search_id),
        )


def _import_summary(cache: TcgdexCache, raw: dict[str, Any]) -> int | None:
    card_id, name = raw.get("id"), raw.get("name")
    local_id = raw.get("localId")
    set_data = raw.get("set") or {}
    if not all((card_id, name, local_id is not None, isinstance(set_data, dict), set_data.get("id"))):
        raise ValueError("Résumé de carte TCGdex incomplet")
    set_obj = TcgdexSet(id=set_data["id"], name=set_data.get("name") or set_data["id"])
    cache.upsert_set(set_obj)
    return cache.upsert_card(TcgdexCard(
        id=card_id, name=name, local_id=str(local_id), set_id=set_obj.id, set_name=set_obj.name,
        rarity=raw.get("rarity"), category=raw.get("category"), image_url=raw.get("image"), raw_data=raw,
    ))


def _publish_results(connection: sqlite3.Connection, search_id: int) -> None:
    associations = connection.execute("SELECT listing_id, evidence_hash FROM identification_search_listings WHERE search_id=?", (search_id,)).fetchall()
    for association in associations:
        exists = connection.execute("SELECT 1 FROM catalog_items WHERE id=?", (association["listing_id"],)).fetchone()
        if not exists:
            continue
        resolution = resolve_listing(connection, association["listing_id"])
        if resolution.evidence_hash != association["evidence_hash"] or resolution.decision_source == "human":
            continue
        apply_resolution(connection, association["listing_id"], resolution)
