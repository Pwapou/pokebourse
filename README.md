# ⚡ Pokébourse

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![SQLite](https://img.shields.io/badge/SQLite-WAL%20Mode-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![Docker Compose](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![Chrome Extension](https://img.shields.io/badge/Chrome%20Extension-Manifest%20V3-4285F4?logo=googlechrome&logoColor=white)](extension/README.md)
[![License](https://img.shields.io/badge/Licence-Propriétaire%20%2F%20Locale-gray)](#)

> **Plateforme locale d’aide à la décision pour la détection d'opportunités, l’identification et l’arbitrage d’achat-revente de cartes Pokémon.**

Pokébourse analyse le marché d'occasion (Vinted, Leboncoin, eBay, Wallapop, imports manuels, extension de navigation), identifie formellement les cartes grâce au catalogue officiel **TCGdex**, et calcule la rentabilité nette exacte de chaque annonce en tenant compte de tous les frais réels (commissions, frais de port, emballage, cotes de marché).

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

> **Mise à jour du référentiel** : le bouton **« Réexaminer l’identification »** de la page Catalogue relance le moteur sur toutes les annonces non identifiées avec le référentiel courant — à utiliser après une synchronisation complète du catalogue TCGdex pour rattacher les annonces importées alors que le référentiel était encore incomplet. Les confirmations humaines restent prioritaires.

#### Recherche approfondie et confirmation humaine

La fiche annonce permet de rechercher dans le cache local, de mettre en file une recherche TCGdex ciblée, de comparer les candidats, puis de confirmer ou retirer une carte. Les preuves, décisions et recherches sont persistées dans SQLite et incluses dans les sauvegardes. Une modification de prix ne retire pas une confirmation ; une modification des preuves d’identité la signale « à revoir ». Un faux classement en lot doit être corrigé avec un motif avant toute confirmation unitaire.

L’enrichissement automatique des annonces non résolues est **désactivé par défaut**. Pour l’activer, définir `TCGDEX_AUTO_ENRICH=true` sur les services `app` et `worker`. La recherche manuelle reste disponible sans ce réglage. `TCGDEX_SEARCHES_PER_TICK` borne le nombre de recherches par passage du worker (1 par défaut, maximum 10). Sans worker, une demande reste « En attente du worker ».

Seuls le nom, le numéro, l’extension ou l’identifiant de carte sont envoyés à TCGdex, jamais le titre brut, la description ou le vendeur. Le catalogue fourni est français : une langue étrangère explicite n’est pas remplacée silencieusement par une référence française. Une référence trouvée ne fournit pas de cote de revente.

---

### Validation humaine — premier lot de préparation ML

Depuis **Annotations → Diagnostic des annonces**, examinez les annonces non
identifiées ou ambiguës : candidats locaux, faute de nom possible, contradictions
et inventaire du catalogue. Le diagnostic est en lecture seule et téléchargeable
en JSON. Une faute comme « dracofeu 4/102 » peut proposer **Dracaufeu** ; cette
suggestion reste à confirmer par une personne. La recherche manuelle du formulaire
de validation accepte aussi les noms approchés, en les signalant explicitement.

Le même diagnostic est disponible en CLI :

```bash
docker compose run --rm app pokemon-arbitrage diagnose-identification --status all --limit 100 --json
```

Voir [la recherche lexicale et ses limites](docs/IDENTIFICATION_LEXICALE.md).

Le menu **Annotations** ouvre `/annotations`, le tableau de suivi du pilote.
Cliquez **Constituer la file** pour sélectionner jusqu’à **300 annonces**, puis
**Continuer les lectures**. La file propose des cas variés, conserve les
probabilités de sélection et prévoit **60 doubles lectures** lorsque les 300
annonces sont disponibles. **Compléter la file** ajoute les nouveaux cas après
de nouveaux imports. Filtres et pagination permettent de retrouver les lectures
disponibles, celles qui attendent un autre opérateur et les décisions à valider.

Les lectures du pilote ne changent pas immédiatement l’annonce. Une fois la ou
les lectures terminées, **Valider / arbitrer** enregistre la décision finale.
La seconde lecture exige un opérateur distinct, configuré côté serveur par
`POKEMON_REVIEW_OPERATOR` ; premier avis, suggestions et historique restent
masqués dans ce parcours. Le suivi distingue avancement, accord entre lecteurs
avant arbitrage et diagnostic des décisions finales. Ces résultats décrivent
le pilote et ne certifient pas la précision en production.

Depuis une fiche annonce, **Valider ou corriger l’identité** ouvre le formulaire
`/catalog/{id}/review?blind=false`. Recherchez une carte par nom ou identifiant
TCGdex dans tout le catalogue local, puis enregistrez une **décision** pour
actualiser l’annonce. Vous pouvez aussi marquer un lot, un objet hors périmètre,
une carte absente, des preuves insuffisantes ou retirer une validation.

Le lien **Lecture indépendante sans suggestion** masque suggestions et historique.
Une **annotation indépendante** conserve une lecture sans modifier l’identification ;
un **arbitrage** relie les annotations concernées à une décision. La langue, la
variante, l’édition et l’état se vérifient séparément et restent inconnus si les
champs sont laissés vides. Ce pilote porte uniquement sur le texte.

Les décisions et les observations sont historisées. Une nouvelle collecte
identique ou un changement de prix conserve la validation ; une modification des
preuves demande un réexamen. Le formulaire refuse les corrections concurrentes
obsolètes. Les anciens boutons de confirmation restent compatibles, mais leurs
confirmations ne deviennent pas automatiquement des labels d’apprentissage.

Téléchargez le jeu pilote depuis **Exporter les validations JSONL**, ou utilisez :

```bash
docker compose run --rm app pokemon-arbitrage export-labels --output /opt/pokemon-arbitrage/labels-pilote.jsonl
```

Le fichier doit être nouveau. Il inclut un manifeste, les catalogues TCGdex figés
et les lectures, avec leurs motifs d’exclusion du futur apprentissage. Aucun
modèle n’est entraîné ni activé. Voir [l’état de la phase 0](docs/ML_PHASE0.md)
pour le périmètre livré et les étapes restantes avant les 300 annotations pilotes.

### 4. La Fiche Détaillée & Simulation d'Arbitrage

En cliquant sur une carte du catalogue (`/catalog/{id}`), vous accédez à l'analyse détaillée :

![Fiche Détaillée](docs/images/04-catalog-detail.svg)

- **Liaison Catalogue TCGdex** : carte officielle rattachée, illustrateur, rareté, points de vie et score de confiance.
- **Décomposition financière transparente** :
  $$\text{Gain Net} = \text{Prix de revente estimé} - \text{Commission plateforme} - \text{Frais fixes} - \text{Port/Emballage} - (\text{Prix d'achat} + \text{Port aller})$$
  $$\text{ROI} = \frac{\text{Gain Net}}{\text{Prix d'achat} + \text{Port aller}}$$
- **Profil Vendeur** : évaluation de la réputation du vendeur, bouton d'ajout aux favoris et consultation des avis.
- **Valeur de marché Cardmarket (fichiers officiels)** : deuxième source de prix affichée à côté du prix de l'annonce (tendance + moyennes de vente 1/7/30 jours), avec repli automatique : si Cardmarket ne connaît pas la carte, seul le prix de l'annonce reste affiché. C'est aussi le **dernier repli du moteur de rentabilité** (prix tendance le plus bas des produits assortis, en l'absence de cote dédiée et de médiane du catalogue). **Synchronisation automatique quotidienne** par le worker vers 03:20 (heure de Paris), après la régénération du price guide (~02:45), plus bouton **« Tout synchroniser maintenant »** (cotes + noms) sur la page Rentabilité. Source : fichiers publics publiés chaque jour par Cardmarket (public, gratuit, sans compte — ~80 000 cartes Pokémon).
- **Preuves de prix & cartes comparables** : La section *Preuves de prix · Annonces & ventes réelles* regroupe les éléments tangibles étayant l'estimation de revente :
  1. *Ventes conclues & cotes enregistrées* : issues de `market_references` (ex: ventes eBay réussies, Cardmarket) avec lien direct vers la source et date d'observation.
  2. *En vente actuellement* : annonces similaires actives dans le catalogue local.
  3. *Déjà revendus par vos soins* : achats passés de votre portefeuille passés au statut `vendu`.
  Chaque ligne indique l'écart de prix net en centimes et euros ($\pm X,XX\text{ €}$ vs estimation) pour valider immédiatement la crédibilité du prix retenu.
- **Bouton d'enregistrement d'achat** : un clic permet de convertir l'annonce observée en achat officiel dans votre carnet de suivi.

---

### 5. Le Moteur de Rentabilité & Cotes de Référence

Accessible via la page **Rentabilité** (`/profitability`), le moteur permet de piloter précisément vos hypothèses d'investissement :

![Moteur de Rentabilité](docs/images/05-profitability.svg)

1. **Modèle de prix hybride** :
   - **Cote de marché dédiée prioritaire** : issue de `market_references` (ventes conclues Cardmarket, eBay réelles ou estimations manuelles avec source et date d'observation).
   - **Repli sur la médiane du catalogue** : calculée sur les autres annonces identiques (même nom, numéro, langue, état, variante et devise).
   - **Dernier repli : prix tendance Cardmarket** : si aucune référence ni médiane n'existe, le moteur utilise le plus bas des prix tendances des produits Cardmarket assortis (correspondance par nom de base, pont multilingue FR · EN · KO · JA · ZH via les alias TCGdex) — volontairement prudent, car les fichiers publics Cardmarket ne précisent pas l'extension. Limité aux annonces en EUR.
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
  - IP publique de sortie détectée via `https://api.ipify.org` à chaque démarrage du worker, enregistrée pour l’agent et ses collecteurs, puis affichée sur `/agents`. En cas d’échec de la sonde, l’interface affiche « IP inconnue » sans interrompre le worker. L’URL est personnalisable avec `POKEMON_SUPERVISION_IP_PROBE_URL`.
  - **Résilience anti-bot** : en cas d'erreur 403 / 429 ou CAPTCHA, le collecteur concerné se suspend temporairement sans jamais bloquer les autres plateformes ni le serveur web.

---

### 8. Sauvegardes & Restauration SQLite

La sécurité de vos données est assurée sur la page **Sauvegardes** (`/backups`) :
- **Copies à chaud non bloquantes** : utilisation de l'API de sauvegarde en ligne de SQLite (`sqlite3_backup`), garantissant une copie cohérente même en pleine écriture.
- **Contrôle d'intégrité strict** : chaque fichier créé ou restauré fait l'objet d'un `PRAGMA integrity_check`.
- **Restauration sécurisée** : création automatique d'un snapshot de sécurité de la base actuelle avant toute restauration, suivie de l'application automatique des éventuelles migrations manquantes.

---

### 9. Référencement des Vendeurs, Pépites & CRM d'Achats (`/sellers`)

Pokébourse inclut un annuaire intelligent pour identifier vos meilleurs partenaires d'achat et suivre votre historique réel :
- **Classement Multi-axes** :
  - ⭐ **Les plus fiables** : évaluation en étoiles (0 à 5 ★) calculée sur les avis vérifiés de la plateforme, le taux d'avis positifs et l'absence de ban.
  - 🏆 **Meilleures pépites** : vendeurs qui mettent en ligne le plus de cartes sous-évaluées détectées comme *Opportunité* par le moteur d'arbitrage.
  - 💳 **Fournisseurs clés** : vendeurs chez qui vous avez le plus acheté et dépensé.
  - ❤️ **Favoris & Notes** : marquez vos vendeurs de confiance et notez leurs habitudes de négociation ou la qualité de leur emballage.
- **Fiche Vendeur Détaillée (`/sellers/{id}`)** :
  - Indicateurs de fiabilité et réputation publique détaillée.
  - Carnet de notes personnelles sur le vendeur.
  - Historique des achats conclus avec date, prix payé, port et statut de livraison.
  - Inventaire en direct des cartes en vente du vendeur consolidées dans le catalogue local.
- **Enregistrement d'Achat Intégré** :
  - Formulaire **« Marquer cette annonce comme achetée »** sur chaque fiche annonce (`/catalog/{id}`) pour alimenter automatiquement vos statistiques et l'historique vendeur.

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

Le menu **Référentiel TCGdex** (`/tcgdex`) permet de sélectionner les extensions à enrichir, suivre les identités et fiches détaillées chargées, puis mettre en pause ou reprendre leur traitement par le worker. Les confirmations humaines sont conservées. Voir le [guide de synchronisation](docs/TCGDEX_SYNC.md) pour le cache de 24 heures, la cadence et les limites de couverture.

Toutes les opérations d'administration peuvent être pilotées depuis le conteneur `app` via la commande `pokemon-arbitrage` :

```bash
# Vérifier l'état et l'intégrité de la base de données
docker compose run --rm app pokemon-arbitrage check

# Appliquer manuellement les migrations SQLite
docker compose run --rm app pokemon-arbitrage migrate

# Mettre en file l’enrichissement d’une extension et consulter sa progression
docker compose run --rm app pokemon-arbitrage sync-tcgdex sv08.5
docker compose run --rm app pokemon-arbitrage sync-tcgdex --status

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

# Rapport de vérification des comparables et preuves de prix (lecture seule)
docker compose run --rm app python -m scripts.comparables_report
```

---

## 🧪 Tests & Assurance Qualité

La suite de 30 fichiers de tests automatisés comprend **313 tests rigoureusement hermétiques** (0 échec) : **aucun appel réseau vers Vinted, Leboncoin, eBay, Wallapop, Cardmarket ou TCGdex n'est réalisé pendant les tests**.

```bash
# Exécuter l'intégralité des 313 tests unitaires et d'intégration
docker compose run --rm app pytest

# Lancer les tests avec détails et verbosité
docker compose run --rm app pytest -v

# Tester spécifiquement l'extension Chrome et l'import JSONL
docker compose run --rm app pytest tests/test_chrome_extension.py -v

# Tester le moteur d'identification et la réconciliation
docker compose run --rm app pytest tests/test_identification.py tests/test_tcgdex_cache.py -v

# Tester Cardmarket (guide public, alias de noms, repli et sync quotidienne)
docker compose run --rm app pytest tests/test_cardmarket.py tests/test_cardmarket_guide.py tests/test_cardmarket_daily.py -v

# Tester le pilote d'annotation ML Phase 0 et la recherche lexicale
docker compose run --rm app pytest tests/test_annotation_pilot.py tests/test_lexical_identification.py -v

# Tester le moteur de rentabilité et les comparables de prix
docker compose run --rm app pytest tests/test_profitability.py -v
```

---

## ⚖️ Éthique, Législation & Respect des Plateformes

Le projet Pokébourse adhère aux principes suivants, détaillés dans le fichier [`SOURCES.md`](SOURCES.md) :
1. **Aucun achat automatisé** : Pokébourse est un outil d'aide à la décision humaine. L'acte d'achat demeure sous le contrôle direct de l'utilisateur.
2. **Respect du RGPD** : Seules les métadonnées publiques nécessaires à la qualification de l'offre sont exploitées. Les données personnelles sensibles des vendeurs sont systématiquement ignorées.
3. **Alternative de navigation légitime** : L'extension Chrome officielle permet à l'utilisateur de capturer les annonces pendant ses propres sessions de navigation manuelles, dans le strict respect de la politique des sites consultés.

Les preuves de prix de la fiche distinguent les références enregistrées des annonces collectées. Un achat marqué « vendu » ne constitue pas une preuve de prix de revente tant que ce montant n'a pas été enregistré. Le repli Cardmarket repose sur un rapprochement approximatif par nom et un prix agrégé dont la langue et l'état ne sont pas confirmés ; sa date de marché peut être inconnue.

---

## 🤖 Guide pour les Agents d'IA & Développeurs

Vous utilisez un assistant IA de programmation (Claude, Cursor, Antigravity, Devin, Copilot) ou vous souhaitez contribuer au code ?  
Consultez le fichier d'instructions techniques dédié :  
👉 **[AGENTS.md](AGENTS.md)** : architecture interne, conventions de code, gestion des migrations SQLite et règles d'or de développement.
