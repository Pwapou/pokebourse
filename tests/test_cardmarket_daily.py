"""Planification quotidienne de la synchronisation Cardmarket (worker)."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.cardmarket import daily
from app.cardmarket.aliases import base_card_name
from app.storage.database import connect
from app.storage.migration_runner import apply_migrations

RUN = daily.parse_utc_time("02:20")


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=UTC)


def test_parse_utc_time_accepts_hh_mm_and_rejects_garbage() -> None:
    parsed = daily.parse_utc_time("02:20")
    assert (parsed.hour, parsed.minute) == (2, 20)
    for raw in ("", "2h20", "24:00", "02:60", "aa:bb"):
        with pytest.raises(ValueError):
            daily.parse_utc_time(raw)


def test_should_run_waits_for_the_daily_regeneration() -> None:
    # Avant l'heure planifiée : jamais (le fichier du jour n'existe pas encore).
    assert daily.should_run(at(1, 1, 0), None, RUN) is False
    # Après l'heure planifiée, jamais synchronisé : on lance.
    assert daily.should_run(at(1, 3, 0), None, RUN) is True


def test_should_run_once_a_day_after_success() -> None:
    state = {"last_success_at": "2026-11-01T02:30:00.000Z", "last_attempt_at": "2026-11-01T02:30:00.000Z"}
    # Même jour, après le succès : déjà fait.
    assert daily.should_run(at(1, 5, 0), state, RUN) is False
    # Le lendemain après l'heure planifiée : on relance.
    assert daily.should_run(at(2, 3, 0), state, RUN) is True
    # Le lendemain mais avant l'heure planifiée : on attend la régénération.
    assert daily.should_run(at(2, 1, 0), state, RUN) is False


def test_should_run_backs_off_after_failed_attempt() -> None:
    state = {"last_success_at": None, "last_attempt_at": "2026-11-01T02:25:00.000Z"}
    # Échec il y a 30 minutes : on attend (au plus une tentative par heure).
    assert daily.should_run(at(1, 2, 55), state, RUN) is False
    # Échec il y a plus d'une heure : on réessaie.
    assert daily.should_run(at(1, 3, 30), state, RUN) is True


def _seed_reference_card(connection) -> None:
    connection.execute(
        "INSERT INTO pokemon_reference_sets (id, name) VALUES ('sv03', 'Flammes Obsidiennes')"
    )
    connection.execute(
        """
        INSERT INTO pokemon_reference_cards (tcgdex_id, local_id, name, set_id, set_name)
        VALUES ('sv03-125', '125', 'Dracaufeu-ex', 'sv03', 'Flammes Obsidiennes')
        """
    )
    connection.commit()


LOCALE_DATA = {
    "fr": [{"id": "sv03-125", "name": "Dracaufeu-ex"}],
    "en": [{"id": "sv03-125", "name": "Charizard ex"}],
    "ko": [],
    "ja": [],
    "zh-tw": [],
}


def _fake_fetcher(locale: str) -> list[dict[str, object]]:
    return LOCALE_DATA[locale]


def _fake_guide(connection) -> dict[str, object]:
    card_name = "Charizard ex"
    connection.execute(
        """
        INSERT INTO cardmarket_prices (product_id, card_name, trend_price_cents,
                                       currency, name_base)
        VALUES (9001, ?, 30000, 'EUR', ?)
        ON CONFLICT(product_id) DO UPDATE SET trend_price_cents = excluded.trend_price_cents
        """,
        (card_name, base_card_name(card_name)),
    )
    connection.commit()
    return {"created_at": "2026-11-01T01:47:16Z", "synced": 1, "skipped": 0}


def test_maybe_run_daily_sync_executes_once_then_waits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(daily.cardmarket_guide, "sync_price_guide", _fake_guide)
    with connect(tmp_path / "daily.db") as connection:
        apply_migrations(connection)
        _seed_reference_card(connection)
        now = at(1, 3, 0)

        result = daily.maybe_run_daily_sync(
            connection, now=now, fetcher=_fake_fetcher
        )
        assert result is not None
        assert result["guide"]["synced"] == 1
        assert result["aliases"]["per_locale"] == {
            "fr": 1,
            "en": 1,
            "ko": 0,
            "ja": 0,
            "zh-tw": 0,
        }
        assert connection.execute(
            "SELECT COUNT(*) FROM card_name_aliases"
        ).fetchone()[0] == 2

        state = daily.load_state(connection)
        assert state is not None
        assert state["last_success_at"] is not None
        assert "cotes 1" in str(state["detail"])

        # Déjà synchronisé après la régénération du jour : rien à faire.
        assert daily.maybe_run_daily_sync(
            connection, now=at(1, 5, 0), fetcher=_fake_fetcher
        ) is None
        # Le lendemain matin : nouvelle exécution.
        assert daily.maybe_run_daily_sync(
            connection, now=at(2, 3, 0), fetcher=_fake_fetcher
        ) is not None


def test_failed_sync_records_attempt_and_backs_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken_guide(connection) -> dict[str, object]:
        raise RuntimeError("réseau KO")

    monkeypatch.setattr(daily.cardmarket_guide, "sync_price_guide", broken_guide)
    with connect(tmp_path / "fail.db") as connection:
        apply_migrations(connection)
        with pytest.raises(RuntimeError, match="réseau KO"):
            daily.maybe_run_daily_sync(
                connection, now=at(1, 3, 0), fetcher=_fake_fetcher
            )
        state = daily.load_state(connection)
        assert state is not None
        assert state["last_success_at"] is None
        assert state["last_attempt_at"] is not None

        # 30 minutes plus tard : toujours en attente (rebond évité)…
        assert daily.maybe_run_daily_sync(
            connection, now=at(1, 3, 30), fetcher=_fake_fetcher
        ) is None
        # …plus d'une heure après : on réessaie, nouvel échec.
        with pytest.raises(RuntimeError, match="réseau KO"):
            daily.maybe_run_daily_sync(
                connection, now=at(1, 4, 40), fetcher=_fake_fetcher
            )
