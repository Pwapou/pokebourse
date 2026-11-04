"""Enrichissement français progressif : réseau hors transaction et reprise durable."""

import json
import math
import re
import sqlite3
import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from app.identification.detector import extract_features
from app.identification.normalization import canonical_local_id, normalize_text
from app.tcgdex.cache import TcgdexCache
from app.tcgdex.client import TCGDEX_LOCALE_BASE_URL, TcgdexClient, TcgdexError, TcgdexNotFoundError, TcgdexRateLimitError
from app.tcgdex.models import TcgdexCard, TcgdexSet

STATUS_LABELS = {
    "queued": "En attente", "running": "En cours", "paused": "En pause",
    "completed": "Terminé", "failed": "À reprendre",
}
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}\Z")


def _iso(now: datetime) -> str:
    """Conserve un format UTC unique pour les échéances comparées en SQLite."""
    return now.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _identifier(value: Any, *, maximum: int = 100) -> str:
    """Accepte un identifiant TCGdex et non un chemin ou une URL arbitraire."""
    if not isinstance(value, str) or len(value) > maximum or not _IDENTIFIER.fullmatch(value):
        raise ValueError("Identifiant TCGdex invalide.")
    return value


def validate_set_selection(set_ids: list[str]) -> list[str]:
    """Valide toute une sélection avant d'écrire sa première demande."""
    selected = list(dict.fromkeys(set_ids))
    if not selected or len(selected) > 20:
        raise ValueError("Choisissez entre 1 et 20 extensions à charger.")
    return [_identifier(value, maximum=50) for value in selected]


def _locale(value: Any) -> str:
    """Valide une locale de fiche TCGdex (ex. fr, en, ja)."""
    if not isinstance(value, str) or len(value) > 20:
        raise ValueError("Locale de synchronisation invalide.")
    if not re.fullmatch(r"[a-z]{2}(-[a-z0-9]{2,4})?", value):
        raise ValueError("Locale de synchronisation invalide.")
    return value


def enqueue_sync(
    connection: sqlite3.Connection, set_id: str | None = None, *,
    include_details: bool = True, now: datetime | None = None, locale: str = "fr",
) -> int:
    """Déduplique une demande et réutilise pendant 24 h les étapes terminées.

    La locale « fr » conserve la clé historique ; les autres locales reçoivent
    leur propre tâche, sans écraser les localisations déjà chargées (T05).
    Une locale ajoutée n'active pas automatiquement son identification.
    """
    now = now or datetime.now(UTC)
    set_id = _identifier(set_id, maximum=50) if set_id is not None else None
    locale = _locale(locale)
    key = f"set:{set_id}" if set_id else "directory"
    if set_id and locale != "fr":
        key = f"set:{set_id}:{locale}"
    with connection:
        if not connection.in_transaction:
            connection.execute("BEGIN IMMEDIATE")
        job = connection.execute("SELECT * FROM tcgdex_sync_jobs WHERE resource_key=?", (key,)).fetchone()
        if job is None:
            cursor = connection.execute(
                """INSERT INTO tcgdex_sync_jobs(resource_key, kind, set_id, status, stage,
                include_details, next_attempt_at, created_at, updated_at, locale)
                VALUES (?, ?, ?, 'queued', 'manifest', ?, ?, ?, ?, ?)""",
                (key, "set" if set_id else "directory", set_id, int(bool(set_id and include_details)), _iso(now), _iso(now), _iso(now), locale),
            )
            return int(cursor.lastrowid)
        fresh = bool(job["last_success_at"] and now - datetime.fromisoformat(job["last_success_at"].replace("Z", "+00:00")) < timedelta(hours=24))
        upgrade = bool(set_id and include_details and not job["include_details"])
        if job["status"] == "completed" and fresh and not upgrade:
            return int(job["id"])
        if job["status"] in ("queued", "running"):
            if upgrade:
                connection.execute("UPDATE tcgdex_sync_jobs SET include_details=1 WHERE id=?", (job["id"],))
            return int(job["id"])
        if job["status"] == "completed" and not fresh:
            connection.execute("DELETE FROM tcgdex_sync_cards WHERE job_id=?", (job["id"],))
            connection.execute(
                """UPDATE tcgdex_sync_jobs SET stage='manifest', manifest_json=NULL, expected_count=NULL,
                summary_count=0, include_details=? WHERE id=?""", (int(bool(set_id and include_details)), job["id"]),
            )
        elif upgrade:
            connection.execute(
                "UPDATE tcgdex_sync_jobs SET include_details=1, stage=CASE WHEN manifest_json IS NOT NULL THEN 'details' ELSE 'manifest' END WHERE id=?",
                (job["id"],),
            )
        connection.execute(
            """UPDATE tcgdex_sync_jobs SET status='queued', attempts=0, error_code=NULL,
            error_message=NULL, next_attempt_at=?, lease_owner=NULL, lease_expires_at=NULL, updated_at=? WHERE id=?""",
            (_iso(now), _iso(now), job["id"]),
        )
        return int(job["id"])


