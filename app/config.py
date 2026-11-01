import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    database_path: Path = Path("data/pokemon-arbitrage.db")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    min_watch_interval_seconds: int = Field(default=120, ge=1, le=86_400)
    watch_poll_seconds: float = Field(default=5.0, ge=0.5, le=300.0)
    seller_enrichment_per_tick: int = Field(default=3, ge=0, le=50)
    seller_cache_seconds: float = Field(default=86_400.0, gt=0, le=2_592_000.0)
    supervision_token: str | None = Field(default=None, max_length=200)
    agent_key: str | None = Field(default=None, max_length=200)
    supervision_heartbeat_seconds: float = Field(default=30.0, gt=0, le=3600.0)
    supervision_offline_after_seconds: float = Field(default=90.0, gt=0, le=86_400.0)
    supervision_degraded_after_errors: int = Field(default=3, ge=1, le=100)
    supervision_blocked_after_blocks: int = Field(default=2, ge=1, le=20)
    supervision_suspend_seconds: float = Field(default=900.0, gt=0, le=86_400.0)
    supervision_ip_probe_url: str | None = Field(default=None, max_length=500)

    @classmethod
    def from_env(cls) -> "Settings":
        values: dict[str, object] = {}
        if database_path := os.getenv("POKEMON_DATABASE_PATH"):
            values["database_path"] = Path(database_path)
        if log_level := os.getenv("POKEMON_LOG_LEVEL"):
            values["log_level"] = log_level.upper()
        if min_interval := os.getenv("POKEMON_MIN_WATCH_INTERVAL_SECONDS"):
            values["min_watch_interval_seconds"] = int(min_interval)
        if poll_seconds := os.getenv("POKEMON_WATCH_POLL_SECONDS"):
            values["watch_poll_seconds"] = float(poll_seconds)
        if seller_limit := os.getenv("POKEMON_SELLER_ENRICHMENT_PER_TICK"):
            values["seller_enrichment_per_tick"] = int(seller_limit)
        if seller_cache := os.getenv("POKEMON_SELLER_CACHE_SECONDS"):
            values["seller_cache_seconds"] = float(seller_cache)
        if token := os.getenv("POKEMON_SUPERVISION_TOKEN"):
            values["supervision_token"] = token
        if agent_key := os.getenv("POKEMON_AGENT_KEY"):
            values["agent_key"] = agent_key
        if heartbeat := os.getenv("POKEMON_SUPERVISION_HEARTBEAT_SECONDS"):
            values["supervision_heartbeat_seconds"] = float(heartbeat)
        if offline := os.getenv("POKEMON_SUPERVISION_OFFLINE_AFTER_SECONDS"):
            values["supervision_offline_after_seconds"] = float(offline)
        if degraded := os.getenv("POKEMON_SUPERVISION_DEGRADED_AFTER_ERRORS"):
            values["supervision_degraded_after_errors"] = int(degraded)
        if blocked := os.getenv("POKEMON_SUPERVISION_BLOCKED_AFTER_BLOCKS"):
            values["supervision_blocked_after_blocks"] = int(blocked)
        if suspend := os.getenv("POKEMON_SUPERVISION_SUSPEND_SECONDS"):
            values["supervision_suspend_seconds"] = float(suspend)
        if probe := os.getenv("POKEMON_SUPERVISION_IP_PROBE_URL"):
            values["supervision_ip_probe_url"] = probe
        return cls.model_validate(values)

    def supervision_thresholds(self) -> "SupervisionThresholds":
        from app.supervision.models import SupervisionThresholds

        return SupervisionThresholds(
            heartbeat_interval_seconds=self.supervision_heartbeat_seconds,
            offline_after_seconds=self.supervision_offline_after_seconds,
            degraded_after_consecutive_errors=self.supervision_degraded_after_errors,
            blocked_after_consecutive_blocks=self.supervision_blocked_after_blocks,
            suspend_seconds=self.supervision_suspend_seconds,
        )
