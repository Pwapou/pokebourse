# Suivi de stabilisation — Pokébourse

Date du contrôle initial : 2026-11-01  
Date de la révision TCGdex & Identification : 2026-11-01

---

## 1. État initial constaté et audit du pipeline existant

- **Infrastructure Docker Compose** :
  - Services `app` et `worker` opérationnels avec contrôle de santé `/health`.
  - Volume de données `pokemon-data` monté sur `/data` préservé sans modification destructive.
- **Audit de l'existant (Partie 1)** :
  1. *Collecteurs & Worker* : Présence des connecteurs Vinted (`vinted_scraper`) et Leboncoin (`lbc`), worker autonome `app/worker.py` avec `WatchScheduler` et `WatchSupervisor`. Concurrence bornée à 1 par plateforme.
  2. *Parcours réel d'une annonce* : Veille → recherche première page → normalisation `CollectedListing` → ingestion `catalog_items` (avec batch_id dédié) → affichage catalogue `/catalog` et fiche `/catalog/{id}`.
  3. *Champs conservés vs perdus* :
     - Conservés : `external_id`, `price_cents`, `url`, `image_url` (1ère image), `seller`, `published_at`, `first_seen_at`, `last_seen_at`, `original_title`, `raw_data`.
     - Perdus / non exploités : la description textuelle complète n'était pas stockée dans une colonne dédiée de `catalog_items` ; `shipping_cents` restait nul par défaut en l'absence de données précises sur les listes de recherche.
     - Écrasement critique : `catalog_item_from_listing` utilisait un filtre regex strict (`_EXPLICIT_CARD_PATTERN`). Si le titre ne respectait pas exactement `Carte Pokémon <Nom> - <Set>`, l'annonce recevait systématiquement le libellé « Carte non identifiée » et « Non identifiée ».
  4. *Déduplication & Intégrité* : Déduplication stricte par `UNIQUE (source_id, external_id)`, préservation de `first_seen_at`, mise à jour de `price_cents` et `last_seen_at` en cas de changement.
  5. *Veilles & Données accessibles* :
     - Code présent : connecteurs fonctionnels en simulation avec mocks.
     - Tests automatisés : 100 % simulés sans appel réseau.
     - Collecte réelle : non garantie dans le temps en raison des restrictions anti-bot (Cloudflare, DataDome 403/429).
  6. *Moteur de prix* : En l'absence d'identification fiable, quasi 100 % des annonces collectées se retrouvaient sans cote (`sans_cote` / « Données insuffisantes »), paralysant le moteur de rentabilité.
  7. *TCGdex existant* : Aucun composant, aucun modèle, aucune table n'existait pour TCGdex ou le catalogue de référence Pokémon.

---

## 2. Corrections et ajouts réalisés

### A. Intégration du catalogue officiel Pokémon (TCGdex) & Cache local autonome
1. **Migration SQLite `0008_create_pokemon_reference_catalog.sql`** :
   - Création de `pokemon_reference_sets` (extensions officielles, séries, dates de sortie, visuels).
   - Création de `pokemon_reference_cards` (cartes officielles avec `tcgdex_id`, `local_id`, nom officiel français, rareté, types, points de vie, illustrateur, etc.).
   - Ajout des colonnes d'identification dans `catalog_items` : `identification_status`, `reference_card_id`, `identification_confidence`, `identification_reason`, `is_lot`.
2. **Client TCGdex (`app/tcgdex/client.py`)** :
   - Client HTTP REST vers `https://api.tcgdex.net/v2/fr`.
   - Timeout borné à 10s, 3 tentatives avec backoff exponentiel et jitter, respect du header `Retry-After` et gestion typée des erreurs (`TcgdexNotFoundError`, `TcgdexRateLimitError`, `TcgdexNetworkError`).
3. **Cache local persistant (`app/tcgdex/cache.py`)** :
   - Stockage SQLite autonome.
   - Jeu de seed pré-embarqué (`app/tcgdex/data/seed_data.py`) incluant les cartes et extensions emblématiques en français (*Set de Base*, *Évolutions*, *151*, *Ténèbres Embrasées*, *Flammes Obsidiennes*, *Évolution Céleste*) permettant un fonctionnement 100 % hors-ligne immédiat sans appel réseau.

