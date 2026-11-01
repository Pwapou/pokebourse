# Phase 0 ML — validation et pilote textuel

État au 1er novembre 2026. Référence : [MACHINE_LEARNING_DESIGN.md](../MACHINE_LEARNING_DESIGN.md), sections A et G.

## Livré

- Migration additive `0013_identification_reviews.sql`, après les migrations de recherche de cartes déjà présentes dans l’espace de travail.
- Snapshots des observations distincts des champs d’identité corrigés ; origine `original_text`, `structured_import` ou `legacy_unknown`. Titre et description exacts participent à l’empreinte, avec les attributs observés et la version de normalisation. Prix et dates de collecte n’y participent pas. Une URL d’image contribue seulement à l’invalidation conservatrice : ce n’est pas une preuve photographique archivée.
- Conservation du nom et de la description fournis par les imports JSONL et l’extension avant réidentification. Un import structuré est signalé comme tel : son nom n’est pas présenté comme un titre marketplace brut. Le défaut historique de stockage `language='fr'` n’est pas copié comme preuve ; le détecteur retourne une langue inconnue en l’absence d’indice.
- Historique en ajout des annotations, décisions, arbitrages et retraits ; référence TCGdex vérifiée localement et copie stable de son identifiant externe. Les attributs vérifiés suivent une liste blanche séparée.
- Résolution commune à la collecte, aux imports et à la réidentification. Une lecture indépendante ne remplace pas une décision. La dernière décision applicable fait autorité ; si les preuves ont changé, l’application revient au moteur automatique et signale le réexamen. Un retrait ne ressuscite pas une ancienne confirmation.
- Révision optimiste et transaction d’écriture SQLite. Les anciens boutons de confirmation/retrait utilisent une révision commune pendant la transition. Une décision par ces anciens boutons reste distincte du jeu d’apprentissage et peut rendre un ancien label ML obsolète.
- Formulaire de validation textuelle, recherche paginée dans tout le catalogue local et mode indépendant sans suggestion ni historique visible.
- Export JSONL reproductible via `GET /catalog/labels.jsonl` et la commande `export-labels`. Le CLI refuse d’écraser un fichier existant.
- Migration additive `0014_annotation_pilot.sql` : pilote, vagues de tirage et tâches avec première lecture, seconde lecture et décision finale reliées atomiquement aux annotations.
- Tableau `/annotations` : sélection, avancement vers 300 cas et 60 doubles lectures, filtres, pagination, accord sur l’identité et sur la suffisance du texte avant arbitrage, diagnostic des décisions finales.
- Parcours `/annotations/items/{id}` : première et seconde lectures obligatoirement indépendantes, avec opérateurs distincts ; les choix automatiques et avis humains sont masqués jusqu’à la validation finale. Le paramètre `blind=false` ne permet pas de changer l’étape de la file.
- Exécution transactionnelle des migrations reconstruisant des tables : conservation des références entrantes, contrôle des clés avant validation, rollback sur incohérence et réactivation du contrôle même après échec. Un test vérifie la conservation d’un pilote déjà commencé lors des migrations ultérieures.

## Pilote d’annotation

1. Ouvrir **Annotations**, puis **Constituer la file**. Le pilote vise 300 cas : 150 ambigus, 75 non identifiés, 60 identifiés et 15 lots. Les catégories manquantes redistribuent leurs places aux cas disponibles.
2. **Continuer les lectures** ouvre la prochaine première ou seconde lecture admissible pour l’opérateur courant. Le tableau permet de filtrer les lectures disponibles, les tâches qui attendent un autre opérateur et les décisions à valider.
3. Enregistrer le résultat sur le texte seul. Une lecture dans la file reste une annotation : elle n’applique pas une correction à l’annonce.
4. Faire traiter les doubles lectures par une autre personne et un identifiant opérateur distinct. L’opérateur courant est visible sur le tableau. La file refuse un opérateur ayant déjà annoté ce snapshot, même en dehors de cette tâche.
5. Après les lectures requises, **Valider / arbitrer** montre leurs résultats et permet de choisir explicitement la décision finale. Une seule lecture suffit aux tâches non retenues pour double lecture. Les identifiants d’annotations sont rattachés automatiquement.
6. Après de nouveaux imports, **Compléter la file** tire une nouvelle vague jusqu’au budget courant. Une preuve modifiée ou une annonce supprimée reste dans l’audit, quitte l’avancement courant et peut être remplacée. Une révision ultérieure hors pilote n’est plus comptée comme décision finale applicable ; la tâche permet alors de réexaminer la décision sans effacer les lectures initiales.

