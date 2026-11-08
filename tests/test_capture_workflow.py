"""Contrat W01/W02/W05–W07/W09 du moteur actuel, sans OCR ni réseau réels."""
from __future__ import annotations

import json
from html.parser import HTMLParser
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from test_capture_preview import client, _capture  # noqa: F401 — fixture hermétique commune
from app.catalog import CatalogItem, catalog_export_rows
from app.catalog_export import build_catalog_csv
from app.identification.detector import extract_features
from app.identification.matcher import CardMatcher
from app.identification.normalization import valid_card_number
from app.listing_preview import preview_listing, prefill_identity_fields
from app.storage.database import connect
from app.tcgdex.cache import TcgdexCache


class Inputs(HTMLParser):
    """Rejoue les champs du formulaire rendu, y compris leur provenance."""

    def __init__(self, html: str) -> None:
        super().__init__()
        self.values: dict[str, str] = {}
        self.feed(html)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == 'input' and attributes.get('name'):
            self.values[attributes['name']] = attributes.get('value') or ''


def test_legacy_title_fallback_proposal_reanalysis_and_human_correction(client: TestClient) -> None:
    payload = _capture()
    first = client.post('/previsualiser-capture', data=payload)
    fields = Inputs(first.text).values
    assert fields['name'] == 'Dracaufeu'
    assert fields['captured_name'] == fields['title'] == payload['title']
    assert fields['proposed_name'] == 'Dracaufeu'
    assert 'Proposée depuis le référentiel' in first.text
    fields.update(description=payload['description'], language='fr')
    second = client.post('/previsualiser-capture/analyser', data=fields)
    assert Inputs(second.text).values['proposed_name'] == 'Dracaufeu'
    fields['name'] = 'Dracaufeu personnel'
    corrected = client.post('/previsualiser-capture/analyser', data=fields)
    assert Inputs(corrected.text).values['name'] == 'Dracaufeu personnel'
    assert Inputs(corrected.text).values['captured_title'] == payload['title']


def test_no_candidate_does_not_present_seller_title_as_canonical(client: TestClient) -> None:
    first = client.post('/previsualiser-capture', data=_capture(
        title='Objet absolument inconnu', name='Objet absolument inconnu', description='', set_name='', card_number=''))
    assert Inputs(first.text).values['name'] == ''
    assert Inputs(first.text).values['captured_name'] == 'Objet absolument inconnu'