### B. Moteur d'identification et de réconciliation des annonces (`app/identification/`)
1. **Détecteur de caractéristiques (`app/identification/detector.py`)** :
   - Détection explicite des lots, coffrets, displays, boosters et vrac (`is_lot=True`).
   - Extraction des numéros de carte (formats fractions `X/Y`, `#X`, `n°X`).
   - Détection des extensions officielles, langues (`fr`, `en`, `ja`), variantes (*Holo*, *Reverse*, *VMAX*, *VSTAR*, *ex*, *Secrète*, *Alternative*, *1ère Édition*), gradations (*PSA*, *PCA*, *BGS*, *CGC*) et états (*Near Mint*, *Neuf*, *Excellent*, *Played*).
2. **Réconciliateur de catalogue (`app/identification/matcher.py`)** :
   - **Règle absolue sur les lots** : aucune carte unitaire n'est attribuée arbitrairement à un lot ; l'annonce est marquée `lot` avec justification explicite.
   - **Identification certaine** : si le nom et le numéro concordent avec le référentiel TCGdex, statut `identified`, score de confiance élevé et liaison FK vers `pokemon_reference_cards`.
   - **Identification ambiguë** : si plusieurs cartes correspondent sans discriminant fort, marquage `ambiguous` (« À vérifier ») sans forcer d'association.
   - **Échec de correspondance** : l'annonce reste marquée `unidentified` (« Non identifiée ») mais demeure 100 % consultable et réexaminable ultérieurement.
   - **Présomption d'authenticité refusée** : aucune conclusion sur l'authenticité n'est tirée sur la simple foi du texte.

### C. Pipeline d'ingestion et interface utilisateur
1. **Ingestion transactionnelle (`app/collectors/service.py`)** :
   - Réconciliation automatique à l'ingestion via `CardMatcher`.
   - Mise à jour des noms officiels, numéros et variantes pour les annonces identifiées, permettant au moteur de rentabilité (`app/profitability.py`) de retrouver les cotes dans `market_references`.
2. **Interface web (`app/web.py`, `catalog.html`, `catalog_detail.html`)** :
   - Filtre par statut d'identification (`ident`) dans le catalogue.
   - Badges visuels d'identification : « Identifiée » (vert), « À vérifier » (ambre), « Lot » (bleu), « Non identifiée » (gris).
   - Fiche produit enrichie avec panneau dédié *Catalogue officiel Pokémon (TCGdex)* affichant la justification de la correspondance et la carte officielle liée.
   - Bouton et route d'action `POST /catalog/{id}/reidentify` pour réexaminer une annonce à la demande.
3. **Correction de `tests/test_migrations.py`** :
   - Prise en compte de la migration `0007_create_supervision.sql` et de `0008_create_pokemon_reference_catalog.sql`.
4. **Précision du connecteur Leboncoin (`app/collectors/leboncoin.py`)** :
   - Remontée explicite de l'erreur anti-bot DataDome lorsque l'exception est encapsulée.

### D. Module Google Chrome pour l'import assisté (`extension/`)
1. **Manifest V3 et architecture sécurisée** :
   - Conforme aux standards Google Chrome Manifest V3 (`extension/manifest.json`).
   - Service worker éphémère (`extension/background/service-worker.js`) gérant le stockage dédupliqué dans `chrome.storage.local` et l'affichage du badge d'annonces en attente.
   - Vraies icônes PNG respectant les dimensions imposées par Chrome (16x16, 48x48, 128x128).
2. **Content Script & Détection automatique (`extension/content/`)** :
   - Détection des mots-clés Pokémon (*pokémon*, *dracaufeu*, *charizard*, *pikachu*, etc.) sur n'importe quel site web visité.
   - Extracteurs dédiés pour Vinted, Leboncoin, et extracteur universel basé sur Schema.org / JSON-LD et OpenGraph.
   - Toast flottant discret prévenant l'utilisateur de la capture sans perturber la navigation.
