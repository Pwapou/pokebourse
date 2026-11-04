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

## 6. Recherche approfondie et confirmations — novembre 2026

- Référence initiale mesurée : 15 cartes, 6 extensions, 14 annonces ; suite initiale : 205 tests passants.
- Recherche locale normalisée (Unicode, accents, ponctuation), numéros canoniques sans rapprochement par suffixe, vocabulaire dérivé du catalogue et ex æquo conservés comme ambigus.
- Migrations `0012` et `0013` : preuves, décisions humaines, file dédupliquée avec bail, historique des révisions et versions de catalogue. Les clés étrangères et suppressions d’imports sont couvertes par les tests.
- Recherche TCGdex ciblée par le worker, sans réseau dans le matcher ou les transactions d’import ; reprise bornée et préservation des détails déjà connus.
- Fiche annonce : candidats, recherche approfondie, confirmation/retrait, correction motivée d’un faux lot, états d’attente et d’échec. Le popup distingue identité et disponibilité d’une cote.
- Réglage `TCGDEX_AUTO_ENRICH` désactivé par défaut ; `TCGDEX_SEARCHES_PER_TICK=1` par défaut. Référentiel français uniquement, sans substitution silencieuse des cartes étrangères.
- Recette finale : **248 tests passants**, sans appel réseau réel. Une dépréciation Starlette concernant `httpx` reste signalée, sans échec fonctionnel.

## 7. Supervision réseau des agents — novembre 2026

- La sonde `https://api.ipify.org` est désormais configurée par défaut : chaque enregistrement du worker détecte à nouveau l’IP publique et remplace celle du déploiement précédent.
- Le signal de vie propage cette IP à l’agent et aux collecteurs Vinted et Leboncoin ; les pages `/agents` et `/agents/{id}` affichent les valeurs persistées existantes. Une sonde indisponible laisse « IP inconnue » et ne bloque pas le démarrage.
- Tests de configuration, d’enregistrement, de redéploiement et d’interface simulés, sans appel réseau réel.

## 8. Cotes Cardmarket officielles & repli prudent — novembre 2026

- Migrations `0011_create_cardmarket_prices.sql`, `0015_cardmarket_name_aliases.sql` et `0017_create_cardmarket_sync_state.sql`.
- Téléchargement et synchronisation SQLite du price guide officiel public de Cardmarket (~80 000 références en EUR, gratuit, sans compte API).
- Modèle de repli à 3 niveaux dans `app/profitability.py` : (1) Cote dédiée manuelle ou ventes conclues `market_references`, (2) Médiane du catalogue d'annonces strictement identiques, (3) Prix tendance Cardmarket le plus conservateur avec pont multilingue FR · EN · JA · KO · ZH via les alias de noms officiels TCGdex.
- Synchronisation quotidienne intégrée au worker (`app/monitoring/scheduler.py`) planifiée à 01h45 UTC juste après la publication Cardmarket, ou déclenchable manuellement depuis `/profitability`.

---

## 9. Extension multi-plateformes : eBay & Wallapop — novembre 2026

- Migration `0016_add_ebay_wallapop_platforms.sql` autorisant `'ebay'` et `'wallapop'` comme plateformes natives dans `sources`, `listing_watches`, `supervision_collectors` et `seller_profiles`.
- Connecteurs HTTP `app/collectors/ebay.py` et `app/collectors/wallapop.py` avec normalisation des filtres de recherche (prix min/max en centimes).
- Ingestion unifiée, respect de `first_seen_at`, verrous dédiés par plateforme (`_platform_locks`) dans le scheduler pour éviter les exécutions concurrentes.
- Extension Chrome mise à jour : détection automatique du domaine eBay/Wallapop, extraction dédiée et styles de badges de source.

---

## 10. Phase 0 ML & Pilote d'annotation textuelle — novembre 2026

- Migration `0014_annotation_pilot.sql` : gestion des vagues de tirage stratifié, attribution déterministe et suivi d'avancement vers un budget de 300 annonces et 60 doubles lectures indépendantes.
- Snapshots immuables d'observations (`listing_identification_snapshots`) séparés des champs corrigés, avec masquage préventif des données de contact personnelles (`redact_contacts`).
- Interface `/annotations` et `/annotations/items/{id}` : première et seconde lectures aveugles garantissant l'indépendance des annotateurs grâce à la configuration serveur `POKEMON_REVIEW_OPERATOR`.
- Formulaire d'arbitrage final et diagnostic en lecture seule `/identification/diagnostics` (aussi disponible en CLI `pokemon-arbitrage diagnose-identification`).
- Export reproductible sans fuite de données personnelles : `GET /catalog/labels.jsonl` et commande CLI `pokemon-arbitrage export-labels`.

