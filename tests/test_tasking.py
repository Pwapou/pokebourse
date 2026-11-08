from app.tasking import tasking_data


def test_tasking_reads_checkboxes_and_tracker_without_claiming_validation(tmp_path):
    (tmp_path / 'TASKING_TEST.md').write_text('# Plan test\n## Étape\n- [x] Réalisé\n- [ ] À vérifier\n', encoding='utf-8')
    (tmp_path / 'tracker.md').write_text('| TRK-001 | P1 | ouvert | T01 | Problème |\n', encoding='utf-8')
    result = tasking_data(tmp_path)
    assert result['done'] == 1 and result['total'] == 2
    assert result['documents'][0]['sections'][0]['items'][1]['text'] == 'À vérifier'
    assert result['incidents'][0]['state'] == 'ouvert'
    assert not result['git']['available']


def test_dependencies_preserve_qualifiers_and_document_scope(tmp_path):
    (tmp_path / 'TASKING_A.md').write_text(
        '# Plan A\n| Lot | Priorité | Dépendances | Résultat |\n|---|---|---|---|\n'
        '| T08 — Capture | P0 | T08.1 : T03/T05 ; T08.2 : T03 à T07 | Résultat |\n'
        '### T08 — Capture\n- [ ] Faire\n', encoding='utf-8')
    (tmp_path / 'TASKING_B.md').write_text(
        '# Plan B\n#### T1.2 — Recherche\n- [ ] Faire\n**Dépendance :** T1.1 et T0.1.\n', encoding='utf-8')
    documents = tasking_data(tmp_path)['documents']
    assert documents[0]['dependencies'][0]['dependency'] == 'T08.1 : T03/T05 ; T08.2 : T03 à T07'
    assert documents[1]['dependencies'][0]['task'] == 'T1.2 — Recherche'
    assert documents[1]['dependencies'][0]['dependency'] == 'T1.1 et T0.1.'


def test_consolidated_dashboard_uses_documented_statuses(tmp_path):
    (tmp_path / 'TASKING_PROJET.md').write_text(
        '# Suivi\n## 2. Chantiers\n| Chantier / document | État | Acquis | Suite |\n'
        '|---|---|---|---|\n| [Radar](PLAN.md) | Partiel | Socle testé | Notifications à réaliser |\n'
        '## 3. Identification\n| Lots | État | Preuve / prochaine action |\n|---|---|---|\n'
        '| T06 / T07 | À réaliser | Mesurer |\n## 4. Actions\n- [ ] Suite\n', encoding='utf-8')
    data = tasking_data(tmp_path)['consolidated']
    assert data['projects'][0] == {'name': 'Radar', 'state': 'Partiel', 'achievements': 'Socle testé', 'next': 'Notifications à réaliser', 'tone': 'partial'}
    assert data['identification'][0]['state'] == 'À réaliser'


def test_status_colors_do_not_treat_partial_work_as_complete():
    from app.tasking import status_tone
    assert status_tone('Réalisé et testé') == 'done'
    assert status_tone('Réalisé pour le socle ; recette exhaustive ouverte') == 'partial'
    assert status_tone('À réaliser') == 'todo'
    assert status_tone('Bloqué') == 'blocked'
    assert status_tone('Conditionnel') == 'conditional'
    assert status_tone('État inconnu') == 'neutral'
