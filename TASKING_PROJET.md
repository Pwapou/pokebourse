# Pokébourse — Suivi consolidé du développement

Révision du **8 novembre 2026**. Référence inspectée : commit `a904eca` et arbre de travail non committé, comprenant les corrections de capture et la page `/tasking` déjà en cours. Ce document donne l'ordre de reprise de tous les chantiers ; les spécifications détaillées restent dans leurs documents respectifs.

## 1. Règles de lecture et sources de vérité

- **Réalisé et testé** : code présent et contrôles automatisés passants sur le périmètre indiqué. Cela ne vaut pas déploiement, recette visuelle exhaustive ni mesure de précision.
- **Partiel** : socle utilisable présent ; les critères manquants restent ouverts et nommés.
- **À réaliser** : spécification présente, comportement cible absent ou non intégré.
- **Conditionnel** : travail soumis à un diagnostic, une décision produit ou une capacité externe. Ce n'est pas une fonctionnalité promise.
- **Historique** : état daté conservé pour expliquer les choix ; aucun ancien inventaire ou résultat de test ne décrit implicitement l'installation actuelle.

Les cases décrivent des critères précis ; ne pas calculer un pourcentage de livraison à partir du nombre de cases de documents qui se recouvrent. Une case ouverte de recette ne signifie pas que le code correspondant manque. Les IDs sont locaux à chaque plan : `Identification/T02`, `Recherche-cartes/T2` et `Radar/P2` désignent des travaux différents.

Ordre de lecture : **ce suivi → spécification du chantier → plan de validation → preuves datées / tracker**. Les règles d'AGENTS restent obligatoires. Une précision récente du chantier Identification remplace un constat ancien sur ce même périmètre ; elle ne valide pas son implémentation. En cas de divergence code/spécification, consigner l'écart avant de modifier le comportement. [SUIVI](SUIVI.md) conserve les livraisons historiques ; [tracker](tracker.md) suit les défauts et obstacles, pas les fonctionnalités.

## 2. Carte des chantiers et état vérifié

| Chantier / document | État au 8 novembre | Acquis vérifiables | Suite et dépendances |
|---|---|---|---|
| [Design Mosaic × Flowbite](TASKING_INTEGRATION_DESIGN.md) | Réalisé pour le socle ; recette exhaustive ouverte | Layout Jinja et CSS locaux, catalogue (recetté aux 5 largeurs), inventaire des actions T5, fiche, dashboard et écrans secondaires ; `tests/test_web.py`, `tests/test_search.py` | Conserver la charte ; ne pas rejouer une refonte entière. Compléter la recette des autres écrans secondaires aux cinq largeurs |
| [Simplification](TASKING_SIMPLIFICATION_CIBLE.md) | Réalisé pour navigation, catalogue, achats, réglages et gestion ; partiel pour configuration guidée | `app/purchases.py`, `app/gestion.py`, garde-fous extracteurs Chrome T2.4, templates et suites `test_simplification_navigation.py` / `test_simplification_avancee.py` / `test_chrome_extension.py` | Guide de progression présent ; assistant à trois questions/préréglages (T2.2) et raccourci popup (T2.3) absents. Recette responsive des écrans secondaires à compléter |
| [Recherche de cartes](TASKING_RECHERCHE_CARTES.md) | Réalisé et testé sur annonces enregistrées | Recherche locale, file TCGdex, reviews/résolution communes ; suites `test_identification_research.py`, `test_identification_reviews.py`, `test_tcgdex_sync.py` | Réutiliser ce socle pour Identification/T08.2 et T09 ; confirmation avant ajout encore absente |
| [Extraction](PROMPT_PATCH_EXTRACTION.md) | Réalisé et testé pour le périmètre déterministe | Numéros isolés, certificateurs, formats collés ; tests identification, candidate-number et extension | Préserver les garde-fous ; les hypothèses OCR spatiales relèvent d'Identification/T06–T07 |
| [Recherche et tendances](TASKING_RECHERCHE_TENDANCES.md) | Réalisé et testé pour les lots 1–3 ; lot 4 conditionnel | `/search` (tris financiers, diagnostic métadonnées T1.2, clauses SQL communes T1.3), export, externe explicite, `/trends` paginé, profilage `EXPLAIN QUERY PLAN` T1.4/T5.2, recette 5 largeurs + clavier T1.5/T3.4, migration `0020`, suites `test_search.py` / `test_trends.py` | Lot 4 (ventes conclues par pays) conditionnel à une source officielle fournissant transaction, date et pays (T0.2) |
| [Radar](PLAN_RADAR_OPPORTUNITES.md) | Partiel | `app/radar/repository.py`, migration `0019`, observations/événements et décisions persistantes testés ; prix d'achat exclus des preuves de revente | `/radar`, recherches métier groupées, notifications et attribution de gains restent à réaliser ; réutiliser Identification/T09 et T15–T18 pour qualifier les alertes |
| [Identification fiable](TASKING_IDENTIFICATION_FIABLE.md) | Chantier actif, J1/J2/J3 non livrés globalement | T00, T02, T03, T04 et T08.1 acquis ; T05 sauf alias non vérifié ; contrôles T08.3 du moteur actuel acquis | Détail et ordre ci-dessous ; aucune reconnaissance spatiale ni comparaison de marché automatique complète annoncée |
| [Phase 0 ML](docs/ML_PHASE0.md) | Outils réalisés ; campagne humaine inachevée | Snapshots, pilote, double lecture, export ; preuves visuelles explicites T04 et localisations T05 | Labels indépendants, audit représentatif, quasi-doublons et diagnostic de justesse à constituer |
| [Conception ML](MACHINE_LEARNING_DESIGN.md) / [prompt initial](PROMPT_ML_DESIGN.md) | Conception, expériences conditionnelles | Baseline lexicale trigrammes/distance d'édition déjà présente | Pas de ranker, embeddings, FTS5/BM25 ou modèle visuel livré. Prioriser T01/T10 ; ne pas recréer la phase 0 technique |
| [Sync TCGdex](docs/TCGDEX_SYNC.md) | Réalisée et testée | File durable, pause/reprise, détails et locales, migrations `0018` et `0026` | Une locale chargée ne qualifie pas automatiquement identification ou rentabilité dans cette langue |
| Suivi dans l'application | Présent dans l'arbre non committé | `/tasking`, `app/tasking.py`, `tests/test_tasking.py` | Lecture des plans TASKING/PLAN et tableau des incidents ; les PROMPT et documents techniques sont référencés ici, pas comptés directement par la page |

