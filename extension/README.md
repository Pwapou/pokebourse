# Extension Google Chrome — Pokébourse Capture

Module Chrome officiel (Manifest V3) permettant de capturer automatiquement ou semi-automatiquement les annonces Pokémon lors de votre navigation réelle (Vinted, Leboncoin, eBay, boutiques TCG, etc.) et de les injecter directement dans Pokébourse.

---

## 🎯 Pourquoi ce module ?

Certaines plateformes de vente (Vinted, Leboncoin) disposent de protections anti-bot strictes (Cloudflare, DataDome) et interdisent le scraping automatisé par script headless.
Cette extension agit comme un **assistant de navigation légitime** :
- Elle tourne dans votre navigateur Google Chrome pendant vos sessions normales.
- Elle analyse le DOM de la page consultée dès qu'un mot-clé Pokémon est détecté.
- Elle extrait proprement les métadonnées (titre, prix, vendeur, image, URL, numéro de carte, extension).
- Elle vous permet de tout exporter en format JSONL standard Pokébourse ou de l'envoyer en 1 clic à votre instance locale (`http://localhost:8000`).

---

## 🚀 Installation dans Google Chrome (Mode Développeur)

L'extension ne nécessite aucune compilation, tout est prêt dans le dossier `extension/` :

1. Ouvrez Google Chrome et accédez à :
   ```text
   chrome://extensions/
   ```
2. En haut à droite, activez le **Mode développeur** (Developer mode).
3. Cliquez sur le bouton **Charger l'extension non empaquetée** (Load unpacked).
4. Sélectionnez le dossier `extension/` situé à la racine du projet :
   ```text
   /Users/mathieu/Documents/pokebourse/extension
   ```
5. L'icône Pokébourse apparaît immédiatement dans votre barre d'outils Chrome ! (Cliquez sur l'épingle dans Chrome pour la garder visible).

---

## 💡 Fonctionnalités & Utilisation

### 1. Détection automatique intelligente
Dès que vous visitez une page web contenant des termes Pokémon (*pokémon*, *dracaufeu*, *charizard*, *pikachu*, *tcgdex*, etc.) :
- L'extension inspecte les données structurées de la page (Schema.org / JSON-LD, OpenGraph, ou sélecteurs spécialisés Vinted / Leboncoin).
- Si une annonce de carte est détectée, elle est automatiquement enregistrée dans le stockage local du navigateur (`chrome.storage.local`).
- Une notification discrète (toast) s'affiche en haut à droite de la page :
  `⚡ Pokébourse : [Nom de la carte] - [Prix]`
- Le badge sur l'icône de l'extension se met à jour pour afficher le nombre d'annonces en attente.

### 2. Gestion et Sélection depuis le Popup Chrome
En cliquant sur l'icône Pokébourse :
- **Sélection personnalisée** : cochez ou décochez les cartes que vous souhaitez transmettre à l'aide des cases à cocher unitaires ou de la case « Tout sélectionner ». Le bouton d'envoi affiche dynamiquement le nombre de cartes sélectionnées.
- **Liste des cartes capturées** : affichage du titre, prix d'achat en euros, vendeur, plateforme et vignette photo.
- **Suppression unitaire** : retirez les cartes indésirables d'un simple clic sur la croix.
- **Interrupteur Auto / Pause** : suspendez temporairement la capture automatique si vous naviguez sans vouloir collecter.
- **Tout vider** : nettoyez la liste en un clic.

### 3. Export et Synchronisation avec Pokébourse
Le popup met à disposition 3 modes de transfert :
1. **🚀 Envoyer à Pokébourse locale (avec estimation financière en direct)** :
   Transmet les cartes sélectionnées via l'API locale (`http://localhost:8000/imports`).
   - Le backend identifie instantanément la carte avec le référentiel officiel TCGdex.
   - Le moteur calcule en direct le **prix de revente estimé** (cote Cardmarket/eBay ou médiane), le **bénéfice net** et le **ROI**.
   - Le popup affiche immédiatement les résultats sous chaque carte :
     * Si la carte est cotée : Prix d'achat, Prix de revente estimé, Bénéfice net (+XX €), ROI (+XX%) et verdict (Opportunité / À surveiller).
     * Si la carte n'a pas encore de cote dans Pokébourse : statut « Sans cote » clair avec un lien direct `+ Renseigner une cote` vers `/profitability#cotes`.
     * Lien d'accès direct vers la fiche de l'annonce dans Pokébourse.
2. **⬇️ Télécharger .jsonl** :
   Génère un fichier horodaté pour la sélection, importable manuellement via le formulaire web ou en CLI.
3. **📋 Copier JSONL** :
   Place les cartes sélectionnées dans le presse-papier.

---

## 🏗️ Architecture technique

Conforme à 100% aux exigences modernes **Manifest V3** de Google Chrome :
- `manifest.json` : déclarations V3, permissions minimales (`storage`, `activeTab`), permissions d'hôtes pour l'accès aux sites de vente et à `http://localhost:8000/*`.
- `icons/` : vraies icônes PNG générées aux formats requis (16x16, 48x48, 128x128).
- `background/service-worker.js` : Service worker éphémère, gestion asynchrone des messages, déduplication sans état global en RAM (persistance `chrome.storage.local`).
- `content/content.js` & `content/content.css` : Content scripts isolés, extracteurs dédiés pour Vinted, Leboncoin et extracteur générique Schema.org / Microdata / OpenGraph.
- `popup/` : Interface utilisateur moderne et réactive en HTML5 / CSS3 / JavaScript sans framework externe lourd.

---

## 🧪 Tests automatisés

La compatibilité du manifest, des fichiers graphiques et du format d'échange JSONL avec le backend Pokébourse est validée par les tests d'intégration :
```bash
docker compose exec app pytest tests/test_chrome_extension.py -v
```
Tous les tests sont au vert.
