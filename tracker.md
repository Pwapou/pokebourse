# Tracker — identification, OCR et intégrations

Créé le **8 novembre 2026** pour le [tasking Identification fiable](TASKING_IDENTIFICATION_FIABLE.md). Ce registre suit les défauts et obstacles de validation du chantier, sans remplacer sa liste de fonctionnalités. Référence : [plan des skills, intégrations et validations](docs/identification/PLAN_VALIDATION_LOTS.md).

Le registre initial reprend les observations du code, les captures fournies dans le chat et les rapports datés du dépôt. **Aucun échec pytest ni résultat OCR réel n'a été mesuré pendant cette mise à jour documentaire.** Un écart statique, un risque à reproduire et une capacité indisponible restent distingués.

Référence de code lue : **`a904eca`**, avec changements applicatifs et documentaires non committés. Revue transversale du 8 novembre : [TASKING_PROJET.md](TASKING_PROJET.md). Les preuves historiques gardent leur propre date ; les deux incidents documentaires TRK-010/TRK-011 ont été corrigés et contrôlés sur cet arbre de travail.

## Règles de tenue

- Ajouter ou mettre à jour une entrée dès qu'une erreur de test, de fonctionnement, d'OCR, d'intégration, de migration ou d'outillage empêche un contrôle requis ; ne pas attendre la fin du lot. Dédupliquer par symptôme/cause/périmètre, garder les IDs stables.
- États : `ouvert`, `à reproduire`, `en cours`, `corrigé à revalider`, `validé`, `bloqué`. `Accepté comme limite` exige une décision explicite avec date, périmètre et impact produit ; ce n'est pas une correction ni une validation fonctionnelle.
- Priorités : **P0** perte/corruption de données, rattachement ou valorisation erronés automatiques ; **P1** parcours essentiel ou validation du jalon bloqués ; **P2** problème avec contournement utilisable ; **P3** défaut mineur. Réévaluer avec les preuves, sans exagérer un risque non reproduit.
- Pour chaque entrée : lots/étapes W concernés, état/priorité/nature, preuve et environnement/version, reproduction attendue/observée, responsable de la prochaine action, correction ou diagnostic, tests de régression/intégration et résultat de revalidation daté.
- Aucune clôture sur « le code a changé » : reproduire le cas initial, vérifier les intégrations affectées et enregistrer les commandes/résultats. Un test obligatoire sauté/non exécuté reste une validation ouverte. Réouvrir le même ID si le défaut revient, en conservant l'historique.
- Pas de données privées vendeur, secret, image ou texte OCR complet dans ce registre. Les captures temporaires peuvent rester hors dépôt ; conserver ici une synthèse reproductible et les références/versions. Images/annotations durables uniquement selon T04.
- Mettre à jour ce fichier dans la même livraison que la correction et son compte rendu. Un incident bloquant ouvert empêche de déclarer validé le périmètre concerné ; les autres lots peuvent continuer.

## Registre initial

| ID | Priorité | État | Nature / lots | Symptôme ou obstacle |
|---|---|---|---|---|
| TRK-001 | P1 | validé | Défaut observé dans le code — T08.1, W01/W06 | Titre recopié comme nom de carte et conservé par préremplissage |
| TRK-002 | P1 | à reproduire | Anomalie de capture fournie — T07/T08.3, W04–W07 | `n` proposé comme numéro au lieu de `20/82` |
| TRK-003 | P1 | validé | Couplage observé dans le code — T08.3, W02/W05 | Prix/port mal saisi pouvant empêcher la recherche d'identité |
| TRK-004 | P1 | à reproduire | Risque d'intégration — T08.2, W02–W06 | OCR attendu dans le popup avant ouverture de la prévisualisation |
| TRK-005 | P1 | ouvert | Intégration cible manquante — T08.2/T09, W08/W09 | Choix de référence avant ajout et décision persistée à raccorder |
| TRK-006 | P1 | validé (captures) | Contrat observé dans le code — T08.2/T09, W09 | Langue imposée à l'ajout et défaut `fr` à neutraliser pour l'inconnu |
| TRK-007 | P1 | ouvert | Branche cible à intégrer — T03/T08.3/T09, W08 | Résolution motivée d'un titre faux depuis la prévisualisation |
| TRK-008 | P1 | bloqué | Capacité externe non établie selon T15 — T15–T18, W10/W11 | Offres/ventes automatiques et prix gradés non établis par la matrice actuelle |
| TRK-009 | P1 | ouvert | Preuve de qualification manquante — T01/T06/T07/T10 | Gain OCR et justesse finale non démontrés par les rapports disponibles |
| TRK-010 | P1 | validé | Critères documentaires — T02/T08/T12/T13 | Critères resserrés sur le périmètre de chaque lot et jalon |
| TRK-011 | P2 | validé | Outillage documentaire — plan de validation | Couverture corrigée et vérifiée des 26 tâches/sous-tâches |
| TRK-012 | P2 | validé | Régression T08.3/W09 | Priorité du doublon en saisie URL après initialisation du catalogue |
| TRK-013 | P1 | validé | Intégration MV3 T08.1/W01 | Nom vide rejeté par le service worker après séparation du titre |
| TRK-014 | P1 | validé | MV3 T08.1 | Capture sans extension ou nom rejetée malgré un titre brut |
| TRK-015 | P2 | validé | Finances T08.3 | Devise absente sans erreur par champ |
| TRK-016 | P2 | validé | URL T08.3 | Diagnostics financiers et titre original perdus lors de l’ajout URL |
| TRK-017 | P1 | ouvert | Intégration et recette manquantes — T06.1/T08.2 | Cadrage disponible sur fiche seulement ; sélection des photos de capture et validation photographique restent à réaliser |
| TRK-100 | P1 | ouvert | Intégration cible manquante — T19, C01–C06 | Collecteurs/veilles à raccorder aux images et à l'OCR commun |
| TRK-101 | P2 | résolu | Conversion exacte livrée — T19.1 | Filtres Vinted/eBay convertis depuis les centimes sans flottant ; 840 tests passants |
| TRK-102 | P2 | validé | Recette responsive & actions UI — Recherche T1.5/T3.4, Design T2/T5/T6 | Débordements à 320/390 px, 6e colonne ROI à 1024 px sur `/trends` et 3 formulaires GET sans `action` explicite corrigés ; 867 tests passants |
| TRK-200 | P2 | ouvert | Outillage / données de test | Un clone neuf doit retrouver ou documenter les fixtures locales ignorées requises par certaines suites |
| TRK-201 | P3 | validé | Outillage T06.3 | `pgrep` absent ; contrôle des processus orphelins réalisé via `/proc` dans les tests du runner |
| TRK-203 | P1 | ouvert | Concurrence T06.3/T19.2 | Le sémaphore intégré borne un processus ; la limite agrégée app/worker reste à réaliser |
| TRK-204 | P1 | ouvert | Intégration T06/T07/T08.2 | Composants spatiaux internes consolidés ; parcours HTTP/capture, confirmation et recette photographique non livrés |

