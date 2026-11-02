# Pokébourse — Identification fiable, comparaison de marché et marge

Date : **2 novembre 2026**. Statut : **plan global en cours ; T02 implémenté et validé sur fixtures, autres lots non validés par cette livraison**. La rédaction d'une cible ne vaut pas réalisation.

**Recadrage produit :** ajout du parcours de comparaison et d'estimation (J3, T14 à T18). Ces lots sont à réaliser ; leur ajout ne modifie pas l'état des travaux d'identification existants.

## 1. Objectif et définition de « terminé »

Livrer un parcours utilisable : **capturer une annonce et sa photo → identifier la carte et ses attributs → demander confirmation en cas de doute → enregistrer → rechercher les offres comparables et les ventes documentées accessibles → estimer un prix de revente et une marge lorsque les données le permettent**. Identification et calcul restent locaux ; la recherche de marché utilise uniquement les sources externes autorisées et configurées.

Une annonce imparfaite doit toujours aboutir à un résultat explicite et à une action disponible. Une photo illisible ou une référence absente peut empêcher l'identification exacte ; le logiciel doit alors conserver l'annonce et proposer la bonne suite, sans fabriquer d'identité.

Trois jalons de livraison :

- **J1 — parcours complet assisté** : T00 à T09 et T12 réalisés, tests et recette fonctionnelle passants. L'utilisateur peut terminer les cas résolubles, conserver les cas indéterminables et enrichir le référentiel. Les nouvelles preuves OCR restent des suggestions soumises à vérification ; aucun gain statistique n'est annoncé sans mesure.
- **J2 — qualité mesurée et extension éventuelle de l'automatisation** : T10 réalisé sur un jeu indépendant. T11 est une expérience conditionnelle, à réaliser seulement si le diagnostic justifie la vision. Une conclusion documentée « vision non retenue » clôt ce lot ; une expérience négative n'empêche pas J1. Toute nouvelle automatisation passe les critères de T10 avant activation.
- **J3 — comparaison de marché et estimation expliquée** : T14 à T18 réalisés, recette T13 étendue passante, T12 réactualisé. Après enregistrement d'une identité admissible, recherche automatique bornée sur les sources activées, offres en cours et ventes conclues séparées, prix et marge accompagnés de leurs preuves et limites. En cas d'identité incertaine, demander une confirmation avant tout calcul. Les choix ouverts ci-dessous doivent être tranchés avant activation des comportements concernés. Une source de ventes indisponible n'est pas une fonctionnalité livrée : documenter la couverture réelle et faire valider toute réduction du périmètre demandé.

Le chantier couvre l'identification, ses entrées et ses conséquences. Il ne demande ni réécriture générale de Pokébourse, ni automatisation du contournement des marketplaces, ni certification des faux, ni estimation automatique de l'état à partir d'une photo.

### 1.1 Périmètre confirmé avec l'utilisateur

- **Produits :** cartes à l'unité non gradées et cartes gradées **PSA ou PCA**. Les autres certificateurs, lots et produits scellés restent enregistrables selon les parcours existants, mais hors du nouveau périmètre de comparaison qualifiée ; conserver leurs garde-fous et données.
- **Résultat attendu sans action supplémentaire dans le cas nominal :** identité exacte suffisamment étayée, offres ailleurs, estimation de revente et marge si admissibles. La présence d'une annonce et d'une photo ne garantit jamais l'identification ni la disponibilité d'un prix.
- **Prix :** afficher séparément les offres actuellement disponibles et les ventes réellement conclues documentées ; une cote agrégée constitue une troisième catégorie, pas une liste de transactions.
- **Doute sur l'identité/version :** interrompre la valorisation et demander un choix ou une confirmation humaine. Une recherche TCGdex peut aider à résoudre l'identité ; un prix plausible ne prouve pas cette identité.
- **Choix des sources :** confié au cadrage technique. Proposition initiale : guide Cardmarket pour les cotes, eBay pour les offres si accès établi, captures locales et reventes personnelles documentées en complément ; vérifier les capacités en T15, notamment pour les gradées et les ventes conclues.

### 1.2 Choix encore ouverts — ne pas les transformer en décisions implicites

| Choix | État / décision attendue | Partie dépendante |
|---|---|---|
| Zone géographique | France, UE ou monde ; pays de livraison et traitement des devises/importations à préciser | Requêtes, coût livré et comparabilité T16/T17 |
| Données de prix insuffisantes | Estimation indicative, absence d'estimation ou scénario saisi par l'utilisateur : pas encore choisi | Repli et affichage financier T18 |
| Canal de revente | Plateforme choisie par l'utilisateur ou comparaison des canaux : pas encore choisi | Frais et scénario de marge T18 |
| Niveau de comparabilité | Proposition conservatrice : même version/langue/finition/état ; pour les gradées, même certificateur et même note. Assouplissements éventuels à valider | Sélection des preuves T17 |
| Source complémentaire éventuellement payante | Aucun abonnement ni budget validé ; ne pas engager de coût pour obtenir des ventes conclues | Capacités et arbitrage T15 |

Les contrats, interfaces et tests simulés peuvent avancer indépendamment. Un choix manquant ne se remplace pas par une hypothèse silencieuse en production ; consigner les propositions et demander les réponses avant d'activer le comportement dépendant.

## 2. Documents de référence et état de départ

Lire [AGENTS.md](AGENTS.md), [README.md](README.md), [SOURCES.md](SOURCES.md), [SUIVI.md](SUIVI.md), [TASKING_RECHERCHE_CARTES.md](TASKING_RECHERCHE_CARTES.md), [TASKING_RECHERCHE_TENDANCES.md](TASKING_RECHERCHE_TENDANCES.md), [docs/IDENTIFICATION_LEXICALE.md](docs/IDENTIFICATION_LEXICALE.md), [docs/TCGDEX_SYNC.md](docs/TCGDEX_SYNC.md), [docs/ML_PHASE0.md](docs/ML_PHASE0.md) et [MACHINE_LEARNING_DESIGN.md](MACHINE_LEARNING_DESIGN.md).

Le présent document pilote le nouvel enchaînement automatique après identification. La recherche externe générale de `/search` reste explicite comme décrit dans le tasking Recherche/Tendances ; T16 réutilise ses capacités sans déclencher de requêtes à chaque frappe ou consultation d'une fiche.

Pour l'interface : [TASKING_INTEGRATION_DESIGN.md](TASKING_INTEGRATION_DESIGN.md). Pour la capture : [extension/README.md](extension/README.md) et [PROMPT_PATCH_EXTRACTION.md](PROMPT_PATCH_EXTRACTION.md).

Les taskings historiques contiennent des constats antérieurs à leurs implémentations. Vérifier le code courant avant de recréer une fonction ou de reprendre un ancien numéro de migration.

Constats vérifiés lors de la préparation :

| Existant | Conséquence pour ce chantier |
|---|---|
| `detector.py` reçoit les noms de cartes et d'extensions du cache, avec alias historiques en repli | Compléter les alias et la couverture ; conserver ce qui fonctionne |
| `listing_preview.py` ajoute les noms/numéros OCR seulement lorsque les preuves textuelles correspondantes manquent | Préserver cette priorité et éviter de perdre la provenance dans une chaîne concaténée |
| `ocr.py` lit l'image entière et deux bandes de secours, avec taille, concurrence et délais bornés | Mesurer avant/après ; localiser la carte plutôt que supposer sa position dans la photo |
| `resolution.py`, `reviews.py` et le pilote gèrent déjà décisions, snapshots, révisions et export | Étendre les contrats existants plutôt que créer une seconde vérité humaine |
| Le pilote Phase 0 est textuel ; des campagnes manuelles conservent séparément certaines photos | Ne pas assimiler ces photos à des preuves visuelles déjà rattachées et sauvegardées par le pilote |
| Le schéma possède `reference_language`, mais `tcgdex_id` reste unique | Le champ de langue ne suffit pas à permettre plusieurs localisations d'un même identifiant |
| `validation/ocr/marketplaces/run_30_liens.py` compare titre/OCR/combiné ; le résumé compte des statuts | Ajouter les labels indépendants, la description et les mesures de justesse |
| L'espace de travail contient des changements en cours | Inventorier et préserver les modifications ; ne jamais réinitialiser le dépôt pour ce chantier |
| `profitability.py` exploite références enregistrées, annonces locales et guide Cardmarket lié ; `search/external.py` porte une recherche externe distincte | Ne pas présenter l'identification comme une recherche de marché automatique déjà acquise |

