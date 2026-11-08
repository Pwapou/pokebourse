# Pokébourse — Conception de la phase Machine Learning

**Revue du 8 novembre 2026 : conception ML, pas moteur livré.** Le [suivi consolidé](TASKING_PROJET.md) et [Identification/T01–T11](TASKING_IDENTIFICATION_FIABLE.md) donnent l'état courant. Originaux, reviews, résolution, export, lexique, preuves visuelles et localisations existent déjà. Les annotations indépendantes et la qualification restent ouvertes ; aucun ranker, embedding ni modèle visuel n'est déclaré disponible. Les exemples de tables ci-dessous sont conceptuels : ne pas les appliquer comme une migration supplémentaire dupliquant le schéma existant.

1. Construire d’abord une vérité terrain humaine, historisée et résistante aux nouvelles collectes.
2. Traiter l’identification comme un rattachement d’entités : recherche de candidats, classement, puis abstention possible.
3. Mesurer séparément la couverture du catalogue, le rappel des candidats et la qualité de la décision finale.
4. Remplacer les listes figées par des dictionnaires issus de TCGdex et établir une référence lexicale solide.
5. Comparer règles, régression logistique et LightGBM sur les mêmes candidats avant de complexifier.
6. Tester les embeddings seulement si le diagnostic justifie leur apport ; mesurer séparément leur gain.
7. Garder les règles de décision, les contradictions et les preuves lisibles hors du modèle.
8. N’automatiser que les segments dont la précision a été vérifiée ; conserver la validation ailleurs.
9. Mesurer dès le pilote le plafond du texte et le potentiel des photos ; prioriser OCR ou modèles textuels selon les erreurs.
10. Déployer progressivement sur CPU, avec artefacts versionnés, mesure de latence et retour aux règles.

Document de conception, daté du **1er novembre 2026**. Il décrit des développements proposés, sans les implémenter. Les volumes, gains et latences ci-dessous sont des hypothèses ou critères d’acceptation, pas des performances observées.

Le développement du premier lot textuel de phase 0 est suivi séparément dans [docs/ML_PHASE0.md](docs/ML_PHASE0.md), avec son périmètre livré et les critères restant à satisfaire.

## A. Cadrage et préalable indispensable

### A.1. État courant et prérequis restant ouverts

| État vérifié au 8 novembre | Conséquence pour la conception |
|---|---|
| Quatre statuts et score entier conservés ; observations/versionnement T03 depuis `0022` | Réutiliser les contrats ; le score historique n'est pas une probabilité |
| Originaux/snapshots, reviews et résolution communes, pilote/export (`0012`–`0014`) | Ne pas recréer la boucle humaine ; constituer les labels et respecter les révisions |
| Vocabulaire issu du catalogue, trigrammes et distance d'édition, candidats classés puis bornés | Mesurer la baseline actuelle ; l'ancien plafond arbitraire à 20 résultats n'est plus le diagnostic courant |
| Alias/localisations et sync par locale (`0024`–`0026`) | Isoler les localisations ; une locale chargée ne qualifie pas le matching ou les prix de cette langue |
| Détecteur sans français implicite ; `und` pour captures, défaut historique maintenu pour anciens JSONL | Distinguer observation de langue et défaut de stockage ; ne pas entraîner sur une langue supposée |
| Preuves visuelles explicites, intégrité/sauvegarde/purge (`0023`) | Rattacher les images durables ; les campagnes séparées ne deviennent pas automatiquement des labels visuels |
| Inventaire figé et rejeu T00/T01, pas de vérité terrain humaine complète | Les volumes/rapports datés ne mesurent pas une précision actuelle ; T01/T10 restent ouverts |
| Contrôle d'admissibilité métier complet et nouveau workflow OCR/choix avant ajout encore à intégrer | Réutiliser Identification/T08–T09, puis T14–T18 pour le marché ; conserver les formules financières |

Le catalogue de la sauvegarde du 3 novembre est inventorié dans [STATUS_T00_T01.md](validation/ocr/evaluation/STATUS_T00_T01.md). Les 15 000 à 40 000 cartes citées dans le prompt initial n'étaient pas une mesure locale ; aucun inventaire de base opérationnelle n'a été refait par cette revue.

Le ML ne résout ni un catalogue absent, ni un texte sans discriminant. Sans labels, une amélioration reste invérifiable : commencer par des exemples fiables et des mesures.

### A.1 bis. Prérequis du projet et ordre de réalisation

Conserver **FastAPI, SQLite, le worker Python et Docker sur CPU**. Ces adaptations préparent les données et la mesure ; elles ne nécessitent ni GPU, ni base vectorielle, ni service ML séparé. Installer les dépendances de modèles uniquement pour une expérience justifiée.

| Échéance | Adaptation et points de raccordement | Critère vérifiable |
|---|---|---|
| Avant les annotations | Dans l’ingestion et les imports, conserver titre original et description explicite, leur provenance et un snapshot ; séparer les champs observés des champs calculés | Une réidentification ne modifie jamais les preuves originales ; les anciennes entrées sans original fiable sont signalées et exclues du train textuel |
| Avant les annotations | Corriger les valeurs inconnues dans `detector.py`, les modèles et les exports ; distinguer extrait, supposé et vérifié pour langue/variante/état | Une langue absente reste inconnue ; un défaut historique « fr » ne devient pas une preuve |
| Avant les annotations | Ajouter snapshots, annotations, décisions et attributs vérifiés selon A.3 ; interface dans `catalog_detail.html` et routes associées dans `web.py` | Une correction, un retrait et une double lecture sont traçables ; la recherche humaine dépasse le top-K |
| Avant les annotations | Résolution commune dans `collectors/service.py` et `catalog.py` | Une collecte identique conserve la correction ; une preuve modifiée exige un réexamen ; une écriture concurrente obsolète est rejetée |
| Avant le benchmark | Inventorier cartes, extensions, langues, descriptions et images ; définir le périmètre couvert et compléter TCGdex via `tcgdex/cache.py` | Rapport de complétude et catalogue versionné disponibles ; aucune couverture globale supposée |
| Avant le benchmark | Corriger accents, numéros, alias et troncature des candidats ; séparer extraction, récupération, classement et décision | Baseline lexicale reproductible et causes d’échec mesurées |
| Avant l’entraînement | Export JSONL, regroupement des doublons, partitions, script d’évaluation et journal `identification_runs` | Mêmes entrées et candidats rejouables ; aucun label de test utilisé pour apprendre ou choisir un seuil |
| Avant le déploiement | Calcul hors transaction SQLite, artefacts locaux versionnés, modes observation/ML et repli mesuré | Latence mesurée, validation humaine prioritaire et retour arrière vérifié |
| Avant exploitation des résultats | Contrôle d’éligibilité entre identité effective et rentabilité | Une identité acceptée ne suffit pas si les attributs nécessaires à la comparaison restent inconnus |

