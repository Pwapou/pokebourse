# Identification — skills, intégrations et validation par lot

**Revue du 8 novembre :** état et dépendances consolidés dans [TASKING_PROJET.md](../../TASKING_PROJET.md). Le plan couvre **30 IDs**, en comptant T13 et les sous-lots T06/T08/T19 ; la numérotation n’est pas un ordre strict. Les résultats historiques du tracker ne modifient pas ces prescriptions.

Date : **8 novembre 2026**. Plan d'exécution associé au [tasking](../../TASKING_IDENTIFICATION_FIABLE.md) et au workflow W01–W11. **Prescriptions à appliquer lors de l'implémentation, pas compte rendu de tests exécutés.** Les résultats historiques gardent leur date et leur périmètre ; aucune case livrée n'est réinitialisée par ce plan.

## Choix des skills

**UI** désigne `build-web-apps:frontend-testing-debugging`, dont le [SKILL.md consulté](/Users/mathieu/.codex/plugins/cache/openai-curated-remote/build-web-apps/0.1.2/skills/frontend-testing-debugging/SKILL.md) guide la validation des écrans, interactions, console, clavier et responsive. Ce chemin appartient à l'environnement de travail ; il ne constitue pas une dépendance du dépôt. Relire le skill disponible au moment d'exécuter la QA. Choisir Browser si le plugin et son skill sont disponibles ; sinon utiliser les tests Playwright Python existants et consigner l'absence de Browser. Pour le chargement réel de l'extension MV3, employer le harnais Chromium/Xvfb du dépôt. Tout obstacle d'outillage qui empêche la validation entre au tracker.

Les étapes Python, SQLite, OCR, statistiques et logique financière n'ont **aucun skill spécialisé approprié dans le catalogue de cette session**. La mention **aucun** signifie développement guidé par AGENTS.md et les références du lot, avec les tests ci-dessous. Ne pas imposer un skill sans rapport avec la stack. UI intervient seulement si le lot modifie effectivement un rendu ou une interaction.

## Règles communes et preuves attendues

1. Avant modification : identifier les contrats d'entrée/sortie et dépendances, puis reproduire le défaut sur fixtures/base temporaire. Une anomalie de code observée statiquement peut être enregistrée sans être présentée comme un échec pytest exécuté.
2. Tests automatisés dans Docker : mocks/fixtures pour les marketplaces, TCGdex, téléchargements d'images et modèles ; bloquer toute sortie externe non simulée. Les échanges entre navigateur et serveur local du test restent permis. Aucun test ne dépend de la base utilisateur.
3. Couvrir comportement nominal, erreur, inconnu, contradiction et résultat périmé aux frontières concernées ; vérifier les effets de bord, pas seulement les objets retournés. Ajouter un test de régression utile au défaut corrigé ; une simple édition documentaire ne demande pas de nouveaux tests applicatifs.
4. Séparer tests unitaires, intégrations serveur/SQLite/worker, bout en bout navigateur/extension et mesures OCR réelles. Un mock de Tesseract ne prouve pas une meilleure lecture ; une image synthétique de texte ne qualifie pas des photographies marketplace.
5. Pour une modification UI : trajet exact, état avant/après, console, clavier, bureau et une largeur mobile lorsque pertinent. Conserver les captures/traces temporaires hors du dépôt ; résumer la preuve et les commandes dans le tracker. Les artefacts durables de benchmark suivent le mode explicite T04.
6. Consigner commande, version/commit et diff concerné, date, environnement, résultat, comptes pass/fail/skip et artefacts utiles. **Un test sauté ou non exécuté n'est pas passant** ; un scénario obligatoire sauté laisse sa validation ouverte.
7. Tout échec, défaut OCR, incohérence de champ, problème d'intégration, de migration ou d'outillage bloquant est créé/dédupliqué dans [tracker.md](../../tracker.md). Après correction, rejouer la reproduction et les intégrations affectées ; clôturer seulement avec preuve.
8. Un lot est validé pour un périmètre explicite quand tests concernés, intégrations et critères d'acceptation passent, sans incident bloquant ouvert sur ce périmètre. Un blocage indépendant n'empêche pas les travaux autonomes des autres lots ; aucune validation globale ni réduction du besoin n'est implicite.

## T00