Les performances et le volume de catalogue installé ne sont pas déduits du seed, des anciens rapports ou des compteurs de statuts. Les établir en T00/T01.

## 3. Contrat produit et règles invariantes

### 3.1 Résultats et actions

Conserver les statuts compatibles `identified`, `ambiguous`, `unidentified`, `lot`. Ajouter des raisons structurées et une origine de décision, plutôt que multiplier les statuts incompatibles.

| Situation | Résultat visible | Action suivante |
|---|---|---|
| Preuves textuelles suffisantes dans le périmètre qualifié | Identité proposée automatiquement, preuves accessibles | Enregistrer ou vérifier |
| Identité confirmée par l'utilisateur | Confirmation humaine applicable à ces preuves | Corriger ou retirer la confirmation |
| Plusieurs impressions plausibles | À vérifier, différences entre candidats | Comparer et choisir si déterminable |
| Preuves insuffisantes ou contradictoires | Non identifiée/à vérifier, raison précise | Compléter, joindre/recadrer une photo, ou conserver non résolu |
| Référence non chargée | Référentiel local incomplet, si cette cause est établie | Charger l'extension ou lancer la recherche existante |
| Recherche distante sans résultat | Référence non trouvée dans le périmètre interrogé | Recherche manuelle ; ne pas conclure à une absence mondiale |
| Langue/impression hors périmètre | Périmètre non couvert | Recherche dans la locale adaptée ou maintien non résolu |
| Lot ou scellé | Lot/coffret, aucune identité unitaire effective | Conserver et suivre comme lot |
| Service OCR indisponible | Analyse indisponible, annonce conservée | Saisie manuelle ou réessai |
| Identité correcte mais attributs/cote insuffisants | Identité connue, estimation limitée ou indisponible | Compléter les attributs ou la cote |

La confirmation d'ajout d'une annonce, la correction d'un champ et la confirmation de son identité sont des actions distinctes. Une suggestion préremplie ne devient pas une validation humaine par simple enregistrement.

### 3.2 Invariants bloquants

- Aucun lot/scellé ne reçoit une identité unitaire effective, même si une carte principale est reconnaissable. Une erreur de classification peut être corrigée explicitement et auditée avant le choix d'une carte.
- Le titre et la description ne sont jamais remplacés par l'OCR. Une contradiction significative avec la photo est exposée et bloque la nouvelle acceptation automatique.
- Un champ inconnu reste inconnu. Langue du vendeur, langue du site et locale du catalogue ne prouvent pas la langue de l'exemplaire.
- Une identité de catalogue situe une carte dans une extension ; une extension inférée depuis le candidat n'est pas une mention d'extension observée dans l'annonce.
- Nom, suffixes significatifs (`V`, `VMAX`, `GX`, `EX`/`ex`), numéro et extension contribuent à l'identité. Langue de l'exemplaire, finition, édition et état ont leurs preuves propres. Une traduction n'est pas automatiquement une autre impression équivalente.
- `Near Mint` extrait du texte est un état déclaré. Une identité ou une photo générique ne vérifie ni état, ni finition, ni authenticité.
- Un score historique n'est pas un pourcentage de probabilité. Conserver sa compatibilité, afficher son sens, séparer toute probabilité calibrée future.
- Une suggestion OCR, une réparation ou un résultat visuel n'autorise pas à lui seul une nouvelle acceptation automatique en J1. Une identité déjà justifiée indépendamment par le texte conserve son traitement, sauf contradiction significative.
- Préserver `first_seen_at`, décisions humaines applicables, audit, clés étrangères, sauvegardes et calculs monétaires en centimes/bps.
- Traitement des photos et inférence exclusivement locaux. Aucun poids ni image n'est téléchargé pendant une identification hors ligne. Les références publiques peuvent être enrichies par les mécanismes autorisés ; aucune photo ni texte d'annonce n'est envoyé à TCGdex.
- Tests hermétiques : aucun accès distant, y compris téléchargement de modèle, d'image de référence ou requête indirecte depuis un worker.
- Carte gradée : séparer identité de la carte, certificateur, note et numéro de certificat éventuel. PSA/PCA et notes différentes ne sont pas interchangeables ; une cote non gradée ne valorise pas automatiquement un exemplaire gradé.
- Une annonce retirée/inactive n'est pas une vente conclue ; un prix affiché, une enchère en cours ou un montant d'offre négociée non connu ne sont pas un prix de vente réalisé.
- Aucune marge calculée sur une identité incertaine. Après confirmation, les données de prix et les frais doivent encore être admissibles ; ni identité confirmée ni estimation ne garantissent la revente.

## 4. Architecture cible minimale

Réutiliser les modules actuels et extraire uniquement les responsabilités nécessaires :

1. **Observations** : texte brut, champs structurés et leur origine, indices photographiques liés à une image/région. Un champ peut porter plusieurs observations contradictoires.
2. **Qualification produit** : unitaire, lot/scellé ou quantité incertaine. Séparer les objets photographiés des objets effectivement vendus.
3. **Extraction** : noms, numéros, extensions et attributs, sans décision d'identité.
4. **Récupération** : union dédupliquée des candidats structurés et lexicaux, puis des candidats visuels expérimentaux si retenus.
5. **Vérification/classement** : accords, contradictions, couverture et qualités de preuve. Un champ absent n'est pas une contradiction.
6. **Décision commune** : règles d'acceptation, abstention, priorité des décisions humaines et contrôle des révisions.
7. **Projection UI/export/rentabilité** : même identité effective et mêmes restrictions dans tous les parcours.
8. **Recherche de marché** : tâches bornées rattachées à l'identité et à sa révision ; lecture des données locales puis des sources activées, sans bloquer l'enregistrement.
9. **Comparabilité et estimation** : sélection expliquée des preuves, séparation offres/transactions/cotes, scénario de revente et frais explicites.

Le contrat d'une preuve doit pouvoir porter : champ, valeur brute, valeur normalisée, origine, extrait ou image/région, version d'extracteur, qualité technique et éventuelle transformation. Distinguer extrait, déclaré, inféré, corrigé et vérifié. Une confiance qualitative n'est pas une probabilité.

Conserver une représentation transitoire en mémoire pour l'OCR éphémère. La persistance durable des preuves visuelles est un mode explicite distinct, décrit en T04. Ne jamais conserver silencieusement toutes les images analysées.

## 5. Ordre d'exécution

| Lot | Priorité | Dépendances | Résultat |
|---|---|---|---|
| T00 — Inventaire et point de départ | P0 | Aucune | Périmètre, divergences et état initial connus |
| T01 — Vérité terrain et comparateur | P0 | T00 | Premières mesures reproductibles |
| T02 — Corrections déterministes | P0 | T00 ; mesure avec T01 | Lots, langues et états fiables sur les cas ciblés |
| T03 — Contrat de preuves et décision commune | P0 | T00, T02 | Même décision de tous les points d'entrée |
| T04 — Preuves visuelles et annotations | P0 | T01, T03 | Benchmark photos et confirmations reproductibles |
| T05 — Alias et couverture du référentiel | P0 | T02, T03 | Recherche et enrichissement explicables |
| T06 — Lecture photographique locale | P1 | T04, T05 | Cadrage et OCR mesurés |
| T07 — Réparations OCR sous contrôle | P1 | T03, T05, T06 | Suggestions auditables sans identité fabriquée |
| T08 — Parcours utilisateur et capture | P0 | T03 à T07 | Capture → résolution → enregistrement cohérents |
| T09 — Persistance et usage métier | P0 | T03, T04, T05, T08 | Décisions durables et rentabilité admissible |
| T10 — Qualification indépendante | P0 | T01 à T09 | Rapport de qualité et périmètre d'automatisation |
| T11 — Vision et fusion expérimentales | Conditionnel | T10 et besoin visuel démontré | Gain démontré ou abandon motivé |
| T12 — Livraison et exploitation | P0 | T01 à T09 ; réactualisé après T10/T11 | Version utilisable, documentée et réversible |
| T14 — Cartes non gradées et gradées PSA/PCA | P0 pour J3 | T03, T06, T08, T09 | Attributs et confirmation adaptés aux deux parcours |
| T15 — Capacités réelles des sources de prix | P0 pour J3 | T00 ; indépendant des améliorations OCR | Matrice offres/ventes/cotes, accès et limites vérifiés |
| T16 — Recherche de marché après identification | P0 pour J3 | T03, T09, T14, T15 | Orchestration automatique, dédupliquée et révisable |
| T17 — Comparables et preuves de prix | P0 pour J3 | T14, T15, T16 | Offres, ventes et cotes séparées et justifiées |
| T18 — Estimation, marge et parcours complet | P0 pour J3 | T17, choix produit dépendants résolus | Scénario expliqué, recette et limites visibles |