---

## 11. Bilan de la suite de tests automatisés (Novembre 2026)

- **313 tests automatisés passants sur 30 suites** (0 échec, exécution en ~9,8s dans Docker).
- Aucun appel réseau réel émis (100 % mocké ou basé sur les jeux locaux embarqués).
- Herméticité absolue, précision monétaire en centimes et points de base, et intégrité SQLite (18 migrations versionnées de 0001 à 0018) validées.

---

## 12. Preuves de prix & cartes comparables dans la fiche détaillée — novembre 2026

- **Extension de `find_price_comparables` (`app/profitability.py`)** : la recherche de preuves de prix consolide désormais trois sources distinctes pour la même carte :
  1. `references` : ventes conclues et cotes enregistrées dans `market_references` (ex: ventes réussies eBay, Cardmarket, etc.), avec date d'observation et lien source.
  2. `listings` : annonces du catalogue local (actives en priorité, triées par proximité de prix).
  3. `sales` : achats passés du portefeuille (`purchases`) au statut `vendu`.
- **Calcul de l'écart relatif (`delta_cents`)** : chaque preuve affiche son écart net par rapport à l'estimation de revente calculée, permettant d'apprécier immédiatement la cohérence du prix.
- **Rendu dans `catalog_detail.html`** : affichage modulaire structuré par catégorie de preuve avec étiquettes de provenance, dates et liens sortants.
- **Outil d'audit en lecture seule (`scripts/comparables_report.py`)** : script console autonome permettant de vérifier la base locale et d'éditer un rapport des annonces avec comparables disponibles.
- Couverture de test étendue dans `tests/test_profitability.py` portant le total de la suite à **313 tests au vert**.

---

## 13. Prochaines étapes recommandées

1. **Exécution du protocole pilote Phase 0** : Réaliser les 300 annotations (dont 60 doubles lectures aveugles) via l'interface `/annotations`, mesurer l'accord inter-annotateurs et exporter le jeu consolidé pour l'apprentissage.
2. **Phase 1 ML** : Établir la baseline lexicale mesurée puis entraîner le modèle de ranking (LightGBM) avec partitions étanches sans fuite de données.
3. **Support multilingue étendu** : Intégrer les référentiels TCGdex anglais et japonais avec gestion des équivalences d'extensions.

---

## 14. Référentiel TCGdex progressif et reprenable — novembre 2026

- Écran `/tcgdex`, accessible depuis le menu et le diagnostic : sélection des extensions utiles, inventaire local, distinction résumés / fiches détaillées / effectifs annoncés, progression et pause/reprise.
- Migration additive `0018_tcgdex_sync_jobs.sql` : file dédupliquée persistante, étapes par carte et réservation partagée ; réseau hors transaction SQLite et rejet des réponses d’un ancien worker après pause ou reprise.
- Exécution par le worker après les recherches ciblées, un appel par passage ; trois tentatives par étape, replanification des 429 et cache de réussite de 24 h. Aucun appel réseau dans les routes de demande ou d’affichage.
- Préservation des références, métadonnées détaillées, annonces originales et confirmations humaines. La synchronisation ne déclenche ni réidentification ni entraînement ML.
- Commande `sync-tcgdex` pour demander des extensions, consulter la file hors ligne ou exécuter au plus une requête. Procédure et limites dans `docs/TCGDEX_SYNC.md`.
- Validation Docker : **329 tests passants**, dont 16 nouveaux scénarios de synchronisation, avec réponses API simulées uniquement. Le parcours sélection, chargement partiel, pause, reprise et fin a aussi été vérifié dans Chromium sur ordinateur et mobile, sans erreur console.

### Radar — première correction des preuves de prix

Les achats historiques marqués « vendu » ne fournissent pas de prix de revente : ils sont exclus des preuves de prix. Les évaluations exposent une qualité de référence structurée et signalent le rapprochement approximatif et la portée agrégée du repli Cardmarket. Les montants et le calcul de rentabilité existants restent inchangés. Le reste du plan Radar reste à réaliser.

### Radar — observations et décisions