- **Skill :** aucun.
- **Intégrations :** configuration Compose → application/worker/CLI, migrations et inventaire sur sauvegarde cohérente ; préserver le volume réel.
- **Tests :** `tests/test_config.py`, `tests/test_cli.py`, `tests/test_migrations.py`, puis suite complète pour une baseline versionnée. Vérifier versions Python/Tesseract/langues, présence Chromium/Xvfb et jeux de données nécessaires aux scénarios suivants.
- **Validation :** inventaire, écarts de configuration et baseline horodatés ; distinguer échecs initiaux, skips et régressions introduites. Entrée tracker pour chaque anomalie constatée.

## T01

- **Skill :** aucun.
- **Intégrations :** acquisition manuelle séparée → magasin T04/manifeste → rejeu local → évaluateur/labels indépendants.
- **Tests :** `tests/test_identification_benchmark.py`, `tests/test_ocr_benchmark_preparation.py`, `tests/test_replay_local.py` ; refuser artefact absent, téléchargement implicite et changement de catalogue/labels non versionné. Exécuter ensuite le benchmark local annoté hors de la petite suite pytest.
- **Validation :** empreintes et partitions reproductibles, doublons regroupés, labels non tirés des prédictions ; métriques avec dénominateurs/exclusions. Sans annotations indépendantes, outillage validable mais justesse non démontrée.

## T02

- **Skill :** aucun.
- **Intégrations :** extraction backend et extension → matcher → ingestion/réidentification ; mêmes cas et garde-fous aux deux entrées.
- **Tests :** `tests/test_identification.py`, `tests/test_identification_reliability.py`, `tests/test_candidate_number_warning.py`, `tests/test_lexical_identification.py`, `tests/test_chrome_extension.py`, `tests/test_pipeline_integration.py`. Lots, négations, suffixes, langues contradictoires, numéro de série et état déclaré.
- **Validation :** aucune identité unitaire/cote pour un lot, aucune langue inventée et aucun abaissement silencieux des seuils ; cas déterministes et limites documentés.

## T03

- **Skill :** aucun pour les contrats ; UI si leur présentation évolue.
- **Intégrations :** URL/extension/JSONL/collecte → observations → décision commune → confirmation/export ; validation serveur des enveloppes reçues.
- **Tests :** `tests/test_identification_evidence.py`, `tests/test_pipeline_integration.py`, `tests/test_imports.py`, `tests/test_listing_preview.py`, `tests/test_identification_reviews.py` et `tests/test_identification_evidence_browser.py`. Égalité à observations identiques, contradictions, anciens clients et absence d'auto-confirmation après préremplissage.
- **Validation :** provenance et priorité humaines conservées, prévisualisation sans écriture, observations proposées jamais recréées comme déclarations/confirmations ; même identité effective dans toutes les projections.

## T04

**Dépendance :** outillage T01 et contrat T03 ; la conservation ne dépend pas de la fin des 300/1 000 annotations. T01 l’utilise ensuite pour les preuves visuelles.

- **Skill :** aucun ; UI si le parcours de conservation/annotation est modifié.
- **Intégrations :** image éphémère ou conservation explicite → preuves/snapshots → annotation/export → sauvegarde/restauration/purge.
- **Tests :** `tests/test_visual_evidence.py`, `tests/test_annotation_pilot.py`, `tests/test_identification_reviews.py`, `tests/test_backups.py`, `tests/test_migrations.py`. Fichier absent/altéré, chemin hors magasin, purge, rollback et restauration des octets nécessaires au rejeu.
- **Validation :** image éphémère non archivée implicitement ; aucune preuve prétendument disponible ; replay identique après restauration, décisions/éligibilité réévaluées si preuve manquante.

## T05

- **Skill :** aucun.
- **Intégrations :** alias/localisations → cache/recherche → files sync/research → worker → réexamen → liens Cardmarket/décisions existantes.
- **Tests :** `tests/test_reference_aliases_localizations.py`, `tests/test_reference_coverage_report.py`, `tests/test_tcgdex_cache.py`, `tests/test_tcgdex_sync.py`, `tests/test_identification_research.py`, `tests/test_cardmarket.py`, `tests/test_migrations.py`. Collision d'alias, cache partiel, locales, pause/reprise, erreurs et résultats périmés simulés.
- **Validation :** pas d'écrasement d'une localisation, ID/liens préservés, absent distingué d'inconnu ; enrichissement distant séparé du matcher et reprise W05 sans nouvel OCR inutile.

