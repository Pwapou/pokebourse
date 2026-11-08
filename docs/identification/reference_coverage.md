# Diagnostic de couverture du référentiel TCGdex local

**État au 8 novembre :** outil d’inventaire livré, utilisé en T00/T05. Le socle alias/localisations de T05 a depuis été implémenté (`0024`–`0026`) ; ce rapport reste un diagnostic en lecture seule et ne valide pas l’alias « gempack 2 » ni la couverture globale. Voir [le suivi](../../TASKING_PROJET.md).

Lot préparatoire à **T05** de `TASKING_IDENTIFICATION_FIABLE.md` : distinguer un
problème de **couverture du catalogue** d'un problème **d'identification**.
Ce document décrit l'outil `scripts/reference_coverage_report.py`, son usage
et les règles d'interprétation obligatoires.

## Principe

L'outil produit un inventaire **hors ligne et en lecture seule** d'une
sauvegarde SQLite cohérente du référentiel Pokémon. Il :

- ouvre la base exclusivement en URI `mode=ro` (jamais `immutable=1` pour
  contourner une base active) ;
- ne lance aucune migration, aucune initialisation, ne charge aucun seed ;
- ne modifie aucune donnée, ne lance aucun worker, OCR ou matcher ;
- n'effectue aucun appel réseau ;
- ne lit que les tables du référentiel (`pokemon_reference_sets`,
  `pokemon_reference_cards`) et les métadonnées de synchronisation
  (`schema_migrations`, `tcgdex_sync_jobs`, `tcgdex_sync_cards` quand elles
  existent). Aucune annonce, vendeur, contact ou contenu brut n'est exporté.

## Utilisation

```bash
# Aide
docker compose run --rm app python -m scripts.reference_coverage_report --help

# Inventaire complet d'une sauvegarde produite par le mécanisme existant
docker compose run --rm app python -m scripts.reference_coverage_report /data/backups/pokebourse-YYYYMMDD-HHMMSS-ffffff.sqlite

# Avec export JSON versionné (refuse d'écraser un fichier existant)
docker compose run --rm app python -m scripts.reference_coverage_report /data/backups/<fichier>.sqlite --json /data/reference-coverage.json

# Recherche ciblée (diagnostic, pas identification d'annonce)
docker compose run --rm app python -m scripts.reference_coverage_report /data/backups/<fichier>.sqlite --set sv01 --card-name Pikachu --local-id 001
```

La commande reçoit **explicitement** le chemin d'une sauvegarde. Ne pas lui
passer la base opérationnelle, ne pas copier naïvement le seul fichier d'une
base active en mode WAL : une telle copie peut être incohérente. Préférer une
sauvegarde produite par `pokemon-arbitrage backup` (API de sauvegarde en
ligne `sqlite3_backup`, qui fige le journal en mode DELETE après vérification
d'intégrité). Si le fichier ouvert est encore en mode WAL, le rapport ajoute
une limite explicite à ce sujet.

Erreurs compréhensibles : base absente, fichier invalide (non SQLite ou
intégrité compromise), schéma incompatible (tables du référentiel manquantes).
Code de retour `2` dans ces cas.

## Contenu du rapport

### 1. Inventaire global

Version de schéma (dernière migration enregistrée, si la table existe),
nombre d'extensions et de cartes, répartition des langues de référence
enregistrées, cartes avec URL d'image renseignée, et champs optionnels absents
de la sauvegarde (par exemple `reference_language` sur une sauvegarde
antérieure à la migration 0012).

### 2. Inventaire par extension

Pour chaque extension : identifiant, nom, série, dates, cartes locales, URL
d'images, langues enregistrées, effectifs annoncés (avec leur signification :
totaux déclarés selon la locale et les conventions de comptage du fournisseur),
niveau de détail (établi uniquement à partir des métadonnées fiables de la
file de synchronisation : étape, fiches complétées vs attendues) et état de la
dernière demande de synchronisation, si le schéma le permet.

Quatre situations sont distinguées sans confusion :

- **extension connue sans cartes chargées** (fait établi) ;
- **effectif local égal à l'effectif annoncé** (conformité) ;
- **effectif différent** (`à vérifier` : jamais présenté comme des cartes
  manquantes — locales, sous-séries et conventions de comptage peuvent
  différer) ;
- **information insuffisante** (aucun effectif annoncé enregistré).

### 3. Recherche ciblée

Filtres combinables : identifiant ou nom d'extension, nom de carte, numéro
local (comparaison canonique : zéros initiaux neutres). Toutes les
correspondances sont retournées avec leur contexte (extension, langue de
référence, présence d'URL d'image), tri déterministement, sans en choisir
arbitrairement la première. Une expression sans correspondance — « gempack 2 »
par exemple — est simplement signalée absente **de ce référentiel** : l'outil
n'invente aucun alias, cible française ni équivalence entre impressions.

### 4. Anomalies et limites

Chaque anomalie porte un effectif, des exemples bornés (5 maximum) et un
niveau de certitude parmi :

- `probleme_confirme` : références orphelines (carte rattachée à une extension
  absente du répertoire), numéros locaux manquants ;
- `point_a_verifier` : noms d'extension incohérents entre carte et répertoire,
  numéro canonique partagé par plusieurs cartes d'une même extension,
  répartition des langues enregistrées ;
- `information` : numéros identiques entre extensions/langues (ce n'est **pas**
  automatiquement des doublons erronés) ;
- `information_indisponible` : colonne `reference_language` ou table de
  synchronisation absente de la sauvegarde.

## Règles d'interprétation (inviolables)

1. Une langue enregistrée historiquement par défaut n'est **pas** une preuve
   de la langue d'un exemplaire vendu.
2. Une URL d'image renseignée ne signifie pas qu'une image a été téléchargée,
   vérifiée ou reste accessible.
3. Ne jamais conclure qu'une carte n'existe pas chez TCGdex ou dans le monde
   parce qu'elle est absente de cette sauvegarde.
4. Des noms ou numéros identiques entre extensions/langues ne sont pas
   automatiquement des doublons erronés.
5. La recherche ciblée sert au diagnostic, pas à identifier une annonce.

## Limites du diagnostic

- Analyse figée d'une sauvegarde : aucune donnée live ni réseau.
- Les exemples sont bornés ; les effectifs complets restent dans les compteurs.
- Le niveau de détail des fiches n'est établi que lorsque les métadonnées de
  la file de synchronisation le prouvent ; sinon il est marqué indisponible.
- Un écart d'effectifs n'est jamais interprété comme des cartes manquantes.

## Ce que ce rapport permet de préparer pour T05

- **Prioriser les extensions à synchroniser** : connues sans cartes, ou dont
  l'effectif diffère, ou sans demande de synchronisation enregistrée.
- **Qualifier les locales utiles** : répartition réelle des langues enregistrées
  avant d'étendre le périmètre (une locale ajoutée n'active pas automatiquement
  son identification).
- **Cibler les alias à vérifier** : cas comme « gempack 2 » sans correspondance
  locale sont recensés comme absents du référentiel, à vérifier sur source de
  référence avant tout ajout contrôlé.
- **Isoler les vrais problèmes de référentiel** (orphelins, numéros manquants)
  des problèmes d'identification, qui relèvent d'autres lots.

Ce lot fournit l'**inventaire uniquement** : aucune synchronisation, aucun
nouvel alias, aucune modification du cache multilingue. T05 n'est pas terminé
par ce rapport.
