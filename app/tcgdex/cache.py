import json
import logging
import sqlite3
import unicodedata
from typing import Any

from app.tcgdex.client import TcgdexClient
from app.tcgdex.data.seed_data import INITIAL_CARDS, INITIAL_SETS
from app.tcgdex.models import ReferenceCardRecord, TcgdexCard, TcgdexSet

logger = logging.getLogger(__name__)


def _normalize_token(value: str | None) -> str:
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFKD", value)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(stripped.casefold().split())


class TcgdexCache:
    """Gestionnaire de cache local SQLite pour le catalogue de référence Pokémon TCGdex."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def is_empty(self) -> bool:
        row = self.connection.execute("SELECT COUNT(*) FROM pokemon_reference_cards").fetchone()
        return (row[0] if row else 0) == 0

    def seed_initial_if_empty(self) -> int:
        """Remplit le cache avec les données de base si la base est vide."""
        if not self.is_empty():
            return 0

        inserted = 0
        with self.connection:
            for s in INITIAL_SETS:
                self.connection.execute(
                    """
                    INSERT INTO pokemon_reference_sets (
                        id, name, series, card_count_total, card_count_official,
                        release_date, logo_url, symbol_url
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name = excluded.name,
                        series = excluded.series,
                        card_count_total = excluded.card_count_total,
                        card_count_official = excluded.card_count_official,
                        release_date = excluded.release_date,
                        logo_url = excluded.logo_url,
                        symbol_url = excluded.symbol_url
                    """,
                    (
                        s["id"],
                        s["name"],
                        s.get("series"),
                        s.get("card_count_total"),
                        s.get("card_count_official"),
                        s.get("release_date"),
                        s.get("logo_url"),
                        s.get("symbol_url"),
                    ),
                )

            for c in INITIAL_CARDS:
                self.connection.execute(
                    """
                    INSERT INTO pokemon_reference_cards (
                        tcgdex_id, local_id, name, set_id, set_name,
                        rarity, category, types, hp, stage, illustrator,
                        image_url, raw_data
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(tcgdex_id) DO UPDATE SET
                        local_id = excluded.local_id,
                        name = excluded.name,
                        set_id = excluded.set_id,
                        set_name = excluded.set_name,
                        rarity = excluded.rarity,
                        category = excluded.category,
                        types = excluded.types,
                        hp = excluded.hp,
                        stage = excluded.stage,
                        illustrator = excluded.illustrator,
                        image_url = excluded.image_url,
                        raw_data = excluded.raw_data
                    """,
                    (
                        c["tcgdex_id"],
                        c["local_id"],
                        c["name"],
                        c["set_id"],
                        c["set_name"],
                        c.get("rarity"),
                        c.get("category"),
                        json.dumps(c.get("types", []), ensure_ascii=False),
                        c.get("hp"),
                        c.get("stage"),
                        c.get("illustrator"),
                        c.get("image_url"),
                        json.dumps(c, ensure_ascii=False),
                    ),
                )
                inserted += 1

        logger.info("Cache TCGdex initialisé avec %d cartes de référence hors-ligne.", inserted)
        return inserted

    def upsert_set(self, set_obj: TcgdexSet) -> None:
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO pokemon_reference_sets (
                    id, name, series, card_count_total, card_count_official,
                    release_date, logo_url, symbol_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    series = excluded.series,
                    card_count_total = excluded.card_count_total,
                    card_count_official = excluded.card_count_official,
                    release_date = excluded.release_date,
                    logo_url = excluded.logo_url,
                    symbol_url = excluded.symbol_url,
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                """,
                (
                    set_obj.id,
                    set_obj.name,
                    set_obj.series,
                    set_obj.card_count_total,
                    set_obj.card_count_official,
                    set_obj.release_date,
                    set_obj.logo_url,
                    set_obj.symbol_url,
                ),
            )

    def upsert_card(self, card_obj: TcgdexCard) -> int:
        with self.connection:
            cursor = self.connection.execute(
                """
                INSERT INTO pokemon_reference_cards (
                    tcgdex_id, local_id, name, set_id, set_name,
                    rarity, category, types, hp, stage, illustrator,
                    image_url, raw_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tcgdex_id) DO UPDATE SET
                    local_id = excluded.local_id,
                    name = excluded.name,
                    set_id = excluded.set_id,
                    set_name = excluded.set_name,
                    rarity = excluded.rarity,
                    category = excluded.category,
                    types = excluded.types,
                    hp = excluded.hp,
                    stage = excluded.stage,
                    illustrator = excluded.illustrator,
                    image_url = excluded.image_url,
                    raw_data = excluded.raw_data,
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                RETURNING id
                """,
                (
                    card_obj.id,
                    card_obj.local_id,
                    card_obj.name,
                    card_obj.set_id,
                    card_obj.set_name,
                    card_obj.rarity,
                    card_obj.category,
                    json.dumps(card_obj.types, ensure_ascii=False),
                    card_obj.hp,
                    card_obj.stage,
                    card_obj.illustrator,
                    card_obj.image_url,
                    json.dumps(card_obj.raw_data, ensure_ascii=False),
                ),
            )
            row = cursor.fetchone()
            return int(row[0]) if row else 0

    def get_card_by_id(self, card_id: int) -> ReferenceCardRecord | None:
        row = self.connection.execute(
            """
            SELECT id, tcgdex_id, local_id, name, set_id, set_name,
                   rarity, category, types, hp, stage, illustrator,
                   image_url, raw_data, updated_at
            FROM pokemon_reference_cards
            WHERE id = ?
            """,
            (card_id,),
        ).fetchone()
        if not row:
            return None
        return self._row_to_record(row)

    def get_card_by_tcgdex_id(self, tcgdex_id: str) -> ReferenceCardRecord | None:
        row = self.connection.execute(
            """
            SELECT id, tcgdex_id, local_id, name, set_id, set_name,
                   rarity, category, types, hp, stage, illustrator,
                   image_url, raw_data, updated_at
            FROM pokemon_reference_cards
            WHERE tcgdex_id = ?
            """,
            (tcgdex_id,),
        ).fetchone()
        if not row:
            return None
        return self._row_to_record(row)

    def find_cards(
        self,
        *,
        name: str | None = None,
        local_id: str | None = None,
        set_query: str | None = None,
        limit: int = 50,
    ) -> list[ReferenceCardRecord]:
        """Recherche dans le cache local avec nom, numéro local ou extension."""
        clauses: list[str] = []
        params: list[Any] = []

        if name:
            norm_name = _normalize_token(name)
            clauses.append("LOWER(name) LIKE ?")
            params.append(f"%{norm_name}%")

        if local_id:
            # Nettoyer zéros initiaux ou chercher variante exacte
            cleaned_id = local_id.lstrip("0") or "0"
            clauses.append("(local_id = ? OR local_id = ? OR local_id LIKE ?)")
            params.extend([local_id, cleaned_id, f"%{cleaned_id}"])

        if set_query:
            norm_set = _normalize_token(set_query)
            clauses.append("(set_id = ? OR LOWER(set_name) LIKE ?)")
            params.extend([set_query.lower(), f"%{norm_set}%"])

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"""
            SELECT id, tcgdex_id, local_id, name, set_id, set_name,
                   rarity, category, types, hp, stage, illustrator,
                   image_url, raw_data, updated_at
            FROM pokemon_reference_cards
            {where}
            ORDER BY id ASC
            LIMIT ?
        """
        params.append(limit)
        rows = self.connection.execute(query, params).fetchall()
        return [self._row_to_record(row) for row in rows]

    def list_sets(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT id, name, series, card_count_total, card_count_official,
                   release_date, logo_url, symbol_url, updated_at
            FROM pokemon_reference_sets
            ORDER BY release_date DESC, name ASC
            """
        ).fetchall()
        return [dict(r) for r in rows]

    def sync_set(self, client: TcgdexClient, set_id: str) -> int:
        """Télécharge et met en cache une extension complète depuis TCGdex."""
        raw_set = client.get_set(set_id)
        if not raw_set or not raw_set.get("id"):
            return 0

        set_obj = TcgdexSet(
            id=raw_set["id"],
            name=raw_set.get("name", raw_set["id"]),
            series=raw_set.get("serie", {}).get("name") if isinstance(raw_set.get("serie"), dict) else None,
            card_count_total=raw_set.get("cardCount", {}).get("total") if isinstance(raw_set.get("cardCount"), dict) else None,
            card_count_official=raw_set.get("cardCount", {}).get("official") if isinstance(raw_set.get("cardCount"), dict) else None,
            release_date=raw_set.get("releaseDate"),
            logo_url=raw_set.get("logo"),
            symbol_url=raw_set.get("symbol"),
        )
        self.upsert_set(set_obj)

        count = 0
        raw_cards = raw_set.get("cards") or []
        for c in raw_cards:
            card_id = c.get("id")
            local_id = str(c.get("localId", ""))
            name = c.get("name", "")
            if not card_id or not local_id or not name:
                continue

            card_obj = TcgdexCard(
                id=card_id,
                local_id=local_id,
                name=name,
                set_id=set_obj.id,
                set_name=set_obj.name,
                image_url=c.get("image"),
                raw_data=c,
            )
            self.upsert_card(card_obj)
            count += 1
        return count

    def _row_to_record(self, row: sqlite3.Row) -> ReferenceCardRecord:
        raw_data = {}
        if row["raw_data"]:
            try:
                raw_data = json.loads(row["raw_data"])
            except Exception:
                pass
        return ReferenceCardRecord(
            id=row["id"],
            tcgdex_id=row["tcgdex_id"],
            local_id=row["local_id"],
            name=row["name"],
            set_id=row["set_id"],
            set_name=row["set_name"],
            rarity=row["rarity"],
            category=row["category"],
            types=row["types"],
            hp=row["hp"],
            stage=row["stage"],
            illustrator=row["illustrator"],
            image_url=row["image_url"],
            raw_data=raw_data,
            updated_at=row["updated_at"],
        )
