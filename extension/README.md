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
Le popup met à disposition 4 modes de transfert :
1. **🔍 Prévisualiser dans Pokébourse (recommandé, une annonce à la fois)** :
   Sélectionnez **exactement une** annonce (comportement explicite : avec zéro ou plusieurs annonces cochées, le popup vous le signale et rien n'est envoyé ni validé silencieusement). Le popup vérifie que Pokébourse locale répond (`http://localhost:8000/health`) puis ouvre un nouvel onglet de prévisualisation (`POST /previsualiser-capture`) avec **uniquement les données déjà capturées depuis la page ouverte**.
   - Chaque champ est présenté avec sa provenance : **extrait** de la page, **saisi/corrigé** par vous (ancienne et nouvelle valeur affichées côte à côte), ou **manquant** — jamais inventé.
   - L'identification proposée (détecteur + matcher + référentiel TCGdex local) affiche statut, candidats, score et motif ; ce n'est **pas** une confirmation humaine et ne le devient pas sans action explicite. Un lot ne reçoit jamais arbitrairement l'identité d'une carte unitaire.
   - La rentabilité indicative utilise uniquement les références locales (cotes enregistrées, médiane des comparables, Cardmarket relié de façon fiable) : achat, port (celui de l'annonce prime, y compris à zéro ; celui du profil en repli), coût d'acquisition, revente estimée avec source/nature/date, frais, gain net, marge et ROI. Ce n'est ni un prix temps réel garanti, ni une vente conclue, ni une preuve d'état ou d'authenticité.
   - Après correction éventuelle (la langue doit être choisie explicitement, jamais déduite), **« Confirmer et ajouter l'annonce »** enregistre via le flux transactionnel existant : déduplication, pseudonyme vendeur limité aux champs publics autorisés, `first_seen_at` préservé en cas de doublon.
   - **Aucune écriture n'a lieu pendant la prévisualisation.** Si Pokébourse est indisponible, le popup l'indique clairement et vos captures restent enregistrées dans l'extension.
2. **🚀 Envoyer à Pokébourse** :
   Sélectionnez une annonce. L'extension récupère son image principale si elle est disponible sur un domaine d'images pris en charge, puis la transmet au moteur OCR local. Les indices reconnus alimentent l'identification et restent à vérifier. Un onglet de prévisualisation s'ouvre même si le prix, la devise ou l'image manquent : complétez les champs requis et confirmez pour enregistrer l'annonce.
   - La récupération est limitée à une image HTTPS, 8 Mo, sans redirection ni cookies, sur les domaines Vinted, eBay, Leboncoin et Wallapop reconnus. Une image inaccessible ne bloque pas la prévisualisation.
   - Le texte OCR brut n'est pas enregistré. L'analyse ne confirme pas automatiquement l'identité et n'attribue pas de carte à un lot.
3. **⬇️ Télécharger .jsonl** :
   Génère un fichier horodaté pour la sélection, importable manuellement via le formulaire web ou en CLI.
4. **📋 Copier JSONL** :
   Place les cartes sélectionnées dans le presse-papier.

Les captures sans prix ou sans devise restent accessibles dans l'extension et peuvent être complétées en prévisualisation. L'export JSONL exige un prix et une devise connus pour chaque annonce sélectionnée ; aucune valeur par défaut n'est inventée.

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

Le repli d'extraction des numéros isolés exclut aussi les ventes avec cartes
supplémentaires/offertes et les cartes « au choix ». Les mentions de protection,
de photos ou « pas un lot » ne déclenchent pas ce garde-fou. Les fractions et
numéros préfixés restent des indices capturés ; seul le backend décide du statut
et interdit l'identité unitaire effective d'un lot. Les tests comparent ces cas
entre l'extension et le détecteur backend.

Les règles T02 distinguent aussi les noms comme « Gem Pack 2 » des packs
explicitement proposés (« pack Pokémon », « pack de 3 boosters », « pack 151
scellé »). Un numéro étiqueté comme numéro de série n'est ni une quantité vendue
ni un numéro de carte ; cette exclusion s'applique aussi aux fractions et
préfixes. Les quantités écrites et les négations sont testées avec le backend.
Les protections fondées sur les noms du catalogue, les conflits de langues et
l'état déclaré brut relèvent du backend ; aucun matcher n'est ajouté à
l'extension.

Le backend T03 conserve séparément les indices OCR et les valeurs préremplies.
Une réanalyse ou « Confirmer et ajouter l’annonce » ne les transforme pas en
confirmation humaine d’identité. Leur provenance est visible dans « Indices et
provenance », avant et après l’import. Un désaccord significatif reste à vérifier,
avec les références contradictoires dans une rubrique de diagnostic distincte.
Le contrat JSONL historique reste accepté ; le champ optionnel `identity_evidence`
est décrit dans [le guide T03](../docs/identification/T03_EVIDENCE.md).

La compatibilité du manifest, des fichiers graphiques et du format d'échange JSONL avec le backend Pokébourse est validée par les tests d'intégration. Le parcours de prévisualisation (transmission des champs capturés, sélection unique, application indisponible) est couvert à la fois côté popup (Playwright) et côté serveur (analyse sans écriture, correction conservée, enregistrement confirmé, doublon) :
```bash
docker compose exec app pytest tests/test_chrome_extension.py tests/test_capture_preview.py -v
```
Tous les tests sont au vert.

### Test de bout en bout (Chromium + extension chargée)

Le parcours complet « capture → Envoyer → OCR → prévisualisation → confirmation → fiche » est couvert par un test e2e hermétique (`tests/test_extension_e2e.py`) : un Chromium réel est lancé sous Xvfb avec l'extension chargée, une annonce Vinted simulée localement est capturée par le content script, le popup envoie l'image à l'OCR local (photo JPEG simulée lisible par Tesseract), la prévisualisation sans écriture est vérifiée (aucune ligne en base avant confirmation), puis la confirmation explicite enregistre la fiche via le flux transactionnel (`import_jsonl`). Aucun appel réseau réel : la page annonce, son image et les autres destinations sont interceptés par Playwright. Le test exige Xvfb et s'auto-saute s'il est indisponible :
```bash
docker compose exec app pytest tests/test_extension_e2e.py -v
```
Ce test ne valide pas le comportement sur une marketplace réelle.