Commencer T01 sur les données disponibles pendant les corrections. Ne pas attendre mille annotations pour corriger un bug déterministe. Ne pas attendre T11 pour livrer J1.

T13 reste la matrice de recette de tous les lots, y compris J3 ; sa numérotation ne désigne pas une étape d'implémentation. Commencer T15 dès maintenant pour détecter une impossibilité d'accès aux ventes avant d'annoncer leur automatisation. J3 peut avancer sans T11, en conservant les confirmations requises en J1 ; il ne dépend d'aucun nouveau modèle visuel imposé.

### T00 — Inventorier et figer le point de départ

- [ ] Relever les modifications de travail, versions, migrations et tests existants ; ne pas écraser les travaux en cours.
- [ ] Exécuter les tests Docker sur les bases temporaires et consigner les échecs initiaux sans les attribuer au chantier.
- [ ] Auditer les entrées : URL, extension, JSONL, saisie, collecte, prévisualisation, fiche, réidentification, worker et validation.
- [ ] Comparer code, documentation et Compose : autorisations réseau réellement actives, persistance des photos, limites OCR, locales et sources de vérité.
- [ ] Inventorier le catalogue sur copie/sauvegarde : cartes/extensions/locales, fiches partielles, images disponibles et manquantes. Ne pas modifier la base réelle pour établir cet inventaire.
- [ ] Figer la version initiale, le catalogue et les rapports existants avant toute comparaison.

**Livrable :** rapport initial versionné, matrice des entrées et lacunes ; liste des acquis à réutiliser. **Acceptation :** aucune référence absente n'est présentée comme un défaut OCR sans vérification.

### T01 — Construire la vérité terrain et le benchmark hors ligne

- [ ] Reprendre les 30 annonces existantes : conserver titre ET description disponibles, photos exactes, provenance et données manquantes. Ne pas compléter les absences par invention.
- [ ] Annoter indépendamment type de produit, identité/impression déterminable, présence dans le catalogue figé, attributs observables, suffisance texte seul puis apport des images.
- [ ] Permettre une identité externe documentée si la carte manque au référentiel, sans lui fabriquer un ID TCGdex ; un ID absent n'est pas une mauvaise prédiction exacte.
- [ ] Séparer annotation indépendante et décision appliquée. Rechercher au-delà des candidats automatiques, arbitrer les désaccords, conserver les lectures initiales.
- [ ] Versionner un manifeste avec empreintes, catalogue, règles, moteur OCR/langues, configurations, partitions et groupes de doublons ; y joindre les images via T04.
- [ ] Séparer acquisition réseau manuelle et rejeu strictement local. Le rejeu refuse un artefact manquant et ne le télécharge pas implicitement.
- [ ] Produire des rapports texte seul, OCR seul, texte+OCR ; ajouter ensuite les variantes de cadrage et de vision sans changer les labels.
- [ ] Étendre à 300 cas diagnostiques, dont au moins 20 % en double lecture indépendante, puis environ 1 000 cas pour les comparaisons. Réutiliser le pilote existant ; ne pas déclarer ces volumes acquis.
- [ ] Constituer séparément un audit aléatoire représentatif du flux local admissible et un jeu difficile. Documenter les probabilités de sélection ; ne pas assimiler le flux local à tout le marché.

**Livrable :** jeu de développement annoté, protocole, comparateur et rapport initial. **Acceptation :** les compteurs `identified` sont distingués des identités correctes ; toutes les métriques donnent leur dénominateur et leurs exclusions.

### T02 — Corriger les règles de détection

- [x] Reconnaître `nearmint`, `near-mint`, `near mint` et variantes d'espaces/casse ; éviter que `mint` interne annule `near mint`.
- [x] Conserver l'état déclaré brut. Ne pas convertir automatiquement « très bon état », « neuf » ou une note de gradation en état physique vérifié.
- [x] Résoudre les collisions `EX` état/suffixe de carte avec le contexte ; préserver les suffixes discriminants.
- [x] Retirer `en` isolé comme preuve générale d'anglais. Réserver les codes courts à des champs ou contextes explicites ; `VO` seul laisse la langue inconnue.
- [x] Détecter les langues multiples ou contradictoires sans choisir arbitrairement le premier motif. La langue du texte français ne suffit pas à déduire celle de la carte.
- [x] Détecter cadeaux et quantités réellement incluses : « vendu avec 3 cartes en plus », « + 3 cartes offertes », formulations équivalentes retenues par les fixtures.
- [x] Traiter les contre-exemples : « sans lot », « pas un lot », « 3 photos », « avec protection », « une carte au choix parmi 3 ». Une vente au choix ne justifie pas une identité unique de l'annonce.
- [x] Ne pas interpréter le dénominateur, un numéro de série ou un nom d'extension comme une quantité ; ne pas classer « Gem Pack 2 » comme produit scellé sur le seul mot `pack` hors contexte.
- [x] Ajouter les mêmes contre-exemples côté extension et backend ; le backend reste l'autorité de décision.

**Fichiers :** `app/identification/detector.py`, `matcher.py`, modèles, `extension/content/content.js`, suites d'identification et extension. **Acceptation :** matrice de T13 entièrement passante, sans baisse des seuils pour masquer les erreurs.

**Livraison T02 — 2 novembre 2026 :** règles déterministes réalisées et validées sur les fixtures de leur périmètre. `languages` conserve les valeurs explicites reconnues (français, anglais, japonais), `language` reste inconnu en cas de conflit et le matcher s'abstient ; le diagnostic distingue ce conflit d'une référence absente. `condition_raw` conserve l'extrait déclaré exact, sans modifier les équivalences historiques ni vérifier l'état physique. Le contexte de produit est exigé pour `pack` ; les noms d'extensions effectivement présents dans le cache et les numéros étiquetés comme séries sont protégés. Aucun alias « Gem Pack 2 », réparation OCR, changement de seuil, migration, dépendance ou appel distant n'a été ajouté.

**Fichiers de cette livraison :** `app/identification/{detector,models,matcher,diagnostics}.py`, `extension/content/content.js`, `tests/test_identification_reliability.py`, `tests/test_chrome_extension.py`, `tests/test_pipeline_integration.py`, `tests/test_lexical_identification.py`, `docs/IDENTIFICATION_LEXICALE.md`, `extension/README.md` et ce tasking. Les modifications du premier lot T02 restent conservées.

**Vérification Docker :** 297 tests ciblés passants (identification, fiabilité, numéros, lexical/diagnostic, extension, pipeline, prévisualisation, validations humaines et annotation), puis `docker compose run --rm app pytest` : **713 passants**, un avertissement de dépréciation FastAPI/Starlette/httpx déjà présent. Les cas comprennent ingestion et réidentification de lots sans identité unitaire/cote, langues contradictoires et exemple « Evoli V 0113/15 gempack 2 nearmint » conservé non résolu dans le cache de test incomplet.

**Limites et suite :** validation des lignes T13 relevant des règles T02 ; la recette T13 entière, qui dépend des autres lots, n'est pas déclarée acquise. Les règles restent lexicales et bornées aux formulations testées, sans mesure globale de précision. L'extrait d'état et les langues sont exposés dans le résultat compatible ; le contrat de preuves durable complet relève de T03. Les annotations indépendantes et la qualification restent à établir en T01/T10. Aucun autre lot n'est lancé par cette livraison.

### T03 — Séparer preuves, recherche et acceptation

