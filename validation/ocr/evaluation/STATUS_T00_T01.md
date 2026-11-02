# Qualification T00 / T01 — état constaté

Date du contrôle : 3 novembre 2026. Périmètre : inventaire du point de départ et premier outillage d’évaluation de `TASKING_IDENTIFICATION_FIABLE.md`.

## Verdict

| Lot | Statut | Portée du verdict |
|---|---|---|
| **T00 — Inventaire et point de départ** | **Terminé comme inventaire, avec réserves** | Les artefacts, versions, lacunes et échecs courants sont consignés. Le code courant n’est pas validé et l’état antérieur aux changements déjà présents ne peut pas être reconstitué. |
| **T01 — Vérité terrain et benchmark hors ligne** | **Non terminé** | Le comparateur, le manifeste, le squelette de labels et le rapport initial sont livrés. La vérité terrain humaine, le rejeu local figé et le rapport de justesse restent absents. |
| **T10 — Qualification indépendante** | **Non démontrée** | Aucun test indépendant, intervalle ou seuil de promotion n’est établi par ce travail. |

## T00 — Inventaire réalisé

### Version et changements

- Commit de référence : `b7b1a2070c10ea4e06d05f8b4469a76b129548ed`.
- Arbre de travail non propre : 56 fichiers suivis modifiés et 99 fichiers non suivis non ignorés au contrôle.
- Aucune restauration Git ni écrasement des changements existants.
- L’état « avant travaux » antérieur à ces changements n’est pas observable sans restauration interdite : les tests ci-dessous qualifient l’état courant, pas un état initial vierge.

### Environnement et persistance

- Python 3.12.16 ; Tesseract 5.5.0 ; langues OCR `eng`, `fra`, `osd`.
- 22 migrations présentes dans la source au contrôle, dont `0022_identification_observations.sql`.
- La sauvegarde figée utilisée pour l’inventaire contient 21 migrations appliquées, jusqu’à `0021_purchase_sale_price.sql`. Cette différence source/sauvegarde est explicitement conservée.
- Sauvegarde cohérente créée par le mécanisme SQLite en ligne : `/data/backups/pokebourse-20261102-230603-171195.sqlite` dans le volume Docker.
- Empreinte SHA-256 de la sauvegarde : `f0b4c17828451be37a2a03cdb3d87c269bf3c5673cfcd30d35d15cd670bfe015`.
- Aucune restauration, suppression de volume ou modification de la base opérationnelle.

### Entrées et politique d’exécution

| Entrée | État inventorié |
|---|---|
| Saisie par URL et pré-analyse | Présente ; tests existants, avec un échec OCR courant consigné ci-dessous. |
| Extension Chrome et prévisualisation | Présentes ; parcours et contrats JSONL existants. |
| Import JSONL et collecte | Présents ; ingestion et réidentification couvertes par la suite courante. |
| Fiche, correction et réidentification | Présents ; un échec de rattachement et un échec de retrait de confirmation sont consignés. |
| Worker et veilles | Présents ; aucun worker lancé par l’évaluateur ou le diagnostic de catalogue. |
| Rapports OCR enregistrés | Présents ; le comparateur les relit sans lancer OCR, matcher ou réseau. |

Compose autorise la récupération de pages pour les hôtes Vinted configurés. Les outils T00/T01 livrés ici n’effectuent aucune acquisition : ils relisent des artefacts et une sauvegarde. Les tests ciblés utilisent des fixtures locales.

### Catalogue figé

Le diagnostic `catalogue-inventory.json` établit :

- 202 extensions et 22 201 cartes ;
- 18 345 cartes avec URL d’image et 3 856 sans URL ;
- 22 201 lignes enregistrées avec la locale de référence `fr`, ce qui ne prouve pas la langue des exemplaires vendus ;
- 21 migrations appliquées dans la sauvegarde ;
- journal SQLite `delete` après sauvegarde cohérente ;
- aucune anomalie de référence orpheline ou de numéro manquant rapportée par l’outil ; 428 numéros partagés entre extensions sont informatifs, pas des doublons erronés automatiques.

Une URL d’image ne prouve ni téléchargement, ni disponibilité, ni exactitude visuelle. Une absence dans cette sauvegarde n’est pas une absence mondiale chez TCGdex.

### Tests de l’état courant

Commande :

```bash
docker compose run --rm app pytest
```

Résultat : **707 réussites, 21 échecs, 1 avertissement** en 29,77 s.