La migration 0019 ajoute les décisions locales, les observations économiques et leurs événements. Les états connus à la migration sont marqués comme historiques, sans événement rétroactif. Les collecteurs, imports et captures enregistrent leurs observations dans la transaction d'ingestion ; les révisions d'identité restent distinctes des événements de prix. Le radar visuel et les étapes suivantes restent à développer.

---

## 15. Recherche Avancée Multi-Critères & Externe (`/search`) — novembre 2026

- **Migration SQLite `0020_search_indexes.sql`** :
  - Création d'index composites sur `catalog_items` (`is_lot`, `identification_status`, `price_cents`, `reference_card_id`, `set_name`, `currency`) pour accélérer le filtrage complexe.
  - Création d'index sur `pokemon_reference_cards` (`tcgdex_id`, `local_id`, `name`, `set_id`, `rarity`) pour les recherches instantanées dans le référentiel officiel.
- **Moteur de recherche unifié (`app/search/service.py`)** :
  - Formulaire unique avec portées modulables : Tout, Cartes du référentiel, Annonces observées.
  - Filtres complets : texte libre, extension, rareté officielle, année ou intervalle d'années de sortie (`release_date`), prix min/max, état, langue, variante, société de gradation et note, source, statut d'identification et exclusion des lots.
  - Respect strict des règles d'intégrité : aucun filtre de rareté ou d'année n'est appliqué à une annonce non identifiée ; aucun lot n'est rattaché à une carte unitaire.
  - Détection exacte et suggestions approchées basées sur le lexique trigramme officiel.
  - Export CSV conforme (`/search/export.csv`) avec encodage UTF-8 BOM, séparateur point-virgule et protection anti-injection CSV.
- **Recherche externe contrôlée (`app/search/external.py`)** :
  - Déclenchement uniquement sur action explicite via le paramètre `external=1`.
  - Résilience locale totale : les résultats locaux s'affichent même en cas de coupure réseau ou d'indisponibilité externe.
  - TCGdex : enfilage des demandes de complétion dans `identification_searches` avec déduplication stricte des critères pour traitement ordonné par le worker.
  - eBay : requêtes bornées avec connecteur officiel, backoff exponentiel et quotas.
  - Vinted et Leboncoin : signalées avec statut explicite « Non disponible » et motif (respect des CGU et protections anti-bot documentées dans `SOURCES.md`).
  - Importation contrôlée en un clic (`POST /search/external/import`) avec déduplication `(source_id, external_id)`, préservation inviolable de `first_seen_at` et enregistrement de l'historique dans `listing_observations`.
- **Validation** : 31 tests automatisés dédiés dans `tests/test_search.py`.

---

## 16. Tendances de Marché & Radar d'Arbitrage (`/trends`) — novembre 2026

- **Module dédié (`app/trends/`) et interface Jinja2 (`app/templates/trends.html`)** :
  - Calcul des variations de prix officielles Cardmarket : évolution des moyennes `avg7` vs `avg30` (moyen terme) et `avg1` vs `avg7` (court terme), avec variations en centimes et points de base (`bps`) arrondies en `ROUND_HALF_UP`.
  - Exclusion stricte des produits dont le prix de référence est nul ou incomplet pour éliminer les variations aberrantes.
  - Activité des annonces récentes : calcul du nombre d'annonces observées par carte dans le catalogue local sur 7 ou 30 jours, présenté avec honnêteté comme un proxy d'activité d'offres sans jamais prétendre faussement être un volume de ventes conclues.
  - Radar des meilleures opportunités : sélection et tri des annonces générant le meilleur gain net estimé et ROI selon les cotes de marché officielles enregistrées, avec indicateur de fraîcheur des données.
  - Filtres dynamiques : fenêtre temporelle (7j, 30j), extension officielle, rareté et seuil minimal d'annonces observées.
- **Validation** : 17 tests automatisés dédiés dans `tests/test_trends.py`.

---

## 17. Assistance Visuelle & OCR Local (`/ocr/suggestions`) — novembre 2026

