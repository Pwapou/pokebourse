# Captures d'écran et Visuels — Pokébourse

Ce dossier contient les visuels et captures d'écran illustrant le fonctionnement de Pokébourse dans la documentation Git (`README.md`).

---

## 🖼️ Fichiers fournis par défaut

Par défaut, ce dossier intègre des maquettes vectorielles SVG fidèles au design réel **Mosaic × Flowbite** de Pokébourse. Elles s'affichent immédiatement de façon nette (HD / Retina) sur GitHub et GitLab :

| Fichier | Écran représenté | Usage dans le README |
|---|---|---|
| [`01-dashboard.svg`](01-dashboard.svg) | Tableau de bord principal, KPIs et opportunités | Section *1. Tableau de bord* |
| [`02-chrome-extension.svg`](02-chrome-extension.svg) | Extension Chrome Manifest V3 & Popup de capture | Section *2. Extension Chrome* |
| [`03-catalog.svg`](03-catalog.svg) | Catalogue filtré avec statuts TCGdex | Section *3. Catalogue & Recherche* |
| [`04-catalog-detail.svg`](04-catalog-detail.svg) | Fiche détail annonce, réconciliation et rentabilité | Section *4. Fiche détaillée & Arbitrage* |
| [`05-profitability.svg`](05-profitability.svg) | Moteur de rentabilité et cotes Cardmarket | Section *5. Moteur de Rentabilité* |
| [`06-sellers-purchases.svg`](06-sellers-purchases.svg) | Annuaire des vendeurs et carnet d'achats | Section *6. Vendeurs & Portefeuille* |
| [`07-watches-supervision.svg`](07-watches-supervision.svg) | Veilles automatiques et supervision du worker | Section *7. Veilles & Supervision* |

---

## 📸 Comment remplacer par de vraies captures d'écran PNG ?

Si vous souhaitez remplacer ces maquettes SVG par de vraies captures d'écran prises depuis votre navigateur :

1. Démarrez l'application locale :
   ```bash
   docker compose up --build -d
   ```
2. Ouvrez [http://localhost:8000](http://localhost:8000) dans votre navigateur (Chrome / Safari / Firefox).
3. Prenez une capture d'écran de chaque page (largeur recommandée : **1200 px**).
4. Déposez vos captures dans ce dossier `docs/images/` sous les noms correspondants :
   - `01-dashboard.png`
   - `02-chrome-extension.png`
   - `03-catalog.png`
   - `04-catalog-detail.png`
   - `05-profitability.png`
   - `06-sellers-purchases.png`
   - `07-watches-supervision.png`
5. Ajustez l'extension `.svg` en `.png` dans `README.md` (ou conservez les deux).