### TRK-017 — Recadrage à intégrer à la capture et à qualifier

- **Preuve, 8 novembre :** la fiche unitaire propose le cadrage d'un téléversement ; `capture_preview.html` et le transport extension ne proposent pas encore ce choix. La comparaison baseline/manuel/automatique et la recette sur photos annotées ne sont pas réalisées.
- **Reproduction :** ouvrir une prévisualisation de capture contenant plusieurs photos et chercher à choisir puis recadrer l'image avant OCR : le contrôle n'y est pas présent.
- **Prochaine action / responsable :** développement T06.1/T08.2, raccorder le contrôle au parcours capture, conserver la référence de l'image/région analysée, puis tester changements en vol, EXIF, coordonnées et comparaison sur mêmes images annotées. Vérifier latence et mémoire ; ne pas compter le test synthétique comme qualification OCR.
- **Revalidation :** tests Docker OCR et Chromium fiche passants ; intégration capture et qualification non exécutées. Lot non validé.

### TRK-001 — Titre et nom de carte confondus

- **Preuve :** [content.js](extension/content/content.js), extracteurs `name: title` ; [listing_preview.py](app/listing_preview.py), `prefill_identity_fields()` limité aux champs vides ; capture Tortank du chat. Constat statique du 8 novembre, pas de test exécuté ici.
- **Reproduction :** fixture du titre « carte Pokémon ancienne Tortant obscur », catalogue local annoté compatible et photo `20/82` ; observer le nom proposé après analyse puis réanalyse.
- **Attendu :** titre conservé séparément, nom canonique proposé, correction humaine préservée.
- **Prochaine action / responsable :** implémentation T08.1 ; régression dans `test_chrome_extension.py`, `test_capture_preview.py`, `test_listing_preview.py`, puis intégration navigateur.
- **Clôture (8 novembre, périmètre moteur actuel) :** `test_capture_workflow.py` vérifie ancien client, absence de candidat, faute vendeur, correction humaine, réanalyse et ajout restant ambigu avec titre original/nom proposé distincts. Extension Chromium réelle : stockage sans nom canonique inventé, titre brut intact. 188 tests ciblés puis 829 tests complets passants, zéro skip ; recette visuelle desktop/mobile. État `validé` pour T08.1 ; recette photographique Tortant complète toujours T06/T07/T08.2/TRK-002/TRK-009.

### TRK-002 — Fragment `n` proposé comme numéro

- **Preuve :** capture fournie le 8 novembre : numéro proposé `n`, photo lisible `20/82`. Cause et chemin exact d'extraction inconnus ; ne pas l'attribuer à Tesseract sans reproduction.
- **Reproduction :** préparer fixture autorisée/annotée et payload capturé ; suivre champ brut, lectures OCR, observations, candidat et préremplissage. Distinguer screenshot et photo originale.
- **Attendu :** bruit non utilisé comme filtre exact/numéro exploitable ; lecture `20/82` conservée lorsqu'établie, numéros alphanumériques légitimes préservés.
- **Prochaine action / responsable :** diagnostic T07/T08.3, puis test minimal de la cause et trajet OCR → formulaire.
- **Clôture :** reproduction et cause documentées, régression et cas négatifs passants. Correction/revalidation initiales : non réalisées à l’ouverture ; mise à jour ci-dessous.

### TRK-003 — Validation financière avant identification

- **Preuve :** [capture_preview.py](app/capture_preview.py), `_analyse()` appelle `_parse_money()` avant `preview_listing()` ; une exception peut empêcher l'identification. Constat statique du 8 novembre.
- **Reproduction :** fixture avec identité exploitable et prix ou port mal formé ; soumettre initialisation/réanalyse, observer diagnostic financier et candidats.
- **Attendu :** OCR/recherche disponibles, erreur financière par champ, aucune conversion en zéro ; correction financière sans nouvel OCR ni perte de choix.
- **Prochaine action / responsable :** T08.3 ; régressions serveur sans JavaScript dans `test_capture_preview.py`/`test_listing_preview.py` et intégration T08.2.
- **Clôture (8 novembre) :** `test_financial_error_keeps_identity_and_ocr_without_reexecution` (prix/port/devise) et Chromium avec prix invalide puis correction ; aucun nouvel OCR ni zéro implicite. Candidats et provenance conservés ; confirmation invalide ne crée pas d’annonce. Analyse commune aux formulaires capture et saisie URL. 188 ciblés et 829 complets passants, zéro skip ; état `validé` pour les chemins existants.

### TRK-004 — Continuité lorsque le popup ferme

- **Preuve :** [popup.js](extension/popup/popup.js), `runAutomaticPreview()` attend `automaticOcr()` avant `openPreviewTab()`. Ordre observé ; perte/interruption de traitement à reproduire dans un vrai Chromium avec extension.
- **Reproduction :** OCR local retardé de façon déterministe, fermer le popup, vérifier ouverture/progression, capture, résultat et reprise. Aucun délai ni réseau externe réel.
- **Attendu :** orchestration et résultat indépendants du maintien du popup ouvert ; correction/capture récupérables et aucun résultat périmé appliqué.
- **Prochaine action / responsable :** T08.2 ; compléter `test_extension_e2e.py` et le harnais W01–W09 avec interruption/reprise.
- **Clôture :** incident reproduit ou risque couvert par un test démontrant le comportement effectif ; noter explicitement le verdict. Correction : non réalisée ; revalidation : non exécutée.

### TRK-005 — Conserver une sélection avant l'ID persistant

- **Preuve :** [capture_preview.py](app/capture_preview.py), `confirm_capture()` importe les champs sans contrat complet du futur choix ; [reviews.py](app/identification/reviews.py), `save_review()` nécessite `item_id`. Écart d'intégration cible, pas confirmation d'une sélection déjà existante perdue en production.
- **Reproduction :** après ajout du choix en prévisualisation, choisir un candidat, confirmer puis enregistrer ; tester doublon, concurrence et erreur transactionnelle.
- **Attendu :** sélection transitoire revalidée et annonce/décision appliquées atomiquement ; aucune annonce provisoire requise ni état partiellement confirmé.
- **Prochaine action / responsable :** T08.2/T09 ; harnais W01–W09 et `test_identification_reviews.py`, `test_imports.py`, `test_capture_preview.py`.
- **Clôture :** même identité/décision sur fiche après ajout, rollback complet et décision humaine existante protégée. Intégration : à réaliser ; revalidation : non exécutée.