- **Module serveur (`app/identification/ocr.py`) & script client (`app/static/ocr.js`)** :
  - Moteur de reconnaissance optique 100 % local et conteneurisé basé sur Tesseract (`fra+eng`, page segmentation mode 11) intégré à l'image Docker (`Dockerfile`).
  - Respect strict de la vie privée et politique « zéro persistance » : l'image est décodée en mémoire vive via Pillow, nettoyée de ses métadonnées EXIF (`ImageOps.exif_transpose`), et convertie en flux PNG éphémère sans jamais être écrite sur disque ni stockée en base de données.
  - Bornes de sécurité : fichier limité à 8 Mo, résolution maximale de 12 millions de pixels, sémaphore de concurrence borné à 2 slots et timeout strict de 20 secondes.
  - Extraction ciblée des indices : recherche dans le texte extrait du nom de la carte, du numéro imprimé (fraction `X/Y` ou numéro isolé), de l'extension et des points de vie (PV).
  - Suggestions en 1 clic : interrogation du cache local TCGdex pour remonter les cartes candidates les plus pertinentes et préremplir le formulaire de réconciliation (`catalog_detail.html`).
- **Validation** : tests unitaires et web dans `tests/test_ocr_local.py` et `tests/test_ocr_web.py`.

---

## 18. Parcours d'Import Enrichi : Saisie par URL & Prévisualisation Chrome — novembre 2026

- **Saisie assistée par URL (`app/manual_listing.py`, `app/templates/manual_listing.html`)** :
  - Reconnaissance syntaxique locale d'URL pour eBay, Vinted, Leboncoin et Wallapop sans téléchargement de la page distante.
  - Détection instantanée des doublons existants par `(source, external_id)` (`app/listing_identity.py`).
  - Pré-analyse indicative en lecture seule (`/ajouter-annonce/analyser` via `app/listing_preview.py`) : propose une identification et une estimation de rentabilité sans modifier la base de données.
  - Enregistrement transactionnel via `app.catalog.import_jsonl` avec déduplication et préservation de `first_seen_at`.
- **Prévisualisation avant confirmation depuis l'extension Chrome (`app/capture_preview.py`, `app/templates/capture_preview.html`)** :
  - Nouveau mode recommandé dans le popup de l'extension Chrome Manifest V3 : sélection d'une annonce unique et ouverture dans un nouvel onglet Pokébourse (`POST /previsualiser-capture`).
  - Affichage transparent de l'origine de chaque champ : extrait de la page, proposé par le système, saisi/corrigé par l'utilisateur, ou manquant (jamais inventé).
  - Identification indicative (statut, candidats, score) et rentabilité indicative basées sur les références locales sans écriture en base.
  - Bouton « Confirmer et ajouter l'annonce » déclenchant l'ingestion transactionnelle finale.
- **Extraction bornée de métadonnées HTML (`app/collectors/page_extract.py`)** : extracteur passif de métadonnées de page.
- **Validation** : tests dans `tests/test_manual_listing.py`, `tests/test_capture_preview.py`, `tests/test_listing_preview.py` et `tests/test_page_extract.py`.

---

## 19. Simplification de l'Interface & Architecture de Navigation Cible — novembre 2026

- **Mise en œuvre du document de cadrage `TASKING_SIMPLIFICATION_CIBLE.md`** :
  - Parcours utilisateur clarifié : « Capturer → Décider → Suivre l'achat ».
  - Navigation principale restructurée dans `app/templates/base.html` :
    1. **Accueil** (`/`) : météo du marché, KPIs, opportunités prioritaires et état du système.
    2. **Opportunités** (`/catalog`) : fusion du catalogue et de l'analyse de rentabilité avec filtres de verdicts (`opportunite`, `surveiller`, `non_rentable`, `sans_cote`), tris financiers et export CSV.
    3. **Recherche** (`/search`) : moteur multi-critères et externe.
    4. **Tendances** (`/trends`) : mouvements de prix et activité des annonces.
    5. **Mes achats** (`/achats`) : carnet de suivi d'investissements.
    6. **Réglages** (`/reglages`) : frais, seuils, cotes de marché et synchronisation Cardmarket (remplaçant `/profitability` qui redirige de façon transparente).
    7. **Gestion avancée** (`/gestion`) : hub réunissant les modules spécialisés (Vendeurs, Veilles, Imports, TCGdex, Annotations ML, Agents, Sauvegardes).
  - Bouton global « Ajouter des annonces » en topbar (URL, Extension Chrome, JSONL, Veille).
  - Maquettes cibles de référence créées dans `app/static/prototype-cible.html`, `prototype-cible.css` et `prototype-cible.js`.
- **Validation** : tests de navigation et de compatibilité dans `tests/test_simplification_navigation.py` et `tests/test_simplification_avancee.py`.

