# Enrichissement progressif du référentiel TCGdex

**Revue du 8 novembre 2026 : fonctionnalité réalisée et testée**, migrations `0018` et `0026` (locale). Le stockage des cartes distingue `(tcgdex_id, reference_language)` depuis `0024`. Les anciennes demandes françaises conservent leur clé ; la sync permet des locales utiles à la demande, sans qualifier automatiquement leur identification ni leurs prix. Ordre de reprise : [TASKING_PROJET.md](../TASKING_PROJET.md).

La page **Référentiel TCGdex** (`/tcgdex`) permet de choisir les extensions utiles aux annonces à identifier. Les extensions explicitement mentionnées dans les observations non résolues sont présentées en premier, parmi les 1 000 observations récentes analysées. Le filtre recherche uniquement dans le cache local ; un identifiant connu peut aussi être saisi directement.

## Ce qui est chargé

- **Liste des extensions** : une requête pour connaître leurs noms et identifiants, sans télécharger leurs cartes.
- **Identités d’une extension** : une requête pour récupérer les noms, numéros et identifiants de ses cartes. Ces résumés deviennent immédiatement utilisables dans les recherches locales.
- **Fiches détaillées**, facultatives : une requête par carte du manifeste, pour compléter notamment rareté, catégorie, types, illustrateur et variantes disponibles dans la réponse.

Les effectifs locaux, effectifs annoncés et fiches détaillées récupérées sont affichés séparément. Un écart avec le total annoncé peut provenir du contenu servi par TCGdex dans la locale française ; relancer le chargement ne garantit pas de le combler. Une tâche terminée signifie que les ressources fournies ont été traitées, pas que toutes les données théoriquement possibles existent.

Les endpoints utilisés sont documentés par TCGdex : [extensions](https://tcgdex.dev/rest/sets), [extension et manifeste](https://tcgdex.dev/rest/set), [fiche carte](https://tcgdex.dev/rest/card).

## File, pause et reprise

Les routes web enregistrent les demandes sans appel distant. Le service `worker` doit fonctionner pour les exécuter. Il traite au plus une requête d’enrichissement par passage, après les recherches ciblées d’identification. Avec la configuration Compose par défaut, deux passages sont espacés d’au moins 5 secondes, auxquelles s’ajoute le temps des traitements.

La migration `0018_tcgdex_sync_jobs.sql` ajoute une file persistante, les cartes restant à détailler et un contrôle partagé des requêtes. Une réservation de 60 secondes et un jeton empêchent un ancien worker de publier une réponse après une pause ou une reprise par un autre worker. Aucun verrou d’écriture SQLite n’est gardé pendant le réseau.

- Une sélection contient de 1 à 20 extensions ; les demandes identiques sont dédupliquées.
- **Mettre en pause** conserve le manifeste et les fiches déjà chargées. Une requête éventuellement en vol peut finir, mais sa réponse est écartée.
- **Reprendre** repart de la première fiche non terminée. Trois tentatives infructueuses sur une étape demandent une reprise manuelle ; une ressource absente (404) est signalée immédiatement.
- Un 429 replanifie la requête en respectant `Retry-After` (secondes ou date HTTP), avec un délai partagé entre les tâches de cette file. Les autres erreurs temporaires utilisent un délai croissant.
- Une tâche réussie est réutilisée pendant 24 heures. Demander les détails après un chargement de résumés récent réutilise son manifeste. Passé 24 heures, une nouvelle demande recharge le manifeste et les détails sélectionnés ; les références existantes ne sont jamais supprimées.
- Le suivi automatique s’active après une demande ou une reprise et s’arrête quand cette tâche est terminée ou en pause. Le lien « Arrêter le suivi automatique » permet de remplir les formulaires sans rechargement périodique.

`TCGDEX_SYNC_INTERVAL_SECONDS` (1 à 60, défaut 1) définit en plus un intervalle minimal partagé entre débuts de requêtes de cette file. Il ne remplace pas la cadence générale du worker et n’accélère pas son passage par défaut de 5 secondes.

## Utilisation en CLI

```bash
# Appliquer les migrations avant toute utilisation sur une base existante
docker compose run --rm app pokemon-arbitrage migrate

# Mettre deux extensions en file, avec leurs fiches détaillées
docker compose run --rm app pokemon-arbitrage sync-tcgdex sv08.5 swshp

# Charger uniquement les identités d’une extension
docker compose run --rm app pokemon-arbitrage sync-tcgdex base1 --summaries-only

# Demander uniquement la liste des extensions
docker compose run --rm app pokemon-arbitrage sync-tcgdex --directory

# Consulter les 50 tâches les plus récentes en JSON, sans réseau
docker compose run --rm app pokemon-arbitrage sync-tcgdex --status

# Exécuter au plus une requête immédiatement disponible, sans lancer une boucle
docker compose run --rm app pokemon-arbitrage sync-tcgdex --once
```

## Données protégées et portée ML

L’enrichissement met à jour les tables de référence et sa propre progression. Il conserve les identifiants SQLite des références, les attributs détaillés absents des résumés et les confirmations humaines. Il ne réécrit ni annonces, ni observations, ni annotations ; la réidentification reste une action explicite depuis le catalogue.

Seuls les identifiants des extensions et cartes choisis sont envoyés à TCGdex. Aucun titre d’annonce, description ou donnée vendeur n’est transmis par ce service. Le téléchargement des données ne lance aucun entraînement ML et ne suffit pas à identifier une annonce dépourvue d’indices. Il améliore la couverture des candidats disponibles pour le matcher et le futur classement appris.

Les tests `tests/test_tcgdex_sync.py` utilisent des réponses simulées : progression, reprise, erreurs, concurrence, transactionnalité, préservation des décisions humaines, routes, CLI et migration sur une base préexistante.