### TRK-006 — Langue inconnue non représentée dans le parcours

- **Preuve :** [capture_preview.py](app/capture_preview.py), choix requis dans `confirm_capture()` ; [catalog.py](app/catalog.py), `CatalogItem.language` possède le défaut `fr` ; formulaire avec sélection requise. Constat statique du 8 novembre.
- **Reproduction :** annonce aux informations financières valides, identité/langue non déterminées ; tenter conservation sans inventer d'attribut.
- **Attendu :** inconnus explicites de bout en bout, pas de langue française appliquée par défaut, limites de comparaison affichées.
- **Prochaine action / responsable :** T08.2/T09, contrat de stockage/JSONL/observations/export commun ; migration additive seulement si nécessaire, avec tests migrations et anciens imports.
- **Clôture (8 novembre, captures) :** `und` explicite à l’ajout et dans les nouveaux exports extension ; détecteur ne le transforme pas en preuve française, libellé Inconnue sur formulaire/fiche/catalogue. Régression stockage/observations/CSV et défaut historique `fr` pour anciens JSONL sans langue ; Chromium enregistre `und` sans décision humaine. 188 ciblés et 829 complets passants, zéro skip. Aucune migration : schéma réel vérifié jusqu’à `0026`, colonne TEXT existante compatible. La confirmation des autres attributs inconnus reste T08.2/T09.

### TRK-007 — Sortir d'un conflit titre/photo par décision explicite

- **Preuve :** décision commune dans [decision.py](app/identification/decision.py), conflits exposés et candidats déplacés au diagnostic ; workflow cible §4.3 demande une résolution motivée dès la prévisualisation. L'existence des reviews après ajout ne valide pas ce nouveau raccordement.
- **Reproduction :** titre désignant une autre carte, photo de la référence attendue ; ouvrir diagnostic, sélectionner, qualifier l'observation vendeur erronée, confirmer et ajouter.
- **Attendu :** titre et désaccord conservés, résolution humaine auditée, attributs non prouvés inconnus ; aucune levée automatique du conflit ni rattachement unitaire d'un lot actif.
- **Prochaine action / responsable :** T03/T08.3/T09 ; tests preuve/confirmation serveur, cas négatif sans motif et trajet navigateur.
- **Clôture :** décision applicable après réingestion, aucune auto-confirmation sur simple saisie/ajout. Intégration : à réaliser ; revalidation : non exécutée.

### TRK-008 — Capacités d'offres/ventes et prix gradés non établies

- **Preuve :** [matrice T15](docs/identification/T15_SOURCES_PRIX.md), état daté du 3 novembre ; aucune nouvelle vérification réseau réalisée ici. Guide Cardmarket agrégé non gradé distinct d'offres/ventes ; accès qualifié aux autres capacités non établi par ce rapport.
- **Impact :** J3 complet ne peut pas être déclaré disponible sur la seule réussite de l'identification. Cela ne bloque pas les corrections OCR/formulaire ni les intégrations simulées.
- **Prochaine action / responsable :** T15 puis T16–T18 ; actualiser accès/capacités et choix §1.2 avec preuves datées, sans coût engagé ni activation implicite. En attendant, disponibilité et imports/cotes locales selon leurs limites restent explicites.
- **Tests :** futurs `test_market_source_capabilities.py`/`test_market_research_workflow.py` et suites Cardmarket ; absence de source simulée sans fausse liste vide ni vente inventée.
- **Clôture :** capacité effectivement établie pour le périmètre demandé, ou réduction/limite explicitement décidée ; une simulation ne prouve pas un accès réel. Résolution : non établie.

### TRK-009 — Justesse OCR et identification à qualifier

- **Preuve :** [STATUS_T00_T01.md](validation/ocr/evaluation/STATUS_T00_T01.md) distingue rejeu reproductible et justesse non démontrée ; le tasking conserve T01/T10 ouverts sur annotations/qualification. Ce constat ne prétend pas compter de nouvelles annotations au 8 novembre.
- **Impact :** impossible de conclure à un gain OCR ou de promouvoir l'acceptation automatique à partir de tests mockés, de statuts ou d'une démonstration unique.
- **Prochaine action / responsable :** T01/T04/T06/T07/T10 ; actualiser les annotations disponibles, compléter le jeu photographique autorisé et figer labels/catalogue/partitions avant mesures appariées.
- **Tests et mesures :** tests de harnais séparés des campagnes Tesseract réelles et du test indépendant ; métriques par champ, rappel, fausses complétions, abstention, précision/couverture et ressources selon T10.
- **Clôture :** rapport daté avec effectifs, exclusions, incertitude et verdict limité au périmètre mesuré ; aucun gain ou volume inventé. Qualification : non démontrée par cette mise à jour.

### TRK-010 — Périmètre des critères de validation

- **Preuve / date :** revue documentaire du 8 novembre ; T02 exigeait la matrice T13 entière, T08 toutes ses lignes alors que T16 dépend de T08/T09. Les nouvelles lignes marché ne peuvent pas conditionner la clôture du seul correctif de capture.
- **Attendu :** T02 limité aux cas déterministes concernés, T08 et J1 à W01–W09 et contrat de sortie simulé ; W10/W11 et sources validés en J3.
- **Correction :** critères T02/T08/T12 et règle générale de périmètre précisés ; aucune modification de code.
- **Responsable / clôture :** maintien du tasking. Revalidation documentaire du 8 novembre : lecture des critères T02/T08/T12 (W01–W09 et contrat simulé pour J1, W10/W11 en J3), `git diff --check` sans erreur et contrôles statiques des liens/ancres réussis. État `validé` pour ce défaut documentaire ; aucune recette applicative déclarée.

### TRK-011 — Couverture des sous-tâches T06 dans le plan