Le tableau calcule l’accord sur les deux annotations originales, avant l’arbitrage : résultat et identifiant TCGdex d’une part, suffisance du texte d’autre part. Un arbitrage ne réécrit ni les annotations ni leur désaccord. Les dénominateurs sont les paires terminées sur des preuves courantes ; ils ne constituent pas une mesure de précision du moteur. Aucun objectif n’est présenté comme atteint par le seul développement.

Le diagnostic compare les décisions finales courantes aux propositions figées au tirage : premier candidat correct, carte absente des candidats proposés, mauvais classement, catalogue incomplet, texte insuffisant ou rejet métier. Les premières vagues conservent au plus 10 candidats ; les nouvelles vagues `lexical-v1` en conservent au plus 50. Ce tableau ne qualifie pas à lui seul le rappel@50. Les causes d’extraction et l’apport des photos restent à qualifier séparément. Le [diagnostic des annonces non résolues](IDENTIFICATION_LEXICALE.md) ajoute un inventaire en lecture seule et des suggestions orthographiques à vérifier.

### Configuration des opérateurs en local

L’identité est définie côté serveur. Avec Compose, par exemple :

```bash
POKEMON_REVIEW_OPERATOR=lecteur-1 docker compose up -d --force-recreate app
# Après les premières lectures, pour la personne qui effectue la seconde lecture :
POKEMON_REVIEW_OPERATOR=lecteur-2 docker compose up -d --force-recreate app
```

Chaque redémarrage de l’interface conserve la file et les lectures dans SQLite. Un changement d’identifiant ne prouve pas qu’une autre personne a relu : l’organisation de la double lecture reste humaine. Le parcours masque les avis précédents, mais n’est pas une barrière de confidentialité contre une consultation volontaire du catalogue ou de l’export.

### Protocole de tirage

Le tirage utilise uniquement les snapshots courants dont l’origine est connue, sans annotation ou décision antérieure sur ce snapshot et sans tâche active pour le même groupe source/identifiant. La population est celle des annonces locales admissibles, pas celle du marché. Les originaux historiques non fiables restent accessibles par le formulaire individuel, mais sont exclus de la file.

Les quotas de statut sont répartis entre plateformes, langues explicitement observées ou extraites du texte, et présence de description. L’allocation entre strates est déterministe ; au sein de chaque strate, le tirage est uniforme sans remise. Les strates sans place ont une probabilité nulle. Les probabilités des cas sélectionnés sont enregistrées comme fractions exactes `n/N`, avec une copie de la population des snapshots et la graine de chaque vague. L’ordre des tâches est ensuite mélangé.

Les nouvelles doubles lectures sont tirées uniformément dans la vague pour atteindre le cinquième supérieur de l’effectif courant, compte tenu des doubles lectures déjà prévues. Pour une vague, leur probabilité conditionnelle est `double_count/selected_count`, distincte de la probabilité de sélection d’une annonce. Des suppressions peuvent temporairement augmenter la part des doubles lectures restantes ; les engagements existants ne sont pas annulés.

Les probabilités portent sur chaque vague et sa population enregistrée. Les cas déjà exposés ou sélectionnés sont retirés des vagues suivantes. Le pilote cible les besoins d’apprentissage et ne remplace pas l’audit aléatoire représentatif de production demandé par la conception. Ne pas appliquer d’intervalle binomial simple aux proportions brutes de ce tirage stratifié.

## Utilisation

1. Redémarrer l’application sur le code courant selon le workflow habituel du projet pour appliquer les migrations. Les vérifications de développement utilisent des bases temporaires et ne migrent pas la base réelle.
2. Ouvrir une fiche et choisir **Valider ou corriger l’identité**.
3. Lire les observations, rechercher la référence, choisir le résultat et confirmer si le texte seul suffit. Un résultat `matched` exige une référence locale et un texte déclaré suffisant.
4. Choisir **Décision sur l’annonce** pour appliquer une correction, **Annotation indépendante** pour conserver une lecture, ou **Arbitrage d’annotations** en renseignant leurs identifiants. Un retrait est une décision de résultat **Validation retirée** sans carte choisie.
5. Ne renseigner langue, variante, édition ou état que si le texte permet de les vérifier. Ces valeurs ne deviennent pas automatiquement des critères de rentabilité confirmés.
6. Exporter le jeu pilote ; conserver l’export original comme un artefact de travail versionné.