---

## 20. Suivi des Achats & Prix de Vente Réel (`/achats`) — novembre 2026

- **Migration SQLite `0021_purchase_sale_price.sql`** :
  - Ajout de la colonne `sale_price_cents INTEGER DEFAULT NULL` dans la table `purchases`.
- **Interface dédiée (`app/templates/achats.html`) et service métier (`app/purchases.py`)** :
  - Suivi des 4 statuts du cycle de vie : `📦 Commandé` $\rightarrow$ `📬 Reçu` $\rightarrow$ `🏷️ En vente` $\rightarrow$ `💰 Vendu`.
  - Saisie facultative du prix de vente réel constaté (`sale_price_cents`) lors du passage à `vendu`.
  - Synthèse financière rigoureuse des montants investis par devise (EUR, USD, GBP).
  - Règle financière stricte : les frais de revente réels n'étant pas collectés sur chaque canal de sortie, aucune rentabilité réalisée théorique n'est calculée pour éviter les fausses affirmations.
- **Validation** : tests dans `tests/test_sellers_directory_and_purchases.py`.

---

## 21. Renforcement de l'Extraction des Preuves d'Identification — novembre 2026

- **Implémentation des spécifications `PROMPT_PATCH_EXTRACTION.md`** :
  - **Prise en charge des numéros isolés** dans `app/identification/detector.py` et `extension/content/content.js` : extraction d'un numéro seul de 2 à 3 chiffres (`<= 300`) sous garde-fous stricts (pas un lot, pas une année `1900-2099`, pas de symbole monétaire ou pourcentage accolé, pas une note de gradation, présence préalable d'un nom ou d'une extension).
  - **Remontée de l'incertitude dans le matcher** (`app/identification/matcher.py`) : tout numéro sans dénominateur remonte `numéro isolé, sans dénominateur` dans `uncertain_fields` et plafonne la classification automatique à `ambiguous` (score maximal de 79, jamais de classement `identified` arbitraire).
  - **Prise en charge de certificateurs additionnels** : reconnaissance de `CollectAura` (variantes `Collect'Aura`, `Collect Aura`) et des formats avec grade accolé (`PSA10`, `PCA9.5`). La gradation reste neutre sur le score de confiance d'identification.
- **Validation** : tests dans `tests/test_identification.py`, `tests/test_candidate_number_warning.py` et `tests/test_chrome_extension.py`.

---

## 22. Bilan Global Actualisé de la Suite de Tests (Novembre 2026)

- **452 tests automatisés passants sur 43 suites** (0 échec, exécution rapide et entièrement hermétique).
- **Zéro appel réseau réel** : tous les tests utilisent des simulateurs (mocks) ou le référentiel SQLite local embarqué (`seed_data.py`).
- **Idempotence des 21 migrations SQLite** : rejeu intégral de `0001` à `0021` validé sans dérive de schéma (`test_migrations.py`).

---

## 23. T03 — Preuves, proposition et confirmation distinctes — 3 novembre 2026

- Contrat optionnel `identity_evidence` compatible JSONL : valeurs brutes et
  normalisées, sources, extraits et métadonnées d'image/région ; aucune
  provenance cliente ne devient une confirmation humaine.
- Proposition locale commune aux prévisualisations, imports, collecte et
  réidentification ; OCR/préremplissages indicatifs, contradictions bloquantes,
  références de diagnostic séparées des suggestions admissibles.
- Migration additive `0022_identification_observations.sql` : observations et
  versions dans les preuves/snapshots, sans réécriture des anciennes décisions.
  Empreintes historiques conservées à preuves égales ; nouvelle preuve explicite
  = confirmation à réexaminer, avec audit préservé.
- Rubrique « Indices et provenance » dans la prévisualisation et la fiche.
  La réanalyse et l'ajout d'une annonce ne confirment pas les indices OCR.
  Le pilote et les exports textuels excluent les attributs seulement indicatifs
  de leurs preuves textuelles, tout en conservant la provenance dans l'audit.
- **Validation Docker :** 386 tests ciblés ; 749 tests sur la suite complète,
  même avertissement de dépréciation FastAPI/Starlette/httpx. Recette Chromium
  locale bureau/mobile, sans requête distante, avec contrôle des erreurs JS et
  de l'absence d'écriture avant enregistrement. Les cotes historiques et le
  moteur financier restent compatibles, sans modification du moteur financier.
