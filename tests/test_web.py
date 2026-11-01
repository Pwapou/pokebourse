from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.web import app, format_date


def test_format_sqlite_timestamp_for_display() -> None:
    assert format_date("2026-11-01T17:26:01.450Z") == "01/11/2026 · 17:26"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("POKEMON_DATABASE_PATH", str(tmp_path / "web.db"))
    with TestClient(app) as test_client:
        test_client.post(
            "/profitability/settings",
            data={
                "buyer_shipping_euros": "0",
                "platform_fee_percent": "5",
                "seller_fixed_fee_euros": "0",
                "shipping_packaging_euros": "2",
                "min_net_profit_euros": "5",
                "min_roi_percent": "15",
                "min_catalog_samples": "2",
            },
        )
        yield test_client


def test_dashboard_and_health(client: TestClient) -> None:
    dashboard = client.get("/")
    health = client.get("/health")

    assert dashboard.status_code == 200
    assert "Commencez par importer vos annonces" in dashboard.text
    assert "built-in method" not in dashboard.text
    assert health.status_code == 200
    assert health.json() == {"status": "ok", "database": "ok"}


def test_import_then_search_catalog(client: TestClient) -> None:
    content = (
        b'{"external_id":"pika-1","name":"Pikachu","set_name":"Evolutions",'
        b'"price_cents":1290,"condition":"NM"}\n'
        b'{"external_id":"draco-1","name":"Dracaufeu","set_name":"Base Set",'
        b'"price_cents":25000,"seller":"Vendeur test"}'
    )

    response = client.post(
        "/imports",
        files={"file": ("annonces.jsonl", content, "application/x-ndjson")},
        follow_redirects=False,
    )
    dashboard = client.get("/?imported=2")
    catalog = client.get("/catalog", params={"q": "Pikachu"})
    no_result = client.get("/catalog", params={"q": "Absent"})

    assert response.status_code == 303
    assert response.headers["location"] == "/?imported=2"
    assert "Import réussi." in dashboard.text
    assert 'href="/catalog/1"' in dashboard.text
    assert 'href="/catalog/2"' in dashboard.text
    assert "Pikachu" in catalog.text
    assert "Dracaufeu" not in catalog.text
    assert "12,90 €" in catalog.text
    assert "Aucun résultat" in no_result.text


def test_invalid_import_returns_visible_error(client: TestClient) -> None:
    response = client.post(
        "/imports",
        files={"file": ("invalide.jsonl", b"not-json", "application/x-ndjson")},
    )

    assert response.status_code == 200
    assert "Import impossible." in response.text
    assert "JSON invalide" in response.text


def test_profitability_page_settings_and_cotes_flow(client: TestClient) -> None:
    listings = (
        b'{"external_id":"pika-deal","name":"Pikachu","set_name":"Evolutions",'
        b'"card_number":"35/108","condition":"NM","price_cents":1000}\n'
        b'{"external_id":"draco-high","name":"Dracaufeu","set_name":"Base Set",'
        b'"card_number":"4/102","condition":"NM","price_cents":34000}'
    )
    client.post(
        "/imports",
        files={"file": ("annonces.jsonl", listings, "application/x-ndjson")},
    )
    client.post(
        "/profitability/settings",
        data={
            "buyer_shipping_euros": "0",
            "platform_fee_percent": "5",
            "seller_fixed_fee_euros": "0",
            "shipping_packaging_euros": "2",
            "min_net_profit_euros": "5",
            "min_roi_percent": "15",
            "min_catalog_samples": "2",
        },
    )

    # Save a manual cote for Pikachu (25,00 €)
    save_ref = client.post(
        "/profitability/references",
        data={
            "name": "Pikachu",
            "set_name": "Évolutions",
            "card_number": "35/108",
            "language": "fr",
            "condition": "NM",
            "reference_price_euros": "25,00",
            "currency": "EUR",
            "source_name": "Cardmarket",
            "reference_kind": "ventes_conclues",
            "observed_at": "2026-10-31",
            "sample_size": "12",
            "note": "Cote test",
        },
    )
    assert save_ref.status_code == 200
    assert "Cote enregistrée pour Pikachu." in save_ref.text

    # Import JSONL cote for Dracaufeu (300,00 € -> listing at 340,00 € is non_rentable)
    cotes_jsonl = (
        b'{"name":"Dracaufeu","set_name":"Base Set","card_number":"4/102",'
        b'"condition":"NM","reference_price_cents":30000,"currency":"EUR"}'
    )
    import_ref = client.post(
        "/profitability/references/import",
        files={"file": ("cotes.jsonl", cotes_jsonl, "application/x-ndjson")},
    )
    assert import_ref.status_code == 200
    assert "1 cote(s) importée(s) ou mise(s) à jour." in import_ref.text

    # Filter opportunities only
    opp_page = client.get("/profitability", params={"verdict": "opportunite"})
    assert opp_page.status_code == 200
    assert "built-in method" not in opp_page.text
    assert "Pikachu" in opp_page.text
    assert "+11,75 €" in opp_page.text
    assert "Ventes conclues" in opp_page.text
    assert "Cardmarket" in opp_page.text
    assert "2026-10-31" in opp_page.text

    # Dashboard and catalog reflect the opportunity
    dashboard = client.get("/")
    catalog = client.get("/catalog", params={"q": "Pikachu"})
    assert "+11,75 €" in dashboard.text
    assert "Opportunité" in catalog.text

    detail = client.get("/catalog/1")
    assert "Coût total d’achat" in detail.text
    assert "Commission 1,25 €" in detail.text
    assert "Gain net estimé" in detail.text
    assert "+11,75 €" in detail.text

    # Update fee settings
    settings_resp = client.post(
        "/profitability/settings",
        data={
            "buyer_shipping_euros": "2,00",
            "platform_fee_percent": "10",
            "seller_fixed_fee_euros": "0,50",
            "shipping_packaging_euros": "2,50",
            "min_net_profit_euros": "5,00",
            "min_roi_percent": "20",
            "min_catalog_samples": "2",
        },
    )
    assert settings_resp.status_code == 200
    assert "Paramètres de rentabilité enregistrés." in settings_resp.text
    # New profit for Pikachu: 2500 - 250 - 50 - 250 - (1000 + 200) = +750 (+7,50 €)
    assert "+7,50 €" in settings_resp.text

    # Delete first reference
    delete_resp = client.post("/profitability/references/1/delete")
    assert delete_resp.status_code == 200
    assert "Cote supprimée." in delete_resp.text