def control_job(connection: sqlite3.Connection, job_id: int, action: Literal["pause", "resume"], *, now: datetime | None = None) -> None:
    """Met en pause ou reprend une tâche sans effacer les fiches déjà récupérées."""
    if action not in ("pause", "resume"):
        raise ValueError("Action de synchronisation inconnue.")
    now = now or datetime.now(UTC)
    with connection:
        if not connection.in_transaction:
            connection.execute("BEGIN IMMEDIATE")
        job = connection.execute("SELECT * FROM tcgdex_sync_jobs WHERE id=?", (job_id,)).fetchone()
        if job is None:
            raise LookupError("Synchronisation introuvable.")
        if job["status"] == "completed":
            return
        if action == "resume" and job["status"] not in ("paused", "failed"):
            return
        connection.execute(
            "UPDATE tcgdex_sync_control SET lease_owner=NULL, lease_expires_at=NULL WHERE lease_owner=?", (job["lease_owner"],),
        )
        connection.execute(
            """UPDATE tcgdex_sync_jobs SET status=?, attempts=0, next_attempt_at=?,
            lease_owner=NULL, lease_expires_at=NULL, error_code=NULL, error_message=NULL, updated_at=? WHERE id=?""",
            ("paused" if action == "pause" else "queued", _iso(now), _iso(now), job_id),
        )


def claim_sync(connection: sqlite3.Connection, *, now: datetime | None = None, interval_seconds: int = 1) -> dict[str, Any] | None:
    """Réserve une seule requête pour toute la file, avec bail et cadence partagés."""
    if connection.in_transaction:
        raise ValueError("Terminez la transaction avant de réserver une requête distante.")
    if not 1 <= interval_seconds <= 60:
        raise ValueError("L'intervalle TCGdex doit être compris entre 1 et 60 secondes.")
    now = now or datetime.now(UTC)
    with connection:
        connection.execute("BEGIN IMMEDIATE")
        gate = connection.execute("SELECT * FROM tcgdex_sync_control WHERE id=1").fetchone()
        if gate["next_request_at"] > _iso(now) or (gate["lease_owner"] and gate["lease_expires_at"] > _iso(now)):
            return None
        job = connection.execute(
            """SELECT * FROM tcgdex_sync_jobs WHERE next_attempt_at<=?
            AND (status='queued' OR (status='running' AND lease_expires_at<=?))
            ORDER BY CASE WHEN kind='directory' THEN 0 WHEN stage='manifest' THEN 1 ELSE 2 END,
            updated_at, id LIMIT 1""", (_iso(now), _iso(now)),
        ).fetchone()
        if job is None:
            return None
        if job["attempts"] >= 3:
            connection.execute("UPDATE tcgdex_sync_jobs SET status='failed', error_code='interrupted', error_message='Trois tentatives interrompues : reprise manuelle requise.', lease_owner=NULL, lease_expires_at=NULL WHERE id=?", (job["id"],))
            return None
        task = dict(job)
        task["operation"] = "directory" if job["kind"] == "directory" else job["stage"]
        if task["operation"] == "details":
            card = connection.execute(
                "SELECT * FROM tcgdex_sync_cards WHERE job_id=? AND status='pending' ORDER BY position LIMIT 1", (job["id"],),
            ).fetchone()
            if card is None:
                connection.execute("UPDATE tcgdex_sync_jobs SET status='completed', stage='done', last_success_at=?, updated_at=? WHERE id=?", (_iso(now), _iso(now), job["id"]))
                return None
            task["card_id"] = card["tcgdex_id"]
            task["summary"] = json.loads(card["summary_json"])
        token = uuid.uuid4().hex
        expiry = _iso(now + timedelta(seconds=60))
        connection.execute(
            "UPDATE tcgdex_sync_control SET lease_owner=?, lease_expires_at=?, next_request_at=? WHERE id=1",
            (token, expiry, _iso(now + timedelta(seconds=interval_seconds))),
        )
        connection.execute(
            "UPDATE tcgdex_sync_jobs SET status='running', attempts=attempts+1, lease_owner=?, lease_expires_at=?, updated_at=? WHERE id=?",
            (token, expiry, _iso(now), job["id"]),
        )
        task["lease_owner"] = token
        return task


