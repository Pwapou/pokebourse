# ⚡ Pokébourse

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![SQLite](https://img.shields.io/badge/SQLite-WAL%20Mode-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![Docker Compose](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![Chrome Extension](https://img.shields.io/badge/Chrome%20Extension-Manifest%20V3-4285F4?logo=googlechrome&logoColor=white)](extension/README.md)
[![License](https://img.shields.io/badge/Licence-Propriétaire%20%2F%20Locale-gray)](#)

> **Plateforme locale d’aide à la décision pour la détection d'opportunités, l’identification et l’arbitrage d’achat-revente de cartes Pokémon.**

Pokébourse analyse le marché d'occasion (Vinted, Leboncoin, imports manuels, extension de navigation), identifie formellement les cartes grâce au catalogue officiel **TCGdex**, et calcule la rentabilité nette exacte de chaque annonce en tenant compte de tous les frais réels (commissions, frais de port, emballage, cotes de marché).

---

## 🎯 Pourquoi Pokébourse ?

Le marché d'occasion des cartes Pokémon présente plusieurs défis majeurs :
1. **Les fausses opportunités** : Une carte achetée 15 € et cotée 20 € génère souvent une perte une fois déduits le port aller, la commission de la plateforme, l'enveloppe bulle et le toploader.
2. **Le piège des lots et des descriptions floues** : De nombreux outils automatisés associent aveuglément un lot de 50 cartes à la carte la plus chère du lot, créant des alertes erronées.
3. **Les protections anti-bot strictes** : Les plateformes grand public (Vinted, Leboncoin) bloquent l'aspiration automatisée par script headless.
4. **Le manque de suivi d'investissement** : Impossible d'évaluer ses gains réels sans un carnet d'achats et de reventes rigoureux.

**Pokébourse résout ces problèmes en local, de façon 100 % privée et transparente, sans dépendance cloud payante ni compte marketplace requis.**

---

## ⚡ Démarrage Rapide en 60 secondes

### Prérequis
- [Docker](https://docs.docker.com/get-docker/) avec le plugin **Docker Compose**.
- Aucun environnement Python n'est nécessaire sur votre machine hôte : tout s'exécute dans les conteneurs isolés.

### Lancer Pokébourse

```bash
# 1. Cloner le dépôt et entrer dans le dossier
git clone <url-du-depot> pokebourse
cd pokebourse

# 2. Démarrer l'application web et le worker de surveillance
docker compose up --build -d
```

### Accès aux services
- **Interface Web principale** : [http://localhost:8000](http://localhost:8000)
- **Contrôle de santé API** : [http://localhost:8000/health](http://localhost:8000/health)
- **Logs du worker de veille** : `docker compose logs -f worker`

Pour arrêter l'application tout en conservant l'intégralité de vos données :
```bash
docker compose down
```
> [!IMPORTANT]
> Ne lancez jamais `docker compose down -v` ou `down --volumes` : vos annonces, cotes et historiques sont conservés dans le volume Docker persistant `pokemon-data`.

---

## 🧭 Visite Guidée & Fonctionnement

---

### 1. Le Tableau de Bord (Dashboard)

Le tableau de bord centralise en un coup d'œil la météo du marché et la santé de votre système local :
- **Indicateurs clés (KPIs)** : volume d'annonces surveillées, nombre d'opportunités rentables détectées, cotes de référence chargées et montant total investi.
- **Opportunités prioritaires** : cartes immédiatement actionnables classées par gain net et retour sur investissement (ROI).
- **Importation rapide JSONL** : glisser-déposer un fichier d'annonces pour analyse instantanée.
- **Journal des imports & Échecs récents** : transparence totale sur les fichiers importés et rapport téléchargeable des erreurs.

![Tableau de Bord Pokébourse](docs/images/01-dashboard.svg)

---

### 2. L'Extension Chrome — Pokébourse Capture

Pour surmonter les protections anti-bot (Cloudflare, DataDome) sans risque de bannissement, Pokébourse inclut une extension Chrome officielle (**Manifest V3**) dans le dossier [`extension/`](extension/README.md) :

- **Capture automatique pendant votre navigation réelle** : dès que vous visitez une annonce Pokémon sur Vinted, Leboncoin ou une boutique TCG, l'extension extrait proprement les données (titre, prix, vendeur, image, état).
- **Notification Toast discrète** : confirmation visuelle en haut à droite sans perturber votre consultation.
- **Envoi direct en 1 clic** : transmettez votre panier de cartes directement à Pokébourse locale (`POST http://localhost:8000/imports`).
- **Export & Sauvegarde** : exportez également vos captures en fichier standard `.jsonl` horodaté ou dans le presse-papier.

![Extension Chrome Pokébourse Capture](docs/images/02-chrome-extension.svg)

> [!TIP]
> **Installation de l'extension en 3 clics** :
> 1. Ouvrez `chrome://extensions/` dans Google Chrome et cochez le **Mode développeur**.
> 2. Cliquez sur **Charger l'extension non empaquetée**.
> 3. Sélectionnez le sous-dossier `extension/` du projet. C'est tout !

---

### 3. Le Catalogue & L'Identification TCGdex

Toutes les annonces (veilles, imports JSONL ou extension Chrome) convergent dans le catalogue unifié (`/catalog`) :
- **Recherche plein texte** et filtres par extension officielle.
- **Tri multi-critères** : date de découverte, prix croissant/décroissant, rentabilité estimée et fiabilité vendeur.
- **Tri et pagination rapide** : 25 annonces par page avec export CSV compatible Excel (encodage UTF-8 avec BOM, séparateur point-virgule et protection anti-injection).

![Catalogue et Identification](docs/images/03-catalog.svg)

#### Les 4 Statuts d'Identification TCGdex :
Le moteur d'identification (`app/identification/`) compare chaque annonce au référentiel officiel Pokémon :
1. 🟢 **Identifiée (`identified`)** : Le nom et le numéro concordent avec une carte officielle TCGdex (ex: *Dracaufeu #4/102*). Les métadonnées sont normalisées et le moteur de rentabilité s'active immédiatement.
2. 🟡 **À vérifier (`ambiguous`)** : Plusieurs cartes concordent sans critère discriminant fort (ex: réédition sans précision du numéro de série). Le système s'abstient pour éviter toute fausse conclusion.
3. 🔵 **Lot / Coffret (`lot`)** : Détection explicite de termes de vrac, boosters scellés, coffrets ou displays. **Règle absolue : aucun lot n'est jamais rattaché arbitrairement à une seule carte**.
4. ⚪ **Non identifiée (`unidentified`)** : Annonce au libellé trop vague. Elle reste consultable et réexaminable à la demande via le bouton **Réexaminer l’identification**.

---

### 4. La Fiche Détaillée & Simulation d'Arbitrage

En cliquant sur une carte du catalogue (`/catalog/{id}`), vous accédez à l'analyse détaillée :

![Fiche Détaillée](docs/images/04-catalog-detail.svg)

- **Liaison Catalogue TCGdex** : carte officielle rattachée, illustrateur, rareté, points de vie et score de confiance.
- **Décomposition financière transparente** :
  $$\text{Gain Net} = \text{Prix de revente estimé} - \text{Commission plateforme} - \text{Frais fixes} - \text{Port/Emballage} - (\text{Prix d'achat} + \text{Port aller})$$
  $$\text{ROI} = \frac{\text{Gain Net}}{\text{Prix d'achat} + \text{Port aller}}$$
- **Profil Vendeur** : évaluation de la réputation du vendeur, bouton d'ajout aux favoris et consultation des avis.
- **Bouton d'enregistrement d'achat** : un clic permet de convertir l'annonce observée en achat officiel dans votre carnet de suivi.

---

### 5. Le Moteur de Rentabilité & Cotes de Référence

Accessible via la page **Rentabilité** (`/profitability`), le moteur permet de piloter précisément vos hypothèses d'investissement :

![Moteur de Rentabilité](docs/images/05-profitability.svg)

1. **Modèle de prix hybride** :
   - **Cote de marché dédiée prioritaire** : issue de `market_references` (ventes conclues Cardmarket, eBay réelles ou estimations manuelles avec source et date d'observation).
   - **Repli sur la médiane du catalogue** : calculée sur les autres annonces identiques (même nom, numéro, langue, état, variante et devise).
2. **Profil de frais personnalisable** :
   - Commission de revente en points de base (ex: 500 bps = 5,00 %).
   - Frais fixes vendeur (€) et coût d'emballage/expédition (€).
   - Frais de port acheteur par défaut.
   - Seuils de qualification : gain net minimum (ex: 10,00 €) et ROI minimum (ex: 15,00 %).
3. **Zéro approximation financière** : Tous les montants sont calculés en centimes entiers et les pourcentages en points de base (`bps`), éliminant les erreurs d'arrondis des nombres à virgule flottante.

---

### 6. Annuaire des Vendeurs & Suivi des Achats

Pokébourse enrichit les annonces avec les profils publics des vendeurs (`/sellers`) et gère votre portefeuille d'arbitrage :

![Annuaire Vendeurs et Carnet d'Achats](docs/images/06-sellers-purchases.svg)

- **Indicateur de Fiabilité (★ à ★★★★★)** :
  - Calculé sur les avis réels de la plateforme (Vinted / Leboncoin).
  - Plafonné à 3 étoiles si le vendeur compte moins de 5 avis.
  - Plafonné à 2 étoiles si le taux d'avis négatifs dépasse 10 %.
  - 0 étoile pour un compte banni.
- **Protection de la vie privée (RGPD)** : les informations personnelles sensibles (emails, noms réels, coordonnées) sont filtrées par liste blanche stricte et jamais stockées.
- **Carnet des achats & Reventes (`purchases`)** :
  - Statuts du cycle de vie : `📦 Commandé` $\rightarrow$ `📬 Reçu` $\rightarrow$ `🏷️ En vente` $\rightarrow$ `💰 Vendu`.
  - Calcul automatique de la rentabilité réelle constatée après revente.

---

### 7. Veilles Automatiques & Supervision des Collecteurs

Le worker d'arrière-plan (`python -m app.worker`) exécute les veilles périodiques programmées (`/watches`) :

![Veilles et Supervision](docs/images/07-watches-supervision.svg)

- **Surveillance ciblée** : paramètres de recherche personnalisés (mots-clés, prix min/max, intervalle en secondes).
- **Contrôle manuel à la demande** : bouton **Contrôler ⚡** pour déclencher une vérification immédiate.
- **Supervision en direct (`/agents`)** :
  - Suivi des états : *Opérationnel*, *Dégradé*, *Bloqué*, *Hors-ligne*, *Arrêté*.
  - Sonde d'IP publique de sortie et signal de vie périodique (*heartbeat*).
  - **Résilience anti-bot** : en cas d'erreur 403 / 429 ou CAPTCHA, le collecteur concerné se suspend temporairement sans jamais bloquer les autres plateformes ni le serveur web.

---

### 8. Sauvegardes & Restauration SQLite

La sécurité de vos données est assurée sur la page **Sauvegardes** (`/backups`) :
- **Copies à chaud non bloquantes** : utilisation de l'API de sauvegarde en ligne de SQLite (`sqlite3_backup`), garantissant une copie cohérente même en pleine écriture.
- **Contrôle d'intégrité strict** : chaque fichier créé ou restauré fait l'objet d'un `PRAGMA integrity_check`.
- **Restauration sécurisée** : création automatique d'un snapshot de sécurité de la base actuelle avant toute restauration, suivie de l'application automatique des éventuelles migrations manquantes.

---

## 📥 Format d'Import de Fichiers JSONL

Vous pouvez importer des annonces ou des cotes en masse via l'interface web ou la ligne de commande.

### Format d'annonces (`annonces.jsonl`)

Un objet JSON par ligne, encodé en UTF-8 (taille max : 2 Mo) :

```jsonl
{"external_id":"vinted-89102","name":"Dracaufeu","set_name":"Set de Base","card_number":"4/102","language":"fr","condition":"NM","price_cents":14500,"currency":"EUR","seller":"PokeMaster92","url":"https://www.vinted.fr/items/89102"}
{"external_id":"lbc-77123","name":"Pikachu VMAX","set_name":"Voltage Éclatant","card_number":"188/185","price_cents":6500,"currency":"EUR","seller":"Julien_K","url":"https://www.leboncoin.fr/collection/77123"}
```

| Champ | Requis | Description |
|---|---|---|
| `external_id` | **Oui** | Identifiant unique de l'annonce pour la plateforme source |
| `name` | **Oui** | Nom de la carte Pokémon |
| `set_name` | **Oui** | Nom de la série / extension officielle |
| `price_cents` | **Oui** | Prix demandé en centimes d'euros (`14500` = `145,00 €`) |
| `card_number` | Non | Numéro de la carte dans l'extension (ex: `4/102`, `188/185`) |
| `language` | Non | Code langue (`fr`, `en`, `ja`), `fr` par défaut |
| `condition` | Non | État de la carte (`NM`, `EX`, `Good`, `Played`) |
| `variant` | Non | Variante (*Holo*, *Reverse*, *Secret Rare*...) |
| `grading_company` | Non | Organisme de certification (*PSA*, *PCA*, *BGS*, *CGC*) |
| `grade` | Non | Note attribuée (ex: `9`, `10`) |
| `seller` | Non | Pseudonyme public du vendeur |
| `url` | Non | Lien web vers l'annonce d'origine |

### Format des cotes de référence (`cotes.jsonl`)

```jsonl
{"name":"Dracaufeu","set_name":"Set de Base","card_number":"4/102","condition":"NM","reference_price_cents":29000,"currency":"EUR","source_name":"Cardmarket","reference_kind":"ventes_conclues","observed_at":"2026-10-31","sample_size":14}
```

---

## 🛠️ Utilisation en Ligne de Commande (CLI)

Toutes les opérations d'administration peuvent être pilotées depuis le conteneur `app` via la commande `pokemon-arbitrage` :

```bash
# Vérifier l'état et l'intégrité de la base de données
docker compose run --rm app pokemon-arbitrage check

# Appliquer manuellement les migrations SQLite
docker compose run --rm app pokemon-arbitrage migrate

# Importer un fichier d'annonces JSONL
docker compose run --rm app pokemon-arbitrage import-catalog mon_fichier.jsonl --source mon_import

# Importer un fichier de cotes de référence
docker compose run --rm app pokemon-arbitrage import-references cotes.jsonl

# Configurer les frais de revente et seuils
docker compose run --rm app pokemon-arbitrage configure-fees \
  --platform-fee-bps 500 \
  --shipping-packaging-cents 200 \
  --buyer-shipping-cents 450 \
  --min-net-profit-cents 1000 \
  --min-roi-bps 1500

# Analyser les opportunités de rentabilité
docker compose run --rm app pokemon-arbitrage analyze --only-opportunities

# Gérer les sauvegardes
docker compose run --rm app pokemon-arbitrage backup
docker compose run --rm app pokemon-arbitrage restore /data/backups/pokebourse-20261101.sqlite --yes

# Gérer les veilles
docker compose run --rm app pokemon-arbitrage list-watches
docker compose run --rm app pokemon-arbitrage run-watch 1
```

---

## 🧪 Tests & Assurance Qualité

La suite de tests automatisés est rigoureusement hermétique : **aucun appel réseau vers Vinted, Leboncoin ou TCGdex n'est réalisé pendant les tests**.

```bash
# Exécuter l'intégralité des tests unitaires et d'intégration
docker compose run --rm app pytest

# Lancer les tests avec détails et verbosité
docker compose run --rm app pytest -v

# Tester spécifiquement l'extension Chrome et l'import JSONL
docker compose run --rm app pytest tests/test_chrome_extension.py -v

# Tester le moteur d'identification et la réconciliation
docker compose run --rm app pytest tests/test_identification.py tests/test_tcgdex_cache.py -v
```

---

## ⚖️ Éthique, Législation & Respect des Plateformes

Le projet Pokébourse adhère aux principes suivants, détaillés dans le fichier [`SOURCES.md`](SOURCES.md) :
1. **Zéro contournement anti-bot** : Pokébourse n'utilise aucun solveur de CAPTCHA, aucun proxy tournant et aucune tentative de contournement des protections Cloudflare ou DataDome. En cas de blocage, le système se suspend gracieusement.
2. **Aucun achat automatisé** : Pokébourse est un outil d'aide à la décision humaine. L'acte d'achat demeure sous le contrôle direct de l'utilisateur.
3. **Respect du RGPD** : Seules les métadonnées publiques nécessaires à la qualification de l'offre sont exploitées. Les données personnelles sensibles des vendeurs sont systématiquement ignorées.
4. **Alternative de navigation légitime** : L'extension Chrome officielle permet à l'utilisateur de capturer les annonces pendant ses propres sessions de navigation manuelles, dans le strict respect de la politique des sites consultés.

---

## 🤖 Guide pour les Agents d'IA & Développeurs

Vous utilisez un assistant IA de programmation (Claude, Cursor, Antigravity, Devin, Copilot) ou vous souhaitez contribuer au code ?  
Consultez le fichier d'instructions techniques dédié :  
👉 **[AGENTS.md](AGENTS.md)** : architecture interne, conventions de code, gestion des migrations SQLite et règles d'or de développement.