## T06

- **Skill :** UI pour sélection photo/recadrage et rendu des régions ; aucun pour géométrie/Tesseract/langue.
- **Intégrations :** extension/téléversement → EXIF/géométrie → processus OCR borné → TSV/fragments/langue → API et recherche commune.
- **Tests :** bases `tests/test_ocr_local.py`, `tests/test_ocr_web.py`, `tests/test_visual_evidence.py`. À créer : `tests/test_ocr_geometry.py`, `tests/test_ocr_spatial.py`, `tests/test_ocr_languages.py`. EXIF, transformation/reprojection, objets distincts, texte fragmenté, abstention de langue, six passes/budget global, sortie excessive, annulation et libération des processus/sémaphores.
- **Validation :** fixtures géométriques passantes et petit jeu de photos autorisées/annotées avec Tesseract réel ; comparaison appariée baseline/manuel/spatial, noms/numéros exacts, rappel, abstention, mémoire et latence. Raccordement T08.2 requis pour déclarer le parcours utilisateur livré.

### T06.1

- **Skill :** UI pour choix/cadrage ; aucun pour géométrie.
- **Intégrations :** photo capturée ou téléversée → orientation EXIF → coordonnées CSS/image → région redressée → moteur OCR.
- **Tests :** `tests/test_ocr_local.py`, futurs `tests/test_ocr_geometry.py` et harnais navigateur. EXIF 1/3/6/8, marges/zoom CSS, rotations, coins croisés/colinéaires/hors cadre, confusion boîtier/carte et sélection d'une autre photo.
- **Validation :** reprojection vérifiée sur géométrie connue, source/région visibles, repli manuel utilisable, latence/mémoire bornées ; ancienne réponse jamais appliquée à la nouvelle photo.

### T06.2

- **Skill :** aucun ; UI si affichage des régions modifié.
- **Intégrations :** TSV → tokens/lignes → transformations de coordonnées → lectures nom/numéro du même objet → matcher commun.
- **Tests :** futurs `tests/test_ocr_spatial.py`, `tests/test_ocr_geometry.py` et bases `tests/test_ocr_local.py`. Confiance absente, boîtes invalides, blocs distincts, fragments `025`, `/`, `165`, texte hors carte et suffixes/préfixes.
- **Validation :** lectures brutes et positions conservées, aucune association entre objets ni concaténation globale, sortie compatible avec les consommateurs historiques.

### T06.3

- **Skill :** aucun.
- **Intégrations :** superviseur/processus Tesseract → budget global → recherche locale et sérialisation → réponse/erreur HTTP.
- **Tests :** `tests/test_ocr_local.py`, `tests/test_ocr_web.py` ; créer `tests/test_ocr_limits.py` pour délai, six passes, sortie excessive, saturation, annulation et processus récoltés. Mesurer séparément latence/mémoire sur photos annotées et matériel décrit.
- **Validation :** budget global respecté, pas de processus orphelin ni sémaphore perdu, sortie partielle/indisponible expliquée ; bilan incluant refus/replis et p50/p95, sans assimiler vitesse et justesse.

### T06.4

- **Skill :** aucun pour la méthode ; UI pour suggestion et confirmation.
- **Intégrations :** fragments discriminants de la carte → hypothèses de langue → validation des observations → exploration des locales → formulaire/confirmation distincte.
- **Tests :** futur `tests/test_ocr_languages.py`, `tests/test_identification_evidence.py`, `tests/test_capture_preview.py`, `tests/test_reference_aliases_localizations.py`. Français/anglais, nom commun, texte court/bruité, langue du site différente et conflit déclaré/photo.
- **Validation :** suggestion justifiée ou abstention, alternatives non transformées en déclarations simultanées, aucun défaut français ni confiance tirée de `fra+eng` ; mesures par langue effectivement testée.

## T07

- **Skill :** aucun ; UI si l'affichage des hypothèses est modifié.
- **Intégrations :** lectures/groupes d'alternatives → hypothèses → recherche structurée/lexicale → décision commune → candidats/champs T08.
- **Tests :** `tests/test_identification.py`, `tests/test_identification_evidence.py`, `tests/test_candidate_number_warning.py`, `tests/test_lexical_identification.py`, `tests/test_ocr_local.py`. À créer : `tests/test_ocr_hypotheses.py`. Original conservé, préfixes/secrets, mauvaise réparation plausible, bonne référence absente, première hypothèse erronée, fragment `n`, absence de fausses contradictions entre alternatives.
- **Validation :** recherche bornée et déterministe, provenance et dénominateur attesté, aucune auto-confirmation par réparation ; gain de rappel mesuré sans masquer les nouvelles fausses suggestions ; cas §1.3 utilisé dans T08.