def import_bulk(client: TestClient, count: int, name: str = "Carte") -> None:
    content = "".join(
        '{"external_id":"%s-%03d","name":"%s %03d","set_name":"Base Set",'
        '"price_cents":%d,"seller":"Vendeur %d"}\n'
        % ("annonce", index, name, index, 100 * (index + 1), index)
        for index in range(count)
    ).encode()
    response = client.post(
        "/imports",
        files={"file": ("annonces.jsonl", content, "application/x-ndjson")},
    )
    assert response.status_code == 200


def test_catalog_pagination_and_filter_preservation(client: TestClient) -> None:
    import_bulk(client, 30)

    page = client.get("/catalog")
    assert page.status_code == 200
    assert "1–25 sur 30" in page.text
    assert "Précédent" in page.text
    assert "Suivant" in page.text
    assert "/catalog/export.csv" in page.text
    assert "page=2" in page.text

    filtered = client.get(
        "/catalog", params={"q": "Carte 029", "set_name": "Base Set", "sort": "price_asc"}
    )
    assert filtered.status_code == 200
    assert "1–1 sur 1" in filtered.text
    # Les liens de pagination et l'export conservent recherche, extension et tri.
    assert "q=Carte+029" in filtered.text
    assert "set_name=Base+Set" in filtered.text
    assert "sort=price_asc" in filtered.text
    assert "export.csv?q=Carte+029" in filtered.text

    second = client.get(
        "/catalog",
        params={"q": "Carte", "set_name": "Base Set", "sort": "name_asc", "page": 2},
    )
    assert second.status_code == 200
    assert "26–30 sur 30" in second.text
    assert "q=Carte" in second.text
    assert "sort=name_asc" in second.text


def test_catalog_rejects_invalid_pages_and_sorts(client: TestClient) -> None:
    import_bulk(client, 3)

    negative = client.get("/catalog", params={"page": -4})
    zero = client.get("/catalog", params={"page": 0})
    huge = client.get("/catalog", params={"page": 9999})
    injection = client.get("/catalog", params={"sort": "price_cents; DROP TABLE"})

    for response in (negative, zero, huge, injection):
        assert response.status_code == 200
    assert "1–3 sur 3" in negative.text
    assert "1–3 sur 3" in zero.text
    assert "1–3 sur 3" in huge.text
    # La base reste intacte après une tentative d'injection SQL.
    assert "Carte 000" in injection.text


