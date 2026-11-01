import json
import logging
from contextlib import nullcontext
import sqlite3
import unicodedata
from typing import Any

from app.identification.normalization import canonical_local_id, normalize_text
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
        with self.connection if not self.connection.in_transaction else nullcontext():
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
                        image_url, raw_data, normalized_name, normalized_set_name,
                        canonical_local_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        normalized_name = excluded.normalized_name,
                        normalized_set_name = excluded.normalized_set_name,
                        canonical_local_id = excluded.canonical_local_id
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
                        normalize_text(c["name"]),
                        normalize_text(c["set_name"]),
                        canonical_local_id(c["local_id"]),
                    ),
                )
                inserted += 1

        logger.info("Cache TCGdex initialisé avec %d cartes de référence hors-ligne.", inserted)
        return inserted

    def upsert_set(self, set_obj: TcgdexSet) -> None:
        with self.connection if not self.connection.in_transaction else nullcontext():
            self.connection.execute(
                """
                INSERT INTO pokemon_reference_sets (
                    id, name, series, card_count_total, card_count_official,
                    release_date, logo_url, symbol_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = CASE WHEN excluded.name=excluded.id AND pokemon_reference_sets.name<>pokemon_reference_sets.id
                                THEN pokemon_reference_sets.name ELSE excluded.name END,
                    series = COALESCE(excluded.series, pokemon_reference_sets.series),
                    card_count_total = COALESCE(excluded.card_count_total, pokemon_reference_sets.card_count_total),
                    card_count_official = COALESCE(excluded.card_count_official, pokemon_reference_sets.card_count_official),
                    release_date = COALESCE(excluded.release_date, pokemon_reference_sets.release_date),
                    logo_url = COALESCE(excluded.logo_url, pokemon_reference_sets.logo_url),
                    symbol_url = COALESCE(excluded.symbol_url, pokemon_reference_sets.symbol_url),
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
        """Insère un résumé sans effacer les détails absents de la réponse."""
        with self.connection if not self.connection.in_transaction else nullcontext():
            cursor = self.connection.execute(
                """
                INSERT INTO pokemon_reference_cards (
                    tcgdex_id, local_id, name, set_id, set_name,
                    rarity, category, types, hp, stage, illustrator,
                    image_url, raw_data, normalized_name, normalized_set_name,
                    canonical_local_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tcgdex_id) DO UPDATE SET
                    local_id = excluded.local_id,
                    name = excluded.name,
                    set_id = excluded.set_id,
                    set_name = excluded.set_name,
                    rarity = COALESCE(excluded.rarity, pokemon_reference_cards.rarity),
                    category = COALESCE(excluded.category, pokemon_reference_cards.category),
                    types = CASE WHEN excluded.types <> '[]' THEN excluded.types ELSE pokemon_reference_cards.types END,
                    hp = COALESCE(excluded.hp, pokemon_reference_cards.hp),
                    stage = COALESCE(excluded.stage, pokemon_reference_cards.stage),
                    illustrator = COALESCE(excluded.illustrator, pokemon_reference_cards.illustrator),
                    image_url = COALESCE(excluded.image_url, pokemon_reference_cards.image_url),
                    raw_data = excluded.raw_data,
                    normalized_name = excluded.normalized_name,
                    normalized_set_name = excluded.normalized_set_name,
                    canonical_local_id = excluded.canonical_local_id,
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                RETURNING id
                """,
                (
                    card_obj.id, card_obj.local_id, card_obj.name, card_obj.set_id,
                    card_obj.set_name, card_obj.rarity, card_obj.category,
                    json.dumps(card_obj.types, ensure_ascii=False), card_obj.hp,
                    card_obj.stage, card_obj.illustrator, card_obj.image_url,
                    json.dumps(card_obj.raw_data, ensure_ascii=False),
                    normalize_text(card_obj.name), normalize_text(card_obj.set_name),
                    canonical_local_id(card_obj.local_id),
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

    def get_cards_by_ids(self, card_ids: list[int]) -> list[ReferenceCardRecord]:
        """Lit des références connues sans tronquer avant leur classement."""
        ids = sorted(set(card_ids))
        cards = []
        for start in range(0, len(ids), 500):
            batch = ids[start:start + 500]
            placeholders = ",".join("?" for _ in batch)
            rows = self.connection.execute(
                f"SELECT id, tcgdex_id, local_id, name, set_id, set_name, rarity, category, "
                f"types, hp, stage, illustrator, image_url, raw_data, updated_at "
                f"FROM pokemon_reference_cards WHERE id IN ({placeholders}) ORDER BY id", batch,
            ).fetchall()
            cards.extend(self._row_to_record(row) for row in rows)
        return cards

    def find_cards(
        self,
        *,
        name: str | None = None,
        local_id: str | None = None,
        set_query: str | None = None,
        tcgdex_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ReferenceCardRecord]:
        """Recherche paginée avec la même normalisation à l'écriture et à la lecture."""
        clauses: list[str] = []
        params: list[Any] = []
        if tcgdex_id:
            clauses.append("tcgdex_id = ?")
            params.append(tcgdex_id)
        if name:
            norm_name = normalize_text(name)
            clauses.append("normalized_name LIKE ?")
            params.append(f"%{norm_name}%")
        if local_id:
            clauses.append("canonical_local_id = ?")
            params.append(canonical_local_id(local_id))
        if set_query:
            norm_set = normalize_text(set_query)
            clauses.append("(set_id = ? OR normalized_set_name LIKE ?)")
            params.extend([set_query, f"%{norm_set}%"])
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.connection.execute(
            f"""
            SELECT id, tcgdex_id, local_id, name, set_id, set_name,
                   rarity, category, types, hp, stage, illustrator,
                   image_url, raw_data, updated_at
            FROM pokemon_reference_cards {where}
            ORDER BY name COLLATE NOCASE ASC, set_name COLLATE NOCASE ASC,
                     canonical_local_id ASC, id ASC
            LIMIT ? OFFSET ?
            """,
            [*params, max(1, min(limit, 200)), max(0, offset)],
        ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def catalog_vocabulary(self) -> tuple[list[str], list[str]]:
        """Noms et extensions dérivés du référentiel, sans liste figée."""
        names = [row[0] for row in self.connection.execute(
            "SELECT DISTINCT name FROM pokemon_reference_cards ORDER BY length(name) DESC"
        )]
        sets = [row[0] for row in self.connection.execute(
            "SELECT DISTINCT set_name FROM pokemon_reference_cards ORDER BY length(set_name) DESC"
        )]
        return names, sets

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