## T08

**État :** T08.1 et contrôles T08.3 du moteur actuel acquis ; T08.2 et contrôles de sélection/révision à intégrer avec T09. Les nouveaux modules spatiaux ne sont pas encore présents.

- **Skill :** UI ; références projet Mosaic × Flowbite, extension MV3 et procédure OCR.
- **Intégrations :** couvrir ensemble T08.1, T08.2 et T08.3, jusqu'à la fiche persistée et aux critères structurés transmis à T16 ; T19 vérifie le même contrat depuis les collecteurs/veilles.
- **Tests :** suites des trois sous-lots et `tests/test_web.py`, `tests/test_simplification_navigation.py`, `tests/test_identification_evidence_browser.py`. Ajouter un harnais `tests/test_capture_workflow.py` pour les transitions W01–W09 et leurs effets de bord.
- **Validation :** vraie interaction navigateur, cas Tortank et variantes T13, aucun blocage nécessitant SQL/script, aucune annonce écrite avant ajout final ; provenance et même référence sur formulaire/fiche. Une API correcte seule ne valide pas le lot.

### T08.1

- **Skill :** UI.
- **Intégrations :** content script → stockage extension/ancien JSONL → formulaire → proposition du matcher.
- **Tests :** `tests/test_chrome_extension.py`, `tests/test_capture_preview.py`, `tests/test_listing_preview.py`. Titre recopié distingué du nom canonique, candidat absent, faute du vendeur, ancien client, correction humaine et réanalyse.
- **Validation :** titre original conservé, repli remplacé seulement par proposition appropriée, saisie humaine préservée, badges corrects ; livrable sur le moteur actuel sans attendre T06.

### T08.2

- **Skill :** UI.
- **Intégrations :** popup/transport image autorisé → orchestration hors durée de vie du popup → OCR → référence → choix transitoire → ajout/décision atomiques → fiche.
- **Tests :** `tests/test_extension_e2e.py`, `tests/test_capture_preview.py`, `tests/test_manual_listing.py`, `tests/test_ocr_web.py`, `tests/test_identification_reviews.py`. Compléter le harnais W01–W09 : fermeture popup, image inaccessible, sélection autre vue, choix avant ID persistant, doublon, conflit de révision et rollback.
- **Validation :** extension réellement chargée sous Chromium/Xvfb, services HTTP locaux et toutes destinations externes interceptées ; progression visible, côte à côte, diagnostic/action, même choix enregistré. Les photos annotées complètent l'image synthétique existante pour qualifier l'OCR ; aucun scénario requis sauté compté comme succès.

### T08.3

- **Skill :** UI pour erreurs par champ ; aucun pour validation serveur.
- **Intégrations :** observations/champs → contrôles de forme/cohérence → recherche partielle → confirmation/enregistrement ; séparer identité et finances.
- **Tests :** `tests/test_capture_preview.py`, `tests/test_listing_preview.py`, `tests/test_manual_listing.py`, `tests/test_identification_evidence.py` et le nouveau harnais W01–W09. Soumission directe sans JavaScript, prix invalide, champs compatibles isolément mais incompatibles ensemble, ID divergent, langue inconnue et titre faux résolu explicitement.
- **Validation :** messages par champ, critères utilisés/écartés visibles, recherche possible avec indices partiels, pas d'auto-confirmation par champs recopiés ; correction financière sans nouvel OCR ni perte de sélection.

## T09

**Ordre :** définir les contrats après T03/T04/T05, puis intégrer avec T08.2 ; ne pas attendre la clôture de T08 pour préparer la persistance dont T08 a besoin.

- **Skill :** aucun ; UI seulement si projection de décision modifiée.
- **Intégrations :** ingestion/déduplication + choix humain → transaction/snapshot/révision → fiche/export/opportunités/rentabilité → worker.
- **Tests :** `tests/test_identification_reviews.py`, `tests/test_validation_history.py`, `tests/test_imports.py`, `tests/test_catalog.py`, `tests/test_pipeline_integration.py`, `tests/test_catalog_export.py`, `tests/test_profitability.py`, `tests/test_migrations.py`. Concurrence, retrait/réingestion, rollback annonce+review, résultat ancien et conservation `first_seen_at`.
- **Validation :** une même identité effective partout, aucune décision humaine écrasée ni annotation indépendante activée, aucune finance sur identité inadmissible ; inconnus persistés sans faux défaut français.