## 3. Identification : état et chemin de reprise

Les contrats et critères détaillés sont dans [Identification](TASKING_IDENTIFICATION_FIABLE.md), les vérifications par lot dans le [plan de validation](docs/identification/PLAN_VALIDATION_LOTS.md). T13 est une matrice transversale, pas une étape placée après T12.

| Lots | État | Preuve / prochaine action |
|---|---|---|
| T00 | Réalisé comme inventaire daté | [Rapport T00/T01](validation/ocr/evaluation/STATUS_T00_T01.md). Catalogue du 3 novembre figé, pas un inventaire de la base opérationnelle au 8 novembre |
| T01 | Partiel | Manifeste, comparateur et rejeu local présents ; annotations indépendantes, doubles lectures, partitions et effectifs de qualification ouverts (TRK-009) |
| T02–T03 | Réalisés et testés sur fixtures | Détection, provenance, abstention et décision communes ; [contrat T03](docs/identification/T03_EVIDENCE.md) |
| T04 | Réalisé et testé | `evidence_store.py`, migration `0023`, tests visuels et sauvegardes ; conservation explicite distincte de l'OCR éphémère |
| T05 | Partiel, socle livré | Alias/localisations/diagnostic et migrations `0024`–`0026` ; cible « gempack 2 » toujours à vérifier, aucune équivalence inventée |
| T06.1–T06.4 / T07 | Partiel | T06.1 : cadrage manuel sur fiche et OCR local, testé sur images synthétiques ; capture, localisation automatique et recette restent ouvertes (TRK-017). [Procédure OCR](docs/identification/T06_T07_PROCEDURE_OCR.md) : TSV, langue, hypothèses et budget global encore à réaliser ; timeout actuel par appel |
| T08.1 | Réalisé et testé | [Contrôles du moteur actuel](docs/identification/T08_CONTROLES_MOTEUR_ACTUEL.md), TRK-001/013/014 ; titre séparé du nom canonique |
| T08.3 | Partiel | Prix/port/devise indépendants de l'identification, indices invalides filtrés, préremplissage non auto-confirmant ; sélection transitoire, résolution motivée et invalidation à intégrer avec T08.2/T09 |
| T08.2 / T09 | À compléter | TRK-004/005/007 : exécution hors popup, choix avant ajout et décision atomique ; contrôle commun d'admissibilité financière à terminer |
| T10 | À réaliser après mesures indépendantes | Précision/couverture/gain avec dénominateurs, groupes et incertitude ; pas de gain OCR déduit des tests de formulaire |
| T11 | Conditionnel | Vision seulement si le diagnostic T10 la justifie ; ne bloque pas J1 ou J3 |
| T12 / T13 | Ouverts pour les jalons complets | Livraisons et recettes limitées aux fonctions réellement intégrées ; aucune migration/déploiement de l'instance réelle par cet audit |
| T14 | À réaliser, champs textuels existants à réutiliser | PSA/PCA : lecture et confirmation séparées de la carte et de l'étiquette ; dépend de T06/T08/T09 |
| T15 | Matrice documentaire réalisée ; accès à requalifier avant activation | [Matrice du 3 novembre](docs/identification/T15_SOURCES_PRIX.md), décisions D1–D6 ouvertes, TRK-008. Pas de nouvelle vérification réseau lors de cet audit |
| T16–T18 | À réaliser | Orchestration durable de marché, comparabilité et estimation expliquée. Contrats/tests simulés possibles ; activation selon T15 et décisions produit |
| T19.1 | À réaliser, capture partielle déjà corrigée | Adapter parcours et images des collecteurs ; réutiliser le contrat Chrome actuel ; TRK-100/101 |
| T19.2–T19.3 | À réaliser après moteur et parcours communs | File OCR collecte, concurrence app/worker, reprise et recette C01–C06 ; [spécification T19](docs/identification/T19_COLLECTE_OCR.md) |

