import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import web
from app.collectors.models import CollectionResult, CollectedListing
from app.collectors.service import ensure_collection_source, ingest_collected_listings
from app.monitoring.service import WatchService
from app.storage.database import connect
from app.web import app


def fake_vinted_collection() -> CollectionResult:
    return CollectionResult(
        listings=[
            CollectedListing(
                source="vinted",
                external_id="web-1",
                title="Carte Pokémon Pikachu - Évolutions",
                price_cents=1250,
                url="https://www.vinted.fr/items/web-1",
                seller="Vendeur web",
            )
        ]
    )


@pytest.fixture
def watch_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    monkeypatch.setenv("POKEMON_DATABASE_PATH", str(tmp_path / "watches-web.db"))
    service = WatchService(
        min_interval_seconds=120,
        collectors={"vinted": lambda **_params: fake_vinted_collection()},
    )
    monkeypatch.setattr(web, "watch_service_from", lambda _request: service)
    with TestClient(app) as test_client:
        yield test_client


def test_watch_page_create_run_pause_resume_and_delete(watch_client: TestClient) -> None:
    page = watch_client.get("/watches")
    assert page.status_code == 200
    assert "Veilles" in page.text
    assert "Aucune veille configurée" in page.text

    created = watch_client.post(
        "/watches",
        data={
            "platform": "vinted",
            "name": "Pikachu à surveiller",
            "search_text": "Carte Pokémon Pikachu",
            "price_min_euros": "5,00",
            "price_max_euros": "50,00",
            "interval_seconds": "180",
        },
        follow_redirects=False,
    )
    assert created.status_code == 303
    assert created.headers["location"].startswith("/watches?notice=")
    listing = watch_client.get("/watches")
    assert "Pikachu à surveiller" in listing.text
    assert "Active" in listing.text
    assert "180 s" in listing.text
    assert "Jamais exécutée" in listing.text

    invalid = watch_client.post(
        "/watches",
        data={
            "platform": "vinted",
            "name": "Intervalle invalide",
            "search_text": "Pikachu",
            "interval_seconds": "60",
        },
    )
    assert "intervalle minimum est de 120 secondes" in invalid.text

    executed = watch_client.post("/watches/1/run", follow_redirects=False)
    assert executed.status_code == 303
    after_run = watch_client.get("/watches")
    assert "Réussi" in after_run.text
    assert "1 résultat" in after_run.text
    assert "1 nouveau(x) · 0 mis à jour" in after_run.text
    assert '"id": "web-1"' not in after_run.text

    paused = watch_client.post("/watches/1/pause", follow_redirects=False)
    assert paused.status_code == 303
    assert "En pause" in watch_client.get("/watches").text
    resumed = watch_client.post("/watches/1/resume", follow_redirects=False)
    assert resumed.status_code == 303
    assert "Active" in watch_client.get("/watches").text

    unconfirmed = watch_client.post(
        "/watches/1/delete", data={}, follow_redirects=False
    )
    assert unconfirmed.status_code == 303
    assert "confirmation explicite" in watch_client.get(
        unconfirmed.headers["location"]
    ).text
    deleted = watch_client.post(
        "/watches/1/delete",
        data={"confirm": "yes"},
        follow_redirects=False,
    )
    assert deleted.status_code == 303
    assert "Aucune veille configurée" in watch_client.get("/watches").text


def test_catalog_source_filters_include_marketplace_and_manual(
    watch_client: TestClient,
) -> None:
    manual_jsonl = (
        b'{"external_id":"manual-web","name":"Dracaufeu","set_name":"Base Set",'
        b'"price_cents":30000}'
    )
    import_response = watch_client.post(
        "/imports",
        files={"file": ("annonces.jsonl", manual_jsonl, "application/x-ndjson")},
    )
    assert import_response.status_code == 200
    watch_client.post(
        "/watches",
        data={
            "platform": "vinted",
            "name": "Source Vinted",
            "search_text": "Pikachu",
            "interval_seconds": "180",
        },
    )
    run_response = watch_client.post("/watches/1/run", follow_redirects=False)
    assert run_response.status_code == 303
    assert "notice=" in run_response.headers["location"]

    all_page = watch_client.get("/catalog")
    vinted_page = watch_client.get("/catalog", params={"source": "vinted"})
    manual_page = watch_client.get("/catalog", params={"source": "manual"})
    export = watch_client.get("/catalog/export.csv", params={"source": "vinted"})

    assert "Dracaufeu" in all_page.text
    assert "Pikachu" in all_page.text
    assert "Dracaufeu" not in vinted_page.text
    assert "Pikachu" in vinted_page.text
    assert "Vinted" in vinted_page.text
    assert "Dracaufeu" in manual_page.text
    assert "Carte non identifiée" not in manual_page.text
    assert "Imports manuels" in manual_page.text
    assert "Source" in export.text
    assert "vinted" in export.text
    assert "Dracaufeu" not in export.text