L’opérateur provient de la configuration serveur `POKEMON_REVIEW_OPERATOR`, identifiant local stable composé de lettres ASCII, chiffres, `_` ou `-`, par défaut `local`. Ce n’est pas un système de comptes ni une preuve d’indépendance entre lecteurs. Pour une vraie double lecture, utiliser des identifiants distincts configurés côté serveur, puis vérifier l’accord avant arbitrage. Le formulaire ne permet pas d’usurper un opérateur par un champ libre.

## Contrat de l’export

Le premier enregistrement `manifest` contient la version de schéma `identity-pilot-v2`, l’empreinte du contenu, les catalogues utilisés et les effectifs. Les enregistrements `catalog` embarquent les attributs figés du référentiel. Les enregistrements `review` contiennent les observations, la provenance, la lecture et les attributs explicitement vérifiés. Leur objet `pilot_assignment` relie les lectures au pilote, à la vague, au rôle, à la strate, aux fractions exactes de sélection et aux candidats automatiques figés. Les enregistrements `sampling_batch` conservent le protocole, la population par strate, la graine, les effectifs et la version de catalogue, même avant la première lecture.

`eligible_for_text_training` identifie une décision courante disposant d’un original de provenance connue et d’un texte déclaré suffisant. Les annotations, retraits, décisions remplacées, preuves obsolètes et annonces supprimées restent dans l’audit avec `exclusion_reasons`. Un statut éligible ne suffit pas à constituer une paire de ranking : les résultats sans carte servent notamment à étudier l’abstention. Les imports structurés doivent être distingués des textes marketplace dans les futures expériences.

Les champs vendeur, URLs, JSON brut, commentaires et identité directe de l’opérateur ne sont pas exportés. Les contacts explicites (emails, téléphones français et liens) sont masqués dans les copies textuelles d’apprentissage. Ce masquage ne détecte pas tous les renseignements personnels possibles dans du texte libre : contrôler les données avant de partager un jeu. Les originaux opérationnels restent distincts. `reviewer_key` pseudonymise l’opérateur pour comparer les lectures ; `group_key` relie les mêmes annonces source/identifiant sans exporter cet identifiant.

La suppression d’un import détache ses snapshots ; elle n’efface pas leur audit. Les lignes correspondantes sont exclues du train. Sauvegardes SQLite et restauration existantes incluent ces tables. Une procédure dédiée de purge et une durée de rétention restent à définir avant accumulation à grande échelle.

## Restant avant de clore la phase 0

- Archiver les images avec empreintes durables, sauvegarde et rétention avant d’autoriser `image` ou `both`. Le service refuse ces provenances pour ce pilote.
- Constituer les **300 annotations humaines**, dont **20 % en double lecture**, puis mesurer l’accord et la suffisance du texte. Aucun de ces volumes n’est acquis par le développement.
- Ajouter un audit aléatoire représentatif distinct du pilote stratifié, et définir les segments et effectifs à qualifier avant toute automatisation.
- Produire le diagnostic texte/photos/catalogue prévu en A.5. Les catalogues sont figés pour les labels, mais l’inventaire de couverture reste à développer.
- Définir et implémenter la purge des données d’apprentissage et la politique de conservation des preuves.
- Traiter les quasi-doublons et republications interplateformes avant de partitionner. `group_key` ne résout que l’identité exacte de la source.
- Finaliser l’éligibilité métier à la rentabilité à partir des attributs vérifiés. Le moteur financier existant n’est pas requalifié par ce lot.

Les phases suivantes restent la baseline lexicale mesurée, les partitions sans fuite, puis les expériences de régression logistique/LightGBM selon le diagnostic. Aucun téléchargement de poids, nouvelle dépendance ML, entraînement ni activation automatique n’est introduit par ce lot.