Ordre opérationnel, sans confondre dépendance de développement et qualification finale :

1. **Préserver les acquis et compléter les preuves T01.** Préparer la photo originale et l'annotation indépendante du cas Tortant ; TRK-002 reste ouvert sur l'origine exacte de `n`, malgré les corrections déterministes déjà testées. T04 est utilisable sans attendre la fin de toutes les annotations T01.
2. **Construire T06/T07 et intégrer T08.2/T09.** Les contrôles existants T08.3 restent le socle. Découpage technique selon la procédure OCR, puis trajet photo → candidats → choix → ajout atomique → fiche. Le diagnostic « catalogue incomplet » exige une preuve de couverture.
3. **Adapter T19.** T19.1 et la correction monétaire TRK-101 peuvent avancer sur fixtures ; l'activation OCR de collecte attend le moteur et les décisions communs. Aucun nouveau mode d'accès marketplace n'est établi par ce plan.
4. **Recetter et livrer J1 via T12/T13**, sur le périmètre de capture et collecte effectivement démontré. T01 reste partiel si les volumes manquent ; publier la réserve sans déclarer J2 acquis. J1 n'attend ni T11 ni un modèle appris, mais exige les mesures ciblées prévues pour T06/T07.
5. **Qualifier J2 via T10**, puis décider T11. Aucune nouvelle acceptation automatique OCR/vision avant les critères de T10.
6. **Préparer J3 sans attendre T11.** Actualiser T15 et trancher D1–D6 ; intégrer T14 → T16 → T17 → T18, puis T12/T13 J3. Contrats et simulations peuvent être préparés avant l'accès réel ; la disponibilité finale ne peut pas être simulée.

Les anciens « jobs 1/2/3 » dans les rapports désignent des périmètres de travaux antérieurs, pas des processus actuellement lancés : job 1 = contrôles moteur actuel, job 2 = moteur OCR cible, job 3 = intégration capture/collecteurs. Vérifier la présence des modules avant de les raccorder ; au présent audit les modules spatiaux restent absents.

## 4. File d'actions restante

Ces actions récapitulent les plans détaillés ; elles ne créent pas une seconde implémentation des mêmes fonctions.