3. **Interface utilisateur Popup (`extension/popup/`)** :
   - Sélection personnalisée des cartes à envoyer via cases à cocher unitaires et case « Tout sélectionner » avec compteur dynamique.
   - Envoi ciblé de la sélection vers Pokébourse (`POST /imports`).
   - Calcul et affichage immédiat en direct sous chaque carte du prix de revente estimé, du bénéfice net, du ROI et du verdict d'arbitrage.
   - Si la carte n'est pas encore cotée dans Pokébourse, indication explicite « Sans cote » et lien direct d'ajout de cote Cardmarket/eBay.
   - Visualisation des cartes capturées, vignette, prix d'achat, vendeur et lien source.
   - Suppression unitaire ou vidage complet de la liste.
   - Interrupteur de pause pour la capture automatique.
4. **Validation et tests automatisés (`tests/test_chrome_extension.py`)** :
   - Validation du Manifest V3, des en-têtes et formats binaires PNG réels.
   - Test de compatibilité des JSONL produits avec `app.catalog.parse_jsonl()`.
   - Test d'ingestion directe du JSONL dans la base de données et test HTTP du endpoint d'import avec en-tête `Accept: application/json`.
   - Test de calcul complet de rentabilité et retour de cote de revente (`test_import_with_known_resell_price_returns_full_profitability`).

### E. Référencement des Vendeurs, Pépites & Suivi des Achats (`app/sellers/`)
1. **Migrations SQLite `0009` et `0010`** :
   - Migration `0009_create_seller_profiles.sql` : table `seller_profiles` (réputation, avis, taux de réponse, ban), file d'enrichissement `seller_enrichment_queue` et colonne `seller_profile_id` dans `catalog_items`.
   - Migration `0010_create_purchases_and_seller_stats.sql` : table `purchases` pour le suivi des achats réels (carte, set, prix payé, frais de port, statut, date, notes), ajout de `is_favorite` et `user_notes` sur `seller_profiles`.
2. **Scoring de fiabilité & extraction en liste blanche** :
   - Modèle `SellerProfile` et calcul `reliability_rating` sur 5 étoiles avec garde-fous stricts (plafonnement si peu d'avis ou taux d'avis négatifs > 10 %).
   - Extraction des profils Vinted et Leboncoin sans conservation de données personnelles.