**Prochaine étape :** utiliser les outils déjà livrés pour constituer les annotations indépendantes et le diagnostic T01/T10, tout en développant T06/T07/T08.2/T09 selon le plan actif. Les 300 annotations ne sont pas acquises par l’existence du pilote. Ce lot apporte une valeur propre même si aucun modèle n’est ensuite déployé. Les tests de non-régression associés sont précisés en G. Les autres lignes deviennent des jalons successifs, sans refonte préalable de toute l’application.

### A.2. Unité de validation et interface minimale

Une validation confirme le **rattachement à une entrée TCGdex donnée**, sur une version précise des données observées. Elle ne certifie ni authenticité, ni état, ni édition, ni prix. Une variante reverse ou une première édition peut partager l’entrée de référence : ces attributs restent séparés, explicitement inconnus lorsqu’ils ne sont pas vérifiables.

Le parcours de fiche déjà livré fournit texte original et description utile, photo disponible, cinq candidats avec nom/extension/numéro/identifiant, recherche libre dans tout TCGdex et actions « Confirmer », « Choisir une autre carte », « Lot », « Hors périmètre », « Carte absente du catalogue », « Preuves insuffisantes ». La recherche complète est indispensable pour corriger un défaut de récupération. Une correction peut ensuite être révisée ou retirée, avec historique.

Conserver les quatre statuts publics. Un objet hors périmètre ou absent du catalogue reste `unidentified` ; une hésitation entre candidats reste `ambiguous`. Distinguer « carte absente » et « impossible à déterminer » dans les motifs humains.

Demander si la décision repose sur le texte, la photo ou les deux, et si le texte seul suffit. Une carte reconnue sur photo constitue une vérité d’identité utile, mais ne justifie pas l’identification automatique d’un texte indécidable. Enregistrer également la vérification éventuelle de langue et de variante, indépendamment du rattachement.

Échantillonnage initial proposé : 50 % d’`ambiguous`, 25 % d’`unidentified`, 20 % d’`identified`, 5 % de `lot`, couvrant plateformes, langues, extensions et descriptions manquantes. Pour mesurer la production, conserver aussi un échantillon aléatoire représentatif et sa probabilité de sélection ; la file de cas difficiles biaise les résultats.

### A.3. Schéma SQLite proposé

Des tables associées conservent annotations indépendantes, décisions effectives, révisions et preuves observées. Les tables de production sont déjà définies par `0012`, `0013`, `0014`, puis étendues par `0022`–`0026`. Utiliser leurs contrats actuels ; pour toute donnée réellement nouvelle, vérifier le dernier numéro disponible (`0026` à cette revue). Le schéma ci-dessous illustre la conception initiale, pas une migration prête à exécuter :

```sql
CREATE TABLE listing_identification_snapshots (
    id INTEGER PRIMARY KEY,
    listing_id INTEGER REFERENCES catalog_items(id) ON DELETE SET NULL,
    input_hash TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    image_evidence_hash TEXT,
    image_evidence_ref TEXT,
    normalization_version TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    UNIQUE(listing_id, input_hash)
);

CREATE TABLE listing_identification_reviews (
    id INTEGER PRIMARY KEY,
    snapshot_id INTEGER NOT NULL
        REFERENCES listing_identification_snapshots(id),
    outcome TEXT NOT NULL CHECK(outcome IN (
        'matched', 'lot', 'not_card', 'no_catalog_match',
        'insufficient_evidence', 'withdrawn')),
    validated_card_id INTEGER REFERENCES pokemon_reference_cards(id),
    validated_tcgdex_id TEXT,
    review_kind TEXT NOT NULL CHECK(review_kind IN (
        'annotation', 'decision', 'adjudication')),
    supersedes_review_id INTEGER REFERENCES listing_identification_reviews(id),
    reviewed_annotation_ids_json TEXT NOT NULL DEFAULT '[]',
    verified_attributes_json TEXT NOT NULL DEFAULT '{}',
    validated_by TEXT NOT NULL CHECK(length(trim(validated_by)) > 0),
    validated_at TEXT NOT NULL,
    evidence_basis TEXT NOT NULL CHECK(evidence_basis IN (
        'text', 'image', 'both')),
    text_sufficient INTEGER NOT NULL CHECK(text_sufficient IN (0, 1)),
    catalog_version TEXT NOT NULL,
    sampling_probability REAL CHECK(
        sampling_probability > 0 AND sampling_probability <= 1),
    comment TEXT,
    CHECK((outcome = 'matched' AND validated_card_id IS NOT NULL
              AND validated_tcgdex_id IS NOT NULL)
       OR (outcome <> 'matched' AND validated_card_id IS NULL
              AND validated_tcgdex_id IS NULL))
);

CREATE INDEX identification_reviews_latest
    ON listing_identification_reviews(snapshot_id, id DESC);
```

`validated_card_id` référence `pokemon_reference_cards.id` pour l’exploitation courante. Copier aussi `validated_tcgdex_id` à la décision et conserver un catalogue immuable identifié par `catalog_version` : une jointure vers le catalogue courant ne suffit pas pour reproduire un label historique. Vérifier la cohérence des deux identifiants à l’écriture et préserver les références historiques lors des synchronisations.

Une `annotation` est une lecture indépendante ; elle ne remplace jamais la décision effective. Une `decision` est une validation simple, une `adjudication` tranche les annotations référencées dans `reviewed_annotation_ids_json`. La validation courante est la dernière décision ou adjudication du snapshot courant, y compris un retrait. Conserver les révisions en ajout seulement ; relier la révision précédente par `supersedes_review_id`. Exposer les champs `validated_*` depuis cette résolution. Pour le pilote, ne montrer ni suggestion ni première annotation à la seconde personne ; mesurer l’accord avant arbitrage, sur l’identité et séparément sur la suffisance du texte.