- [ ] Ajouter un contrat de preuves compatible avec les snapshots existants ; conserver les observations concurrentes et la provenance après fusion.
- [ ] Retirer la dépendance à la concaténation de textes comme seule trace d'origine ; distinguer champs saisis, extraits, préremplis et explicitement confirmés.
- [ ] Conserver les contrats JSON/JSONL existants avec ajouts compatibles et validation des nouveaux champs. Une provenance déclarée par le client ne lui confère pas une autorité humaine.
- [ ] Centraliser les règles réutilisées par prévisualisation, import, collecte, fiche et réidentification. Séparer la pure proposition de l'application transactionnelle à une annonce.
- [ ] Exposer les motifs : preuve insuffisante, contradiction, plusieurs candidats, lot, référence locale absente, périmètre non couvert, service indisponible.
- [ ] Conserver les candidats utiles mais contradictoires dans un espace de diagnostic explicitement marqué, sans les promouvoir parmi les suggestions admissibles ni masquer leur contradiction.
- [ ] Vérifier en particulier qu'un nom/numéro apporté par OCR ne transforme pas silencieusement une proposition en confirmation humaine ou en nouvelle acceptation automatique J1.
- [ ] Introduire des versions de pipeline/normalisation et une politique explicite de réexamen ; aucune mise à jour ne supprime l'audit.

**Fichiers :** `models.py`, `pipeline.py`, `matcher.py`, `resolution.py`, `reviews.py`, `app/listing_preview.py`, `capture_preview.py`, `manual_listing.py`, `catalog.py`, services d'ingestion. **Acceptation :** à observations et versions identiques, mêmes candidats/statut/motifs sur tous les points d'entrée ; une prévisualisation ne fait aucune écriture.

### T04 — Rendre les preuves visuelles reproductibles

- [ ] Garder l'OCR courant éphémère par défaut. Créer un mode explicite de conservation locale pour benchmark/annotation ou confirmation durable sur photo, distinct d'une simple analyse.
- [ ] Nettoyer les métadonnées ; stocker les images dans un espace contrôlé persistant, non dans une URL publique ou un répertoire temporaire de conteneur.
- [ ] Rattacher chaque preuve à ses octets exacts par empreinte, à une observation et à la version des transformations ; identifier image et région pour chaque lecture.
- [ ] Prévoir stockage atomique, déduplication, quotas, suppression des temporaires/orphelins, rétention et purge. Une photo peut contenir des contacts : limiter l'archivage aux preuves nécessaires et ne pas l'exporter par défaut.
- [ ] Étendre le pilote et l'export pour les provenances `image` et `both`, en conservant les anciennes annotations textuelles et leurs règles d'éligibilité.
- [ ] Sauvegarder/restaurer ensemble base, manifeste et preuves ; tester la vérification d'intégrité et les fichiers manquants.
- [ ] Si la preuve durable n'est pas conservée, ne pas créer de label visuel reproductible ; signaler les limites de la confirmation opérationnelle. Une preuve supprimée/indisponible rend son label visuel inéligible et demande un réexamen des décisions qui en dépendent.
- [ ] Une simple analyse ne change pas l'identité. Remplacement explicite d'une preuve, ajout de contradiction, décision et invalidation sont des opérations distinctes et auditables.

**Fichiers :** `ocr.py`, `reviews.py`, `dataset.py`, `annotation_pilot.py`, stockage et `backups.py`. **Acceptation :** scénario sauvegarde → restauration → rejeu identique ; fonctionnement éphémère sans persistance implicite ; aucun accès à un fichier hors de l'espace de preuves.

### T05 — Alias, couverture et langues du référentiel

- [ ] Alimenter les noms depuis le référentiel déjà utilisé ; créer des alias contrôlés portant cible, langue/périmètre, provenance et version.
- [ ] Conserver les collisions d'alias et les fautes approchées comme suggestions. Ne pas utiliser une correspondance floue unique comme preuve exacte.
- [ ] Vérifier la cible de « gempack 2 » sur une source de référence et les photos disponibles avant de l'ajouter ; ne pas inventer une équivalence française ou un ID attendu pour le cas B.
- [ ] Distinguer répertoire d'extensions, manifestes, cartes détaillées et images ; afficher ce qui manque et ce qui est effectivement couvert.
- [ ] Réutiliser les files `research.py`/`tcgdex/sync.py`, déduplication, pause/reprise, erreurs et cadence. Pas de seconde file ad hoc, pas d'appel réseau depuis le matcher.
- [ ] Étendre le modèle pour isoler identité et localisations. Préserver les identifiants SQLite, relations humaines, liens Cardmarket et anciennes clés externes lors de la migration.
- [ ] Charger les locales utiles à la demande, sans supposer que les IDs, numéros ou impressions coïncident entre langues/régions. Les rapprochements inter-impressions exigent un lien vérifié séparé.
- [ ] Versionner périmètres et locales réellement pris en charge. Une locale ajoutée n'active pas automatiquement son identification ni sa rentabilité.
- [ ] Conserver la langue de l'exemplaire inconnue si elle n'est pas observée ; la langue d'une fiche de référence est une propriété distincte.

**Fichiers :** `tcgdex/cache.py`, client/modèles/sync, recherche locale, `identification/research.py`, alias Cardmarket et migrations. **Acceptation :** ajout d'une localisation sans écrasement d'une autre ; cas absent conservé et enrichissable ; confirmations et liaisons financières préservées.

### T06 — Améliorer et mesurer le cadrage/OCR

- [ ] Comparer photo entière, recadrage manuel et recadrage automatique sur les mêmes images ; conserver la baseline existante.
- [ ] Introduire d'abord le recadrage manuel utilisable au clavier/avec alternative de saisie ; transmettre ses coordonnées dans le repère correct après orientation EXIF.
- [ ] Expérimenter la localisation par contours/quadrilatères, orientation et perspective ; rejeter les géométries douteuses et proposer le manuel.
- [ ] Séparer carte, boîtier et étiquette de gradation. Plusieurs régions/cartes restent séparées ; ne pas combiner le nom d'une carte et le numéro d'une autre.
- [ ] Une carte détectée sur plusieurs photos ne prouve pas l'absence d'autres objets vendus. Plusieurs vues recto/verso ne deviennent pas un lot par simple comptage d'images.
- [ ] Lire les régions nom/numéro/code/symbole avec quelques échelles et modes de segmentation adaptés ; conserver la lecture originale et éviter les traitements destructifs systématiques.
- [ ] Employer des jeux de caractères adaptés uniquement sur les régions correspondantes ; préserver lettres, préfixes, zéros et suffixes valides selon le référentiel.
- [ ] Mesurer les noms/numéros exacts et l'identité finale, pas seulement le nombre de caractères reconnus. Mesurer séparément échec de localisation et échec OCR sur cadrage humain.
- [ ] Préserver taille maximale 8 Mo, 12 millions de pixels et deux analyses simultanées ; ajouter un budget global de 20 secondes de calcul OCR par image, cancellation et limites mémoire. Ce budget inclut les essais de secours, hors téléversement.
- [ ] Langue OCR non installée, image inexploitable ou délai dépassé : réponse explicite et saisie manuelle, sans boucle infinie ni téléchargement implicite.

**Fichiers :** `ocr.py`, `app/static/ocr.js`, templates concernés, Dockerfile si nécessaire. **Acceptation :** rapport de comparaison et latence p50/p95 sur machine décrite ; essais bornés ; aucune régression des garde-fous ; aucun modèle de détection lourd imposé sans gain démontré.

### T07 — Proposer des réparations OCR contrôlées

- [ ] Générer des hypothèses bornées à partir d'erreurs observées ; garder lecture originale, opération et alternatives. Ne pas modifier silencieusement un numéro textuel.
- [ ] Tester `108/59 → 108/159` comme hypothèse d'insertion, jamais comme vérité acquise. Vérifier le numéro imprimé et le périmètre d'extension plutôt qu'un effectif global générique.
- [ ] Rechercher les autres références compatibles et les cas où la bonne réponse est absente ; l'unicité dans un cache partiel ne démontre pas l'unicité réelle.
- [ ] Exiger un indice discriminant supplémentaire pour mettre une réparation en avant ; l'absence de contradiction ne suffit pas.
- [ ] Ne pas compter les essais OCR d'une même image/région comme preuves indépendantes.
- [ ] Garder les réparations soumises à confirmation humaine en J1 et après, sauf chantier ultérieur explicitement qualifié selon T10.