3. **Moteur de classement multi-axes (Sourcing & CRM)** :
   - Classement par **Fiabilité** (note en étoiles, réputation plateforme, avis positifs).
   - Classement par **Pépites / Opportunités** (nombre d'annonces de ce vendeur détectées en `opportunite` par le moteur de rentabilité).
   - Classement par **Achats réels** (nombre d'achats conclus, montant cumulé dépensé).
   - Filtre par **Favoris** (❤️) et recherche textuelle.
4. **Interface utilisateur & Actions** :
   - Page `/sellers` : annuaire avec filtres, tris et indicateurs clés.
   - Page `/sellers/{id}` : fiche détaillée regroupant 4 cartes métriques, réputation, formulaire de notes perso, historique d'achats passés, et annonces actives du vendeur dans le catalogue.
   - Page `/catalog/{id}` : lien direct vers la fiche vendeur et formulaire « Marquer cette annonce comme achetée » (`POST /catalog/{id}/purchase`).
   - Page `/catalog` : nom du vendeur cliquable menant directement à sa fiche profil.

---

## 3. Synthèse des tests automatisés

Commandes exécutées :
```bash
docker compose exec -T app pytest
```

| Fichier de test | Domaine testé | Statut |
|---|---|---|
| `tests/test_migrations.py` | Idempotence des 10 migrations SQLite, clés étrangères et tables | **5 passés** |
| `tests/test_sellers_directory_and_purchases.py` | Annuaire vendeurs, tri pépites/achats/fiabilité, favoris, CRM | **4 passés** |
| `tests/test_sellers.py` | Extraction liste blanche, calcul étoiles, ré-enfilement et reliaison | **16 passés** |
| `tests/test_chrome_extension.py` | Manifest V3, icônes PNG réelles, sélection, estimation revente & API | **5 passés** |
| `tests/test_tcgdex_cache.py` | Cache TCGdex, lecture hors-ligne, seed, gestion des erreurs 404/429/réseau | **5 passés** |
| `tests/test_identification.py` | Détection de lots, identification claire/ambiguë, variantes, champs manquants | **8 passés** |
| `tests/test_pipeline_integration.py` | Parcours complet collecte → identification → rentabilité → web | **4 passés** |
| `tests/test_collectors.py` | Connecteurs Vinted/Leboncoin, backoff, 403, 429, DataDome, collections vides | **8 passés** |
| `tests/test_watch_ingestion.py` | Ingestion, déduplication, conservation `first_seen_at`, màj prix | **7 passés** |
| `tests/test_monitoring_service.py` | Planification des veilles, scheduler, isolation des erreurs | **11 passés** |
| `tests/test_web.py` & `test_watches_web.py` | Routes web FastAPI, templates Jinja, pagination, filtres, imports API | **40 passés** |
| `tests/test_profitability.py` | Calculs de rentabilité, cotes de marché, profils de frais | **27 passés** |
| `tests/test_imports.py`, `test_backups.py`, `test_cli.py`, etc. | Imports JSONL, sauvegardes WAL/DELETE, export CSV, CLI | **43 passés** |
| **Total suite automatisée** | **Couverture intégrale sans aucun appel réseau réel** | **183 passés / 0 échec** |

---

## 4. Conditions d'accès aux sources et collecte réelle

- **Vérification contractuelle (`SOURCES.md`)** :
  - **Vinted** : Accès automatisé interdit par les CGU. Risques de blocage IP (Cloudflare 403/429).
  - **Leboncoin** : Accès par robot formellement interdit par les CGU et protégé par le droit de base de données. Blocage anti-bot DataDome immédiat.
  - **TCGdex** : Accès officiel autorisé (API publique communautaire open-source sous Fair Use avec cache local impératif).
- **Collecte réelle** :
  - **Aucune collecte réelle n'a été effectuée** sur Vinted ou Leboncoin lors de cette intervention, conformément à l'interdiction stricte du cahier des charges tant que les conditions d'accès autorisé ne sont pas formellement établies.
  - Aucun appel réseau réel dans la suite pytest (100 % mocké ou basé sur le cache local).
- **Solution de repli opérationnelle** :
  - Import de fichiers JSONL manuels (`app/catalog.py`) préservé et 100 % compatible.

---

## 5. Limites restantes avant utilisation pour une décision d'achat

1. **Dépendance aux cotes de marché manuelles (`market_references`)** :
   Le catalogue TCGdex fournit l'identité officielle exacte des cartes (nom, numéro, set), mais ne fournit pas les prix de vente observés sur les places de marché. Pour qu'une opportunité d'arbitrage soit validée, une référence de prix de revente doit être enregistrée (via l'onglet Cotes ou import JSONL de cotes).
2. **Absence d'authentification physique de la carte** :
   L'algorithme analyse les déclarations de l'annonceur. Il ne peut pas garantir que la carte reçue n'est pas une contrefaçon ou abîmée (micro-rayures, blanchiment au verso non visible en photo basse résolution).
3. **Frais de port acheteur réels variables** :
   Sur les marketplaces de particuliers, les frais de port dépendent du transporteur choisi par l'acheteur et de son pays. Le profil de frais doit être ajusté avec prudence.
4. **Légalité de la collecte en direct non établie** :
   Tant qu'un accord formel ou une API publique payante n'est pas souscrite auprès de Vinted et Leboncoin, le scraping automatisé en production reste exposé au bannissement d'adresse IP.

---

## 6. Prochaine étape recommandée

- **Mise en place d'un module d'export/import semi-automatique par bookmarklet ou extension locale** :
  Développer un script d'export manuel pour le navigateur de l'utilisateur (bookmarklet ou mini-extension locale) permettant d'exporter en 1 clic au format JSONL les annonces consultées légitimement par l'utilisateur connecté, afin d'alimenter Pokébourse via la solution de repli autorisée sans risque de blocage robot.