def _set_model(raw: Any) -> TcgdexSet:
    """Valide les attributs d'extension sans fabriquer de nombres manquants."""
    if not isinstance(raw, dict):
        raise ValueError("Extension TCGdex invalide.")
    counts = raw.get("cardCount") or {}
    serie = raw.get("serie") or {}
    return TcgdexSet(
        id=_identifier(raw.get("id"), maximum=50), name=raw.get("name"),
        series=serie.get("name") if isinstance(serie, dict) else None,
        card_count_total=counts.get("total") if isinstance(counts, dict) else None,
        card_count_official=counts.get("official") if isinstance(counts, dict) else None,
        release_date=raw.get("releaseDate"), logo_url=raw.get("logo"), symbol_url=raw.get("symbol"),
    )


def _card_model(raw: Any, extension: TcgdexSet, *, locale: str = "fr") -> TcgdexCard:
    """Valide l'identité avant toute publication ; aucun identifiant n'est deviné."""
    if not isinstance(raw, dict) or type(raw.get("localId")) not in (str, int):
        raise ValueError("Fiche TCGdex invalide ou numéro manquant.")
    card_id = _identifier(raw.get("id"))
    if not card_id.startswith(f"{extension.id}-"):
        raise ValueError("Carte rattachée à une autre extension.")
    return TcgdexCard(
        id=card_id, local_id=str(raw["localId"]), name=raw.get("name"),
        set_id=extension.id, set_name=extension.name, reference_language=locale,
        rarity=raw.get("rarity"), category=raw.get("category"),
        types=raw.get("types") or [], hp=raw.get("hp"), stage=raw.get("stage"), illustrator=raw.get("illustrator"),
        image_url=raw.get("image"), raw_data=raw,
    )


def _owned(connection: sqlite3.Connection, task: dict[str, Any]) -> sqlite3.Row | None:
    """Un ancien worker ne peut pas écrire après pause ou récupération de son bail."""
    return connection.execute(
        """SELECT j.* FROM tcgdex_sync_jobs j JOIN tcgdex_sync_control c ON c.id=1
        WHERE j.id=? AND j.status='running' AND j.lease_owner=? AND c.lease_owner=?""",
        (task["id"], task["lease_owner"], task["lease_owner"]),
    ).fetchone()


def _release(connection: sqlite3.Connection, token: str) -> None:
    """Libère seulement le bail appartenant à cette requête."""
    connection.execute("UPDATE tcgdex_sync_control SET lease_owner=NULL, lease_expires_at=NULL WHERE lease_owner=?", (token,))


def _store_card(cache: TcgdexCache, card: TcgdexCard) -> None:
    """Préserve les attributs et le JSON détaillé déjà connus d'une même localisation."""
    existing = cache.get_card_by_tcgdex_id(card.id, locale=card.reference_language)
    if existing:
        merged = dict(existing.raw_data)
        merged.update({key: value for key, value in card.raw_data.items() if value is not None})
        card = card.model_copy(update={"raw_data": merged})
    cache.upsert_card(card)