- **Preuve / date :** le 8 novembre, le script préparant les liens s'est arrêté sur `Unexpected task headings` : il attendait 22 rubriques alors que les quatre sous-tâches T06 portent le total à 26. Le garde-fou a empêché toute modification partielle.
- **Attendu :** une fiche et un lien pour chaque lot T00–T18 et chaque sous-lot T06.1–T06.4/T08.1–T08.3.
- **Correction :** quatre fiches T06 ajoutées ; contrôler les identifiants réellement présents et leur correspondance au plan plutôt qu'une liste incomplète.
- **Responsable / clôture :** maintien du plan. Revalidation documentaire du 8 novembre : comparaison exacte des 26 IDs du tasking et du plan, quatre rubriques par fiche, 95 liens/ancres sur cinq documents, 43 fichiers de tests existants et 11 futurs explicitement distingués ; zéro erreur. `git diff --check` sans erreur. État `validé` pour l'incident d'outillage documentaire ; aucun test applicatif exécuté par ce contrôle.

### TRK-100 — Adaptation des collecteurs marketplace à la pipeline OCR

- **État / date / périmètre :** ouvert, P1, 8 novembre 2026 ; T19.1/T19.2/T19.3, C01–C06. Intégration cible demandée, pas échec de test mesuré ici. IDs 100–101 choisis pour distinguer ce complément des incidents des jobs déjà en cours.
- **Preuve :** [normaliseur](app/collectors/normalizer.py) conserve principalement une première image ; [ingestion](app/collectors/service.py) rapproche les indices textuels, [ordonnanceur](app/monitoring/scheduler.py) ne raccorde pas de file OCR de collecte ; Vinted/Leboncoin démarrent à la première page et le navigateur de secours reste opt-in. Observations statiques, sans collecte réelle.
- **Attendu :** parcours et photos fiables par plateforme, C01–C06 durable et borné, même matcher que la capture, annonce conservée en cas d'erreur image/OCR et décisions humaines préservées.
- **Responsable / prochaine action :** job 3, après intégration des jobs 1/2 ; implémenter [T19](docs/identification/T19_COLLECTE_OCR.md) et sa matrice de capacités/modes réellement retenus.
- **Revalidation :** fixtures par plateforme et tests navigation/contrats/file/e2e du plan T19 ; concurrence agrégée app/worker, restart, réingestion, ancienne photo/révision et comparaison extension/veille. Aucun test exécuté dans ce complément documentaire ; ne pas fermer sur les seuls tests de l'extension.

### TRK-101 — Conversion flottante des filtres de prix collecteurs

- **État / date / périmètre :** résolu, P2, 8 novembre 2026 ; T19.1, constructeurs de filtres Vinted/eBay.
- **Preuve :** `_euros_from_cents()` dans [vinted.py](app/collectors/vinted.py) et [ebay.py](app/collectors/ebay.py) utilisait `cents / 100` avant formatage. Contraire à la règle monétaire d'AGENTS.md ; aucune erreur de montant concrète ni régression de tests démontrée ici.
- **Correctif (8 novembre 2026) :** conversion entière exacte `f"{cents // 100}.{cents % 100:02d}"` dans les deux connecteurs, avec rejet explicite des centimes négatifs ; format inchangé pour les adaptateurs (`"10.00"`, `"0.05"`). Cas limites ajoutés dans [tests/test_collectors.py](tests/test_collectors.py) : zéro, centimes non ronds (1, 105, 5, 499) et grandes bornes (10 000 000 / 999 999 999 centimes), sans réseau.
- **Revalidation :** exécutée le 8 novembre 2026 — `docker compose run --rm app pytest tests/test_collectors.py -v` : **14 passed** ; suite complète `docker compose run --rm app pytest` : **840 passed**, zéro échec, zéro skip (une première passe a montré un échec isolé et non reproductible du test de retry `test_exponential_backoff_recovers_from_temporary_error`, passant seul puis en suite complète ; sans lien avec ce correctif).
- **Clôture :** critères de la fiche couverts (zéro, centimes non ronds, bornes, filtres min/max, suites passantes, commande/version/résultat consignés). La conformité est limitée aux filtres de prix ; TRK-100 (intégration OCR des collecteurs) reste ouvert et indépendant.

## Modèle pour une nouvelle entrée

### TRK-XXX — Symptôme concret

- **État / priorité / nature / dates :** …
- **Lots, étapes W et responsable de la prochaine action :** …
- **Environnement, version/commit et diff :** …
- **Preuve et reproduction minimale :** fixture/commande ; observé ; attendu. Éviter les secrets/données vendeur et distinguer observation statique d'exécution.
- **Impact et intégrations affectées :** …
- **Correction ou diagnostic :** …
- **Régression et intégrations à rejouer :** …
- **Revalidation / décision / historique :** date, commande, pass/fail/skip, preuve utile ; raison d'un éventuel blocage/réouverture.

## Session T08.1/T08.3 — 8 novembre 2026 (en cours)

- TRK-001/TRK-003/TRK-006 : corrections en cours, aucune clôture avant tests et navigateur.
- TRK-002 : reproduction Docker établie avec `ocr_numbers=['n']` : `_features()` accepte toute chaîne alphabétique de 1–5 caractères, puis `prefill_identity_fields()` recopie `features.card_number='n'` sans référence admissible. Ceci prouve la propagation du parasite, pas que Tesseract l'a produit sur la photo du chat. Vérification complémentaire du préfixe `no` du détecteur en cours.
- Outillage de diagnostic : deux premières commandes exploratoires échouées (`connect` utilisé sans contexte puis avec `str` au lieu de `Path`). Reproduction reprise avec SQLite en mémoire et migrations ; code 0. Aucune base utilisateur ouverte ou modifiée.
- Validation UI : `Browser plugin not available` (plugin/skill Browser absent de la session) ; utilisation du Playwright déjà installé dans Docker conformément au skill frontend-testing-debugging. Aucun ajout de dépendance.
- Outillage local : alias `python` absent sur l’hôte ; script d’édition relancé avec `python3`, code 0. Accès socket Docker refusé dans le sandbox pour la première commande de tests ; relance avec l’autorisation Docker existante, tests ciblés exécutés (99 passants). Aucun rejet d’auto-approbation.
- TRK-002 : second chemin reproduit avant correction : `extract_features('Non identifiée')` retourne `card_number='n'`, le préfixe `no` sans frontière et sans chiffre consomme le début de « Non ». Le titre exact Tortant/description 1995 ne produit pas de numéro. Ne pas attribuer l’incident photo à ce chemin sans payload/photo original.

### TRK-012 — Priorité du diagnostic de doublon en saisie URL

