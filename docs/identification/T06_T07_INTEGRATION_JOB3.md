# Intégration consolidée — composants OCR T06/T07

Date : **8 novembre 2026**. La branche `codex/integration-ocr-consolidation-20261108` réunit le pipeline spatial de `codex/ocr-parallele` (`4d0746d`) et le superviseur de processus de `codex/ocr-p2` (`862a0d7`). Les deux suites d’origine ont été rejouées avant sélection : **59** et **77 tests** respectivement.

## Base retenue et compléments

| Module | Origine | Fonction intégrée |
|---|---|---|
| `ocr_types.py` | `ocr-parallele`, échéance commune adaptée | Types immuables, configuration, budgets et transport borné |
| `ocr_geometry.py` | `ocr-parallele` | EXIF, cadrage manuel, homographie, reprojection et localisation OpenCV optionnelle avec repli explicite |
| `ocr_text.py` | `ocr-parallele` + adaptateur `ocr-p2` | Parsing TSV/lignes ; l’ancien appel `run_tesseract_tsv` délègue au runner renforcé |
| `ocr_numbers.py` | `ocr-parallele` | Fenêtres spatiales, hypothèses groupées, union et classement des candidats |
| `ocr_language.py` | `ocr-parallele` | Indices de langue, abstention et conflits ; remplace le doublon `ocr_languages.py` de p2 |
| `ocr_runner.py` | `ocr-p2`, adapté au `Deadline` commun | Groupe de processus, annulation, sortie bornée et sémaphore local |
| `ocr_spatial.py` | `ocr-parallele` | Orchestration manuelle/automatique, résultats partiels et enveloppe `ocr_evidence` |
| `matcher.py` | socle + `ocr-parallele` | `retrieve_candidates()` public, sans écriture, avec les corrections T08 du socle préservées |

Les implémentations géométrie/TSV/nombres/langue/orchestration de p2 ne sont pas superposées à celles retenues : leurs contrats sont incompatibles et leurs tests spatiaux sont déjà couverts par la variante retenue. Les tests p2 de processus, annulation, saturation et sémaphore sont conservés dans `tests/test_ocr_limits.py`.

## Raccordements toujours à réaliser

1. **Parcours HTTP/T03/T08.2** : transporter et revalider `ocr_evidence` et les hypothèses de langue, sans aplatir les alternatives ni créer de confirmation implicite. L’appel historique `analyze_image(connection, content)` reste la baseline.
2. **Capture complète** : choix de photo et cadrage dans la prévisualisation, orchestration indépendante du popup, choix transitoire et ajout/décision atomiques (TRK-004/005/007/017).
3. **Concurrence agrégée** : composer `OcrSupervisor` avec un verrou partagé app/worker ; la limite actuelle du superviseur reste locale à un processus (TRK-203).
4. **Budget de recherche** : propager l’échéance aux requêtes SQLite avec `set_progress_handler`, retiré en `finally`.
5. **Qualification** : benchmark apparié baseline/manuel/automatique sur photos annotées, métriques de justesse, latence et mémoire (TRK-009). Les tests mockés et l’image synthétique ne prouvent aucun gain OCR.
6. **T19** : file OCR durable et adaptateurs collecteurs, avec `first_seen_at` et décisions humaines préservés (TRK-100).

## Validation de l’intégration

- `docker compose run --rm app pytest tests/test_ocr_geometry.py tests/test_ocr_hypotheses.py tests/test_ocr_languages.py tests/test_ocr_spatial.py tests/test_ocr_limits.py tests/test_ocr_local.py tests/test_ocr_web.py tests/test_ocr_crop_browser.py -ra` : **86 passed**, 1 avertissement connu, zéro skip.
- Deux écarts d’intégration ont été corrigés avant ce résultat : imports des tests spatiaux p2 retirés avec leurs doublons, puis message historique « Sortie OCR excessive » restauré dans l’adaptateur.
- Suites communes capture/extension/prévisualisation/reviews/migrations/sauvegardes/preuves/recherche/tendances/tasking : **359 passed**, zéro skip.
- `docker compose run --rm app pytest -ra` : **936 passed, 1 warning in 45.18s**, zéro échec et zéro skip. Les scénarios Chromium/Playwright et MV3 existants sont inclus ; ils ne constituent pas une mesure de précision OCR.
- Aucun raccordement HTTP/capture/worker nouveau, aucune migration et aucune dépendance ajoutée par cette consolidation. La présence des composants internes ne vaut pas livraison du parcours complet (TRK-204).