def process_sync_step(
    connection: sqlite3.Connection, client: Any | None = None, *,
    now: datetime | None = None, interval_seconds: int = 1,
) -> bool:
    """Effectue au plus un appel, puis publie une étape atomique et reprenable."""
    now = now or datetime.now(UTC)
    task = claim_sync(connection, now=now, interval_seconds=interval_seconds)
    if task is None:
        return False
    locale = task.get("locale") or "fr"
    client = client or TcgdexClient(base_url=TCGDEX_LOCALE_BASE_URL.format(locale=locale), max_retries=1)
    try:
        # Aucun verrou SQLite n'est conservé pendant les appels HTTP.
        operation = task["operation"]
        if operation == "directory":
            raw = client.get_sets()
            if not isinstance(raw, list) or not raw or len(raw) > 5000:
                raise ValueError("Liste d'extensions TCGdex invalide ou vide.")
            extensions = [_set_model(item) for item in raw]
            if len({item.id for item in extensions}) != len(extensions):
                raise ValueError("Extensions dupliquées dans la réponse TCGdex.")
        elif operation == "manifest":
            raw = client.get_set(task["set_id"])
            extension = _set_model(raw)
            if extension.id != task["set_id"] or not isinstance(raw.get("cards"), list) or len(raw["cards"]) > 5000:
                raise ValueError("Manifeste d'extension TCGdex invalide.")
            cards = [_card_model(item, extension, locale=locale) for item in raw["cards"]]
            if len({item.id for item in cards}) != len(cards):
                raise ValueError("Cartes dupliquées dans le manifeste TCGdex.")
        else:
            raw = client.get_card(task["card_id"])
            if not isinstance(raw, dict) or not isinstance(raw.get("set"), dict):
                raise ValueError("Détails d'extension manquants dans la fiche carte.")
            extension = _set_model(raw["set"])
            card = _card_model(raw, extension, locale=locale)
            if card.id != task["card_id"] or extension.id != task["set_id"] or canonical_local_id(card.local_id) != canonical_local_id(str(task["summary"]["localId"])):
                raise ValueError("La fiche détaillée contredit l'identité du manifeste.")
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            current = _owned(connection, task)
            if current is None:
                return True
            cache = TcgdexCache(connection)
            if operation == "directory":
                for extension in extensions:
                    cache.upsert_set(extension)
                connection.execute("UPDATE tcgdex_sync_jobs SET status='completed', stage='done', summary_count=?, manifest_json=?, last_success_at=? WHERE id=?", (len(extensions), json.dumps(raw, ensure_ascii=False), _iso(now), task["id"]))
            elif operation == "manifest":
                cache.upsert_set(extension)
                for position, card in enumerate(cards):
                    _store_card(cache, card)
                    connection.execute("INSERT INTO tcgdex_sync_cards(job_id, tcgdex_id, position, summary_json) VALUES (?, ?, ?, ?)", (task["id"], card.id, position, json.dumps(card.raw_data, ensure_ascii=False)))
                details = bool(current["include_details"] and cards)
                connection.execute(
                    """UPDATE tcgdex_sync_jobs SET status=?, stage=?, manifest_json=?, expected_count=?,
                    summary_count=?, last_success_at=CASE WHEN ?=0 THEN ? ELSE last_success_at END WHERE id=?""",
                    ("queued" if details else "completed", "details" if details else "done", json.dumps(raw, ensure_ascii=False),
                     extension.card_count_total, len(cards), int(details), _iso(now), task["id"]),
                )
            else:
                cache.upsert_set(extension)
                _store_card(cache, card)
                connection.execute("UPDATE tcgdex_sync_cards SET status='completed', completed_at=? WHERE job_id=? AND tcgdex_id=?", (_iso(now), task["id"], card.id))
                remaining = connection.execute("SELECT 1 FROM tcgdex_sync_cards WHERE job_id=? AND status='pending' LIMIT 1", (task["id"],)).fetchone()
                connection.execute("UPDATE tcgdex_sync_jobs SET status=?, stage=?, last_success_at=CASE WHEN ?=0 THEN ? ELSE last_success_at END WHERE id=?", ("queued" if remaining else "completed", "details" if remaining else "done", int(bool(remaining)), _iso(now), task["id"]))
            connection.execute("UPDATE tcgdex_sync_jobs SET attempts=0, lease_owner=NULL, lease_expires_at=NULL, error_code=NULL, error_message=NULL, updated_at=?, next_attempt_at=? WHERE id=?", (_iso(now), _iso(now), task["id"]))
            _release(connection, task["lease_owner"])
    except (TcgdexError, ValueError, TypeError, KeyError) as error:
        _record_failure(connection, task, error, now)
    return True