- **État / priorité / nature / date :** validé, P2, régression de validation, 8 novembre 2026 ; T08.3/W09.
- **Preuve :** premier rejeu étendu : 2 échecs/231 passants. `test_review_then_import_with_shipping_and_correct_platform` reçoit un conflit d’identité au second ajout plutôt que le doublon attendu : le premier import a initialisé le référentiel, ce qui change les diagnostics disponibles.
- **Correction :** lecture du doublon avant nouvelle validation d’identité, sans modification de l’annonce existante. L’ingestion garde son contrôle transactionnel contre les courses. Responsable : session T08 ; rejouer tests manuels et suite complète.
- **Autre échec du même run :** assertion du nouveau harnais sur « depuis le référentiel » alors que le libellé disait « depuis référentiel ». Grammaire corrigée ; aucun comportement métier masqué.
- TRK-012 : revalidation ciblée réussie après correction : **233 passants**, 1 avertissement de dépréciation Starlette/httpx ; code 0. État `validé` pour le diagnostic de doublon ; suite complète encore à exécuter.
- T08.1 : les préremplissages sont exclus des observations indépendantes de conflit ; le titre original et les vrais indices OCR restent contrôlés. Régression ajoutée sur faute vendeur → proposition canonique → réanalyse → ajout sans confirmation implicite.
- Recette navigateur moteur actuel : **65 passants** (dont Chromium réel, 1440×1000 et 390×844), aucun avertissement/erreur console applicatif, pas de débordement horizontal ; captures inspectées hors dépôt dans `/tmp/pokebourse-t08-qa`. Parcours : OCR simulé → prix invalide visible → correction du prix → réanalyse sans OCR → langue inconnue → ajout toujours ambigu, sans décision humaine. Réseau externe intercepté. Ce résultat ne qualifie pas Tesseract ni T08.2 complet.

### TRK-013 — Garde du service worker incompatible avec le nom séparé

- **État / priorité / nature / date :** validé, P1, intégration MV3 T08.1/W01 ; 8 novembre 2026.
- **Preuve :** revue après séparation du titre : `CAPTURE_LISTINGS` exigeait encore `item.name.trim()` non vide. Une nouvelle capture avec `name=''` et `raw_data.title` aurait été ignorée. Toast également lié au nom plutôt qu’au titre.
- **Correction :** accepter un nom historique ou un titre brut non vide, garder les contrôles prix/URL et la déduplication ; toast/popup affichent le titre. Transporter la langue explicite dans le formulaire.
- **Revalidation / responsable :** tests du service worker et extension Chromium à rejouer, puis suite complète ; session T08.
- TRK-013 : le run extension commencé avant le correctif a effectivement reproduit le défaut : compteur popup `0` au lieu de `1`, `test_capture_to_listing_end_to_end` en échec ; total **1 échec/187 passants**. Régression e2e enrichie pour contrôler le stockage (`name=''`, titre brut et `und`) avant ouverture du popup. Correctif déjà appliqué ; revalidation en cours.
- TRK-013 : revalidation après correctif : **188 passants, zéro skip**, dont extension Chromium réellement chargée sous Xvfb, OCR Tesseract sur image synthétique locale et contrôle du stockage séparé titre/nom/langue. État `validé` pour cette régression. Les images de marché réelles ne sont pas qualifiées par ce test.
- Revue visuelle : champs et diagnostics lisibles à 1440×1000/390×844, sans débordement ; message de provenance doublonné simplifié avant recette finale.

## Revalidation finale T08 — 8 novembre 2026