- [x] AUD-01 — Comparer tous les plans racine, guides techniques, migrations et tests ; réconcilier les constats obsolètes et les statuts datés.
- [x] AUD-02 — Revalider la suite Docker sur l'arbre partagé et contrôler liens, IDs, inventaire des migrations et cohérence des documents.
- [ ] ID-01 — Annoter les fixtures photographiques et tracer le cas Tortant ; T01 / TRK-002 et TRK-009, responsable : annotation humaine et développement OCR.
- [ ] ID-02 — Livrer moteur T06/T07 avec raccordement T08.2/T09 et contrôles T08.3 restants ; responsable : développement identification.
- [ ] COL-01 — Livrer T19 et corriger TRK-101 ; responsable : développement collecteurs, après socle OCR pour T19.2/3.
- [ ] REL-01 — Recetter et documenter J1, puis qualifier J2 ; responsable : développement/recette et lecteurs indépendants.
- [ ] MKT-01 — Actualiser T15 et résoudre D1–D6, puis intégrer/recetter J3 ; responsable : cadrage sources et produit, puis développement marché.
- [ ] UX-01 — Compléter les critères de simplification restants : assistant à trois questions (T2.2), raccourci popup (T2.3) et recette aux cinq largeurs des écrans secondaires hors `/catalog`, `/search` et `/trends` (déjà vérifiés) ; responsable : développement UI/recette. Conserver les fonctions déjà livrées.
- [ ] RAD-01 — Livrer Radar/P2–P3 sur le socle P1 existant ; ne pas recréer les tables `0019` ni dupliquer les veilles.
- [ ] RAD-02 — Qualifier les correspondances/historiques P4 puis notifications P5 ; réutiliser T09/T15–T18 avant les alertes financières prioritaires.
- [ ] BUY-01 — Compléter Radar/P6 : frais/date de revente, transitions historisées, estimation figée, attribution et double soumission ; le prix brut de vente et les montants exacts existent déjà.
- [ ] ML-01 — Achever les données de phase 0, mesurer la baseline puis décider des expériences ML ; aucune dépendance de modèle à ajouter sans diagnostic.

Le radar n'est pas un prérequis du parcours capture/identification. Sa page et les recherches groupées peuvent avancer indépendamment ; ses alertes financières attendent la qualification des preuves de prix. Le classement des ventes par pays reste une extension conditionnelle de Recherche/Tendances, en réutilisant T15/T17 si une source adaptée est établie.

## 5. Décisions et limites toujours ouvertes

Le registre produit reste [Identification §1.2](TASKING_IDENTIFICATION_FIABLE.md#12-choix-encore-ouverts--ne-pas-les-transformer-en-décisions-implicites) et [T15 §4](docs/identification/T15_SOURCES_PRIX.md#4-décisions-produit-nécessaires-avant-dactiver-un-comportement-dépendant) : géographie/devises, repli si prix insuffisants, canal de revente, comparabilité, budget éventuel et accès officiel. Aucune réponse n'est déduite de cette remise à jour documentaire.

Le code eBay actuel est un connecteur HTML ; il ne prouve pas un accès Browse API ni aux ventes conclues. Les fichiers Cardmarket sont des cotes agrégées, pas des transactions ni des prix PSA/PCA. Les compteurs locaux et constats d'accès du 3 novembre restent historiques. Cet audit ne consulte ni secrets, ni base opérationnelle, ni services externes.

## 6. Vérification de cette remise à jour

- `docker compose run --rm app pytest -ra` : **867 passants, 0 échec, 0 sauté**, 38,35 s ; un avertissement existant de dépréciation Starlette/TestClient/httpx. Tests de migrations, navigateur/extension, performance/responsive et suivi inclus. Ce résultat qualifie les tests existants, pas les futurs lots.
- Inventaire source : **26 migrations** `0001`–`0026`, dernière `0026_tcgdex_sync_locale.sql` ; **58 fichiers** `tests/test_*.py`. Le numéro suivant devra être revérifié avant tout changement de schéma.
- Contrôles documentaires : **220 liens locaux/ancres sur 29 documents**, correspondance des 30 IDs de lots/sous-lots Identification avec le plan de validation, et `git diff --check`. Détail reproductible dans [SUIVI §28](SUIVI.md#28-remise-à-jour-transversale-du-tasking--8-novembre-2026).
- Lecture de `tasking_data()` dans Docker : **7 plans chargés**, dont ce suivi consolidé (12 actions), **18 incidents uniques**, sans ouverture de base.
- Aucune modification du code applicatif, des dépendances, migrations ou données par cette remise à jour. Les changements applicatifs préexistants sont conservés ; ils restent non committés.

## 7. Tenue du suivi à chaque livraison

1. Mettre à jour le plan du chantier et ce tableau dans la même livraison : état, preuve datée, périmètre, limites et prochaine action.
2. Ajouter le bilan daté à SUIVI ; garder les anciens résultats historiques. Mettre à jour le même ID du tracker pour une correction, avec reproduction et revalidation.
3. Cocher seulement les critères démontrés ; distinguer automatisé, recette navigateur, moteur OCR réel, mesure statistique et accès externe. Une simulation ne valide pas un accès réel.
4. Vérifier les migrations réellement présentes et les documents d'exploitation affectés. Ne pas recopier un ancien numéro proposé dans un prompt.
5. La page `/tasking` relit les Markdown ; actualiser aussi son tableau d'incidents en tête de `tracker.md`. Ne pas laisser un incident « validé » uniquement dans une annexe invisible dans cette synthèse.