**Acceptation :** suggestion lisible « lu / proposé / pourquoi / autres possibilités » ; cas négatifs de réparation passants ; un lot reste lot malgré une réparation plausible.

### T08 — Terminer le parcours utilisateur, y compris les erreurs

- [ ] Harmoniser saisie URL, prévisualisation d'extension, import JSONL et fiche : champs détectés préremplis avec provenance, inconnus visibles, aucune confirmation implicite.
- [ ] Afficher texte original, preuves utiles, propositions et attributs séparés ; permettre de corriger sans perdre les originaux.
- [ ] Comparer les candidats sur les détails discriminants : numéro complet, extension, suffixe, langue de référence et images disponibles ; une image absente ne bloque pas la recherche textuelle.
- [ ] Permettre recherche paginée au-delà du top-K, saisie d'un ID vérifié et recherche de référence manquante. Conserver le formulaire pendant les traitements.
- [ ] Ajouter les actions « conserver non identifiée », « classer en lot », « enrichir le référentiel », « confirmer l'identité », « retirer/corriger la confirmation » avec libellés distincts.
- [ ] Éviter les choix forcés de langue/état inventés pour enregistrer : prévoir l'inconnu dans le contrat de stockage ou une représentation compatible qui reste explicitement inconnue.
- [ ] Afficher progression, indisponibilité, délai dépassé et résultat périmé ; empêcher doubles soumissions, confirmation de mauvaise annonce et application d'une réponse OCR ancienne après modification du formulaire.
- [ ] Conserver les captures si Pokébourse est indisponible ; vérifier compatibilité JSONL, permissions minimales et reprise du service worker MV3.
- [ ] Valider dans le navigateur les parcours nominaux, erreurs, navigation clavier et affichage mobile selon Mosaic × Flowbite ; ressources locales uniquement.

**Fichiers :** `manual_listing.py`, `capture_preview.py`, `web.py`, templates, `forms.js`, `ocr.js`, popup/content/background de l'extension. **Acceptation :** toutes les lignes de T13 sont réalisables dans l'interface sans édition SQL ni script de réparation.

### T09 — Protéger les décisions et leur usage métier

- [ ] Relier confirmation, révision, observations et preuves durables ; conserver les décisions humaines applicables lors des réingestions et enrichissements.
- [ ] Tester changement de preuve, retrait, correction, suppression d'import et concurrence ; une ancienne décision ne ressuscite pas après retrait.
- [ ] Ne pas transformer une annotation indépendante en décision active. Ne pas remplacer un choix humain par un nouveau premier candidat automatique.
- [ ] Rejeter les résultats de worker/OCR périmés par version/révision ; ne jamais garder une transaction SQLite pendant le calcul OCR, l'inférence ou le réseau.
- [ ] Mettre en place un contrôle commun d'admissibilité financière : identité effective, portée de langue/impression, attributs nécessaires et source de prix compatible.
- [ ] Préserver les estimations indicatives existantes avec leurs limites ; ne pas les présenter comme rentabilité confirmée si les attributs sont inconnus. Ne pas bloquer l'enregistrement ni le suivi d'achat quand l'estimation est impossible.
- [ ] Empêcher qu'une référence française ou une cote liée seulement par illustration valorise silencieusement une impression étrangère, un lot ou une finition non vérifiée.
- [ ] Appliquer la même décision aux fiches, catalogue, exports, tendances et opportunités ; conserver les formules en centimes/bps.

**Acceptation :** réingestion idempotente sur l'identité et `first_seen_at` ; conflits explicites ; aucun gain net présenté comme établi sur une identité ou portée inadmissible.

### T10 — Qualifier la qualité sans favoriser l'abstention artificielle

- [ ] Sceller un test indépendant des cas utilisés pour ajuster règles, alias, réparations et paramètres. Les 30 cas initiaux deviennent un jeu de développement/régression, pas le test final.
- [ ] Regrouper republications, quasi-doublons et images identiques avant partition ; prévoir un test temporel et un segment d'identités non vues à l'entraînement si un modèle est appris. Les références de catalogue restent disponibles pour la recherche.
- [ ] Rapporter métriques globales et par plateforme, langue, qualité photo, extension, lot/unitaire et couverture de catalogue ; publier effectifs, données absentes et intervalles d'incertitude.
- [ ] Comparer de façon appariée sur les mêmes annonces/groupes ; conserver le catalogue fixe pour isoler l'algorithme, puis mesurer séparément l'apport d'un catalogue enrichi.
- [ ] Avant toute nouvelle acceptation automatique OCR/vision, satisfaire les critères ci-dessous. Sinon conserver les suggestions et publier les limites, sans abaisser les seuils.

| Mesure | Définition / critère |
|---|---|
| Précision automatique | Identités exactes correctes / décisions automatiques acceptées ; cible de promotion : borne inférieure unilatérale à 95 % ≥ 99,5 % sur le périmètre qualifié |
| Couverture automatique | Décisions automatiques / toutes les annonces admissibles ; publier avec la précision et le taux d'identités correctes sur toutes les annonces |
| Gain utile | Pour promouvoir une nouvelle voie automatique : gain ponctuel d'au moins 5 points de couverture correcte sur la tranche ciblée, avec borne inférieure à 95 % du gain apparié > 0 ; précision cible maintenue et pas de dégradation globale démontrée |
| Recherche | Rappel@3 et rappel@K avant classement, sur identités déterminables présentes dans le catalogue ; cible de travail rappel@50 ≥ 98 %, à confirmer en T01 selon périmètre |
| Lots | Précision/rappel et matrice de confusion ; zéro lot connu accepté comme carte unitaire dans la recette et le jeu évalué ; ne pas généraliser ce zéro sans intervalle/effectif |
| Attributs | Exactitude par champ, taux de champ inconnu et taux de fausse complétion ; distinguer déclaration vendeur et observation vérifiée |
| Hors catalogue | Taux de fausse acceptation et orientation correcte vers enrichissement/abstention ; ne pas exclure ces cas des métriques de bout en bout |
| Coût utilisateur | Temps de résolution humaine, nombre d'actions, proportion de cas conservés sans blocage ; mesurer avec et sans assistance |
| Ressources | p50/p95, erreurs et mémoire sur matériel/configuration décrits ; budget global OCR de T06 respecté |

Ces cibles sont des critères proposés de promotion, pas des résultats observés. Pour un audit aléatoire indépendant avec zéro erreur, environ 600 décisions acceptées permettent seulement d'approcher une borne de précision de 99,5 % à 95 % unilatéral. Des erreurs, doublons, tirages stratifiés ou qualifications par segment changent les effectifs et le calcul. Ne pas utiliser cette approximation pour certifier chaque langue/extension.

Une qualification insuffisante signifie « non démontré » ; elle n'autorise ni une promesse de précision, ni une généralisation aux segments non observés. Une simple correction déterministe peut être livrée en J1 avec tests et résultats limités honnêtement présentés, sans attendre une nouvelle automatisation.

### T11 — Expérience conditionnelle de reconnaissance visuelle et fusion

**Déclencheur :** T10 identifie une tranche significative où l'identité est lisible sur l'image, présente dans le référentiel, mais reste inaccessible après cadrage/OCR améliorés. Documenter effectif, causes et potentiel avant d'installer des dépendances.

- [ ] Comparer un descripteur classique (SIFT ou ORB avec vérification géométrique) et un encodeur image compact figé, par exemple DINOv2 ViT-S/14. Leur intérêt relatif est une hypothèse à mesurer.
- [ ] Réserver le hachage perceptuel à une baseline et à l'aide au regroupement des doublons ; ne pas assimiler illustration proche et impression exacte. CLIP peut être un comparateur, pas un choix imposé.
- [ ] Construire l'index depuis les images de référence autorisées, téléchargées séparément, versionnées et vérifiées ; conserver modèle, licence, paramètres, empreintes et pipeline de normalisation.
- [ ] Comparer carte entière et région d'illustration ; mesurer spécifiquement réimpressions proches, langues, boîtiers, masquages et reflets. Ne pas déduire finition/authenticité de la seule proximité.
- [ ] Commencer avec recherche exacte sur vecteurs locaux ; n'ajouter un index approximatif qu'après mesure de latence/mémoire et perte de rappel.
- [ ] Unir les candidats visuels/textuels puis vérifier leurs contradictions ; une branche visuelle peut proposer malgré un OCR absent, sans confirmer automatiquement.
- [ ] Tester un modèle de fusion simple sur features explicites avant un réseau spécialisé : accords, contradictions, qualité, valeurs manquantes, scores et écarts de classement. Inclure la classe « aucun candidat correct ».
- [ ] Séparer entraînement, validation des paramètres, calibration et test final ; ne pas additionner ou normaliser arbitrairement les scores comme probabilités. Ne pas supposer l'indépendance des preuves dérivées de la même photo.
- [ ] Envisager un entraînement spécialisé seulement si les courbes d'apprentissage et plusieurs milliers d'exemples fiables le justifient ; absence de volume = maintien de la solution simple.
- [ ] Fonctionnement sans poids/index : repli OCR/texte, message explicite, aucun téléchargement ou appel externe à l'exécution. Désactivation et retour à la version précédente sans migration destructive.