def _record_failure(connection: sqlite3.Connection, task: dict[str, Any], error: BaseException, now: datetime) -> None:
    """Replanifie sans attente bloquante et respecte le délai serveur sur toute la file."""
    with connection:
        connection.execute("BEGIN IMMEDIATE")
        current = _owned(connection, task)
        if current is None:
            return
        delay = min(60, 5 * 2 ** max(0, current["attempts"] - 1))
        code = "invalid_response" if isinstance(error, (ValueError, TypeError, KeyError)) else "network_error"
        if isinstance(error, TcgdexRateLimitError):
            server_delay = error.retry_after
            delay = max(1, math.ceil(server_delay)) if server_delay is not None and math.isfinite(server_delay) else 60
            code = "rate_limited"
        elif isinstance(error, TcgdexNotFoundError):
            code = "not_found"
        try:
            retry_at = now + timedelta(seconds=delay)
        except OverflowError:
            retry_at = datetime.max.replace(tzinfo=UTC)
        if code == "rate_limited":
            connection.execute("UPDATE tcgdex_sync_control SET next_request_at=? WHERE id=1", (_iso(retry_at),))
        status = "failed" if current["attempts"] >= 3 or code == "not_found" else "queued"
        connection.execute(
            """UPDATE tcgdex_sync_jobs SET status=?, next_attempt_at=?, error_code=?, error_message=?,
            lease_owner=NULL, lease_expires_at=NULL, updated_at=? WHERE id=?""",
            (status, _iso(retry_at), code, str(error)[:500], _iso(now), task["id"]),
        )
        _release(connection, task["lease_owner"])


def sync_dashboard(connection: sqlite3.Connection, *, query: str = "", page: int = 1) -> dict[str, Any]:
    """Affiche l'inventaire, les trous apparents et les tâches sans requête distante."""
    extensions = [dict(row) for row in connection.execute(
        """SELECT s.*, count(c.id) AS cached_cards,
        sum(CASE WHEN c.rarity IS NOT NULL THEN 1 ELSE 0 END) AS with_rarity
        FROM pokemon_reference_sets s LEFT JOIN pokemon_reference_cards c ON c.set_id=s.id GROUP BY s.id"""
    )]
    mentions: Counter[str] = Counter()
    for row in connection.execute(
        """SELECT c.original_title, s.description FROM catalog_items c
        LEFT JOIN listing_identification_snapshots s ON s.id=c.identification_snapshot_id
        WHERE c.identification_status IN ('unidentified','ambiguous') AND c.original_title IS NOT NULL
        ORDER BY c.id DESC LIMIT 1000"""
    ):
        features = extract_features(row["original_title"], row["description"], catalog_sets=[item["name"] for item in extensions])
        if features.set_name:
            mentions[normalize_text(features.set_name)] += 1
    for extension in extensions:
        extension["mentions"] = mentions[normalize_text(extension["name"])]
        extension["partial"] = extension["card_count_total"] is not None and extension["cached_cards"] < extension["card_count_total"]
    selected = [item for item in extensions if not query or normalize_text(query) in normalize_text(f"{item['id']} {item['name']}")]
    selected.sort(key=lambda item: (-item["mentions"], not item["partial"], item["name"], item["id"]))
    pages = max(1, (len(selected) + 24) // 25)
    page = max(1, min(page, pages))
    jobs = [dict(row) for row in connection.execute(
        """SELECT j.*, s.name AS set_name, (SELECT count(*) FROM tcgdex_sync_cards c
        WHERE c.job_id=j.id AND c.status='completed') AS detail_count FROM tcgdex_sync_jobs j
        LEFT JOIN pokemon_reference_sets s ON s.id=j.set_id ORDER BY j.updated_at DESC, j.id DESC LIMIT 50"""
    )]
    for job in jobs:
        job["manifest_loaded"] = job.pop("manifest_json") is not None
    return {"extensions": selected[(page - 1) * 25:page * 25], "jobs": jobs,
            "query": query, "current_page": page, "total_pages": pages, "filtered_count": len(selected),
            "card_count": sum(item["cached_cards"] for item in extensions), "set_count": len(extensions),
            "partial_count": sum(item["partial"] for item in extensions),
            "with_rarity": sum(item["with_rarity"] for item in extensions), "status_labels": STATUS_LABELS}
