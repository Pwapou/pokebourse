# Conditions d'accès aux sources et référentiels — Pokébourse

Date de vérification globale : **2026-11-01**

Ce document consigne l'audit juridique, technique et contractuel des sources utilisées par Pokébourse pour la collecte d'annonces de marché et l'accès au catalogue de référence Pokémon.

---

## 1. Vinted

### Méthode d'accès utilisée par le projet
- Connecteur Python dans `app/collectors/vinted.py` utilisant la bibliothèque tierce open-source `vinted_scraper`.
- Interrogation directe via requêtes HTTP des endpoints d'API internes web non documentés (`https://www.vinted.fr/api/v2/catalog/items`) avec émulation d'en-têtes de navigateur.
- Aucun compte utilisateur n'est utilisé, aucun achat automatique n'est implémenté.

### Conditions contractuelles applicables
- **Conditions Générales d'Utilisation (CGU) Vinted** :
  - Lien officiel : [Conditions Générales d'Utilisation Vinted](https://www.vinted.fr/terms_and_conditions)
  - Section relative aux *Obligations et interdictions* : Vinted interdit formellement l'utilisation de tout logiciel automatisé, robot (*bot*), programme de collecte (*scraper*), programme d'exploration (*crawler*) ou outil d'indexation (*spider*) pour accéder au site, extraire ou réutiliser des données.
- **Règles relatives aux données personnelles (RGPD)** :
  - Les annonces comportent des identifiants et pseudonymes d'utilisateurs particuliers. L'aspiration automatisée et massive de ces profils est prohibée sans consentement préalable.

### Limites, quotas et coûts connus
- **Coût** : Gratuit, mais sans autorisation d'accès.
- **Quotas** : Aucun quota public ou contractuel. En pratique, des seuils de protection dynamique (Cloudflare / WAF) déclenchent des réponses `429 Too Many Requests` ou des blocages `403 Forbidden` dès qu'un volume modéré de requêtes automatisées est détecté depuis une adresse IP.
- **Sécurité et anti-bot** : Présence de protections anti-bot (Cloudflare, TLS fingerprinting, CAPTCHA).

### Données réellement accessibles
- Identifiant d'article (`external_id`).
- Titre de l'annonce (`title`).
- Prix brut affiché (`price_cents`).
- URL de l'article sur `vinted.fr`.
- URL de l'image principale (`images.vinted.net`).
- Pseudonyme du vendeur.
- Date de publication indicative.
- **Données non accessibles sur la recherche** : frais de port réels pour l'acheteur (dépendent du transporteur choisi et de la localisation), commissions détaillées, description intégrale systématique.

### Points qui restent non vérifiés
- Absence d'autorisation écrite : l'utilisation d'une bibliothèque open-source (`vinted_scraper`) ne constitue en aucun cas une autorisation d'accès accordée par Vinted.
- Pérennité technique : les endpoints privés internes de Vinted évoluent sans préavis, risquant de rendre le connecteur inopérant à tout moment.

### Conséquences et solution de repli autorisée
- **Conséquences** : L'accès par scraping automatisé n'est pas contractuellement autorisé par Vinted. Le projet refuse tout contournement de CAPTCHA, d'anti-bot ou de réponse 403/429. Aucun appel réel n'est effectué dans les tests automatisés.
- **Solution de repli** : **Import manuel autorisé** via fichier JSONL (route `/` ou script d'import), permettant à l'utilisateur d'intégrer des annonces qu'il a lui-même exportées ou saisies manuellement.

---

## 2. Leboncoin

### Méthode d'accès utilisée par le projet
- Connecteur Python dans `app/collectors/leboncoin.py` s'appuyant sur la bibliothèque tierce `lbc`.
- Requêtes HTTP directes vers les endpoints de recherche JSON utilisés par les applications mobiles / web de Leboncoin.

### Conditions contractuelles applicables
- **Conditions Générales d'Utilisation (CGU) Leboncoin** :
  - Lien officiel : [Conditions Générales d'Utilisation Leboncoin](https://www.leboncoin.fr/cgu)
  - Article Propriété Intellectuelle et utilisation du site : Il est expressément interdit d'utiliser des robots, des spiders, des applications de recherche/récupération de sites ou tout autre moyen automatisé pour récupérer, aspirer ou indexer tout ou partie des contenus du site.
  - Fichier `robots.txt` : Interdit l'accès automatisé aux sections de recherche sans accord express.
- **Protection juridique de la base de données** :
  - Leboncoin bénéficie du droit *sui generis* du producteur de bases de données (Code de la propriété intellectuelle, art. L. 341-1 et suivants). La jurisprudence de la Cour de cassation (notamment dans les affaires opposant Leboncoin à des agrégateurs ou extracteurs de données) sanctionne lourdement l'aspiration répétée et systématique d'annonces.

### Limites, quotas et coûts connus
- **Coût** : Gratuit mais formellement non autorisé.
- **Quotas** : Aucun quota officiel ouvert aux tiers.
- **Barrières techniques** : Protection anti-bot avancée **DataDome** (analyse comportementale, fingerprint TLS/navigateur, détection d'adresses IP de datacenters). Blocages immédiats sous code HTTP 403 avec challenge CAPTCHA.

### Données réellement accessibles
- Identifiant d'annonce (`external_id`).
- Titre / sujet de l'annonce (`subject`).
- Prix affiché (`price_cents`).
- URL de l'annonce (`leboncoin.fr`).
- URL de la première image.
- Pseudo ou prénom vendeur.
- Date de première publication / indexation.

### Points qui restent non vérifiés
- Absence d'autorisation d'accès par convention ou partenariat.
- Taux de blocage réel en cas de requêtes répétées : DataDome bloque quasi immédiatement toute session non munie d'un cookie valide issu d'une interaction humaine.

### Conséquences et solution de repli autorisée
- **Conséquences** : Les requêtes automatisées non autorisées sont passibles de blocage technique et de sanctions contractuelles. Le projet n'implémente aucun proxy, rotation d'IP ou contournement DataDome. Les erreurs DataDome sont isolées, journalisées et interrompent la collecte sans planter le worker.
- **Solution de repli** : **Import manuel autorisé** via fichier JSONL ou formulaire de saisie locale.

---

## 3. TCGdex (Catalogue de référence officiel)

### Méthode d'accès utilisée par le projet
- Client REST Python dédié dans `app/tcgdex/client.py` interrogeant l'API publique `https://api.tcgdex.net/v2/fr`.
- Cache local SQLite persistant (`pokemon_reference_cards`, `pokemon_reference_sets`) dans `app/tcgdex/cache.py` permettant un fonctionnement 100% hors-ligne sans dépendance réseau permanente.

### Conditions contractuelles applicables
- **Documentation officielle** : [tcgdex.dev](https://www.tcgdex.dev)
- **Licence et conditions** :
  - Projet open-source communautaire mis à disposition gracieusement.
  - Aucun compte, abonnement ni clé d'API obligatoire.
  - **Politique de Fair Use** : L'API demande aux utilisateurs d'adopter un comportement responsable pour préserver l'infrastructure bénévole, notamment en mettant en cache localement les données et en évitant les requêtes redondantes.

### Limites, quotas et coûts connus
- **Coût** : 100 % gratuit.
- **Quotas** : Pas de quota technique strict par token, mais respect nécessaire des temps de pause (backoff avec respect des codes 429 et du header `Retry-After`).
- **Délais** : Timeout strict de 10 secondes et 3 tentatives bornées avec temporisation exponentielle implémentés dans `TcgdexClient`.

### Données réellement accessibles
- Liste intégrale des séries et extensions officielles Pokémon en français (`id`, `name`, `releaseDate`, `cardCount`).
- Fiches cartes complètes : nom français, numéro local (`localId`), rareté, catégorie (Pokémon, Dresseur, Énergie), types, points de vie (PV), stade d'évolution, illustrateur, visuels officiels (`assets.tcgdex.net`).

### Points qui restent non vérifiés
- Délais d'intégration des toutes dernières extensions sorties dans la semaine courante.
- TCGdex ne fournit pas de cotes de vente en temps réel : il constitue un catalogue d'identité et de référence de cartes, et non un index de transactions conclues sur les marketplaces (les cotes de vente restent gérées par `market_references`).

---

## 4. Synthèse des autorisations et principes directeurs du projet

| Source | Rôle dans le projet | Accès officiel / autorisé | Méthode d'accès | Solution de repli recommandée |
|---|---|---|---|---|
| **Vinted** | Annonces de marché | **Non établi** (scraping interdit par CGU) | `vinted_scraper` (API privée) | Import manuel JSONL |
| **Leboncoin** | Annonces de marché | **Non établi** (scraping interdit par CGU) | `lbc` (endpoints non officiels) | Import manuel JSONL |
| **TCGdex** | Référentiel cartes et sets Pokémon | **Oui** (API publique ouverte, Fair Use) | Client REST `api.tcgdex.net` + cache local | Cache SQLite local autonome pré-embarqué |
| **Extension Chrome (Pokébourse Capture)** | Import assisté côté utilisateur | **Oui** (Navigation humaine légitime sur navigateur personnel) | Content script DOM / Schema.org / JSON-LD | Export JSONL & envoi API locale (`POST /imports`) |

---

## 5. Module Google Chrome d'import assisté (Extension Manifest V3)

### Méthode d'accès
- Extension Chrome installée localement (`extension/`) exécutée exclusivement dans le navigateur de l'utilisateur.
- Analyse passive du DOM et des métadonnées (Schema.org / JSON-LD, OpenGraph, microdonnées) lors de la visite réelle d'une page par l'utilisateur.
- Aucun scraping automatisé en tâche de fond, aucun serveur headless distant, aucune tentative de contournement de CAPTCHA ou de WAF (Cloudflare/DataDome).
- L'utilisateur est connecté avec son compte habituel sur son navigateur habituel.

### Données extraites
- Titre de l'article / carte.
- Prix brut affiché et devise.
- Nom / pseudonyme du vendeur.
- URL de l'annonce et URL de la vignette photo.
- Détection des mots-clés Pokémon et extraction automatique du numéro et de l'extension si présents.

### Transmission à Pokébourse
- Génération d'un fichier JSONL conforme au format d'import du catalogue.
- Envoi direct en un clic vers l'instance Pokébourse locale (`POST http://localhost:8000/imports`), où l'annonce est réconciliée avec le catalogue TCGdex et analysée par le moteur de rentabilité.

---

## 6. Règles impératives appliquées dans le code
1. **Aucun contournement technique** : aucun solveur de CAPTCHA, aucune rotation d'IP/proxy et aucun artifice de contournement anti-bot (Cloudflare, DataDome) ne sont intégrés.
2. **Gestion des codes HTTP 403 et 429** : les réponses 403 ne sont pas retentées (arrêt immédiat et journalisation). Les réponses 429 respectent les en-têtes `Retry-After`.
3. **Zéro appel réel dans les tests automatisés** : 100 % des tests unitaires et d'intégration utilisent des simulateurs (mocks) ou le cache local SQLite sans requêter Vinted, Leboncoin ou TCGdex.
4. **Pas de collecte réelle en production sans cadre d'autorisation établi**.