**Acceptation :** rapport d'ablation et décision intégrer/abandonner. L'intégration de suggestions exige un gain utile et un coût humain acceptable ; l'automatisation exige en plus T10. Un modèle plus complexe sans gain démontré n'est pas retenu.

### T12 — Livrer et exploiter

- [ ] Déployer app et worker compatibles, vérifier migrations sur copie, restauration et parcours nominal. Aucun effacement du volume réel ; sauvegarde vérifiée avant application des migrations à l'instance utilisée.
- [ ] Lire le dernier numéro de migration au moment de coder, ne jamais modifier une migration déjà publiée. Toute nouvelle migration suit `BEGIN IMMEDIATE`, enregistrement dans `schema_migrations`, `COMMIT`, puis tests d'idempotence et conservation des relations.
- [ ] Documenter les dépendances réellement retenues et les modes hors ligne, durées, quotas, stockage/preuves, sauvegarde/purge et solutions de repli. Ajouter seulement les dépendances justifiées par le lot.
- [ ] Mettre à jour README, SOURCES, SUIVI, docs TCGdex/ML et extension selon les fonctions réellement livrées. Résoudre les contradictions documentaires relevées en T00 ; ne pas annoncer une fonctionnalité future comme disponible.
- [ ] Publier une fiche de version : périmètre qualifié, catalogue/modèles, performances observées et limites. Une promotion changeant le rôle indicatif de l'OCR met à jour explicitement contrats, interface, documentation et tests.
- [ ] Prévoir métriques locales agrégées : abstentions, contradictions, corrections humaines, références manquantes, erreurs, latence, taille du stockage. Pas de photos, contacts ou données vendeur privées dans les logs.
- [ ] Prévoir revue des nouvelles erreurs, mises à jour d'alias et réévaluation après modification de modèle/catalogue ; distinguer correction du moteur et nouvelle vérité terrain.
- [ ] Conserver une voie de retour : fonctionnalité désactivable, ancienne version des artefacts, sauvegarde restaurable et données récentes protégées ; ne pas utiliser une restauration ancienne comme rollback automatique qui effacerait les acquisitions récentes.

**Acceptation J1 :** recette de T13, tests requis, notice utilisateur et restauration passantes. **Acceptation J2 :** rapport T10 disponible et décision T11 consignée, y compris si la vision est écartée.

**Acceptation J3 :** T14 à T18 et lignes de recette associées passantes ; choix dépendants de §1.2 résolus, capacités des sources documentées, aucune couverture indisponible présentée comme acquise. Réappliquer les contrôles de livraison T12 au nouveau parcours.

### T14 — Identifier les cartes non gradées et gradées PSA/PCA

- [ ] Séparer carte de référence, langue, finition/édition, état déclaré, présence d'une gradation, certificateur, note et certificat éventuel. Garder inconnu ce qui n'est pas établi.
- [ ] Sur les boîtiers, tenter une lecture locale distincte de la carte et de l'étiquette PSA/PCA ; rattacher chaque indice à sa région, sans prendre la note ou le numéro de certificat pour le numéro de carte.
- [ ] Conserver valeur brute et valeur normalisée de la note ; utiliser une représentation exacte (entier à échelle fixe ou chaîne canonique), jamais un `float` ni une conversion entre barèmes.
- [ ] Exposer les désaccords titre/étiquette/carte. Demander confirmation de l'identité ou de la gradation incertaine avant la valorisation ; ne pas confirmer implicitement en enregistrant.
- [ ] La lecture du nom PSA/PCA ou d'un certificat ne prouve pas l'authenticité du boîtier. Une éventuelle vérification de certificat distante est une capacité distincte, à cadrer et autoriser séparément.
- [ ] Conserver les certificateurs déjà détectés par le projet, sans conversion vers PSA/PCA ni promesse de comparaison qualifiée pour ces autres certificateurs.
- [ ] Prévoir migrations si nécessaires sans modifier les migrations publiées ; préserver décisions humaines et attributs existants. Ajouter des fixtures non gradées, PSA/PCA et des contre-exemples.

**Acceptation :** carte sous protection non assimilée à une carte gradée ; note absente ou illisible non inventée ; carte/grade/certificat correctement séparés ; PSA 10, PSA 9 et PCA 10 constituent des segments distincts. Aucun prix non gradé utilisé comme prix d'un exemplaire gradé.

### T15 — Vérifier les capacités et l'accès aux sources de prix

- [ ] Établir une matrice versionnée par source : offres actives, transactions conclues individuelles, cotes agrégées, couverture non gradée/PSA/PCA, langue/état, port/devise, fraîcheur, provenance, accès, coût et quotas. Distinguer disponibilité théorique et accès réellement configuré pour cette installation.
- [ ] Prioriser le guide public Cardmarket comme cote agrégée et les capacités eBay d'offres actives sous réserve d'accès établi. Ne pas assimiler le guide à une liste d'offres ni présumer qu'il fournit des prix par certificateur/note.
- [ ] Auditer le connecteur eBay existant avant réemploi : bibliothèque ou endpoint présent dans le code ne démontre pas l'accès à une API officielle ni aux ventes conclues. Définir adaptation, authentification et replis nécessaires.
- [ ] Traiter l'historique des ventes comme une capacité distincte : la documentation eBay consultée indique Marketplace Insights restreint et fermé aux nouveaux utilisateurs. Vérifier l'accès effectif avant de promettre un historique automatique. Sans source adaptée, déclarer cette capacité indisponible et soumettre le manque au produit ; aucune simulation de ventes à partir des offres.
- [ ] Réutiliser captures/imports locaux et reventes personnelles avec prix réel documenté ; ne pas assimiler un simple statut « vendu » sans montant à une preuve de prix. Un accès éventuellement payant reste soumis à un choix explicite de budget.
- [ ] Pour Vinted, Leboncoin ou d'autres sources sans accès établi, prévoir captures/imports et liens de recherche manuelle ; ne pas ajouter de recherche serveur automatique sur la seule présence d'un connecteur.
- [ ] Consigner dans SOURCES les moyens réellement retenus, les autorisations, les données transmises et les limites ; aucun secret dans les rapports, fixtures ou logs.

**Livrable / acceptation :** matrice de capacités et décision par source, avec références officielles datées. Chaque capacité manquante est visible et son impact sur J3 explicite ; aucune souscription ou acquisition réelle déclenchée par ce tasking documentaire.

### T16 — Déclencher la recherche de marché après identification admissible

- [ ] Après enregistrement d'une annonce avec identité admissible, mettre en file une recherche de marché sans clic de recherche supplémentaire ; si une confirmation a été demandée, déclencher après cette confirmation. Une suggestion OCR seule en J1 n'autorise pas ce déclenchement comme identité confirmée.
- [ ] Préserver les prévisualisations sans écriture ; aucun job durable ni recherche marketplace à chaque frappe, rechargement ou affichage d'un candidat. La recherche externe générale `/search` conserve son déclenchement explicite.
- [ ] Lire d'abord les observations et cotes locales ; interroger ensuite uniquement les capacités autorisées/activées, en exposant les sources non configurées. Une cote fraîche est réutilisée ; pas de téléchargement complet du guide Cardmarket pour chaque carte.
- [ ] Utiliser le worker et les mécanismes de file/verrou existants si adaptés ; définir clé de déduplication par identité/version/langue/finition/gradation, périmètre géographique et configuration de recherche. Rattacher l'application du résultat à la révision de l'annonce, même si le cache est partagé.
- [ ] Borner tentatives, délais, pagination, nombre de candidats et cadence par source ; respecter `Retry-After`, isoler les erreurs et ne garder aucune transaction SQLite pendant le réseau ou l'OCR. Faire valider les valeurs de configuration et la fraîcheur en T15.
- [ ] Transmettre uniquement les critères structurés nécessaires ; aucune photo, identité de vendeur ou description brute à un service de prix. Identifier séparément données d'identité et observations de marché.
- [ ] Montrer les états « en attente », « en cours », « terminé », « partiel », « indisponible » et « erreur », avec date et portée par source ; proposer un rafraîchissement borné.
- [ ] Une correction d'identité, de langue ou de grade invalide l'estimation associée ; rejeter les réponses périmées. Aucune récursion de recherches automatiques quand un comparable est enregistré ; l'import des offres retenues reste une action distincte.

