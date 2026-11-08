# 🤖 Guide Développeur pour Agents de Code — Pokébourse

Bienvenue, agent de code (Cursor, Claude Code, Antigravity, Devin, Copilot, Aider, etc.).  
Ce document est votre **boussole technique absolue** pour comprendre le projet, naviguer dans la documentation, respecter l'architecture et développer de manière fiable sur **Pokébourse**.

---

## 🗺️ 1. Cartographie de la Documentation : Où Trouver Quoi ?

Avant d'écrire ou de modifier du code, consultez les documents spécialisés du dépôt selon votre tâche :

| Document | Rôle & Contenu | Quand le consulter ? |
|---|---|---|
| [`README.md`](README.md) | **Guide produit & utilisateur** : présentation globale, capture d'écran, visite guidée, installation et CLI. | Pour comprendre la valeur métier, le parcours utilisateur et l'interface web. |
| [`TASKING_PROJET.md`](TASKING_PROJET.md) | **Suivi consolidé** : état des chantiers, dépendances, critères ouverts et ordre de reprise. | Avant de reprendre un tasking ; à actualiser à chaque livraison. |
| [`AGENTS.md`](AGENTS.md) | **Ce guide** : règles d'or, architecture interne, conventions, workflow de dev et commandes de test. | **À lire impérativement avant toute session de travail.** |
| [`SOURCES.md`](SOURCES.md) | **Audit légal et technique des sources** : conditions d'accès (Vinted, Leboncoin, eBay, Wallapop, TCGdex, Cardmarket), respect des CGU, limitations anti-bot, RGPD et solutions de repli. | Dès qu'une modification touche aux collecteurs, au scraping ou aux API externes. |
| [`SUIVI.md`](SUIVI.md) | **Historique de stabilisation** : audits du pipeline, corrections passées, intégration de TCGdex, Cardmarket, extension Chrome et ML Phase 0. | Pour comprendre l'historique des choix d'architecture et éviter de réintroduire d'anciens bugs. |
| [`TASKING_INTEGRATION_DESIGN.md`](TASKING_INTEGRATION_DESIGN.md) | **Directives UI Mosaic × Flowbite** : règles de style CSS/HTML, maquettes prototypes historiques (`prototype.html`) et cibles (`prototype-cible.html`). | Pour toute modification d'un template Jinja2 (`app/templates/`) ou du style (`app/static/style.css`). |
| [`TASKING_SIMPLIFICATION_CIBLE.md`](TASKING_SIMPLIFICATION_CIBLE.md) | **Spécifications simplification & navigation** : parcours « Capturer → Décider → Suivre l'achat », vues `/achats`, `/reglages`, `/gestion`. | Lors de travaux sur la restructuration des pages ou de la navigation. |
| [`TASKING_RECHERCHE_TENDANCES.md`](TASKING_RECHERCHE_TENDANCES.md) | **Spécifications Recherche avancée & Tendances** : moteur `/search`, recherche externe, métriques `/trends` (avg7/avg30, activité). | Lors de travaux sur la recherche plein texte/attributs ou les tendances de marché. |
| [`PLAN_RADAR_OPPORTUNITES.md`](PLAN_RADAR_OPPORTUNITES.md) | **Radar partiellement réalisé** : observations/décisions présentes, page, recherches groupées et notifications à compléter. | Pour les décisions d’examen et alertes ; réutiliser les contrats de prix Identification/T09 et T15–T18. |
| [`PROMPT_PATCH_EXTRACTION.md`](PROMPT_PATCH_EXTRACTION.md) | **Spécifications extraction de preuves renforcée** : numéros isolés sous garde-fous, certificateurs additionnels (`CollectAura`), formats collés. | Lors de travaux sur le détecteur d'identification ou le content script de l'extension. |
| [`TASKING_RECHERCHE_CARTES.md`](TASKING_RECHERCHE_CARTES.md) | **Spécifications recherche approfondie et confirmations TCGdex** : candidats locaux, recherche ciblée worker, file dédupliquée et révisions. | Lors de travaux sur la réconciliation manuelle ou l'intégration TCGdex. |
| [`TASKING_IDENTIFICATION_FIABLE.md`](TASKING_IDENTIFICATION_FIABLE.md) | **Plan actif, acquis et critères restants** : preuves, lots, langues, alias, couverture, OCR, validation humaine, benchmark et vision conditionnelle. | Pour fiabiliser le parcours capture → identification → décision et qualifier ses performances. |
| [`docs/IDENTIFICATION_LEXICALE.md`](docs/IDENTIFICATION_LEXICALE.md) | **Diagnostic lexical & suggestions orthographiques** : index trigrammes, distance d'édition, vocabulaire TCGdex et limitations. | Lors de travaux sur la recherche lexicale ou les faux négatifs d'identification. |
| [`docs/identification/T08_CONTROLES_MOTEUR_ACTUEL.md`](docs/identification/T08_CONTROLES_MOTEUR_ACTUEL.md) | **Contrôles moteur actuel & capture** : séparation titre/nom, neutralisation du parasite `n`, isolation prix/identité et langue `und`. | Lors de travaux sur le préremplissage, la saisie manuelle ou la prévisualisation de capture. |
| [`docs/identification/T19_COLLECTE_OCR.md`](docs/identification/T19_COLLECTE_OCR.md) | **Spécification collecteurs & file OCR** : contrat de collecte, galerie, concurrence app/worker et pipeline d'arrière-plan. | Lors de travaux sur les adaptateurs de collecte ou la file OCR. |
| [`docs/identification/T03_EVIDENCE.md`](docs/identification/T03_EVIDENCE.md) | **Observations et décision commune** : contrat `identity_evidence`, provenances, observations et diagnostics de conflits. | Lors de travaux sur la décision commune d'identification. |
| [`docs/identification/T15_SOURCES_PRIX.md`](docs/identification/T15_SOURCES_PRIX.md) | **Matrice des capacités de prix** : offres actives, ventes conclues et cotes agrégées par plateforme. | Lors de travaux sur l'évaluation financière ou le raccordement de sources de prix. |
| [`docs/ML_PHASE0.md`](docs/ML_PHASE0.md) | **Protocole du pilote d'annotation ML Phase 0** : tirage stratifié, doubles lectures indépendantes et export reproductible. | Lors de travaux sur l'annotation, la labellisation ou la préparation du dataset ML. |
| [`docs/TCGDEX_SYNC.md`](docs/TCGDEX_SYNC.md) | **Enrichissement TCGdex progressif** : sélection d’extensions, file persistante, pause/reprise, cache et limites de couverture. | Lors de travaux sur la synchronisation du référentiel. |
| [`MACHINE_LEARNING_DESIGN.md`](MACHINE_LEARNING_DESIGN.md) & [`PROMPT_ML_DESIGN.md`](PROMPT_ML_DESIGN.md) | **Spécifications futures ML** : feuille de route pour le rattachement d'entités, ranking LightGBM, embeddings et vérité terrain. | Lors de travaux sur l'amélioration de l'identification automatique des cartes. |
| [`docs/identification/PLAN_VALIDATION_LOTS.md`](docs/identification/PLAN_VALIDATION_LOTS.md) & [`tracker.md`](tracker.md) | **Validation et incidents** : critères par lot, preuves, reproduction et revalidation. | Avant de déclarer un lot terminé ou pour suivre un obstacle de validation. |
| [`extension/README.md`](extension/README.md) | **Spécifications de l'extension Chrome** : Manifest V3, content scripts, service worker, formats JSONL et tests associés. | Pour toute tâche liée au module de capture dans le navigateur. |
| [`app/storage/migrations/`](app/storage/migrations/) | **Schéma relationnel SQLite versionné** : 26 migrations séquentielles (de `0001` à `0026` au 8 novembre 2026 ; vérifier le répertoire avant ajout). | Avant toute modification de base de données ou de modèle de données. |

