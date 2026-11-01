from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_default_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("POKEMON_DATABASE_PATH", raising=False)
    monkeypatch.delenv("POKEMON_LOG_LEVEL", raising=False)
    monkeypatch.delenv("POKEMON_SUPERVISION_IP_PROBE_URL", raising=False)

    settings = Settings.from_env()

    assert settings.database_path == Path("data/pokemon-arbitrage.db")
    assert settings.log_level == "INFO"
    assert settings.supervision_ip_probe_url == "https://api.ipify.org"


def test_settings_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POKEMON_DATABASE_PATH", "/tmp/test.db")
    monkeypatch.setenv("POKEMON_LOG_LEVEL", "debug")

    settings = Settings.from_env()

    assert settings.database_path == Path("/tmp/test.db")
    assert settings.log_level == "DEBUG"


def test_invalid_log_level_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POKEMON_LOG_LEVEL", "verbose")

    with pytest.raises(ValidationError):
        Settings.from_env()