**Acceptation :** enregistrement nominal → une seule demande de recherche → résultats explicites, sans attendre une nouvelle action ; identité incertaine → confirmation demandée avant calcul ; doublons/réingestions sans répétition inutile ; panne réseau sans perte d'annonce ; changement de PSA 9 à PSA 10 sans réemploi financier des anciens résultats.

### T17 — Construire les comparables et séparer les preuves de prix

- [ ] Conserver source/identifiant/URL, dates d'observation et de transaction si connues, type de preuve, carte/attributs, montant en centimes, devise et port connu/inconnu. Une date de collecte ne remplace pas une date de vente.
- [ ] Afficher trois groupes : **offres en cours**, **ventes conclues documentées**, **cotes agrégées**. Préciser la nature des références manuelles ; une offre disparue reste une offre observée, pas une transaction.
- [ ] Réidentifier les offres candidates : mots-clés identiques ou illustration proche ne suffisent pas. Exclure lots/scellés, mauvaise impression/version/langue/finition et proxy déclaré des comparables exacts ; inconnu n'est ni égalité ni contradiction prouvée.
- [ ] Appliquer la politique de comparabilité validée en §1.2. Pour les gradées, exiger le même certificateur et la même note ; aucun coefficient inventé pour convertir non gradé, PSA ou PCA. Écarter les différences de label/variante de gradation ayant un effet matériel non résolu.
- [ ] Garder les résultats proches mais incomplets dans un groupe « à vérifier / comparaison partielle », avec motif ; ne pas les injecter silencieusement dans la cote qualifiée.
- [ ] Exclure l'annonce évaluée de sa propre référence de prix ; dédupliquer les republications/observations répétées et signaler les doublons probables entre sources sans gonfler le nombre de preuves.
- [ ] Séparer prix article, port et coût livré. Port inconnu reste inconnu ; pas de mélange de devises ou de frais d'importation supposés tant que la politique géographique n'est pas définie.
- [ ] Montrer les critères, différences, exclusions, effectifs indépendants, dates et fraîcheur. Les cotes issues de moyennes ne sont pas comptées comme autant de transactions individuelles.

**Acceptation :** toute preuve retenue est consultable et expliquée ; aucune confusion offre/vente/cote ; PSA/PCA et notes distinctes jamais fusionnés ; aucune revente sans prix réel, doublon ou auto-comparaison ne fabrique un signal de marché.

### T18 — Estimer la revente et la marge, puis qualifier le parcours complet

- [ ] Définir et versionner la méthode d'estimation par type de preuve ; justifier fenêtre de fraîcheur et effectif minimal sur les données disponibles, sans seuil arbitraire présenté comme validé. Ne pas moyenner indistinctement offres, ventes et guide agrégé.
- [ ] Afficher la base de l'estimation : ventes comparables, prix demandés ou cote agrégée ; les différences de statut et de portée restent visibles. Sans preuves admissibles, appliquer uniquement le choix validé en §1.2.
- [ ] Paramétrer le canal de revente et les frais selon le choix produit restant ; afficher prix d'achat, port aller, frais d'achat, prix de revente estimé, frais de vente/port supporté/emballage et autres coûts applicables. Éviter les doubles comptes ; tout coût manquant est signalé, jamais assimilé silencieusement à zéro.
- [ ] Calculer en centimes et points de base avec arrondi `ROUND_HALF_UP` : marge estimée = recettes nettes estimées − coût d'acquisition total. Définir explicitement la base du ROI ; aucun gain réalisé déduit d'une estimation.
- [ ] Indiquer méthode, source, date, quantité et compatibilité des preuves. Une fourchette de scénarios éventuelle n'est pas un intervalle statistique garanti ; aucun pourcentage de confiance fabriqué.
- [ ] Adapter fiche, catalogue, exports, opportunités et retour d'import à la même décision et à la même qualité financière. La rentabilité incertaine ne peut pas produire un verdict d'achat qualifié ; l'annonce reste enregistrable et suivable.
- [ ] Recetter sur fixtures non gradées/PSA/PCA et sources simulées : identité, gradation, recherche, sélection des comparables, frais et affichage. Mesurer séparément justesse d'identification, justesse des comparables, latence et disponibilité ; une source indisponible n'est pas un échec OCR.
- [ ] Valider l'estimation contre des reventes documentées indépendantes si disponibles ; sinon qualifier la méthode et ses limites sans annoncer une précision prédictive non mesurée. Actualiser documentation, migrations/tests, sauvegarde et retour arrière via T12.

**Acceptation :** démonstration reproductible du parcours complet dans les trois segments, sans requête réelle dans les tests ; résultats et abstentions cohérents dans toutes les vues ; aucun calcul avant résolution du doute d'identité ni estimation présentée comme prix de vente garanti. Les critères produit/source non résolus restent explicitement non validés.

## 6. T13 — Matrice de recette obligatoire

T13 est le référentiel de vérification des lots précédents, pas un chantier différé après livraison. Les identités attendues doivent provenir des annotations/fixtures, jamais du premier résultat du moteur testé.