`verified_attributes_json` suit un schéma validé par le service : clés autorisées `language`, `variant`, `edition`, `condition`, chacune avec `value`, `status` (`unknown` ou `verified`) et `evidence_basis`. Une valeur vérifiée exige une preuve ; une valeur inconnue reste nulle. Les attributs extraits ou supposés restent dans les résultats automatiques, sans être promus en validations. Valider également les listes d’annotations, leur snapshot commun et les chaînes de révision dans la transaction d’écriture ; le SQL ci-dessus ne suffit pas à garantir ces invariants.

L’empreinte couvre titre, description, preuves visuelles et version de normalisation, sans prix ni `last_seen_at`. Une collecte identique conserve la validation ; un contenu modifié demande réexamen. Une preuve photographique nécessite `image_evidence_ref` vers un fichier durable ou un manifeste d’images et son empreinte : une URL distante seule ne suffit pas. Sauvegarder ces preuves avec les données et définir leur rétention ; une preuve devenue indisponible est signalée dans les exports. Une modification du normaliseur impose une réconciliation explicite des snapshots, sans effacement de l’historique.

La priorité de résolution est : validation humaine applicable, décision automatique admissible, abstention. L’ingestion et la réidentification doivent passer par cette résolution commune ; préserver la priorité humaine déjà implémentée et tester toute extension des preuves. Vérifier de nouveau le snapshot au moment d’enregistrer, pour détecter une modification concurrente.

Suivre `migration_runner.py` : fichier SQL ordonné, `BEGIN IMMEDIATE`, insertion du nom dans `schema_migrations`, `COMMIT`. Ne modifier aucune migration déjà publiée ; vérifier le répertoire courant. `ON DELETE SET NULL` préserve la suppression actuelle d’un lot d’import sans bloquer sur les snapshots ; prévoir une purge explicite des données d’apprentissage et une rétention limitée. Tester création, mise à niveau, réapplication, intégrité des clés, restauration et concurrence avec le worker. `validated_by` provient d’une identité opérateur fiable ; en usage local mono-utilisateur, définir un identifiant local stable, sans prétendre disposer d’un système de comptes existant.

### A.4. Quantité et qualité attendues

Commencer par **300 annotations pilotes**, dont 20 % en double lecture, puis **1 000** pour diagnostiquer les erreurs et comparer les approches sans apprentissage. Viser ensuite **3 000 à 5 000 annonces distinctes**, couvrant au moins 200 entrées et plusieurs dizaines d’extensions lorsque le flux le permet, avant un premier ranking supervisé. Ces seuils sont des budgets de départ : une courbe d’apprentissage décidera si davantage de labels est rentable.

Viser au moins 98 % d’accord sur le rattachement dans le pilote ; arbitrer les désaccords et clarifier les consignes. À deux minutes par annotation, 3 000 exemples représentent environ 100 heures, hors arbitrage. Mesurer ce temps sur les 300 premiers ; réduire l’ambition ML si cette capacité n’existe pas.

Le seuil minimal d’auto-étiquetage proposé est une **borne inférieure unilatérale à 95 % de la précision au moins égale à 99,5 %**, sur le segment concerné. Avec zéro erreur, environ 600 observations indépendantes sont nécessaires. Un score règles de 90 ne satisfait pas cette condition statistique. En attendant, garder les propositions comme labels faibles distincts.

### A.5. Diagnostic du pilote : plafond textuel et orientation des expériences

Sur les 300 annonces, annoter d’abord le texte seul puis examiner les photos. Mesurer séparément deux axes : (1) identité déterminable par le texte, uniquement avec les photos, ou indéterminable avec les preuves disponibles ; (2) pour les identités déterminées, présence ou absence dans le catalogue figé. Une carte absente du catalogue peut être reconnaissable sur photo : ces axes ne sont pas exclusifs. Rapporter les effectifs et l’incertitude, en distinguant échantillon représentatif et cas difficiles.

Classer les échecs : catalogue incomplet, extraction erronée, candidat manquant, mauvais classement, preuve absente ou rejet métier. Le classement supervisé ne traite directement que certaines de ces causes. « Dracaufeu excellent état » ne permet pas de départager des cartes sans autre discriminant ; apprendre la carte la plus fréquente ne constitue pas une preuve d’identité.

**Jalon obligatoire :** produire ce diagnostic avant de choisir une famille de modèles. Si les informations décisives sont principalement visuelles, avancer un essai OCR ciblé avant le cross-encoder, voire avant le ranker. Sinon privilégier catalogue, extraction et classement textuel. Le pourcentage d’annonces résolubles par le texte est une estimation humaine du potentiel, pas une garantie de performance automatique.

## B. Formulation du problème ML

### B.1. Rattachement d’entités par récupération et ranking

Une classification fermée demanderait trop de labels par carte et gérerait mal les nouveautés. Retenir l’**entity linking avec abstention**, par recherche puis classement : une nouvelle carte entre dans l’index sans réentraîner toutes les identités.

L’entrée est `x = (titre original, description disponible, champs extraits et provenance)`. Le catalogue versionné est `C_v`, avec une représentation textuelle déterministe par carte : nom, alias vérifiés, extension, numéro local, effectifs officiels, rareté disponible. Ne pas inventer une description marketing.

Le récupérateur produit `R_K(x) ⊂ C_v`, initialement `K = 50`. Le modèle attribue `sθ(x,c)` aux candidats. La sortie comprend top-5, carte retenue ou absence de décision, statut, indices probants, contradictions, versions et éventuelle probabilité calibrée. L’identité peut rester indéterminable même si tous les candidats existent dans le catalogue.

### B.2. Apprentissage et décision

Pour le ranking supervisé, chaque annonce est un groupe ; la carte validée reçoit une pertinence 1, les candidats réellement incompatibles 0. Une perte par paires peut s’écrire :

```text
L = somme_x somme_(c+,c-) w(x,c+,c-)
        × log(1 + exp(-(sθ(x,c+) - sθ(x,c-))))
```