| Suite | Échecs | Thèmes constatés |
|---|---:|---|
| `tests/test_catalog.py` | 1 | Rattachement après enrichissement du référentiel. |
| `tests/test_identification_reliability.py` | 12 | Choix parmi plusieurs, langues et motifs d’abstention. |
| `tests/test_identification_reviews.py` | 1 | Confirmation attendue absente avant retrait. |
| `tests/test_lexical_identification.py` | 4 | Candidats contradictoires et diagnostic lexical. |
| `tests/test_manual_listing.py` | 1 | Prise en compte d’indices OCR dans la saisie. |
| `tests/test_migrations.py` | 1 | Attendu de migration à aligner avec `0022`. |
| `tests/test_pipeline_integration.py` | 1 | Motif de contradiction de langues. |

Ces échecs sont consignés comme état courant et ne sont pas attribués à un agent sans preuve. Ils n’ont pas été corrigés dans le périmètre de cet outillage.

Les vérifications dédiées au comparateur et au diagnostic sont vertes :

```text
docker compose run --rm app pytest tests/test_identification_benchmark.py tests/test_reference_coverage_report.py tests/test_validation_history.py
43 passed, 1 warning in 0.64s
```

## T01 — Artefacts livrés et manquants

### Artefacts disponibles

| Artefact | Contenu |
|---|---|
| `manifest.json` | Empreintes du jeu, du rapport, des 15 photos, du catalogue et des labels ; versions et partitions ; limites. |
| `labels.json` | 30 URL stables, toutes `unannotated`, sans identité préremplie. |
| `evaluation-initiale.json` | 30 annonces, 0 annotée, 30 non annotées ; métriques de justesse `null`. |
| `catalogue-inventory.json` | Inventaire en lecture seule de la sauvegarde figée. |
| `scripts/evaluate_identification.py` | Mesures et comparaisons appariées sur rapports enregistrés. |
| `labels.example.json` | Exemples exclusivement synthétiques. |

Le contrôle automatique du manifeste a vérifié 20 empreintes, l’égalité exacte des 30 URL entre rapport et labels, et l’absence de tout ID attendu.

### Données des 30 annonces

- 30 titres et 30 URL distinctes ; 15 annonces Vinted et 15 eBay.
- Aucune description enregistrée : les descriptions restent manquantes et ne sont pas inventées.
- 15 photos Vinted conservées avec empreintes SHA-256.
- 15 photos eBay absentes : `ocr_only` est indisponible pour ces annonces, ce qui n’est ni une abstention ni une erreur OCR.
- Les trois variantes sont présentes dans le rapport historique : 30 `title_only`, 15 `ocr_only`, 30 `combined`.
- Le rapport historique ne porte pas d’origine de décision ni de version de pipeline/normalisation. Les comparaisons devront conserver cette limite.

### Travail restant avant de déclarer T01 terminé

1. **Annotations humaines indépendantes** : renseigner type de produit, déterminabilité, identité vérifiée éventuelle, présence dans le catalogue figé et statut. Rechercher au-delà des candidats automatiques.
2. **Double lecture et arbitrage** : conserver les lectures initiales et arbitrer les désaccords selon le protocole ; ne pas transformer une suggestion en vérité.
3. **Complétude des preuves** : conserver titre et description lorsqu’ils sont disponibles et documenter les photos manquantes. Ne pas reconstituer les absences par invention.
4. **Rejeu strictement local** : figer le code et la configuration du pipeline, refuser tout artefact manquant et ne lancer aucun téléchargement implicite. Le script historique `run_30_liens.py` n’est pas ce rejeu hermétique.
5. **Rapport initial de justesse** : relancer l’évaluateur avec les labels renseignés et publier effectifs, dénominateurs, exclusions et limites.
6. **Volumes ultérieurs** : les 300 cas diagnostiques, les doubles lectures, l’environ 1 000 cas et l’audit aléatoire distinct ne sont pas acquis.
7. **Partitions** : résoudre republications, quasi-doublons et images identiques avant tout test indépendant. Les 30 cas sont un jeu de développement/régression, pas le test T10.

Après annotation, produire un nouveau fichier sans écraser le rapport initial :

```bash
docker compose run --rm app python -m scripts.evaluate_identification \
  --report validation/ocr/marketplaces/runs/2026-11-02-30-liens/resultats.json \
  --labels validation/ocr/evaluation/labels.json \
  --output validation/ocr/evaluation/evaluation-annotee.json
```

Tant que `labels.json` contient zéro annotation renseignée, aucune précision, couverture correcte, matrice de lots ou conclusion d’amélioration n’est disponible.