- **Arbre de travail :** base `a904eca`, modifications préexistantes documentaires préservées ; aucun commit imposé. Pas de modification de `pyproject.toml`, pas de migration ni suppression de données/volume. Bases de test temporaires, destinations externes interceptées/mocks.
- **Ciblés du plan :** `docker compose run --rm -v /tmp/pokebourse-t08-qa:/qa -e POKEBOURSE_QA_DIR=/qa app pytest tests/test_identification_evidence_browser.py tests/test_capture_workflow.py tests/test_chrome_extension.py tests/test_capture_preview.py tests/test_listing_preview.py tests/test_manual_listing.py tests/test_identification_evidence.py tests/test_ocr_local.py tests/test_ocr_web.py tests/test_identification_reviews.py tests/test_extension_e2e.py tests/test_migrations.py tests/test_backups.py tests/test_web.py tests/test_simplification_navigation.py -ra` → **188 passed, zéro skip**, code 0.
- **Complément déterministe :** mêmes suites cœur avec `test_identification_reliability.py` → **236 passed**, code 0 avant le dernier ajustement des seuls libellés ; tous inclus à nouveau dans la suite complète finale.
- **Dernier rendu :** navigateur + harnais après simplification du message de provenance → **11 passed**, code 0. Playwright/Chromium sur serveur temporaire `127.0.0.1:<port>` ; desktop 1440×1000, mobile 390×844. Identité de page, contenu non vide, absence d’overlay, console et interactions vérifiés ; captures inspectées dans `/tmp/pokebourse-t08-qa/t08-fields-desktop.png` et `t08-fields-mobile.png`.
- **Commande demandée :** `docker compose run --rm app pytest -ra` → **829 passed, 1 warning in 35.00s**, code 0, zéro skip. Avertissement de dépréciation existant Starlette/TestClient/httpx, sans échec ; pas de changement de dépendance pour le masquer.
- **Contrôle statique :** `git diff --check` code 0 avant la mise à jour documentaire finale ; rejoué à la livraison.
- **Restants :** TRK-002 reste `à reproduire` pour l’origine du parasite sur la photo fournie, malgré les deux causes techniques reproduites/corrigées/testées. TRK-004/TRK-005/TRK-007 demeurent ouverts pour orchestration hors popup, sélection atomique et résolution humaine motivée. TRK-008/TRK-009 ne sont pas résolus par des tests de formulaire. Aucun lot OCR ni T08.2 intégral déclaré validé.
- **Relais OCR :** [consignes détaillées et contrats](docs/identification/T08_CONTROLES_MOTEUR_ACTUEL.md#consignes-au-job-ocr-t06t07t082). Annoter/rejouer la photo originale, tracer les frontières, conserver l’inconnu et les corrections, raccorder sélection/confirmation atomiques puis revalider la recette photographique et les mesures appariées.

## Reprise job 1 T08.1/T08.3 — 8 novembre 2026

- Acquis précédents conservés ; revalidation dans le projet Compose isolé `pokebourse-fields-p1`, sans intervention sur les composants OCR du job 2 ni les collecteurs du job 3.
- `Browser plugin not available` : plugin et skill Browser absents ; reprise du harnais Playwright/Chromium existant dans Docker. Parcours : capture → champs proposés/erreurs financières → correction/réanalyse → ajout sans confirmation implicite ; bureau et mobile.
- Premier accès Docker refusé par le sandbox ; relance avec escalade autorisée, construction de l'image du projet isolé en cours. Pas de rejet d'auto-approbation. Une lecture exploratoire de `docker-compose.yml` a trouvé un fichier absent ; configuration réelle lue dans `compose.yaml`.

### TRK-014 — Capture sans extension rejetée par le service worker

- **État / priorité / nature :** validé, P1, défaut observé statiquement ; T08.1, garde MV3.
- **Preuve / reproduction :** `CAPTURE_LISTINGS` rejette `!item.set_name` et exige un `name` de type chaîne, même si `raw_data.title` est présent. Le contrat de capture partielle doit admettre une identité absente sans inventer nom/extension.
- **Prochaine action / responsable :** job 1, remplacer les exigences d'identité par un titre vendeur ou nom historique ; conserver validation prix, URL, déduplication, provenance et stockage. Ajouter un test exécutant le handler réel avec stockage simulé et tester les rejets légitimes.
- **Revalidation :** reproduction, suites extension/capture puis suite complète et parcours navigateur ; aucune clôture avant résultats.

### TRK-015 — Devise absente sans diagnostic financier par champ

- **État / priorité / nature :** validé, P2, défaut observé statiquement ; T08.3.
- **Preuve :** `preview_form()` ne renseigne `financial_errors['currency']` que pour une devise non vide mal formée. L'absence empêche la valorisation mais n'est pas signalée auprès du champ comme les autres erreurs financières.
- **Prochaine action / responsable :** job 1, diagnostic dédié sans bloquer les candidats, conserver la saisie et l'absence de valorisation ; test POST sans JavaScript puis correction sans OCR.
- **Revalidation :** tests formulaire et navigateur, suite complète avant clôture.
- Environnement : l'image `pokebourse-fields-p1-app` a été construite depuis le Dockerfile existant (installation réseau des dépendances à la construction uniquement, pas dans les tests). Le test e2e possède un chemin de police vers matplotlib absent des dépendances déclarées ; vérifier la disponibilité lors du rejeu puis utiliser une police système si nécessaire, sans ajouter matplotlib.
- Reproduction exécutée avant correctif : `docker compose -p pokebourse-fields-p1 run --rm app pytest tests/test_capture_workflow.py tests/test_chrome_extension.py tests/test_capture_preview.py tests/test_listing_preview.py tests/test_manual_listing.py tests/test_identification_evidence.py -ra` → **2 failed, 109 passed**, code 1. Exactement TRK-014 (0 captures au lieu de 2) et TRK-015 (diagnostic devise absent). Corrections minimales appliquées ; état des deux incidents : corrigé à revalider.
- Premier rejeu élargi après corrections : **1 failed, 307 passed**, code 1, zéro skip. TRK-014 passe désormais. TRK-015 : ancien test exige le texte « Devise de l’annonce inconnue », remplacé par le nouveau diagnostic. Libellé historique rétabli dans le message par champ, assertion existante conservée ; revalidation en cours. L'extension MV3 réelle et l'OCR synthétique ont passé ; l'hypothèse d'une police indisponible n'est pas reproduite dans cette image, aucun changement de police/dépendance.
- Des modifications indépendantes de `base.html`, `gestion.html`, `web.py` sont apparues pendant le travail : laissées intactes. Elles sont incluses dans la validation de l'arbre partagé, sans attribution au correctif T08.

### TRK-016 — Soumission finale URL perd les diagnostics après erreur financière

- **État / priorité / nature :** validé, P2, constat statique T08.3 ; `save_listing()` parse les montants avant l'analyse et son rendu d'erreur ne transmet aucun `preview`. La branche finale URL doit garder les candidats même sans JavaScript, comme la capture.
- **Autre garde du titre dans ce chemin :** `raw_data.title` reçoit le titre édité plutôt que `captured_title` à l'ajout. Préserver le titre original avec `edited_title` distinct, comme le chemin capture.
- **Responsable / prochaine action :** job 1 ; régression POST prix/port invalide, contrôle absence d'écriture, titre original après ajout ; réutiliser `preview_form` sans nouveau moteur ni OCR.
- **Revalidation :** suites manuelle/capture/harnais puis complète ; pas de clôture avant résultats.
- TRK-014/TRK-015 : deuxième rejeu élargi **308 passed**, zéro skip, code 0 ; console erreurs/avertissements et clavier contrôlés, screenshots bureau/mobile inspectés. Ces résultats précèdent le complément URL TRK-016.
- TRK-016 reproduit avec trois POST directs : **3 failed**, 11 deselected, code 1 ; diagnostics prix/port absents et `original_title` égal au titre édité. Correction : analyse commune avant validation financière, rendu conservant `preview`, titre capturé et `edited_title` distincts. Priorité du doublon maintenue. Tests et navigateur URL ajoutés ; état corrigé à revalider.
- TRK-016 premier correctif : **1 failed, 31 passed** (ciblage harnais + saisie URL), code 1. Prix/port et titre original passent. Le nouveau test attendait `raw_data.edited_title` alors que l'import JSONL normalise volontairement `raw_data` et conserve l'édition comme observation manuelle ; assertion corrigée pour contrôler le contrat durable réel (`original_title` + observation manuelle), sans modifier l'importeur ni sa liste de champs. Le rejeu élargi déjà lancé a collecté l'ancienne assertion ; ce résultat sera distingué du rejeu final.
- Rejeu élargi lancé avec l'ancienne assertion durable : **1 failed, 310 passed**, zéro skip ; seul échec : attente de `raw_data.edited_title`, déjà corrigée dans le test après examen de l'importeur.
- Rejeu final ciblé sur l'état corrigé : `docker compose -p pokebourse-fields-p1 run --rm -v /tmp/pokebourse-fields-p1-qa:/qa -e POKEBOURSE_QA_DIR=/qa app pytest tests/test_identification_evidence_browser.py tests/test_capture_workflow.py tests/test_chrome_extension.py tests/test_capture_preview.py tests/test_listing_preview.py tests/test_manual_listing.py tests/test_identification_evidence.py tests/test_ocr_local.py tests/test_ocr_web.py tests/test_identification_reviews.py tests/test_extension_e2e.py tests/test_migrations.py tests/test_backups.py tests/test_web.py tests/test_simplification_navigation.py tests/test_identification_reliability.py -ra` → **311 passed, 1 warning in 22.16s**, code 0, zéro skip.
- Serveur sans JavaScript : POST directs d'initialisation/réanalyse/ajout, prix/port/devise invalides, incohérence d'identité et conservation du titre original contrôlés. Navigateur réel : capture → correction prix/devise au clavier → réanalyse → ajout sans auto-confirmation, puis URL → erreur financière finale → correction → réanalyse → ajout, titre original et `und` contrôlés en SQLite.
- QA : `http://127.0.0.1:<port temporaire>`, Chromium, 1440×1000 et 390×844, plugin Browser absent. Identité de page, contenu utile, absence d'overlay, console erreurs/avertissements, clavier, absence de débordement et interactions : passants. Captures dans `/tmp/pokebourse-fields-p1-qa/`, hors dépôt, inspectées visuellement.
- TRK-014/TRK-015/TRK-016 : reproductions et intégrations affectées passantes ; attente de la suite complète finale pour clôture.


## Clôture de la reprise job 1 — T08 moteur actuel

- **Version / environnement :** base `a904eca`, arbre partagé non committé ; Compose `pokebourse-fields-p1`, Python 3.12, Chromium/Playwright et Tesseract de l'image construite par le Dockerfile existant. Modifications préexistantes et travaux indépendants préservés. Dernière migration réelle `0026_tcgdex_sync_locale.sql` ; aucune migration ni dépendance ajoutée.
- **Commande finale demandée :** `docker compose -p pokebourse-fields-p1 run --rm app pytest -ra` → **834 passed, 1 warning in 40.95s**, **code 0, zéro skip**. Avertissement existant : dépréciation Starlette/TestClient/httpx. Aucun appel externe réel dans les scénarios de test ; marchés et images simulés/interceptés, bases temporaires. Le réseau de construction de l'image est distinct des tests.
- **Ciblés du plan :** **311 passed**, code 0, zéro skip, sur les 16 fichiers indiqués ci-dessus. MV3 réellement chargé sous Xvfb, serveur sans JavaScript et interactions capture/URL testés. Confirmation humaine et `first_seen_at` couverts par les suites existantes `test_identification_reviews.py` et la suite complète ; JSONL historique et `und` explicite revalidés.
- **Décision :** TRK-014/TRK-015/TRK-016 validés après reproduction, correction puis revalidation ciblée et complète. T08.1 acquis ; contrôles T08.3 du moteur actuel revalidés. Les cases de T08.3 dépendant de sélection/résolution transitoire et révision ne sont pas déclarées terminées.
- **Fichiers changés par cette reprise :** `app/listing_preview.py`, `app/manual_listing.py`, `extension/background/service-worker.js`, `tests/test_chrome_extension.py`, `tests/test_capture_workflow.py`, `tests/test_identification_evidence_browser.py`, `TASKING_IDENTIFICATION_FIABLE.md`, `docs/identification/T08_CONTROLES_MOTEUR_ACTUEL.md`, `tracker.md`. Les autres modifications de l'arbre appartiennent aux acquis ou travaux indépendants ; elles n'ont pas été annulées.
- **Incidents restants :** TRK-002 (origine sur photo originale), TRK-004/005/007 (orchestration hors popup, sélection/décision atomique, résolution motivée), TRK-008/009 (capacités marché et qualification OCR), TRK-100/101 (collecteurs). Aucun de ces périmètres n'est fermé par une recette de formulaire.
- **Reprise job 3 :** suivre `docs/identification/T08_CONTROLES_MOTEUR_ACTUEL.md`, section « Reprise job 3 » ; intégrer les modules du job 2 et les contrats d'observation existants, conserver l'inconnu/corrections/provenance, raccorder sélection et décision atomiques, tester révision/réingestion, puis T19. Rejouer les commandes ciblée et complète dans le projet isolé. Aucune implémentation de nouveau module OCR/collecteur dans cette reprise.

## Revue transversale du tasking — 8 novembre 2026

- Tableau de synthèse vérifié sans doublon, concordant avec les entrées détaillées TRK-014/015/016 déjà validées dans la clôture du job 1 ; aucun nouvel incident fonctionnel ni changement de priorité.
- `docker compose run --rm app pytest -ra` sur l’arbre partagé : **834 passants, 0 échec, 0 sauté**, 38,38 s, avertissement Starlette/TestClient/httpx existant. Cette revalidation ne ferme pas TRK-002/004/005/007/008/009/100/101.
- Les constats et résultats de l’ouverture restent historiques. La mention initiale « aucun test mesuré pendant cette mise à jour documentaire » ne s’applique pas aux reprises et contrôles datés ajoutés ensuite.
- Dépendances et prochaines actions consolidées dans [TASKING_PROJET.md](TASKING_PROJET.md) ; aucun lot OCR ou accès externe n’est validé par la remise à jour des documents.

### TRK-102 — Défauts localisés de mise en page responsive (`/catalog`, `/search`, `/trends`) et formulaires GET sans `action` explicite

- **État / priorité / nature / date :** validé, P2, recette navigateur 5 largeurs et inventaire UI, 8 novembre 2026 ; Recherche/Tendances `T1.5`/`T3.4`, Intégration Design `T2`/`T5`/`T6`.
- **Preuve :**
  1. Sur `/trends` à `320` et `390` px, `.stack { display: grid }` sans `grid-template-columns: minmax(0, 1fr)` laissait les enfants contenant `.table-wrap > table` adopter la largeur minimale intrinsèque de la table, créant un débordement horizontal du document (`scrollWidth > innerWidth`).
  2. Sur `/search` à `320` px, `.ref-cards-grid` (`minmax(280px, 1fr)`) dépassait la largeur interne d'un panneau (≈ `250` px à `320` px) ; `.search-advanced-grid`, `.gestion-grid` et `.add-menu` présentaient le même risque aux très petites largeurs.
  3. Sur `/trends` à `1024` px (`<= 1100` px), la 6e colonne (`ROI`) des lignes `.product-row` du bloc « Meilleures affaires » n'avait pas la classe `optional-1100`, laissant 7 éléments visibles dans une grille passée à 6 colonnes.
  4. Sous `900` px, `.product-row .decision-wrap` positionné en absolu (`top: 14px; right: 14px`) pouvait chevaucher `.product-identity` sur un titre long à `320` px.
  5. Lors de l'inventaire des actions UI (`T5`), trois formulaires de filtre GET (`annotation_dashboard.html`, `identification_diagnostics.html`, `tcgdex_sync.html`) omettaient l'attribut `action` explicite.
- **Correctif (8 novembre 2026) :**
  - Dans [style.css](app/static/style.css) : `grid-template-columns: minmax(0, 1fr)` et `.stack > * { min-width: 0 }` ; `minmax(min(100%, 280px), 1fr)` sur `.ref-cards-grid` (et `min(100%, 200px)` sur `.search-advanced-grid` / `.gestion-grid`) ; `width: min(290px, calc(100vw - 32px))` sur `.add-menu` ; sous `900` px, `.product-row .decision-wrap` remis en flux (`position: static; grid-column: 1 / -1`) et passage de `.product-row` en 1 colonne sous `420` px. Version d'asset incrémentée dans [base.html](app/templates/base.html) (`?v=20261108-responsive`).
  - Dans [trends.html](app/templates/trends.html) : ajout de `class="optional-1100"` sur la 6e cellule (`ROI`) des lignes `.product-row`.
  - Dans [annotation_dashboard.html](app/templates/annotation_dashboard.html), [identification_diagnostics.html](app/templates/identification_diagnostics.html) et [tcgdex_sync.html](app/templates/tcgdex_sync.html) : ajout des attributs `action="/annotations"`, `action="/identification/diagnostics"` et `action="/tcgdex"`.
- **Revalidation :** exécutée le 8 novembre 2026 dans Docker (`test_responsive_and_keyboard_qa_for_catalog_search_and_trends` et `test_ui_actions_inventory_has_no_decorative_noop_buttons` dans [tests/test_search.py](tests/test_search.py)) : contrôle Playwright/Chromium aux 5 largeurs (`1440`, `1024`, `768`, `390`, `320` px) sur `/catalog`, `/search` et `/trends` (`scrollWidth <= innerWidth`, absence de chevauchement `.product-identity` / `.decision-wrap`, tiroir mobile `#menu-button` + touche `Escape`, focus clavier) et suite complète `docker compose run --rm app pytest -ra` : **867 passed, 1 warning in 38.35s**, code 0, zéro skip.
- **Clôture :** validé sur `/catalog`, `/search` et `/trends` aux 5 largeurs et sur l'inventaire des actions des 26 templates. La recette visuelle des autres écrans secondaires reste ouverte dans `TASKING_INTEGRATION_DESIGN.md` (`T6`).

## Consolidation des branches OCR — 8 novembre 2026

- **Branches comparées :** `codex/ocr-parallele` (`4d0746d`) et `codex/ocr-p2` (`862a0d7`), sur le socle consolidé `0a07d7b`. Leurs suites d’origine ont été rejouées dans Docker : respectivement **59 passed** et **77 passed**, zéro skip.
- **Choix d’intégration :** pipeline spatial de `ocr-parallele` pour géométrie/localisation optionnelle, TSV, noms, hypothèses, langue, recherche et transport ; runner `ocr-p2` pour annulation, groupe de processus, sortie strictement bornée et sémaphore. Le `Deadline` est commun et l’adaptateur historique délègue au nouveau runner. Les autres implémentations p2 ne sont pas empilées : contrats concurrents et couverture spatiale doublonnée.
- **Revalidation ciblée intégrée :** `docker compose run --rm app pytest tests/test_ocr_geometry.py tests/test_ocr_hypotheses.py tests/test_ocr_languages.py tests/test_ocr_spatial.py tests/test_ocr_limits.py tests/test_ocr_local.py tests/test_ocr_web.py tests/test_ocr_crop_browser.py -ra` → **86 passed**, zéro skip, 1 avertissement Starlette/httpx connu. Premier essai interrompu à la collecte par les imports des tests p2 retirés ; second essai : 85 passed/1 failed sur le seul message historique de sortie excessive ; correction du libellé puis résultat vert ci-dessus.
- **Parcours communs :** capture, extension MV3, prévisualisation, reviews, migrations, sauvegardes/restauration, preuves visuelles, recherche, tendances et tasking → **359 passed**, zéro skip, avec la commande complète consignée dans SUIVI §32.
- **Suite complète intégrée :** `docker compose run --rm app pytest -ra` → **936 passed, 1 warning in 45.18s**, code 0, zéro échec et zéro skip. Recettes Chromium/Playwright et extension MV3 incluses ; aucune mesure OCR photographique nouvelle.
- **Dédoublonnage :** TRK-202 (gain non démontré) reste couvert par TRK-009 ; TRK-205 est couvert au niveau interne par l’extraction de noms et les tests de `ocr-parallele`, sans clore l’intégration utilisateur TRK-204. Aucun nouvel incident n’est créé pour ces doublons.
- **Limites :** aucune nouvelle route, capture complète, file worker ou décision atomique ; aucun benchmark apparié nouveau et aucun gain OCR revendiqué. Voir [l’intégration retenue](docs/identification/T06_T07_INTEGRATION_JOB3.md).

### TRK-200 — Fixtures locales ignorées dans un worktree neuf

- **Preuve / périmètre :** constat d’outillage du job p2 ; certaines données locales nécessaires aux suites historiques sont ignorées et ne sont pas ajoutées par cette consolidation. Aucun fichier de données ou photo n’est versionné pour contourner ce constat.
- **Prochaine action / responsable :** chantier outillage/T12 ; décider quelles fixtures minimales doivent être versionnées ou documenter leur restauration, puis valider depuis un clone neuf.
- **Revalidation :** les worktrees existants conservent leurs données locales ; le test en clone neuf n’est pas exécuté. Incident ouvert.

### TRK-201 — Contrôle d’orphelins sans pgrep

- **Correction / revalidation :** la suite du runner inspecte `/proc/*/cmdline`, sans installer procps ni modifier le Dockerfile. Ce contrôle est inclus dans les **86 tests OCR** intégrés passants. État validé pour l’outillage, sans lien avec la justesse OCR.

### TRK-203 — Concurrence app/worker encore locale

- **Preuve :** `OcrSupervisor` utilise un `threading.BoundedSemaphore` et gère les processus de son instance ; aucun verrou partagé entre application et worker n’est ajouté.
- **Prochaine action / responsable :** T06.3/T19.2 ; composer le verrou inter-processus, tester saturation, équité et libération après erreur. La présence du sémaphore local ne ferme pas ce critère.

### TRK-204 — Composants internes ne valent pas parcours T06/T07 complet

- **Intégré :** pipeline spatial, localisation optionnelle avec repli, hypothèses et candidats communs, indices de langue, transport interne et exécution bornée.
- **Restant :** raccordement `/ocr/suggestions` et observations T03, choix de photo/recadrage dans la capture, orchestration hors popup, ajout/décision atomiques, budget de recherche SQLite, T19 et recette photographique annotée.
- **Revalidation :** suites internes et parcours historiques passants ; critères complets non exécutés. Incident ouvert, sans confirmation automatique ni mesure de gain déduite des mocks.