---

## 🧱 2. Stack Technique & Environnement

Pokébourse est conçu pour fonctionner **100 % en local**, sans serveur cloud distant, sans compte marketplace et sans dépendances frontend lourdes :

- **Langage** : Python 3.12 (standard moderne, typage strict `type | None`).
- **Backend Web** : [FastAPI](https://fastapi.tiangolo.com/) (routage asynchrone / synchrone, cycle de vie `lifespan`).
- **Validation des données** : [Pydantic v2](https://docs.pydantic.dev/) (`BaseModel`, validation stricte des schémas d'annonces).
- **Traitement d'images & OCR local** : [Pillow](https://python-pillow.org/) + Tesseract OCR (`fra+eng`, exécution 100% locale et éphémère sans stockage de fichier ni appel externe).
- **Base de données** : SQLite 3 en mode **WAL** (`PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000; PRAGMA foreign_keys=ON;`).
  - Sauvegardes à chaud via l'API en ligne `sqlite3_backup`.
  - Migrations SQL versionnées et séquentielles dans `app/storage/migrations/`.
- **Interface Utilisateur** : Templates Jinja2 serveur + Vanilla HTML5 / CSS3 / JavaScript (aucun framework JS distant, aucun bundler Vite/Webpack, design système autonome Mosaic × Flowbite).
- **Worker d'arrière-plan** : Script autonome `app.worker` géré par Docker Compose pour exécuter les veilles périodiques en parallèle du serveur web.
- **Extension Chrome** : Manifest V3 pur Vanilla JS (`chrome.storage.local`, service worker éphémère).
- **Déploiement** : Docker Compose multi-services :
  - Service `app` : Uvicorn + FastAPI sur `http://localhost:8000`.
  - Service `worker` : boucle de surveillance `python -m app.worker`.
  - Volume persistant : `pokemon-data` monté sur `/data`.

---

## 📜 3. Les 6 Règles d'Or Inviolables du Projet

En tant qu'agent de code, vous devez respecter scrupuleusement ces 6 principes fondamentaux :

### 🧪 Règle 1 : Herméticité absolue des tests (`pytest`)
- **Aucun test automatisé ne doit émettre d'appel réseau réel** vers Vinted, Leboncoin, eBay ou l'API TCGdex.
- Utilisez systématiquement les mocks (`unittest.mock`, `pytest_mock`) et le jeu de données local embarqué (`app/tcgdex/data/seed_data.py`).
- Les tests doivent s'exécuter rapidement et réussir à 100 % dans le conteneur Docker.

### 💾 Règle 2 : Intégrité SQLite & Sauvegarde des données
- **Ne lancez jamais** `docker compose down -v` ou `down --volumes` : le volume `pokemon-data` contient les données réelles de l'utilisateur.
- Toute évolution du schéma de la base de données **doit impérativement faire l'objet d'un nouveau fichier de migration SQL numéroté** dans `app/storage/migrations/` (ex: `0011_nom_descriptif.sql`).
- Chaque fichier de migration doit commencer par `BEGIN IMMEDIATE;`, se terminer par `COMMIT;`, et enregistrer son nom dans la table `schema_migrations`.

### 💰 Règle 3 : Précision monétaire en centimes et points de base
- **Ne jamais utiliser de `float` pour manipuler de l'argent ou des taux**. Les erreurs d'arrondis à virgule flottante sont interdites.
- Les montants sont obligatoirement des entiers en centimes : `price_cents`, `shipping_cents`, `min_net_profit_cents`.
- Les pourcentages et commissions sont en points de base (`bps`) : $1\% = 100\text{ bps}$, $5\% = 500\text{ bps}$, $15,5\% = 1550\text{ bps}$.
- L'arrondi monétaire appliqué est l'arrondi demi-supérieur (`ROUND_HALF_UP`).
- Les conversions de devises et paramètres de requêtes collecteurs (Vinted, eBay) utilisent une arithmétique entière exacte (`f"{cents // 100}.{cents % 100:02d}"`), jamais de division flottante (`cents / 100`), avec rejet des centimes négatifs.

### 📦 Règle 4 : Règle absolue des Lots dans l'identification
- Si une annonce correspond à un lot, un coffret, un booster ou un paquet en vrac (`is_lot = 1`), **il est formellement interdit de lui attribuer arbitrairement l'identifiant d'une carte unitaire TCGdex**.
- Le matcher (`app/identification/matcher.py`) doit la classer avec le statut `lot` avec un motif explicite.

### ⏳ Règle 5 : Préservation des métadonnées temporelles
- Lors de la ré-ingestion d'une annonce déjà existante (`UNIQUE(source_id, external_id)`), le champ `first_seen_at` ne doit **jamais** être écrasé.
- Seuls `last_seen_at`, `price_cents`, `shipping_cents`, `url` et `raw_data` peuvent être actualisés.

### 🔒 Règle 6 : Respect strict du RGPD pour les vendeurs
- L'enrichissement des données publiques vendeur (`app/sellers/collect.py`) applique une **liste blanche stricte**.
- Ne jamais stocker ni journaliser de données personnelles privées (adresses email réelles, noms civils, numéros de téléphone, coordonnées postales).

---

## 📂 4. Arborescence du Code & Responsabilités

```text
pokebourse/
├── app/
│   ├── cardmarket/          # Intégration officielle Cardmarket (price guide quotidien & repli)
│   │   ├── aliases.py       # Pont multilingue et alias de noms TCGdex vers Cardmarket
│   │   ├── client.py        # Client HTTP OAuth 1.0a (dormant, inscriptions fermées)
│   │   ├── daily.py         # Planification de synchronisation quotidienne du price guide
│   │   ├── guide.py         # Téléchargement et intégration SQLite du guide public (~80k cartes)
│   │   ├── models.py        # Modèles de cotes, tendances et moyennes Cardmarket
│   │   └── service.py       # Résolution des cotes et modèle de repli à 3 niveaux
│   ├── collectors/          # Connecteurs de collecte (Vinted, Leboncoin, eBay, Wallapop, Normaliseur, Service)
│   │   ├── models.py        # Modèle Pydantic CollectedListing commun
│   │   ├── vinted.py        # Connecteur HTTP Vinted
│   │   ├── leboncoin.py     # Connecteur HTTP Leboncoin
│   │   ├── ebay.py          # Connecteur HTTP eBay
│   │   ├── wallapop.py      # Connecteur HTTP Wallapop
│   │   ├── page_extract.py  # Extraction bornée de métadonnées HTML autorisées
│   │   ├── normalizer.py    # Transformation vers le modèle unifié
│   │   ├── service.py       # Ingestion transactionnelle et déduplication
│   │   └── browser.py       # Collecteur de secours Crawlee/Playwright (désactivé par défaut)
│   ├── identification/      # Moteur de réconciliation, diagnostic lexical, OCR & validation ML
│   │   ├── aliases.py       # Résolution d'alias contrôlés et normalisation de références
│   │   ├── annotation_pilot.py # Tirage stratifié et gestion du pilote d'annotation Phase 0
│   │   ├── dataset.py       # Export reproductible du dataset de validation ML (labels.jsonl)
│   │   ├── detector.py      # Détection regex : numéros (fractions, isolés), extensions, langues, états, lots
│   │   ├── diagnostics.py   # Diagnostic des annonces non résolues et inventaire du catalogue
│   │   ├── evidence.py      # Observations et preuves structurées d'identité (identity_evidence)
│   │   ├── evidence_store.py# Magasin atomique de preuves visuelles (.sqlite.evidence)
│   │   ├── lexical.py       # Recherche approchée par trigrammes et distance d'édition
│   │   ├── matcher.py       # Rapprochement avec le catalogue TCGdex et calcul de confiance
│   │   ├── models.py        # IdentificationResult, CardFeatures, statuts (identified, ambiguous, lot, unidentified)
│   │   ├── normalization.py # Normalisation de chaînes, accents, casse et numéros
│   │   ├── ocr.py           # Lecture locale éphémère d'images (Tesseract), cadrage et suggestions
│   │   ├── pipeline.py      # Orchestration du pipeline de détection et matching
│   │   ├── reference_search.py # Recherche plein texte et approchée dans le référentiel officiel
│   │   ├── research.py      # File d'enrichissement approfondi traitée par le worker
│   │   ├── resolution.py    # Résolution commune : arbitrage automatique vs validations humaines
│   │   └── reviews.py       # Gestion des validations humaines, double lecture aveugle et audit
│   ├── search/              # Module de recherche avancée multi-critères
│   │   ├── models.py        # Modèles de filtres, portées (tout, cartes, annonces) et tris
│   │   ├── service.py       # Moteur de recherche plein texte, attributs et export CSV
│   │   └── external.py      # Recherche externe contrôlée (TCGdex, eBay) et import en 1 clic
│   ├── trends/              # Module Tendances de marché & opportunités
│   │   ├── models.py        # Modèles de variations de prix (avg7 vs avg30), activité et opportunités
│   │   ├── service.py       # Calcul des mouvements de prix et agrégation d'activité des annonces
│   │   └── opportunities.py # Radar des meilleures affaires d'arbitrage
│   ├── tcgdex/              # Intégration du catalogue officiel Pokémon (TCGdex)
│   │   ├── client.py        # Client HTTP REST avec backoff et gestion de rate-limit
│   │   ├── cache.py         # Cache SQLite persistant (pokemon_reference_cards/sets)
│   │   ├── sync.py          # Synchronisation progressive et durable du catalogue français
│   │   └── data/seed_data.py# Données officielles embarquées pour fonctionnement 100% hors-ligne
│   ├── sellers/             # Annuaire des vendeurs & Suivi du portefeuille d'achats
│   │   ├── models.py        # SellerProfile, SellerReviewSummary, Purchase
│   │   ├── repository.py    # Accès SQLite aux vendeurs et aux achats
│   │   ├── service.py       # Scoring d'avis (étoiles), gestion des favoris et notes
│   │   └── collect.py       # Enrichissement avec respect de la liste blanche RGPD
│   ├── supervision/         # Supervision de la santé des scrapers
│   │   ├── models.py        # AgentState, CollectorState, AgentIncident, codes d'erreur
│   │   ├── repository.py    # Historisation des états et transitions en base
│   │   └── service.py       # Heartbeats, sonde IP publique, transitions d'état et reprise manuelle
│   ├── monitoring/          # Veilles programmées
│   │   ├── repository.py    # CRUD des veilles (listing_watches) et exécutions (listing_watch_runs)
│   │   ├── scheduler.py     # Ordonnancement périodique et verrous de concurrence par plateforme
│   │   └── service.py       # Logique d'activation, pause, contrôle immédiat
│   ├── storage/             # Gestion de la persistance SQLite
│   │   ├── database.py      # Création des connexions avec WAL et busy_timeout
│   │   └── migrations/      # Migrations SQL séquentielles (0001 à 0026 au 8 novembre 2026)
│   ├── templates/           # Vues HTML Jinja2 (Mosaic × Flowbite)
│   │   ├── base.html        # Layout global : sidebar, topbar, menu « Ajouter des annonces »
│   │   ├── dashboard.html   # Tableau de bord principal (KPIs, opportunités, imports)
│   │   ├── catalog.html     # Opportunités unifiées (catalogue + rentabilité, verdicts, export)
│   │   ├── catalog_detail.html # Fiche détaillée annonce, rentabilité, comparables, TCGdex & OCR
│   │   ├── search.html      # Recherche avancée multi-critères et externe
│   │   ├── trends.html      # Tendances de marché, variations de prix et activité
│   │   ├── achats.html      # Suivi des achats, cycle de vie et prix de vente réels
│   │   ├── reglages.html    # Paramétrage des frais, seuils, cotes manuelles et Cardmarket
│   │   ├── gestion.html     # Hub de gestion avancée (accès aux modules secondaires)
│   │   ├── manual_listing.html # Saisie manuelle d'annonce par URL avec pré-analyse
│   │   ├── capture_preview.html # Prévisualisation d'annonce capturée par l'extension Chrome
│   │   ├── tcgdex_sync.html # Enrichissement et suivi de synchronisation TCGdex
│   │   ├── watches.html     # Gestion et contrôle des veilles multi-plateformes
│   │   ├── sellers.html     # Annuaire des vendeurs et carnet d'achats
│   │   ├── seller_detail.html # Fiche vendeur détaillée et historique d'achats
│   │   ├── agents.html      # Supervision en direct des collecteurs et IP publiques
│   │   ├── agent_detail.html# Détail d'un agent et historique d'incidents
│   │   ├── backups.html     # Sauvegarde et restauration SQLite
│   │   ├── tasking.html     # Vue de suivi du projet, plans et incidents en lecture seule
│   │   ├── annotation_dashboard.html # Tableau de bord du pilote d'annotation ML Phase 0
│   │   ├── annotation_blocked.html   # Écran d'attente d'un second opérateur
│   │   ├── identification_diagnostics.html # Diagnostic des annonces non résolues
│   │   ├── identification_review.html # Formulaire de validation humaine et double lecture aveugle
│   │   └── import_detail.html # Détail d'un lot d'import et journal d'erreurs
│   ├── static/              # Fichiers statiques (style.css, forms.js, ocr.js, prototypes)
│   ├── capture_preview.py   # Prévisualisation sans écriture des captures Chrome
│   ├── catalog.py           # Services métier du catalogue (recherche, filtres, pagination, lots)
│   ├── catalog_export.py    # Génération d'export CSV Excel conforme
│   ├── gestion.py           # Données de synthèse du hub de gestion avancée
│   ├── listing_identity.py  # Détection d'annonces identiques et normalisation d'URL
│   ├── listing_preview.py   # Prévisualisation indicative locale sans écriture
│   ├── manual_listing.py    # Saisie assistée par URL d'annonce sans téléchargement distant
│   ├── profitability.py     # Moteur financier (calcul gain net, ROI, cotes de marché, comparables)
│   ├── purchases.py         # Synthèse des achats, cycle de vie et montants par devise
│   ├── tasking.py           # Lecture seule des plans Markdown et suivi projet
│   ├── backups.py           # Logique de sauvegarde SQLite et vérification d'intégrité
│   ├── cli.py               # Interface CLI Typer (pokemon-arbitrage)
│   ├── web.py               # Serveur FastAPI et toutes les routes HTTP
│   └── worker.py            # Point d'entrée de la boucle de veille en arrière-plan
├── docs/                    # Documentation technique spécialisée
│   ├── IDENTIFICATION_LEXICALE.md # Diagnostic lexical, trigrammes, numéros isolés et certificateurs
│   ├── ML_PHASE0.md         # Protocole du pilote d'annotation Phase 0 et double lecture
│   └── TCGDEX_SYNC.md       # Enrichissement progressif TCGdex et gestion de file
├── extension/               # Module Google Chrome Manifest V3
│   ├── manifest.json        # Déclarations V3 et permissions minimales
│   ├── background/          # Service worker Chrome (stockage local et badge)
│   ├── content/             # Content script injecté (détection Pokémon, extracteurs, numéros isolés)
│   ├── popup/               # Interface popup (liste de captures, prévisualisation, push local, JSONL)
│   └── icons/               # Icônes PNG officielles (16, 48, 128 px)
├── scripts/                 # Scripts utilitaires en lecture seule ou de test ponctuel
│   ├── comparables_report.py # Rapport de contrôle des comparables et preuves de prix
│   └── manual_collect_test.py # Test ponctuel manuel d'une recherche marketplace
└── tests/                   # 58 fichiers test_*.py ; 860 tests passants dans Docker au 8 novembre 2026
```

---

## 🧪 5. Commandes de Développement & Tests

Toutes les commandes doivent être exécutées dans le conteneur Docker pour garantir la parité d'environnement :

### Lancer la suite de tests
```bash
# Exécution complète de tous les tests
docker compose run --rm app pytest

# Exécution verbeuse avec détails
docker compose run --rm app pytest -v
```

### Tester un module spécifique
```bash
# Tester l'extension Chrome, prévisualisation et workflow de capture
docker compose run --rm app pytest tests/test_chrome_extension.py tests/test_capture_preview.py tests/test_capture_workflow.py -v

# Tester le moteur d'identification, numéros isolés et réconciliation TCGdex
docker compose run --rm app pytest tests/test_identification.py tests/test_candidate_number_warning.py tests/test_tcgdex_cache.py -v

# Tester la recherche avancée multi-critères, tris financiers et externe
docker compose run --rm app pytest tests/test_search.py -v

# Tester les tendances de marché, pagination et opportunités
docker compose run --rm app pytest tests/test_trends.py -v

# Tester la saisie d'annonce manuelle par URL et la prévisualisation locale
docker compose run --rm app pytest tests/test_manual_listing.py tests/test_listing_preview.py tests/test_page_extract.py -v

# Tester l'OCR local éphémère (Tesseract), cadrage et preuves visuelles
docker compose run --rm app pytest tests/test_ocr_local.py tests/test_ocr_web.py tests/test_ocr_crop_browser.py tests/test_visual_evidence.py -v

# Tester la simplification de la navigation et les pages cibles (/achats, /reglages, /gestion)
docker compose run --rm app pytest tests/test_simplification_navigation.py tests/test_simplification_avancee.py -v

# Tester le suivi de projet en lecture seule (/tasking)
docker compose run --rm app pytest tests/test_tasking.py -v

# Tester la recherche lexicale, les diagnostics et la recherche approfondie
docker compose run --rm app pytest tests/test_lexical_identification.py tests/test_identification_research.py -v

# Tester le pilote d'annotation ML Phase 0 et les validations humaines
docker compose run --rm app pytest tests/test_annotation_pilot.py tests/test_identification_reviews.py -v

# Tester l'intégration Cardmarket (guide public, repli, sync quotidienne)
docker compose run --rm app pytest tests/test_cardmarket.py tests/test_cardmarket_guide.py tests/test_cardmarket_daily.py -v

# Tester le moteur de rentabilité, comparables et calcul de marge
docker compose run --rm app pytest tests/test_profitability.py -v

# Tester l'annuaire vendeurs, le carnet d'achats et les prix de vente réels
docker compose run --rm app pytest tests/test_sellers_directory_and_purchases.py tests/test_sellers.py -v

# Tester la supervision et les collecteurs (Vinted, Leboncoin, eBay, Wallapop)
docker compose run --rm app pytest tests/test_supervision.py tests/test_collectors.py -v

# Tester l'idempotence des migrations SQLite (inventaire courant : 0001 à 0026)
docker compose run --rm app pytest tests/test_migrations.py -v
```

### Commandes CLI utiles (`pokemon-arbitrage`)
```bash
# Vérifier l'état de la base de données
docker compose run --rm app pokemon-arbitrage check

# Forcer le rejeu des migrations
docker compose run --rm app pokemon-arbitrage migrate

# Effectuer un backup d'urgence
docker compose run --rm app pokemon-arbitrage backup

# Lancer un diagnostic lexical d'identification (JSON ou texte)
docker compose run --rm app pokemon-arbitrage diagnose-identification --status all --limit 100 --json

# Exporter le jeu de labels ML du pilote
docker compose run --rm app pokemon-arbitrage export-labels --output /data/labels-pilote.jsonl

# Exécuter le rapport des comparables et preuves de prix (lecture seule)
docker compose run --rm app python -m scripts.comparables_report
```

---

## 🚀 6. Guide Pas-à-Pas pour vos Développements (Workflows)

### Cas 1 : Vous devez modifier le schéma SQLite
1. Repérez le dernier numéro de migration dans `app/storage/migrations/` (`0026_tcgdex_sync_locale.sql` au 8 novembre 2026 ; vérifier l’état courant).
2. Créez le numéro suivant disponible (`0027_<nom_explicite>.sql` seulement si `0026` reste le dernier).
3. Encadrez toujours vos instructions SQL avec :
   ```sql
   BEGIN IMMEDIATE;
   
   -- Vos ALTER TABLE ou CREATE TABLE ici
   
   INSERT INTO schema_migrations (version) VALUES ('0027_<nom_explicite>.sql');
   COMMIT;
   ```
4. Mettez à jour `tests/test_migrations.py` pour inclure le nouveau numéro de migration attendu.
5. Lancez `docker compose run --rm app pytest tests/test_migrations.py` pour valider l'idempotence.

### Cas 2 : Vous modifiez une règle d'identification de carte
1. Les patterns regex de détection se trouvent dans `app/identification/detector.py`.
2. La logique de scoring et de classification (`identified`, `ambiguous`, `lot`, `unidentified`) se trouve dans `app/identification/matcher.py`.
3. **Important** : Ne baissez jamais les seuils d'exigence sans preuve formelle. Tout cas ambigu doit rester `ambiguous`.
4. Validez vos changements avec `docker compose run --rm app pytest tests/test_identification.py`.

### Cas 3 : Vous modifiez un écran ou un template web
1. Les templates héritent de `app/templates/base.html`.
2. Suivez scrupuleusement la charte **Mosaic × Flowbite** décrite dans `TASKING_INTEGRATION_DESIGN.md`.
3. **N'ajoutez aucune ressource distante** (CDN Google Fonts, Tailwind CDN, bibliothèques JS externes). Tout le CSS et le JS résident localement dans `app/static/style.css` et `app/static/forms.js`.
4. Validez le rendu et les routes avec `docker compose run --rm app pytest tests/test_web.py`.

### Cas 4 : Vous faites évoluer l'extension Chrome
1. Fichiers situés dans `extension/`.
2. Conservez la conformité **Manifest V3** (`extension/manifest.json`).
3. Toute nouvelle propriété extraite doit être validée dans `tests/test_chrome_extension.py`.
4. Veillez à ce que le format JSONL généré reste 100 % compatible avec `app.catalog.parse_jsonl()`.

---

### Suivi des erreurs du chantier Identification/OCR

Pour les lots de `TASKING_IDENTIFICATION_FIABLE.md`, consulter [le plan skills/tests/intégrations/validation](docs/identification/PLAN_VALIDATION_LOTS.md). Toute erreur rencontrée ou tout problème d'intégration qui empêche une validation requise doit être créé ou mis à jour dans [`tracker.md`](tracker.md) : ID stable, lot/étape, preuve, reproduction, responsable de la prochaine action et tests de revalidation. Distinguer défaut observé, risque à reproduire et capacité indisponible. Mettre à jour l'entrée avec le correctif et les résultats ; ne pas la clôturer sur la seule modification du code ni présenter un test sauté/non exécuté comme passant. Un incident bloquant empêche la validation du périmètre concerné, sans interrompre les autres travaux indépendants.

---

## ⚠️ 7. Anti-Patterns & Pièges Fréquents à Éviter

- ❌ **Anti-pattern 1 : `float` pour les prix** :  
  *Faux* : `roi = net_profit / buy_price`  
  *Correct* : `roi_bps = (net_profit_cents * 10000) // total_cost_cents` (en centimes et points de base entiers).
- ❌ **Anti-pattern 2 : Appel HTTP externe dans les tests** :  
  *Faux* : Appeler `requests.get("https://api.tcgdex.net/...")` dans un test.  
  *Correct* : Mocker la méthode avec `unittest.mock.patch` ou utiliser `TcgdexCache` avec `seed_data`.
- ❌ **Anti-pattern 3 : Écraser `first_seen_at`** :  
  Lors d'un deuxième passage d'une veille sur la même annonce, seule la date `last_seen_at` doit avancer.
- ❌ **Anti-pattern 4 : Ajouter Tailwind ou React** :  
  Le projet a fait le choix délibéré d'un rendu HTML/CSS pur et rapide via Jinja2 sans dépendance Node.js ni bundler côté serveur.
- ❌ **Anti-pattern 5 : `docker compose down -v`** :  
  Effacerait le volume SQLite `pokemon-data` de l'utilisateur. Préférez toujours `docker compose down`.

---

## Suivi documentaire à chaque livraison

Mettre à jour [TASKING_PROJET.md](TASKING_PROJET.md), le plan concerné et le bilan daté de [SUIVI.md](SUIVI.md). Vérifier les critères individuellement : code, tests, recette, qualification et disponibilité externe restent distincts. Les anciens numéros de migration et inventaires dans les rapports historiques ne sont pas des instructions courantes. Les défauts et obstacles de validation vont dans [tracker.md](tracker.md), avec mise à jour du tableau de synthèse et du détail sous le même ID.

## ✅ Checklist Finale avant d'Achever votre Tâche

Avant de considérer votre mission terminée, assurez-vous que :
- [ ] Tous les tests automatisés passent : `docker compose run --rm app pytest` retourne un code 0.
- [ ] Aucune régression n'a été introduite dans les migrations SQLite (`test_migrations.py`).
- [ ] Aucune dépendance externe non sollicitée n'a été ajoutée à `pyproject.toml`.
- [ ] Les règles RGPD sur les données vendeurs sont respectées.
- [ ] Les docstrings et le typage strict (`Python 3.12`) sont renseignés sur les nouvelles fonctions.
- [ ] Si un nouvel écran ou une commande CLI a été ajouté, le `README.md` a été mis à jour en conséquence.