- **Limites :** T00/T01 et le benchmark ne sont pas déclarés terminés par cette
  livraison ; pas de gain global de précision annoncé, pas de conservation
  durable des images (T04), pas de validation de T13 global. Aucun redémarrage
  ni migration de l'instance réelle n'est lancé par ce lot.
- Contrat, politique de réexamen et fichiers : [guide T03](docs/identification/T03_EVIDENCE.md).

---

## 24. T00/T01 — Inventaire, benchmark figé et rejeu local — 3 novembre 2026

- **T00 terminé comme inventaire** (réserves consignées) : manifeste figé avec
  empreintes SHA-256 (jeu de 30 annonces, rapport historique, 15 photos,
  catalogue, labels), inventaire du référentiel sur sauvegarde cohérente
  (202 extensions, 22 201 cartes, locale `fr` unique), baseline tests.
  Détail : [STATUS_T00_T01.md](validation/ocr/evaluation/STATUS_T00_T01.md).
- **Baseline verte confirmée le soir même** : suite complète Docker à
  **751 réussites, 0 échec** (749 + 2 tests du rejeu local) ; les 21 échecs
  consignés au contrôle initial (commit `b7b1a20`) sont résolus par la livraison
  T03 (`778c28c`).
- **Rejeu strictement local hermétique livré** :
  `validation/ocr/marketplaces/replay_local.py` relit les artefacts figés sur
  une sauvegarde SQLite en lecture seule, DNS désactivé, refus explicite de
  tout artefact manquant (aucun téléchargement implicite). Exécuté sur la
  sauvegarde `pokebourse-20261102-230603-171195.sqlite`, il reproduit le
  rapport historique avec **zéro changement de statut ou d'identité** sur les
  variantes titre/OCR/combiné (30/30, 30/30 et 15/15 cas appariés).
- **Tests dédiés** : `tests/test_replay_local.py` (refus sans acquisition,
  fonctionnement hermétique figé). Aucune base réelle modifiée, aucun appel
  réseau, aucune photo écrite hors des artefacts de validation.
- **T01 non terminé** : annotations humaines indépendantes, double lecture,
  rapport de justesse, volumes 300/1 000 et audit aléatoire restent ouverts ;
  les compteurs `identified` ne sont toujours pas une mesure de justesse.

## 25. T15 — Capacités réelles des sources de prix — 3 novembre 2026

- Matrice versionnée : [docs/identification/T15_SOURCES_PRIX.md](docs/identification/T15_SOURCES_PRIX.md),
  consignée dans [SOURCES.md](SOURCES.md) (§10). Distingue capacité théorique et
  accès réellement configuré, sans secret ni souscription.
- **Divergence corrigée** : le connecteur eBay existant interroge la page de
  recherche HTML publique sans authentification — ce n'est pas l'API officielle
  (aucune clé configurée). La ligne eBay du tableau de synthèse de SOURCES.md
  est rectifiée ; aucune recherche serveur automatique nouvelle n'est ajoutée.
- **Ventes conclues automatiques indisponibles** : Marketplace Insights restreint
  et fermé aux nouveaux utilisateurs ; aucune simulation de ventes à partir des
  offres. Voies disponibles : `market_references` (1 660 références
  `ventes_conclues` locales, nature et dates à documenter) et
  `purchases.sale_price_cents` (0 enregistrement à ce jour).
- **Cardmarket** reste la seule source automatique : cotes agrégées non gradées
  (75 082 prix locaux), jamais des offres ni des transactions, sans prix par
  certificateur/note.
- **Trou de couverture explicite pour J3** : aucune source automatique ne couvre
  les gradées PSA/PCA. Les décisions produit ouvertes (D1–D6 : zone géographique,
  repli prix insuffisants, canal de revente, comparabilité, source éventuellement
  payante, accès eBay officiel) sont recensées ; aucun comportement dépendant
  n'est activé.
- **Validation documentaire** : audit lecture seule du code et de la base
  (compteurs uniquement) ; aucune requête d'essai vers une marketplace.

## 26. T04/T05 — Preuves visuelles reproductibles et alias/localisations du référentiel — 3 novembre 2026