## T10

- **Skill :** aucun.
- **Intégrations :** manifeste/labels indépendants → variantes texte/OCR/combiné → comparaison appariée → critères de promotion.
- **Tests :** `tests/test_identification_benchmark.py`, `tests/test_ocr_benchmark_preparation.py`, `tests/test_replay_local.py` pour l'outillage ; campagne indépendante hors pytest pour la qualité, avec groupes/partitions figés et contrôles de fuite de données.
- **Validation :** rapport par segment, précision/couverture, rappel, faux rattachements, inconnus, intervalles et coût utilisateur selon T10 ; promotion refusée si critères non démontrés. Des tests de calcul passants ne remplacent pas les annotations.

## T11

- **Skill :** aucun skill de reconnaissance visuelle approprié disponible ; UI seulement si des suggestions visuelles sont exposées.
- **Intégrations :** index/images/modèle locaux versionnés → candidats visuels → union textuelle et décision commune → repli sans index/poids.
- **Tests :** si expérience retenue, créer `tests/test_visual_identification.py` pour versions, index absent, aucun téléchargement implicite, objets/versions proches et garde-fous ; évaluer sur le même jeu indépendant que T10, sans réutiliser le test pour régler le modèle.
- **Validation :** décision intégrer/abandonner avec gain/coût mesurés et licence/provenance documentées. T11 non retenu ne bloque pas J1 ; aucune acceptation automatique sans T10.

## T12

- **Skill :** UI pour recette de livraison ; aucun pour Docker/sauvegarde/restauration.
- **Intégrations :** image Docker/version dépendances → migrations → app+worker → anciens JSONL → backup/restauration → parcours utilisateur.
- **Tests :** suite complète, `tests/test_migrations.py`, `tests/test_backups.py`, `tests/test_cli.py`, e2e extension et T13 sur environnement de test isolé. Si Dockerfile ou dépendances changent, tester dans l'image reconstruite et consigner les versions.
- **Validation :** restauration sur base temporaire, pas de volume effacé, documentation/notice/retour arrière et limites à jour ; aucun blocage ouvert du jalon déclaré livré. Les intégrations externes non accessibles restent explicitement indisponibles.

## T13

- **Skill :** UI pour l'exécution des parcours ; aucun pour les assertions métier et mesures.
- **Intégrations :** W01–W11 et C01–C06/T19, dont correction, enrichissement, résultat périmé, indisponibilité, doublon, reprise et comparaisons qualifiées.
- **Tests :** matrice T13 du tasking → cas identifiables dans les suites précédentes et futurs tests de marché. Décrire pour chaque ligne sa fixture, commande/test, étapes exercées et résultat ; compléter le harnais extension par les cas d'interruption et variantes photographiques.
- **Validation :** toutes les lignes du périmètre livré ont preuve réelle ou limite non validée tracée ; cas manquant/fail/skip vers tracker, aucun verdict global fondé sur le seul scénario nominal.

## T14

- **Skill :** UI pour carte/étiquette/confirmation ; aucun pour extraction et modèles.
- **Intégrations :** régions OCR carte/étiquette → attributs de référence/exemplaire → décision humaine → segments de comparabilité.
- **Tests :** `tests/test_identification.py`, `tests/test_identification_reliability.py`, `tests/test_ocr_local.py`, `tests/test_capture_preview.py`, `tests/test_identification_reviews.py`. Ajouter fixtures et tests d'attributs PSA/PCA : certificat voisin du numéro, note absente, titre contradictoire, protection simple et barèmes distincts.
- **Validation :** non gradé, PSA 9, PSA 10 et PCA 10 séparés ; pas de grade/finition/authenticité inventé ni prix non gradé réutilisé comme cote gradée ; note en représentation exacte.

## T15

