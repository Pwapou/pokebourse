"""Tests des pages web et de l'API de supervision."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import web
from app.storage.database import connect
from app.supervision.models import SupervisionThresholds
from app.supervision.service import SupervisionService
from app.web import app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("POKEMON_DATABASE_PATH", str(tmp_path / "agents-web.db"))
    with TestClient(app) as test_client:
        yield test_client


def populate(tmp_path: Path) -> None:
    service = SupervisionService(
        tmp_path / "agents-web.db",
        thresholds=SupervisionThresholds(
            degraded_after_consecutive_errors=1,
            blocked_after_consecutive_blocks=1,
            suspend_seconds=3600,
        ),
        agent_key="agent-web",
    )
    with connect(tmp_path / "agents-web.db") as connection:
        service.register(connection)
        service.mark_operational(connection)
        service.heartbeat(connection)


def test_agents_page_empty_state(client: TestClient) -> None:
    page = client.get("/agents")
    assert page.status_code == 200
    assert "Agents déployés" in page.text
    assert "Aucun agent enregistré" in page.text


def test_agents_page_lists_agent_and_unknown_ip(
    client: TestClient, tmp_path: Path
) -> None:
    populate(tmp_path)
    page = client.get("/agents")
    assert page.status_code == 200
    assert "Worker de veilles Pokébourse" in page.text
    assert "IP inconnue" in page.text
    assert "Opérationnel" in page.text
    assert 'http-equiv="refresh"' in page.text


def test_agents_page_filters_by_site_and_state(
    client: TestClient, tmp_path: Path
) -> None:
    populate(tmp_path)
    page = client.get("/agents", params={"site": "Vinted"})
    assert page.status_code == 200
    # Une ligne d'en-tête et une seule ligne de données (Vinted filtré).
    assert page.text.count("<tr>") == 2

    page = client.get("/agents", params={"state": "blocked"})
    assert page.status_code == 200
    assert "Aucun collecteur ne correspond aux filtres" in page.text


def test_agent_detail_page_and_404(client: TestClient, tmp_path: Path) -> None:
    populate(tmp_path)
    listing = client.get("/api/agents")
    assert listing.status_code == 200
    agents = listing.json()["agents"]
    assert len(agents) == 1
    agent_id = agents[0]["id"]

    detail = client.get(f"/agents/{agent_id}")
    assert detail.status_code == 200
    assert "FICHE AGENT" in detail.text
    assert "Transitions et événements" in detail.text

    missing = client.get("/agents/9999")
    assert missing.status_code == 404


def test_resume_blocked_collector_from_web(client: TestClient, tmp_path: Path) -> None:
    from app.supervision.errors import classify_error

    class FakeResponse:
        status_code = 403
        text = ""
        headers: dict[str, str] = {}

    class FakeHttpError(RuntimeError):
        def __init__(self) -> None:
            super().__init__("http error")
            self.response = FakeResponse()

    service = SupervisionService(
        tmp_path / "agents-web.db",
        thresholds=SupervisionThresholds(blocked_after_consecutive_blocks=1),
        agent_key="agent-web",
    )
    with connect(tmp_path / "agents-web.db") as connection:
        service.register(connection)
        service.mark_operational(connection)
        service.report_error(
            connection,
            collector_key="vinted",
            error=classify_error(FakeHttpError()),
        )
    listing = client.get("/api/agents").json()["agents"]
    agent_id = listing[0]["id"]
    collector = next(
        c for c in listing[0]["collectors"] if c["collector_key"] == "vinted"
    )
    assert collector["state"] == "blocked"

    response = client.post(
        f"/agents/{agent_id}/collectors/vinted/resume", follow_redirects=False
    )
    assert response.status_code == 303
    refreshed = client.get("/api/agents").json()["agents"]
    collector = next(
        c for c in refreshed[0]["collectors"] if c["collector_key"] == "vinted"
    )
    assert collector["state"] == "operational"


def test_api_agents_open_without_token(client: TestClient, tmp_path: Path) -> None:
    populate(tmp_path)
    response = client.get("/api/agents")
    assert response.status_code == 200
    assert len(response.json()["agents"]) == 1


def test_api_agents_requires_token_when_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("POKEMON_DATABASE_PATH", str(tmp_path / "agents-web.db"))
    monkeypatch.setenv("POKEMON_SUPERVISION_TOKEN", "jeton-test")
    with TestClient(app) as test_client:
        assert test_client.get("/api/agents").status_code == 401
        assert (
            test_client.get(
                "/api/agents", headers={"X-Supervision-Token": "jeton-test"}
            ).status_code
            == 200
        )
        assert (
            test_client.get(
                "/api/agents",
                headers={"Authorization": "Bearer jeton-test"},
            ).status_code
            == 200
        )
    monkeypatch.delenv("POKEMON_SUPERVISION_TOKEN")