LambdaRank pondère les gradients notamment par l’effet des inversions sur NDCG ; cette expression en donne le principe. Pour un cross-encoder, commencer par une entropie croisée binaire sur paires.

Un score de ranking, une similarité cosinus ou une sortie sigmoïde ne sont pas automatiquement une probabilité de bonne identification. Estimer séparément `P(top-1 correct | scores, écart top-2, nombre de candidats, champs observés, contradictions)` sur des prédictions hors apprentissage, y compris les échecs de récupération. Une régression logistique de `scikit-learn` suffit d’abord ; réserver l’isotonique aux volumes suffisants. [Calibration des probabilités, scikit-learn](https://scikit-learn.org/stable/modules/calibration.html).

Utiliser uniquement des variables disponibles à l’inférence : la présence de la **vraie** carte dans le catalogue ou le top-K nécessite le label et ne peut pas être une feature. La calibration porte sur la distribution cible, avec erreurs de récupération et cas hors catalogue ; conserver un échantillon représentatif indépendant ou justifier une pondération par probabilités de sélection. Les quotas de cas difficiles du pilote ne représentent pas cette distribution.

Un calibrateur entraîné sur 300–500 annonces peut disposer de trop peu d’erreurs pour estimer la zone de haute confiance. Publier les effectifs et les erreurs par tranche ; qualifier la précision d’acceptation par un audit indépendant, jamais par la seule valeur de probabilité. Tout changement du catalogue, du récupérateur, de K, des features ou du modèle impose une vérification et, si nécessaire, une nouvelle calibration avant promotion.

Le modèle apprend l’ordre ; les règles gardent la politique : lots/scellés, contradictions fiables, minimum de preuves, seuil d’acceptation et abstention. Exemple d’explication : « nom proche ; numéro local exact ; extension non confirmée ; deux éditions possibles : vérification requise ». Une contribution de feature décrit le modèle ; elle ne remplace pas une preuve dans l’annonce.

## C. Stratégie de données

### C.1. Dataset reproductible et négatifs utiles

Exporter les derniers labels humains applicables et arbitrés, associés aux snapshots, à la provenance de preuve et au catalogue figé. Conserver le texte original et une normalisation versionnée. Ne jamais utiliser `catalog_items.name` réécrit par le matcher comme vérité d’entrée lorsque `original_title` existe : ce serait une contamination par la prédiction précédente.

Produire les candidats avec la version du récupérateur évaluée. Retenir des négatifs difficiles : même Pokémon autre extension, même numéro autre série, suffixes EX/GX/VMAX différents. Ajouter quelques négatifs faciles, sans les laisser dominer. Une variante non distinguée par le schéma TCGdex n’est pas une fausse identité. Exclure des négatifs les cas non tranchés.

Si la carte positive manque des candidats, comptabiliser un échec de récupération. On peut l’ajouter explicitement pour entraîner le reranker, avec provenance « positif injecté », mais jamais pour embellir les résultats de test. Les groupes uniquement négatifs et les cas absents du catalogue alimentent surtout l’évaluation d’abstention et la calibration.

Plafonner les cartes populaires et vendeurs répétitifs, avec pondération modérée par carte/extension. Rapporter les métriques macro et par fréquence. Les labels visuels au texte insuffisant servent à mesurer les limites textuelles et l’abstention, sans constituer des exemples univoques.

Augmenter uniquement le train : suppression de description, retrait de numéro, accents, casse, permutations plausibles, fautes observées et abréviations vérifiées. Si la suppression retire le seul discriminant, exclure l’exemple augmenté de l’apprentissage du ranking à label unique : les autres cartes plausibles ne deviennent pas des négatifs. Ces exemples peuvent alimenter un jeu synthétique distinct de robustesse à l’abstention, jamais remplacer l’audit sur le flux réel. Ne jamais transformer `4/102` en `4/100`, ni changer de variante en conservant artificiellement le label. Commencer sans paraphrases génératives : leurs gains doivent justifier leur coût de contrôle.

### C.2. Partitions sans fuite et versions

Avant tout split, former des groupes reliant même `(source, external_id)`, republications, photos identiques et textes quasi dupliqués. Utiliser empreintes exactes puis similarité de n-grammes pour proposer les rapprochements ; vérifier les seuils pour éviter de fusionner tous les titres « Pikachu ». Les variantes d’un exemple augmenté restent dans son groupe.

Répartition indicative : **60 % train, 15 % validation, 10 % calibration, 15 % test**, par groupes, avec test constitué de la période la plus récente. Retirer du train les groupes réapparaissant dans le futur test et contrôler les republications entre plateformes. Ajuster les hyperparamètres sur validation et le calibrateur sur calibration. Séparer dans les données de développement le réglage des seuils de l’ajustement du calibrateur, ou employer des prédictions hors pli groupées ; verrouiller ensuite le pipeline et les seuils avant le test. Ces proportions sont indicatives : dimensionner séparément la qualification selon F.2, sans sacrifier ses effectifs à un split fixe.

La même carte peut apparaître dans plusieurs partitions : reconnaître de nouvelles annonces d’une carte connue est un usage réel. Ajouter une épreuve distincte par extensions/cartes jamais vues dans les labels d’entraînement, toujours présentes dans le catalogue autorisé. Pour rejouer historiquement la production, utiliser le catalogue disponible à la date considérée.

Chaque livraison possède un manifeste : snapshots, groupes, partitions, empreintes textes/catalogue, versions règles/features/normalisation, graine, origine des labels, exclusions et date. Commencer avec `JSONL` immuable et SHA-256 ; envisager Parquet/DVC selon le volume et le partage. Le test reste humain, sans augmentation ni labels faibles ; renouveler un test futur après plusieurs cycles de sélection.

### C.3. Auto-labellisation contrôlée

Le score règles ≥ 90 n’est qu’un filtre de présélection. Un ex æquo reste ambigu dans le moteur courant ; conserver le contrôle d’unicité et de marge, indépendamment du score. Exiger plusieurs indices concordants, aucune contradiction fiable et aucune détection de lot. Nom plus numéro local seuls ne prouvent pas nécessairement l’extension.

Auditer aléatoirement chaque cohorte admissible et appliquer le seuil statistique de A.4. Distinguer `human` et `rule_pseudo` dans les exports ; ne jamais renseigner `validated_by` avec le moteur. Commencer avec un poids de 0,2 et au plus un exemple faible par exemple humain dans le train. Comparer avec/sans labels faibles et sans feature « score règles » pour détecter la simple imitation. Tout désaccord avec une validation humaine exclut le pseudo-label. Aucune récursion automatique modèle → pseudo-labels → même modèle avant un protocole spécifique validé.

## D. Choix des modèles — options comparées

### D.1. Comparaison et ordre d’essai

Les latences sont des **budgets exploratoires par annonce, modèle chargé**, à mesurer dans Docker sur le CPU cible, pour `K ≤ 50`, hors collecte, synchronisation et téléchargement.

| Famille | Données requises | Effort / maintenance | Budget CPU indicatif | Explication et risque principal | Moment pertinent |
|---|---|---|---|---|---|
| Règles améliorées, RapidFuzz, FTS5/BM25 | Aucun label pour construire ; 1 000 pour évaluer | Faible à moyen ; alias à maintenir | 10–100 ms | Correspondances explicites ; bruit lexical et troncature | Immédiatement ; référence obligatoire |
| Embeddings multilingues gelés | Catalogue textuel ; mêmes labels d’évaluation | Moyen ; index lié au modèle | 50–300 ms | Similarité globale peu explicative ; confusion entre numéros | Après diagnostic des erreurs lexicales |
| LightGBM LambdaRank | Environ 3 000–5 000 annonces variées | Moyen ; features et recalibration | 1–20 ms de ranking, hors features | Contributions inspectables ; biais des labels et surapprentissage | Candidat supervisé à comparer à la régression logistique |
| Cross-encoder ajusté | Plutôt 5 000–10 000 annonces, nombreux négatifs difficiles | Élevé ; entraînement, optimisation, déploiement | 200–1 000+ ms sur top-10/20 | Interaction texte/carte riche ; justification indirecte | Seulement si un plafond lexical/structuré subsiste |
| Vision ciblée | Centaines à milliers d’images par distinction visée, selon diversité | Élevé ; cadrage, qualité, versions | 100–1 000+ ms hors acquisition | Preuves localisables ; reflets, dos, montages, variante invisible | Potentiel mesuré dès le pilote ; essai ciblé si besoin démontré |

Ces seuils ne garantissent rien ; multiplier les paires négatives ne crée pas d’annonces indépendantes.

Ordre expérimental recommandé : score déterministe amélioré, régression logistique sur les paires, puis LightGBM sur les mêmes features et les **mêmes ensembles de candidats**. Comparer à K fixé pour isoler l’effet du classement. Ajouter ensuite le cosinus ou une récupération dense en ablation si les erreurs le justifient ; les embeddings ne sont pas un préalable au ranker. Évaluer aussi les pipelines complets lorsqu’un récupérateur change, sans attribuer son gain au seul classement.

### D.2. Baseline classique à construire en premier

Générer noms et extensions depuis TCGdex, complétés par une table d’alias contrôlée. Séparer nom complet et suffixes significatifs ; traiter `EX`, `ex`, `GX`, `V`, `VMAX` selon leur contexte. Normaliser symétriquement annonces et catalogue. Aujourd’hui, normaliser le paramètre tout en cherchant dans `LOWER(name)` laisse notamment un décalage sur les accents ; `local_id LIKE '%4'` peut aussi récupérer `14` ou `104`. Une égalité canonique et des alias corrigent ces problèmes sans ML.

La baseline livrée utilise un index de trigrammes et une distance d’édition Python bornée. Comparer une variante SQLite FTS5/BM25 et/ou RapidFuzz seulement si T01/T10 montrent un gain utile ; ces bibliothèques et index ne sont pas actuellement livrés. FTS5 n’apporte pas seul la tolérance aux fautes ; RapidFuzz intervient sur un lexique borné. SQLite trie les meilleurs scores BM25 vers les valeurs les plus petites. Vérifier FTS5 dans l’image ; sinon utiliser un index en mémoire pour ce petit catalogue. [FTS5/BM25](https://www.sqlite.org/fts5.html), [RapidFuzz](https://rapidfuzz.github.io/RapidFuzz/).

Conserver la cascade actuelle comme source prioritaire, puis unir ses résultats à la recherche lexicale, même lorsqu’elle a trouvé quelques candidats. Dédupliquer par identité et réserver une place aux correspondances structurées fortes. Tester `K = 20, 50, 100` ; retenir le plus petit atteignant le rappel cible. Exploiter le dénominateur extrait via les effectifs officiels disponibles, comme indice contextualisé, sans élimination systématique lorsque promos et séries spéciales rendent la comparaison incertaine.

### D.3. Embeddings : expérience peu coûteuse, utilité à prouver

Essayer `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, modèle multilingue à vecteurs de 384 dimensions. Préencoder les fiches et calculer la similarité cosinus avec le texte d’annonce. [Fiche du modèle](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2).

À 40 000 cartes, la matrice float32 représente environ 61 Mio, hors modèle et index. Un produit matriciel NumPy exact suffit pour un premier essai ; une base vectorielle dédiée serait prématurée. D’abord utiliser la similarité pour reranker l’union des candidats ; si le rappel lexical plafonne, tester une récupération dense complémentaire. Cette séparation recherche/reclassement est un schéma documenté. [Sentence Transformers, récupération et reclassement](https://sbert.net/examples/sentence_transformer/applications/retrieve_rerank/README.html).

Conserver numéros et variantes comme features structurées : proximité sémantique ne signifie pas identité. Comparer texte titre seul et titre+description, avec troncature documentée. La configuration publiée du modèle indique `max_seq_length=128` tokens : mesurer la proportion de textes tronqués et les discriminants perdus ; extraire numéros, extensions et variantes sur le texte complet avant encodage. Vérifier cette limite sur la révision effectivement chargée. Ne fine-tuner le bi-encoder que si les erreurs restantes démontrent un besoin et si les négatifs difficiles sont fiables.

### D.4. Ranking structuré à comparer

Entraîner `lightgbm.LGBMRanker(objective='lambdarank')`, un groupe par annonce, en limitant profondeur, feuilles et threads. Features : score règles décomposé, similarités lexicales, BM25, correspondances/contradictions numéro-extension-suffixe-langue, champs manquants, rang de récupération et éventuellement cosinus. Ne pas utiliser prix, identité vendeur ou identifiant de carte comme raccourcis prédictifs. La documentation précise l’objectif LambdaRank et le regroupement des candidats. [LGBMRanker](https://lightgbm.readthedocs.io/en/stable/pythonapi/lightgbm.LGBMRanker.html).

Comparer à une régression logistique sur les mêmes features : si le petit modèle fait aussi bien, sa simplicité gagne. Calculer éventuellement `pred_contrib=True` pour l’audit technique ; afficher au métier des preuves factuelles et les contradictions. Vérifier les résultats sur les cartes peu fréquentes et inconnues de l’entraînement.

### D.5. Cross-encoder, vision et dépendances

Un `sentence_transformers.CrossEncoder` lit conjointement annonce et fiche, avec une inférence par paire. Tester un petit backbone multilingue, par exemple [Multilingual-MiniLM-L12-H384](https://huggingface.co/microsoft/Multilingual-MiniLM-L12-H384), avec tête binaire entraînée sur les paires Pokébourse. Garder top-10/20, puis mesurer ONNX/int8 sans dégradation de qualité. Si l’entraînement CPU dépasse le budget, conserver LightGBM ; aucun GPU de production n’est nécessaire.

Pour la vision, commencer par localiser une carte et lire numéro/symbole avant un classifieur d’édition : `opencv-python-headless` et `pytesseract` sont des candidats CPU, à tester sur un lot annoté. Une seule miniature ou des reflets peuvent rendre reverse/holo indécidables. Réutiliser les photos déjà disponibles, mesurer leur qualité et isoler les lots ; ne pas promettre de reconnaître toute variante sur une image générique.

Prévoir des extras séparés : lexical (`rapidfuzz`), ranking (`lightgbm`, `numpy`, `scikit-learn`), neuraux (`sentence-transformers`, puis `onnxruntime` si utile). Python 3.12 fait partie de la cible compatible de ces bibliothèques ; figer une combinaison effectivement installée et testée sur Linux amd64/arm64 selon le déploiement, plutôt que leurs dernières versions indépendantes. Vérifier roues binaires, mémoire et runtime OpenMP de LightGBM dans `python:3.12-slim`. Les métadonnées et fichiers de distribution constituent les références de compatibilité : [RapidFuzz](https://pypi.org/project/RapidFuzz/), [LightGBM](https://pypi.org/project/lightgbm/), [Sentence Transformers](https://pypi.org/project/sentence-transformers/), [ONNX Runtime](https://pypi.org/project/onnxruntime/).

## E. Architecture d’intégration cible

### E.1. Flux et points de raccordement

```text
Collecteurs → snapshot des preuves → extraction par règles → lot/scellé ?
                                                        ├─ oui → lot / contrôle
                                                        └─ non
                         cascade existante + recherche lexicale (+ dense)
                                             ↓ union top-K
                                     classement règles ou ML
                                             ↓
                         contradictions + calibration + seuils d’abstention
                                             ↓
                         résolution avec validation humaine applicable
                                             ↓
                         catalogue → éligibilité métier → rentabilité / web
                                             ↓
                         échantillonnage → validation → dataset versionné
                                                        ↓
                               entraînement hors worker → évaluation → artefact
```

Dans `app/identification/`, distinguer extraction, récupération, ranking, décision, résolution humaine et audit. Réserver `app/ml/` aux features, entraînements et artefacts. Injecter le service dans l’ingestion et la réidentification sans recharger chaque modèle.

Créer une table additive `identification_runs` : snapshot, versions du catalogue/récupérateur/modèle/politique, candidats et preuves structurées, scores bruts, probabilité éventuelle, décision, latences et motif de repli. Conserver ces détails en JSON validé et indexer snapshot/date. Les snapshots et tirages conservent déjà des candidats/versions ; le journal exhaustif de chaque exécution ML reste à concevoir en réutilisant ces contrats, sans en déduire qu’il est déjà livré.

Aujourd’hui, l’identification s’exécute dans le bloc transactionnel d’ingestion. Déplacer calcul et inférence avant les écritures, puis enregistrer en transaction courte en vérifiant l’empreinte courante. Ne pas conserver un verrou SQLite pendant des centaines de millisecondes de calcul. Garder WAL et `busy_timeout` existants.

### E.2. Décision, chargement et dégradation

Définir `identified` pour une correspondance acceptée, `ambiguous` pour des candidats plausibles insuffisamment départagés, `unidentified` pour aucune correspondance admissible, `lot` pour le périmètre actuel des lots/scellés. La validation applicable prime sur ces propositions. Une langue ou un numéro explicitement contradictoire interdit l’acceptation automatique si leur extraction est fiable ; une absence d’information n’est pas une contradiction.

Choisir le seuil de probabilité et l’écart minimal top-2 sur validation/calibration ; aucun nombre universel n’est fixé a priori. L’écart dépend de l’échelle du modèle et du récupérateur. En cas de modèle indisponible, employer les règles avec leur version et leur politique mesurée. En cas de score ML insuffisant, s’abstenir ; revenir à l’acceptation des anciennes règles annulerait ce garde-fou.

Garder `identification_confidence` comme score historique compatible et stocker la probabilité calibrée séparément ; clarifier leur libellé dans l’interface. La rentabilité exige une identité effective admissible et suffisamment d’attributs vérifiés : ne pas transformer `identified` en certitude de langue, état ou édition. Ajouter ce contrôle au point d’orchestration ; conserver les formules de `profitability.py`.

Un artefact immuable contient modèle, features ordonnées, normalisation, index, catalogue, calibrateur, politique, manifeste de dataset et métriques. Préférer texte LightGBM/JSON ou ONNX ; conserver la version précédente. Charger une fois par processus, effectuer un contrôle d’empreintes et un préchauffage ; aucune récupération de poids par Internet pendant une annonce. Les extras ONNX CPU sont documentés par [Sentence Transformers](https://sbert.net/docs/installation.html).

Le worker fait l’inférence, jamais le réentraînement. Une action web coûteuse dépose une demande au worker et affiche l’attente. Budget : **p95 ≤ 1 seconde**, p99 suivi, mémoire additionnelle ≤ 1 Gio par processus. Mesurer le débit avec la collecte et borner les threads.

### E.3. Dérive et cycle de maintenance

Suivre chaque semaine par plateforme : longueur de texte, descriptions absentes, langues explicites/inconnues, extensions nouvelles, nombre de candidats, scores, abstentions et corrections. Comparer des fenêtres de sept jours à une référence de quatre semaines, avec effectifs minimaux. Exemples de déclencheurs à ajuster : +10 points d’abstention, +15 points de descriptions absentes, ou dérive de précision auditée sous le seuil.

Une alerte déclenche un diagnostic : catalogue incomplet → synchronisation/indexation ; connecteur modifié → correction des entrées ; classement dégradé avec 500 nouveaux labels utiles → expérience de réentraînement. Réexaminer mensuellement et conserver les critères de promotion.

## F. Évaluation

### F.1. Métriques et dénominateurs

Pour les annonces unitaires dont l’identité est déterminée, distinguer :

| Mesure | Définition / utilité |
|---|---|
| Couverture catalogue | Part des cartes validées représentées dans le catalogue cible |
| Rappel candidats@K | Part des identités présentes dans le top-K récupéré, parmi celles couvertes |
| Précision@1 / exactitude top-1 | Part des premières propositions correctes, avant abstention |
| Succès@5 / rappel@5 | Part des annonces dont la bonne carte apparaît parmi cinq propositions |
| Précision@5 stricte | Nombre de bonnes cartes dans les cinq, divisé par cinq ; avec une seule vérité, maximum 0,2 |
| Précision d’acceptation | Identifications automatiques correctes / identifications automatiques acceptées |
| Taux d’identification correcte | Identifications automatiques correctes / annonces unitaires évaluables, abstentions incluses |
| Escalade | Part du flux envoyée à un opérateur ; suivre séparément le stock non encore examiné |
| Sélectivité et exploitation | Couverture automatique, courbe risque/couverture, latence p50/p95/p99, mémoire |

Publier séparément précision@5 et succès@5. Ajouter MRR, calibration par tranches et Brier score si les effectifs suffisent. Évaluer les fausses acceptations hors catalogue, les lots et les textes insuffisants ; une mesure conditionnelle au rappel réussi ne décrit pas le pipeline complet.

Mesurer également, par 1 000 annonces, le nombre de rattachements erronés acceptés, le temps de validation humaine, le temps économisé face à la baseline et les coûts d’annotation/maintenance. Publier la part réellement exploitable après contrôle des attributs requis pour la comparaison de prix. Une hausse des identités reconnues ne garantit pas une hausse équivalente des annonces exploitables. Définir au pilote le budget humain acceptable et les gains utiles avant de consulter le test.

### F.2. Protocole humain et comparaison

Comparer sur les mêmes snapshots figés : règles actuelles, baseline améliorée, régression logistique, LightGBM, puis apports optionnels des embeddings. Fixer les candidats pour la comparaison des rankers et publier séparément les comparaisons de pipelines complets. Publier résultats globaux, macro par carte/extension et tranches plateforme/langue/description/rareté de fréquence. Le test représentatif estime la production ; un jeu difficile séparé mesure la robustesse, sans mélanger leurs distributions.

Annoter sans afficher d’abord la suggestion ; faire relire 20 % du pilote et tous les désaccords. Pour l’audit périodique, commencer par 100 annonces aléatoires par semaine, plus les cas à risque, avec quotas et probabilités enregistrés. Ce rythme détecte certaines dérives mais ne certifie pas seul une précision élevée dans chaque segment. Utiliser des intervalles binomiaux pour les audits indépendants et un bootstrap par groupe pour les différences entre systèmes.

Avec seulement quelques centaines d’exemples acceptés, annoncer « 99,5 % » sans intervalle serait excessif. À zéro erreur sur 300 observations indépendantes, la borne unilatérale à 95 % est environ 99 % ; sur 600, environ 99,5 %. Des erreurs observées imposent un effectif plus grand. Les republications ne comptent pas comme preuves indépendantes.

**Budget de qualification distinct du budget d’apprentissage.** Avec 3 000 labels, un test de 15 % contient 450 annonces ; à 50 % d’acceptation, seules 225 décisions qualifient la précision d’acceptation. À zéro erreur, leur borne exacte unilatérale à 95 % vaut `0,05^(1/225) ≈ 98,68 %`, sous le plancher de 99 %. À zéro erreur, il faut au moins 299 acceptations indépendantes pour une borne de 99 %, et 598 pour 99,5 %. Ces effectifs concernent chaque segment à certifier et augmentent avec les erreurs observées.

Prévoir un audit complémentaire aléatoire des décisions acceptées par le pipeline verrouillé. Garder en parallèle l’échantillon de flux complet pour mesurer couverture, escalade et gain. Fixer segments, effectifs, dates de lecture et méthode d’intervalle avant l’audit ; ne pas arrêter au premier résultat favorable. Si une garantie simultanée sur plusieurs segments est revendiquée, adapter les intervalles aux comparaisons multiples. Les intervalles binomiaux simples supposent des unités indépendantes et un échantillonnage approprié ; ne pas les appliquer directement aux quotas pondérés. En cas d’effectif insuffisant, poursuivre l’observation sans activer le segment.

### F.3. Conditions de promotion

Autoriser une première automatisation ML par segment si :

1. Appliquer le plancher du chantier actif Identification/T10 : borne inférieure unilatérale à 95 % de la précision ≥ 99,5 % sur le périmètre qualifié. L’ancien critère de conception à 99 % de borne ne suffit pas pour une nouvelle acceptation OCR/vision. A.4 conserve le garde-fou des pseudo-labels.
2. Rappel candidats@50 ≥ 98 % sur le périmètre couvert, avec analyse des échecs et incertitude publiée.
3. Gain d’au moins 5 points de taux d’identification correcte, ou baisse relative d’escalade ≥ 15 %, à précision comparable. Choisir le critère principal avant le test ; exiger une borne inférieure de l’intervalle à 95 % du gain strictement positive, obtenue par bootstrap apparié par groupe. Fixer également la tolérance de différence de précision avant l’évaluation ; chaque système reste soumis au plancher de sécurité. Les seuils de gain sont des valeurs de départ à confirmer selon le temps humain et le coût d’exploitation, puis à verrouiller avant le test.
4. Aucun segment suffisamment documenté ne passe sous le plancher de précision ; les segments peu documentés restent soumis à validation.
5. p95 ≤ 1 seconde, audit complet, validations préservées et repli démontré.

Exécuter d’abord deux semaines en mode observation, en journalisant aussi les désaccords avec les règles, puis activer sur 10 % des identifiants d’annonces admissibles et stables. Élargir après un effectif d’audit suffisant, pas au seul terme d’un délai. Si la baseline atteint les objectifs au même coût, elle reste le système de production. Le ML remplace éventuellement le classement additif, sans supprimer les contrôles métier.

## G. Roadmap séquencée avec jalons mesurables

Les efforts sont des ordres de grandeur pour une personne connaissant le projet, hors attente de collecte et hors temps d’annotation. Réestimer après l’inventaire : conservation des images, double lecture et qualification par segment peuvent allonger le calendrier. Les phases reprennent les prérequis de A.1 bis ; aucun entraînement n’est nécessaire pour réaliser le premier lot.

| Phase | Livrables | Critères de sortie | Effort relatif | Risque / plan B |
|---|---|---|---|---|
| 0 — Prérequis et validation | Originaux, inconnues, migration additive, preuves durables, annotations/décisions, formulaire, résolution commune, export | 300 labels ; 20 % double lecture ; accord ≥ 98 % ; corrections préservées ; diagnostic texte/photos/catalogue de A.5 livré | Moyen, 5–8 jours | Annotation trop lente : réduire périmètre et améliorer recherche/correction |
| 1 — Référence et données | Inventaire catalogue, normalisation symétrique, alias, FTS5/RapidFuzz, groupes de doublons, test figé | 1 000 labels ; rappel@50 cible ≥ 98 % sur catalogue couvert ; latence lexicale p95 < 100 ms | Moyen, 5–8 jours | Rappel insuffisant : enrichir catalogue et récupération avant tout reranking |
| 2 — Expériences selon diagnostic | Régression logistique puis LightGBM à candidats fixes ; embeddings optionnels ; calibration, manifeste et benchmark | Budget initial 3 000–5 000 labels ; ablations et courbes d’apprentissage ; pipeline verrouillé pour qualification, sans activation automatique | Moyen à élevé, 7–12 jours | Labels insuffisants ou gain nul : conserver baseline et suggestions humaines |
| 3 — Qualification et déploiement | Audit indépendant des acceptations, observation du flux, activation limitée, surveillance et retour arrière | Deux semaines d’observation au minimum ; effectifs par segment de F.2 ; critères de F.3 et bénéfice opérationnel vérifiés | Moyen, 4–7 jours puis entretien | Dérive : désactiver segment affecté, corriger source et réévaluer |
| 4 — Options conditionnelles | Cross-encoder ou OCR/vision ; essai OCR avançable dès le diagnostic de phase 0, un besoin à la fois | ≥ 5 points gagnés sur une tranche bloquante, sans dégrader précision/latence globale | Élevé, 10–20 jours par piste | CPU ou images insuffisants : validation humaine ciblée |

En phase 0, compléter les suites existantes `test_migrations`, `test_watch_ingestion`, `test_identification`, `test_catalog`, `test_web` et `test_profitability`. Priorités : recollecte conservant un label, changement de preuve invalidant son applicabilité, correction concurrente, suppression d’import, retrait de validation, candidat hors top-K, lot mal détecté, langue inconnue, séparation annotation/décision et attributs vérifiés. Réserver les tests d’artefact absent, de repli et de chargement aux phases d’intégration ML. Les tests utilisent fixtures et mocks, sans requêtes réelles aux marketplaces.

En phase 2, mesurer les courbes d’apprentissage à 500, 1 000, 2 000 exemples train puis davantage, et l’apport du cosinus et des labels faibles. Prévoir des commandes d’entraînement et d’évaluation produisant artefacts immuables et rapports, avec modes `rules`, `shadow`, `ml`.

## H. Risques et anti-patterns

| Piège | Contrôle concret |
|---|---|
| Fuite par republication, augmentation ou nom déjà corrigé | Groupes avant split ; entrées originales ; test temporel immuable |
| Augmentation supprimant le seul discriminant | Exclusion du ranking à label unique ; évaluation synthétique d’abstention séparée |
| Calibration contaminée ou non représentative | Variables observables seulement ; calibration indépendante ; vérification après changement du récupérateur |
| Qualification sous-dimensionnée ou répétée jusqu’au succès | Budget sur les acceptations par segment ; protocole et lectures fixés à l’avance |
| Auto-labellisation circulaire | Origine et poids distincts ; audits humains ; test exclusivement humain ; ablations |
| Précision flatteuse sur quelques Pokémon populaires | Mesures macro, segments rares et jeu de difficulté séparé |
| Bonne carte absente des candidats ou du catalogue | Mesures de couverture et rappel séparées ; recherche humaine complète |
| Cosinus, score 90 ou sigmoïde présentés comme probabilité | Calibration indépendante et intervalles de confiance |
| Explication narrative qui masque une contradiction | Preuves structurées avec origine ; aucune raison inventée |
| Variante/langue supposées depuis la seule identité | Validation d’attributs distincte ; périmètre linguistique explicite |
| Labels sur photo utilisés pour promettre une certitude textuelle | Provenance de preuve et indicateur de suffisance du texte |
| ML insuffisamment sûr contourné par le repli règles | Abstention en cas d’incertitude ; repli technique soumis à sa politique propre |
| Inférence lourde dans une transaction SQLite | Calcul avant transaction ; vérification optimiste du snapshot |
| Dépendances CPU théoriques, image inutilisable | Installation et mesure dans l’image cible ; poids locaux ; threads bornés |
| Dérive confondue avec besoin d’entraînement | Diagnostiquer collecte, catalogue puis classement ; réentraînement conditionnel |
| Vérité humaine effacée ou donnée sensible recopiée | Historique séparé ; snapshots minimaux ; pas de vendeur/contacts dans les features ; purge définie |

La prochaine décision engageante est l’organisation de la validation humaine et son budget. Le choix d’un modèle dépendra ensuite du type d’erreurs effectivement observées, de leur caractère résoluble avec les preuves disponibles et du gain démontré face à la baseline classique.