- **Skill :** aucun ; sources primaires officielles pour vérifier les capacités, séparées des tests automatisés.
- **Intégrations :** matrice de capacités/configuration → adaptateurs autorisés → messages de disponibilité T16/T18 ; SOURCES.md à jour.
- **Tests :** `tests/test_search.py`, `tests/test_cardmarket.py`, `tests/test_cardmarket_guide.py`, `tests/test_cardmarket_daily.py`. Ajouter `tests/test_market_source_capabilities.py` : source absente/désactivée, absence d'autorisation/clé, cote distincte d'offre/vente, quota et panne simulés ; aucun accès réel dans pytest.
- **Validation :** capacité théorique distincte de l'accès effectivement établi, preuve datée et coûts/limites ; aucune source manquante déclarée fonctionnelle. Absence d'offres/ventes adaptée tracée au tracker, sans activation automatique du connecteur HTML.

## T16

- **Skill :** aucun pour la file/worker ; UI si états de recherche modifiés.
- **Intégrations :** commit annonce+identité → obligation de recherche durable/déduplication → worker → sources simulées → réponse rattachée à la bonne révision.
- **Tests :** `tests/test_identification_research.py`, `tests/test_pipeline_integration.py`, `tests/test_monitoring_service.py` comme bases des mécanismes existants ; créer `tests/test_market_research_workflow.py` pour le nouveau flux marché. Arrêts avant/après commit, retries/backoff, worker relancé, doublon, correction de langue/grade et absence de source.
- **Validation :** une seule recherche admissible, aucune perte après interruption ni exécution sur prévisualisation seule ; pas de transaction SQLite pendant réseau/OCR, résultats périmés rejetés et capture conservée.

## T17

- **Skill :** aucun pour sélection ; UI pour affichage des preuves/motifs.
- **Intégrations :** résultats T16/imports/cotes → réidentification/déduplication → admissibilité des comparables → preuves affichées et estimation.
- **Tests :** `tests/test_profitability.py`, `tests/test_search.py`, `tests/test_cardmarket.py`, `tests/test_sellers_directory_and_purchases.py`. Créer `tests/test_market_comparables.py` : mauvaise version/langue/finition/état, PSA/PCA/notes, auto-comparaison, republication, vente sans montant réel, port/devise inconnus.
- **Validation :** offres/ventes/cotes séparées ; exclusions consultables, attributs bloquants exposés, inconnu distinct d'égalité ; aucun comparable incompatible injecté dans la cote qualifiée.

## T18

- **Skill :** UI pour estimation expliquée et parcours complet ; aucun pour les calculs financiers.
- **Intégrations :** identité/attributs admissibles + preuves T17 + frais/scénario validés → estimation/marge → fiche/export/achats/opportunités.
- **Tests :** `tests/test_profitability.py`, `tests/test_catalog_export.py`, `tests/test_trends.py`, `tests/test_sellers_directory_and_purchases.py`, `tests/test_web.py` ; créer `tests/test_market_estimation.py`. Centimes/bps, ROUND_HALF_UP, frais/port inconnus, devises, annulation d'estimation après correction et données insuffisantes selon le choix produit retenu.
- **Validation :** recette complète non gradé/PSA/PCA avec sources simulées, calcul explicable et identique dans toutes les vues ; pas de montant qualifié sur coûts/identité supposés. Choix §1.2 résolus pour les comportements activés et limites de source visibles.

## T19

- **Skill :** aucun pour collecte HTTP/worker/OCR ; UI pour capture DOM et rendu/validation concernés.
- **Intégrations :** adaptateurs marketplace/extension → données/images normalisées → ingestion → obligation OCR durable → composants communs → publication sous révision → fiche et comparaisons. Voir [la spécification T19](T19_COLLECTE_OCR.md).
- **Tests :** suites des sous-lots ci-dessous, matrice T13 C01–C06 et suite complète Docker ; acquisition externe distincte des tests hermétiques.
- **Validation :** les collecteurs et le worker sont effectivement raccordés au code commun, pas seulement décrits ; périmètre réel par plateforme, ressources/reprise et preuve de bout en bout consignés. Aucun accès non établi annoncé disponible.

### T19.1