- **T04** : conservation explicite et contrôlée des photos (magasin `evidence/` à
  côté de la base, écriture atomique, déduplication par empreinte, quota 512 Mo,
  PNG nettoyé de tout EXIF avec orientation d'origine conservée comme repère,
  `image-store-v1` / `transforms-v1` comme socle T06). Statuts explicites
  présent/manquant/corrompu/supprimé (purge logique) ; purges orphelines et par
  rétention ; vérification d'intégrité sans écriture. Sauvegardes `.sqlite` avec
  sidecar `.sqlite.evidence` restauré ensemble. Provenances `image`/`both`
  acceptées par les reviews (preuve obligatoire et octets présents) ; export
  `identity-pilot-v2` inchangé en règles textuelles, ajout de
  `eligible_for_visual_training` et `needs_reexamination`. L'OCR reste éphémère
  par défaut, sans persistance implicite. Interface : bloc « Preuves visuelles
  conservées » sur la fiche catalogue.
- **T05** : localisations du référentiel (unicité `(tcgdex_id, reference_language)`,
  identifiants internes et données préservés, `fr` référence par défaut) ;
  file de sync TCGdex à locales (`fr` conserve sa clé historique, aucune
  identification/rentabilité activée par une locale ajoutée). Alias contrôlés
  (cible locale vérifiée, provenance, version `aliases-v1`) : collisions
  dégradées en suggestions sans effacement, suggestions floues bornées (distance
  ≤ 2) sans écriture, « gempack 2 » volontairement non résolu. Recherche
  référent : alias exact actif → redirection vers la cible, jamais de
  correspondance floue unique promue en preuve exacte. Diagnostic enrichi
  (clé `catalog.localization` : locales couvertes, identités multi-locales,
  manques image/détails, alias actifs/suggestions).
- **Migrations** : `0023_visual_evidence.sql`, `0024_reference_localizations.sql`,
  `0025_reference_aliases.sql`, `0026_tcgdex_sync_locale.sql` — reconstruction
  additive ; reviews et fiches pré-existantes survivent à l'identique (test
  dédié sur base à l'état 0022). Seed TCGdex rendu compatible avec les bases
  antérieures à 0024.
- **Tests** : nouvelles suites `tests/test_visual_evidence.py` et
  `tests/test_reference_aliases_localizations.py` ; suite complète à jour.

---

## 27. Audit d'avant-commit et corrections P1–P5 — 4 novembre 2026

- **Audit en lecture seule** du lot T04/T05/T00-T01/T15 (périmètre : commit
  `778c28c` + modifications locales) : lecture du code, exécution complète de la
  suite Docker, reproductions sur bases temporaires isolées et serveur HTTP
  temporaire ; base réelle et volume `pokemon-data` non touchés.
- **P1 confirmé et corrigé** : la route `/catalog/{id}/preuves-visuelles`
  affichait « Preuve visuelle conservée » sans persister la ligne (aucun
  commit côté route, INSERT non engagé) et laissait un PNG orphelin. Le
  magasin valide désormais sa propre transaction et retire les octets si le
  commit échoue ; test de route HTTP ajouté (12/12 dans la suite dédiée).
- **P2 confirmé et corrigé** : re-conserver les octets d'une preuve supprimée
  échouait silencieusement (unicité d'empreinte) et annonçait une fausse
  conservation. La re-conservation réactive l'enregistrement existant
  (identité et décisions rattachées conservées) après contrôle du quota.
- **P3 traité** : vérification d'intégrité généralisée (`verify_evidence_store`)
  câblée dans `create_backup` (refus si le sidecar copié est dégradé, nettoyage
  complet) et dans `restore_backup` (refus avant toute écriture) ; nouvelles
  commandes CLI `verify-evidence` et `purge-evidence [--days N]`.
- **P4 traité** : le formulaire de review expose la base de lecture
  (texte/image/both) et l'identifiant de la preuve (affiché sur la fiche
  catalogue) ; la résolution d'alias ne court-circuite plus la recherche dès
  qu'un filtre numéro/extension explicite est présent.
- **P5 traité** : l'archive d'espace de preuves `.pre-restore-*` est supprimée
  après une restauration réussie (déjà contenue dans la sauvegarde de sécurité).
- **Validation** : 818 tests hermétiques, 0 échec (5 nouveaux) ; vérifications
  HTTP réelles sur base temporaire (conservation, affichage, réactivation).
- Artefacts lourds de validation exclus du dépôt (snapshot figé 8 Mo et photos
  de campagne 1,8 Mo, non requis par les tests) ; `.gitignore` mis à jour.