def test_catalog_detail_page_and_404(client: TestClient) -> None:
    content = (
        '{"external_id":"pika-1","name":"Pikachu","set_name":"Évolutions",'
        '"card_number":"35/108","language":"fr","condition":"NM",'
        '"price_cents":1290,"currency":"EUR","seller":"Collection locale",'
        '"url":"https://example.com/annonces/pika-1"}\n'
        '{"external_id":"ronf-1","name":"Ronflex","set_name":"Base Set",'
        '"price_cents":5000}'
    ).encode("utf-8")
    client.post(
        "/imports", files={"file": ("annonces.jsonl", content, "application/x-ndjson")}
    )

    detail = client.get("/catalog/1")
    assert detail.status_code == 200
    assert "Pikachu" in detail.text
    assert "Évolutions" in detail.text
    assert "35/108" in detail.text
    assert "NM" in detail.text
    assert "12,90 €" in detail.text
    assert "1290 centimes EUR" in detail.text
    assert "Prix de revente inconnu" in detail.text
    assert "Ajouter un prix de référence" in detail.text
    assert "Collection locale" in detail.text
    assert "pika-1" in detail.text
    assert "import-web" in detail.text
    assert "#1" in detail.text
    assert 'target="_blank"' in detail.text
    assert 'rel="noopener noreferrer"' in detail.text
    assert "Retour au catalogue" in detail.text

    missing = client.get("/catalog/424242")
    assert missing.status_code == 404
    assert "Page introuvable" in missing.text


def test_catalog_detail_not_found_for_non_integer(client: TestClient) -> None:
    response = client.get("/catalog/abc")
    assert response.status_code == 422


def test_catalog_export_csv_headers_and_content(client: TestClient) -> None:
    import_bulk(client, 30)

    response = client.get("/catalog/export.csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "charset=utf-8" in response.headers["content-type"]
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="pokebourse-catalogue.csv"'
    )
    body = response.content.decode("utf-8-sig")
    lines = body.split("\r\n")
    assert len(lines) == 32  # 1 en-tête + 30 lignes + terminateur final
    assert lines[0].startswith("Identifiant interne")
    assert "Nom de la carte" in lines[0]
    assert "Prix (centimes)" in lines[0]
    assert "Devise" in lines[0]


def test_catalog_export_csv_respects_filters_and_escapes_formulas(
    client: TestClient,
) -> None:
    content = (
        '{"external_id":"safe-1","name":"Pikachu","set_name":"Évolutions",'
        '"price_cents":1290}\n'
        '{"external_id":"evil-1","name":"=1+1","set_name":"Base Set",'
        '"price_cents":100,"seller":"+INF",'
        '"url":"https://example.com/x"}\n'
        '{"external_id":"accents","name":"Méwtwo, \\"shiny\\"\\nvintage",'
        '"set_name":"Évolutions","price_cents":999999}'
    ).encode("utf-8")
    client.post(
        "/imports", files={"file": ("annonces.jsonl", content, "application/x-ndjson")}
    )

    full = client.get("/catalog/export.csv")
    body = full.content.decode("utf-8-sig")
    assert "Pikachu" in body
    assert "'=1+1" in body
    assert "'+INF" in body
    assert '"Méwtwo, ""shiny""' in body

    filtered = client.get(
        "/catalog/export.csv", params={"q": "Pikachu", "set_name": "Évolutions"}
    )
    filtered_body = filtered.content.decode("utf-8-sig")
    lines = [line for line in filtered_body.split("\r\n") if line]
    assert len(lines) == 2  # en-tête + la seule annonce filtrée
    assert "Pikachu" in filtered_body
    assert "evil-1" not in filtered_body


def test_identification_search_and_confirmation_flow(client: TestClient) -> None:
    from app.config import Settings
    from app.identification.resolution import resolve_listing
    from app.storage.database import connect

    content = b'{"external_id":"draco-web","name":"Dracaufeu","set_name":"Set de Base","card_number":"004/102","price_cents":1000}'
    client.post("/imports", files={"file": ("annonces.jsonl", content, "application/x-ndjson")})
    candidates = client.get("/catalog/1/identification", params={"name": "Dracaufeu", "local_id": "4"})
    assert candidates.status_code == 200
    card = candidates.json()["items"][0]
    with connect(Settings.from_env().database_path) as connection:
        resolution = resolve_listing(connection, 1)
    response = client.post("/catalog/1/identification/confirm", data={
        "reference_card_id": card["id"], "evidence_hash": resolution.evidence_hash,
        "revision": resolution.revision,
    }, follow_redirects=True)
    assert response.status_code == 200
    assert "Confirmée manuellement" in response.text
    assert "Retirer la confirmation" in response.text
    queued = client.post("/catalog/1/identification/search", data={"name": "Dracaufeu"}, follow_redirects=False)
    assert queued.status_code == 303
    assert "attente" in queued.headers["location"]