- **Skill :** aucun pour adaptateurs/contrats ; UI pour capture DOM et sélection d'images.
- **Intégrations :** pagination/curseur ou DOM dynamique → normaliseur → modèles/stockage extension et ingestion ; compatibilité photos/galerie/anciens JSONL.
- **Tests :** `tests/test_collectors.py`, `tests/test_collector_models.py`, `tests/test_chrome_extension.py`, `tests/test_watch_ingestion.py`. À créer : `tests/test_collector_capture_contract.py`, `tests/test_collector_navigation.py`. Par plateforme : fin, page répétée, plafond, format inattendu, tuile virtualisée, image différée, miniature/grande vue et filtres monétaires exacts.
- **Validation :** bons texte/photos/ID associés, parcours borné avec état partiel explicite, aucun champ d'identité inventé pour conserver la capture ; modes disponibles/distants séparés selon SOURCES.

### T19.2

- **Skill :** aucun.
- **Intégrations :** transaction d'ingestion → obligation/claim OCR → transport image autorisé → composants T06/T07 et matcher commun → résolution avec empreinte/révision.
- **Tests :** `tests/test_watch_ingestion.py`, `tests/test_monitoring_service.py`, `tests/test_supervision.py`, `tests/test_identification_reviews.py`, `tests/test_pipeline_integration.py`, `tests/test_migrations.py`, suites OCR ; créer `tests/test_collector_ocr_queue.py`. Arrêts avant/après commit/claim, deux processus app/worker, équité des files, retry, résultat périmé et prix seul modifié.
- **Validation :** aucun OCR/réseau sous transaction, analyse dédupliquée et reprise durable, concurrence agrégée bornée, veilles suivantes non bloquées, décisions humaines/`first_seen_at` préservés. Image indisponible ne détruit pas l'annonce.

### T19.3

- **Skill :** UI pour interactions/fiche ; aucun pour assertions métier/worker.
- **Intégrations :** C01–C06 et W03–W08 communs, quatre adaptateurs simulés, MV3 et fiche/formulaire de validation puis critères T16/comparaisons locales.
- **Tests :** créer `tests/test_collection_ocr_e2e.py`, compléter `tests/test_extension_e2e.py`, `tests/test_chrome_extension.py`, `tests/test_capture_workflow.py` et les suites d'ingestion/validation. Même annonce/observations via extension et veille, scénario Tortank et variantes ; Tesseract réel sur petit jeu autorisé/annoté séparé des mocks.
- **Validation :** sortie réellement visible et persistée au bon endroit, même identité admissible, aucune boucle ou auto-confirmation OCR ; sources simulées hermétiques. Skips requis, défauts et périmètres indisponibles consignés au tracker ; nouvelle recette J1 incluant T19.

## Commandes et clôture

Exécuter les fichiers existants indiqués dans la fiche du lot avec `docker compose run --rm app pytest -ra`, puis les nouveaux fichiers une fois créés. Exemples exécutables pour les bases existantes :

```bash
docker compose run --rm app pytest -ra tests/test_ocr_local.py tests/test_ocr_web.py tests/test_identification_evidence.py
docker compose run --rm app pytest -ra tests/test_chrome_extension.py tests/test_capture_preview.py tests/test_listing_preview.py tests/test_manual_listing.py tests/test_identification_reviews.py tests/test_extension_e2e.py tests/test_identification_evidence_browser.py
docker compose run --rm app pytest -ra tests/test_migrations.py tests/test_backups.py
docker compose run --rm app pytest -ra tests/test_collectors.py tests/test_collector_models.py tests/test_watch_ingestion.py tests/test_monitoring_service.py tests/test_supervision.py
docker compose run --rm app pytest -ra
```

Les fichiers annoncés « à créer » décrivent les ajouts attendus au moment de leur planification ; vérifier leur présence et leurs résultats dans l'arbre courant avant de les recréer, car les jobs peuvent avancer en parallèle. Les suites existantes ne démontrent pas automatiquement leurs futurs comportements. Pour e2e, utiliser un conteneur de test avec port local 8000 et affichage Xvfb disponibles ; le harnais peut sauter le test si indisponibles. Vérifier aussi Chromium, langues Tesseract et la police utilisée par la fixture synthétique ; toute dépendance absente doit être tracée et résolue sans faire passer le skip pour une validation.

Fiche de clôture de chaque lot : **périmètre et version → skill utilisé ou aucun → contrats/intégrations vérifiés → commandes et résultats → preuves OCR/navigateur si nécessaires → incidents tracker corrigés/revalidés ou blocages encore ouverts → décision de validation limitée à ce périmètre**. Rejouer la suite complète avant de déclarer une livraison applicative ; après une correction, élargir les tests seulement si les nouvelles modifications ou des risques non résolus le justifient.
