"""Analyse d'une annonce non enregistrée, en lecture seule."""
from pathlib import Path

from app.listing_preview import preview_listing
from app.storage.database import connect
from app.storage.migration_runner import apply_migrations
from app.tcgdex.cache import TcgdexCache


def test_preview_uses_description_and_does_not_write(tmp_path: Path) -> None:
    with connect(tmp_path / 'preview.db') as conn:
        apply_migrations(conn)
        TcgdexCache(conn).seed_initial_if_empty()
        conn.commit()
        before = conn.total_changes
        result = preview_listing(conn, {'title': 'Carte Pokémon', 'description': 'Dracaufeu 4/102 Set de Base français', 'price_cents': 14500, 'currency': 'EUR'})
        assert result['identification']['status'] == 'identified'
        assert result['identification']['matched_card']['tcgdex_id'] == 'base1-4'
        assert result['evaluation'] is not None
        assert conn.total_changes == before
        assert conn.execute('SELECT count(*) FROM catalog_items').fetchone()[0] == 0


def test_preview_never_values_a_lot_or_ambiguous_card(tmp_path: Path) -> None:
    with connect(tmp_path / 'preview.db') as conn:
        apply_migrations(conn)
        TcgdexCache(conn).seed_initial_if_empty()
        lot = preview_listing(conn, {'title': 'Lot de 50 cartes Pikachu', 'price_cents': 2000, 'currency': 'EUR', 'language': 'fr'})
        assert lot['identification']['status'] == 'lot'
        assert lot['identification']['matched_card'] is None
        assert lot['evaluation'] is None
        ambiguous = preview_listing(conn, {'title': 'Pikachu français', 'price_cents': 500, 'currency': 'EUR'})
        assert ambiguous['identification']['status'] == 'ambiguous'
        assert ambiguous['evaluation'] is None


def test_corrected_number_conflict_never_produces_a_cote(tmp_path: Path) -> None:
    with connect(tmp_path / 'preview.db') as conn:
        apply_migrations(conn)
        TcgdexCache(conn).seed_initial_if_empty()
        result = preview_listing(conn, {
            'title': 'Dracaufeu 4/102 Set de Base français',
            'card_number': '15/102', 'price_cents': 1000, 'currency': 'EUR',
        })
        assert result['identification']['status'] == 'ambiguous'
        assert result['identification']['matched_card'] is None
        assert result['evaluation'] is None


def test_explicit_title_number_is_preserved_and_conflicting_ocr_blocks_acceptance(tmp_path: Path) -> None:
    with connect(tmp_path / 'preview.db') as conn:
        apply_migrations(conn)
        TcgdexCache(conn).seed_initial_if_empty()
        result = preview_listing(conn, {
            'title': 'Pikachu 58/102 Set de Base Pokémon Français Vintage 1999',
            'ocr_names': ['Pikachu'], 'ocr_numbers': ['15'],
        })
        identity = result['identification']
        assert identity['status'] == 'ambiguous'
        assert identity['matched_card'] is None
        assert identity['features']['card_number'] == '58/102'
        assert identity['reason_code'] == 'contradiction'
        assert 'number' in identity['evidence_conflicts']
        assert result['evaluation'] is None


def test_ocr_only_completes_missing_text_evidence(tmp_path: Path) -> None:
    with connect(tmp_path / 'preview.db') as conn:
        apply_migrations(conn)
        TcgdexCache(conn).seed_initial_if_empty()
        result = preview_listing(conn, {
            'title': 'Carte photographiée',
            'ocr_names': ['Pikachu'], 'ocr_numbers': ['58/102'],
        })
        identity = result['identification']
        assert identity['status'] == 'ambiguous'
        assert identity['matched_card'] is None
        assert identity['candidates'][0]['tcgdex_id'] == 'base1-58'
        assert identity['reason_code'] == 'indicative_evidence'