@pytest.mark.parametrize('field', ['price', 'shipping', 'currency'])
def test_financial_error_keeps_identity_and_ocr_without_reexecution(client: TestClient, field: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr('app.identification.ocr.analyze_image', lambda *_a, **_k: pytest.fail('OCR relancé'))
    payload = _capture(**{field: 'invalide'})
    payload['ocr_result'] = json.dumps({'recognized': {'names': ['Dracaufeu'], 'numbers': ['4/102']}})
    first = client.post('/previsualiser-capture', data=payload)
    assert f'data-financial-error="{field}"' in first.text
    assert 'base1-4' in first.text
    assert 'Gain net :' not in first.text
    fields = Inputs(first.text).values
    assert fields[field] == 'invalide'
    fields.update(description=payload['description'], language='fr', price='145', shipping='5', currency='EUR')
    second = client.post('/previsualiser-capture/analyser', data=fields)
    assert 'data-financial-error=' not in second.text
    assert 'base1-4' in second.text
    assert 'Gain net :' in second.text


def test_unknown_language_roundtrip_and_legacy_jsonl_default(client: TestClient) -> None:
    payload = _capture(language='', image_url='')
    response = client.post('/previsualiser-capture/confirmer', data=payload, follow_redirects=False)
    assert response.status_code == 303
    with connect(client.app.state.settings.database_path) as connection:
        assert connection.execute('SELECT language FROM catalog_items').fetchone()[0] == 'und'
        assert 'und' in build_catalog_csv(catalog_export_rows(connection)).decode('utf-8-sig')
        raw = json.loads(connection.execute('SELECT observations_json FROM listing_identity_evidence').fetchone()[0])
        assert not any(observation['field'] == 'language' and observation['value'] == 'fr' for observation in raw)
    assert CatalogItem(external_id='legacy', name='Pikachu', set_name='Base', price_cents=100).language == 'fr'


def test_n_from_generic_placeholder_and_ocr_is_ignored(client: TestClient) -> None:
    # Avant correction : extract_features('Non identifiée').card_number == 'n'.
    assert extract_features('Non identifiée').card_number is None
    assert extract_features('Pokémon numéro SM233').card_number == 'SM233'
    assert valid_card_number('TG01/030')
    assert not valid_card_number('n')
    assert valid_card_number('N', {'N'})  # référence alphabétique réellement attestée
    with connect(client.app.state.settings.database_path) as connection:
        result = preview_listing(connection, {'title': 'Carte photographiée', 'ocr_names': ['Pikachu'], 'ocr_numbers': ['n']})
        assert result['identification']['features']['card_number'] is None
        values = {'title': 'Carte photographiée'}
        prefill_identity_fields(values, result)
        assert values.get('card_number', '') != 'n'
    response = client.post('/previsualiser-capture', data=_capture(card_number='n'))
    assert 'Numéro invalide' in response.text
    assert 'base1-4' in response.text
    assert 'Gain net :' not in response.text
    rejected = client.post('/previsualiser-capture/confirmer', data=_capture(card_number='n'))
    assert 'Numéro invalide' in rejected.text


def test_partial_criteria_and_incompatible_valid_fields(client: TestClient) -> None:
    with connect(client.app.state.settings.database_path) as connection:
        for fields in ({'name': 'Dracaufeu'}, {'card_number': '4/102'}, {'set_name': 'Set de Base'}):
            result = preview_listing(connection, {'title': '', **fields})
            assert result['identification']['candidates']
        conflict = preview_listing(connection, {'title': '', 'name': 'Dracaufeu', 'set_name': 'Set de Base', 'card_number': '15/102'})
        assert all(check['status'] == 'used' for key, check in conflict['field_checks'].items() if key != 'language')
        assert conflict['evaluation'] is None
        assert conflict['identification']['diagnostic_candidates']
        assert conflict['identification']['status'] != 'identified'
    payload = _capture(card_number='15/102')
    rejected = client.post('/previsualiser-capture/confirmer', data=payload)
    assert 'Preuves contradictoires' in rejected.text
    with connect(client.app.state.settings.database_path) as connection:
        assert connection.execute('SELECT count(*) FROM catalog_items').fetchone()[0] == 0


def test_typo_title_canonical_proposal_remains_indicative_after_reanalysis(client: TestClient) -> None:
    payload = _capture(title='Dracofeu 4/102', name='Dracofeu 4/102', description='', set_name='', card_number='4/102')
    first = client.post('/previsualiser-capture', data=payload)
    fields = Inputs(first.text).values
    assert fields['name'] == fields['proposed_name'] == 'Dracaufeu'
    fields.update(language='fr', description='')
    second = client.post('/previsualiser-capture/analyser', data=fields)
    assert 'Identification ambiguë' in second.text
    assert 'Indices concordants' not in second.text
    assert 'contradiction_des_preuves' not in second.text
    assert Inputs(second.text).values['captured_title'] == 'Dracofeu 4/102'
    saved = client.post('/previsualiser-capture/confirmer', data=fields, follow_redirects=False)
    assert saved.status_code == 303
    with connect(client.app.state.settings.database_path) as connection:
        row = connection.execute('SELECT original_title, name, identification_status FROM catalog_items').fetchone()
        assert tuple(row) == ('Dracofeu 4/102', 'Dracaufeu', 'ambiguous')
        assert connection.execute('SELECT count(*) FROM listing_identification_decisions').fetchone()[0] == 0


def test_unrecognized_set_does_not_become_an_exact_filter(client: TestClient) -> None:
    response = client.post('/previsualiser-capture', data=_capture(set_name='Valeur fantaisie', language='xx'))
    assert 'Extension non reconnue' in response.text
    assert 'Langue non admise' in response.text
    assert 'Gain net :' not in response.text


def test_missing_currency_is_financial_error_without_blocking_partial_identity(client: TestClient) -> None:
    """POST directs : devise manquante puis correction, sans changement des preuves."""
    response = client.post('/previsualiser-capture', data=_capture(currency=''))
    assert 'data-financial-error="currency"' in response.text
    assert 'base1-4' in response.text
    fields = Inputs(response.text).values
    assert fields['currency'] == ''
    fields.update(currency='EUR', language='fr', description='')
    corrected = client.post('/previsualiser-capture/analyser', data=fields)
    assert 'data-financial-error="currency"' not in corrected.text
    assert 'base1-4' in corrected.text
    assert Inputs(corrected.text).values['captured_title'] == fields['captured_title']


@pytest.mark.parametrize('field', ['price', 'shipping'])
def test_manual_final_financial_error_keeps_candidates(client: TestClient, field: str) -> None:
    """L'ajout direct sans JS conserve les diagnostics et n'écrit rien en cas d'erreur."""
    fields = _capture(**{field: 'invalide'})
    fields['url'] = 'https://www.vinted.fr/items/12345-carte'
    response = client.post('/ajouter-annonce/enregistrer', data=fields)
    assert f'data-financial-error="{field}"' in response.text
    assert 'base1-4' in response.text
    assert Inputs(response.text).values[field] == 'invalide'
    with connect(client.app.state.settings.database_path) as connection:
        assert connection.execute('SELECT count(*) FROM catalog_items').fetchone()[0] == 0


def test_manual_save_retains_original_seller_title(client: TestClient) -> None:
    fields = _capture(title='Dracaufeu 4/102 Set de Base français',
                      captured_title='Carte Pokémon Dracaufeu 4/102 Set de Base français')
    response = client.post('/ajouter-annonce/enregistrer', data=fields, follow_redirects=False)
    assert response.status_code == 303
    with connect(client.app.state.settings.database_path) as connection:
        row = connection.execute('SELECT original_title, raw_data FROM catalog_items').fetchone()
        assert row['original_title'] == fields['captured_title']
        observations = json.loads(connection.execute('SELECT observations_json FROM listing_identity_evidence').fetchone()[0])
        assert any(observation['field'] == 'title' and observation['value'] == fields['title']
                   and observation['source'] == 'manual' for observation in observations)