| Cas | Attendu |
|---|---|
| « Évoli V vendu avec 3 cartes en plus » | Lot, aucune identité unitaire effective, aucune valorisation comme carte seule |
| « en plus », « en bon état », `VO` seul | Aucune langue anglaise inventée |
| `Langue : EN`, « carte anglaise », langues contradictoires | Contexte explicite reconnu ; contradiction conservée ; pas de substitution silencieuse par une référence française |
| `nearmint`, `near-mint`, `near mint` | Même normalisation d'état déclaré, aucune vérification physique implicite |
| `Dracaufeu ex`, état non fourni | Suffixe préservé, pas d'état Excellent déduit de `ex` |
| Carte unique avec 3 photos, protection ou boîtier | Aucun lot déduit seulement de ces accessoires/vues |
| « carte au choix parmi 3 » | Aucune identité unitaire arbitraire pour l'annonce entière |
| Titre `Pikachu 58/102`, OCR `15` | Fraction textuelle conservée, OCR non substitué ; désaccord visible si pertinent |
| OCR `108/59`, candidat `108/159` | Hypothèse tracée, alternatives/limites, confirmation humaine nécessaire |
| Mauvaise réparation plausible ou bonne référence absente | Aucune acceptation automatique fabriquée ; raison de l'échec visible |
| « Evoli V 0113/15 gempack 2 », « nearmint » | Extraction brute conservée, alias vérifié seulement, couverture réelle visible ; identité exacte non imposée sans preuve |
| Référence dans une autre locale ou deux localisations du même ID | Aucun écrasement ni équivalence d'impression inventée ; recherche adaptée ou abstention |
| Deux impressions avec illustration identique | Candidats multiples tant que le détail discriminant manque |
| Holo/reverse, photo sans preuve de finition | Finition inconnue, aucune cote spécifique implicitement confirmée |
| Proxy/faux visuellement proche | Aucune conclusion d'authenticité |
| Photo inclinée, carte loin du centre, masquage, reflet | Cadrage/OCR bornés, qualité signalée, correction manuelle disponible |
| Plusieurs cartes/régions | Aucune combinaison nom/numéro provenant d'objets distincts |
| Image absente, invalide, trop grande, OCR saturé ou délai dépassé | Message utile, pas de crash ni blocage de l'enregistrement |
| Poids/index/langue OCR non disponibles | Repli local explicite, aucune récupération distante implicite |
| Formulaire modifié pendant une analyse, worker en retard | Résultat périmé non appliqué |
| Confirmation → réingestion identique → réidentification | Décision applicable conservée, `first_seen_at` inchangé |
| Modification de preuve, retrait et corrections concurrentes | Réexamen/conflit explicite ; audit conservé ; ancienne décision non réactivée |
| Sauvegarde/restauration, preuve manquante, purge | Intégrité vérifiée, inéligibilité/réexamen signalé, aucune preuve prétendument disponible |
| Identité connue, langue/état/cote manquants | Annonce conservée ; limites financières claires et mêmes résultats dans exports/opportunités |
| Même annonce via URL, extension, JSONL et collecte | Proposition cohérente à observations égales, provenance conservée, aucun clic d'ajout assimilé à une validation d'identité |
| Carte non gradée, PSA 10, PSA 9 et PCA 10 de même identité | Segments distincts ; aucun mélange de prix ni conversion de note |
| Étiquette lisible mais note/certificat proches du numéro de carte | Champs séparés ; aucun numéro de certificat pris pour l'identité de la carte |
| Titre PSA 10, étiquette PCA 9 ou note illisible | Contradiction/inconnu visible ; confirmation demandée avant valorisation |
| Cote Cardmarket non gradée seule pour une carte PSA/PCA | Cote non utilisée comme prix de revente de l'exemplaire gradé |
| Identité admissible enregistrée, sources configurées | Recherche de marché automatique bornée et état visible, sans clic supplémentaire |
| Réingestion, rechargement et import d'un comparable | Pas de duplication inutile ni boucle de recherches automatiques |
| Correction d'identité/gradation pendant la recherche | Ancienne estimation invalidée, résultat périmé non appliqué |
| Offre active, enchère, annonce retirée et vente documentée | Natures distinctes ; aucun prix de vente réalisé fabriqué |
| Vente marquée conclue mais prix négocié réel inconnu | Pas de montant supposé comme transaction exploitable |
| Annonce évaluée retrouvée, republication ou observations répétées | Auto-comparaison exclue ; effectifs non gonflés |
| Même nom mais autre version/langue/finition ou lot | Exclusion des comparables exacts avec motif, aucun prix injecté silencieusement |
| Accès eBay/ventes absent, panne ou quota épuisé | Couverture manquante/partielle visible, annonce conservée, aucun faux résultat vide global |
| Prix uniquement affichés/cote générale, preuves insuffisantes | Offres/ventes/cote séparées ; repli seulement selon le choix produit validé |
| Port/frais inconnus, devise ou destination incompatibles | Inconnus visibles ; absence de marge qualifiée fondée sur des coûts supposés nuls |

## 7. Vérifications à exécuter lors de l'implémentation

Commandes existantes, à exécuter dans Docker. Les tests utilisent uniquement des fixtures et bases temporaires ; vérifier l'isolation avant exécution. Les futurs tests des nouveaux modules s'ajoutent aux groupes concernés.

```bash
docker compose run --rm app pytest tests/test_identification.py tests/test_identification_reliability.py tests/test_candidate_number_warning.py tests/test_lexical_identification.py
docker compose run --rm app pytest tests/test_ocr_local.py tests/test_ocr_web.py tests/test_listing_preview.py tests/test_validation_history.py
docker compose run --rm app pytest tests/test_tcgdex_cache.py tests/test_tcgdex_sync.py tests/test_identification_research.py
docker compose run --rm app pytest tests/test_identification_reviews.py tests/test_annotation_pilot.py tests/test_migrations.py tests/test_backups.py
docker compose run --rm app pytest tests/test_chrome_extension.py tests/test_extension_e2e.py tests/test_capture_preview.py tests/test_manual_listing.py tests/test_page_fetch.py tests/test_page_extract.py
docker compose run --rm app pytest tests/test_watch_ingestion.py tests/test_pipeline_integration.py tests/test_imports.py tests/test_catalog.py tests/test_profitability.py tests/test_web.py
docker compose run --rm app pytest tests/test_search.py tests/test_cardmarket.py tests/test_cardmarket_guide.py tests/test_cardmarket_daily.py tests/test_sellers_directory_and_purchases.py tests/test_trends.py
docker compose run --rm app pytest
```

Ajouter des tests de comportement pour les nouvelles règles, les contrats de preuves, migrations, concurrence, limites et replis. Ajouter des fixtures photographiques locales avec labels exacts pour les régressions OCR ; les mocks OCR seuls ne démontrent pas un gain de reconnaissance. Les tests d'intégration du moteur réel doivent être bornés et distincts des benchmarks volumineux.

Pour J3, ajouter les tests hermétiques d'orchestration de marché et de comparabilité PSA/PCA ; les suites existantes ne démontrent pas à elles seules l'acquisition de ces nouveaux comportements. Le réseau est simulé jusque dans le worker et les réponses de prix sont figées.

La recette navigateur utilise les données locales prévues et le réseau marketplace simulé. L'acquisition réelle éventuelle reste un script manuel distinct conforme à SOURCES ; le benchmark relit ensuite les artefacts locaux figés. Ne pas lancer `run_30_liens.py` comme s'il s'agissait déjà d'un rejeu hermétique.

## 8. Suivi et transmission au développeur

Pour chaque lot, enregistrer état (`à faire`, `en cours`, `bloqué`, `validé`, `non retenu` pour T11), dépendances, fichiers touchés, tests/rapports, limites et prochaine action. Un blocage d'annotation humaine ou de référence indisponible ne se résout pas avec des labels automatiques.

Le développement peut produire les outils et commencer sur les fixtures, mais ne peut déclarer acquises des annotations indépendantes, une expertise humaine ou une qualification statistique manquantes. Réaliser toutes les tâches indépendantes ; laisser explicitement ouverts les critères non démontrés.

**Premier lot de travail concret :** compléter le point de départ T00/T01 sur les 30 annonces disponibles, préserver le correctif T02 déjà implémenté et validé sur fixtures, puis raccorder T03. Vérifier les acquis sur l'état courant avant les travaux de cadrage et de vision.

**Suite au recadrage marché :** préserver le T02 déjà implémenté et vérifier son état courant plutôt que le refaire. Démarrer T15 et recueillir les choix ouverts de §1.2 ; préparer ensuite les contrats T14/T16/T17. Ne pas attendre un nouveau modèle visuel pour vérifier les sources et ne pas engager une implémentation financière dépendante d'un arbitrage encore absent.

**Dossier final attendu :** code et migrations nécessaires, contrats compatibles, recette end-to-end, rapport de benchmark avec vérité terrain, procédure d'exploitation/restauration, périmètre couvert et registre des limites. Aucun lot n'est déclaré validé sur la seule base d'une démonstration réussie ou du nombre de statuts `identified`.

## 9. Références techniques pour les expériences

Ces sources documentent des méthodes ; elles ne démontrent pas leur performance sur Pokébourse. Figer les versions effectivement retenues au moment des expériences.

- [Tesseract — qualité d'entrée, redressement et segmentation](https://tesseract-ocr.github.io/tessdoc/ImproveQuality.html).
- [OpenCV — correspondances locales et homographie](https://docs.opencv.org/4.x/d1/de0/tutorial_py_feature_homography.html).
- [DINOv2 — représentations visuelles](https://arxiv.org/abs/2304.07193).
- [CLIP — apprentissage image/texte](https://proceedings.mlr.press/v139/radford21a.html).
- [Calibration des probabilités — Guo et al.](https://proceedings.mlr.press/v70/guo17a.html).
- [TCGdex — contrat d'une fiche de carte](https://tcgdex.dev/rest/card).

Références d'accès marché consultées lors du recadrage, à revérifier en T15 ; elles ne constituent pas la preuve d'un accès configuré sur cette installation :

- [eBay Browse API — recherche d'offres et authentification](https://developer.ebay.com/develop/api/buy/browse_api).
- [eBay — Marketplace Insights restreint et non ouvert aux nouveaux utilisateurs](https://www.developer.ebay.com/api-docs/buy/static/ref-buy-browse-filters.html).
- [Cardmarket — guide de prix et catalogue téléchargeables, guide actualisé quotidiennement](https://news.cardmarket.com/en/StarWarsUnlimited/were-making-the-price-guide-and-product-catalogue-available-for-download).
