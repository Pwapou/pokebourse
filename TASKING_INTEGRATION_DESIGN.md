# Pokébourse — Intégration du design Mosaic × Flowbite

**Revue du 8 novembre 2026 :** ordre de reprise et état transversal dans [TASKING_PROJET.md](TASKING_PROJET.md). Les cases mises à jour décrivent les critères vérifiés dans le code et les tests ; les contrôles manuels ou critères non démontrés restent ouverts.

**État : socle visuel intégré.** Les templates et `style.css` portent déjà cette charte ; les suites web et de simplification passent. T6/T7 conservent les critères de recette exhaustive non démontrés dans cette revue. Ne pas recommencer T0–T5 comme une nouvelle refonte.

## 1. Objectif

Intégrer dans l’application réelle le langage visuel validé dans la maquette :

- **Mosaic** pour le pilotage : indicateurs, état des données, synthèses et priorités ;
- **Flowbite** pour les listes : catalogue dense, filtres explicites, tris et fiches produit ;
- interface épurée, responsive et accessible, sans framework frontend supplémentaire.

La maquette est une référence visuelle et interactive, **pas une source de données**. Ne jamais recopier ses montants, achats, annonces ou statuts fictifs dans les pages réelles.

## 2. Ressources à fournir au développeur

### Maquette de référence

> **Maquette cible actuelle (simplification) :**
> - URL locale : `http://localhost:8000/static/prototype-cible.html#accueil`
> - Structure HTML : `app/static/prototype-cible.html`
> - Direction visuelle et responsive : `app/static/prototype-cible.css`
> - Interactions de démonstration : `app/static/prototype-cible.js`
> - Tasking associé : `TASKING_SIMPLIFICATION_CIBLE.md`

Maquette historique (itération précédente) :
- URL locale : `http://localhost:8000/static/prototype.html?v=2#dashboard`
- Structure HTML : `app/static/prototype.html`
- Direction visuelle et responsive : `app/static/prototype.css`
- Interactions de démonstration : `app/static/prototype.js`

### Application à modifier

- Layout commun : `app/templates/base.html`
- Tableau de bord : `app/templates/dashboard.html`
- Catalogue et fiche produit : `app/templates/catalog.html`, `app/templates/catalog_detail.html`
- Réglages (frais, références, marché) : `app/templates/reglages.html` (route de compatibilité `/profitability`)
- Veilles : `app/templates/watches.html`
- Achats : `app/templates/achats.html`
- Gestion avancée : `app/templates/gestion.html`
- Sauvegardes et imports : `app/templates/backups.html`, `app/templates/import_detail.html`
- Page d’erreur : `app/templates/404.html`
- Styles et scripts existants : `app/static/style.css`, `app/static/forms.js`
- Routes et contextes Jinja : `app/web.py`
- Documentation fonctionnelle : `README.md`
- Tests : `tests/`, en particulier `tests/test_web.py`

### Commandes

```bash
cd /Users/mathieu/Documents/pokebourse
docker compose up --build -d
curl http://localhost:8000/health
docker compose run --rm app pytest
```

Ne jamais utiliser `docker compose down --volumes` : le volume `pokemon-data` contient les données réelles.

## 3. Contraintes impératives

1. Conserver FastAPI, Jinja et SQLite ; ne pas introduire React, Tailwind, un bundler ou une nouvelle API pour ce chantier.
2. Réutiliser les données déjà transmises par `app/web.py`. Aucun chiffre fictif dans l’application réelle.
3. Ne pas modifier le moteur de rentabilité, les imports, les sauvegardes ou les schémas SQL pour une simple intégration visuelle.
4. Préserver toutes les routes, formulaires, paramètres d’URL, exports CSV, confirmations et messages d’erreur.
5. Une valeur inconnue reste inconnue : afficher `—` ou « Données insuffisantes », jamais `0 €` par défaut.
6. Conserver la distinction entre prix estimé, gain net estimé et vente réellement conclue.
7. Les achats réels existent dans `purchases` et `/achats` ; utiliser leurs données, jamais celles de la maquette. Frais de revente détaillés et gain réalisé restent hors du socle livré.
8. Travailler sur une copie de sauvegarde si des essais sur les données sont nécessaires ; l’intégration CSS/HTML ne doit pas écrire dans la base.
9. Préserver l’autonomie hors ligne : pas de police, script, icône ou image distant obligatoire.

## 4. Découpage des tâches

### T0 — Relever l’existant et sécuriser la reprise

- [x] Relire la charte, le `README.md` et les contrats des templates existants.
- [ ] Comparer visuellement toutes les pages à la maquette dans la recette finale.
- [ ] Lancer l’application et la suite de tests avant toute modification.
- [ ] Faire l’inventaire des pages, formulaires, états vides, erreurs et paginations.
- [ ] Créer une sauvegarde depuis l’interface existante si une vérification sur les données réelles est nécessaire.
- [ ] Noter les résultats initiaux pour distinguer toute régression des problèmes déjà présents.

**Livrable :** application démarrée, tests initiaux exécutés, aucun changement fonctionnel.

### T1 — Poser le système visuel commun

- [x] Transposer les tokens de `prototype.css` dans `style.css` : couleurs, espacements, rayons, bordures, typographie et états.
- [x] Reprendre la sidebar sombre, le logo, les groupes de navigation et l’indicateur local.
- [x] Adapter la topbar : fil d’Ariane/titre contextualisé, état de la base, emplacement de recherche seulement s’il est réellement utilisable.
- [x] Créer les composants CSS réutilisables : boutons, cartes métriques, panneaux, badges, tableaux/listes, formulaires, alertes et pagination.
- [x] Prévoir les états `hover`, `focus-visible`, `disabled`, erreur et succès.
- [x] Incrémenter la version des assets dans `base.html` pour éviter le cache navigateur.

**Critères :** toutes les pages utilisent le même layout ; aucun style critique ne dépend de `prototype.css`.

### T2 — Refondre le catalogue avec le modèle Flowbite

- [x] Transformer chaque annonce en ligne produit dense : identité, extension/état, achat, revente estimée, gain net, ROI et verdict.
- [x] Conserver les filtres existants : recherche, extension, source, tri et pagination.
- [x] Conserver les liens `/catalog/<id>` et l’export CSV avec les filtres actifs.
- [x] Afficher clairement les données manquantes sans fabriquer de rentabilité.
- [x] Conserver les compteurs de résultats et l’état vide avec action de réinitialisation.
- [x] Ajouter les règles responsive du catalogue dans le CSS local.
- [x] Recetter le catalogue aux cinq largeurs T6 et vérifier l’absence de débordement horizontal.

**Critères :** à filtres identiques, les résultats et les chiffres sont strictement identiques à ceux d’avant refonte.

### T3 — Refondre la fiche annonce

- [x] Utiliser la hiérarchie du drawer de la maquette dans la page réelle : identité, verdict, quatre indicateurs, calcul détaillé et hypothèse de prix.
- [x] Afficher le vendeur, l’URL source et les métadonnées utiles déjà disponibles.
- [x] Détailler prix d’achat, port, revente estimée, commission, frais fixes, expédition et gain net.
- [x] Expliquer l’origine et la fraîcheur de la référence lorsque les données existent.
- [x] Préserver le comportement 404 pour une annonce inexistante.

**Critères :** le calcul affiché correspond exactement à l’objet `evaluation` fourni par le backend.

### T4 — Adapter le tableau de bord avec le modèle Mosaic

- [x] Organiser la page en synthèse, priorités et activité récente.
- [x] Ne montrer que des métriques réellement disponibles : annonces, opportunités, imports, échecs et indicateurs de rentabilité existants.
- [x] Transformer les meilleures opportunités en liste produit compacte avec liens réels.
- [x] Conserver les formulaires d’import et leurs retours de succès/erreur.
- [x] Ne pas reprendre le graphique, le donut, la valorisation ou « Mes achats » sans données backend correspondantes.
- [x] Créer un état vide utile pour une base sans annonce.

**Critères :** aucune métrique fictive ; les erreurs et imports récents restent accessibles.

### T5 — Harmoniser les pages secondaires

- [x] Appliquer les mêmes panneaux et formulaires à l’analyse de rentabilité.
- [x] Harmoniser veilles, références, sauvegardes, imports et détails de lot.
- [x] Conserver les confirmations explicites de suppression/restauration.
- [x] Refondre la page 404 avec le layout commun et un retour au catalogue.
- [x] Compléter l’inventaire des actions de chaque écran et vérifier l’absence de bouton décoratif sans comportement.

**Critères :** aucune régression sur les actions POST, redirections et téléchargements.

### T6 — Responsive et accessibilité

- [ ] Vérifier aux largeurs 1440, 1024, 768, 390 et 320 px (`/catalog`, `/search` et `/trends` vérifiés sous Chromium aux 5 largeurs sans débordement horizontal ni chevauchement ; autres écrans secondaires restant à recetter exhaustivement).
- [x] Ajouter la navigation mobile avec bouton libellé, fermeture après navigation et gestion d’Échap (`forms.js`) ; la recette exhaustive reste ci-dessus.
- [ ] Garantir des libellés de formulaire, une navigation clavier et un focus visible.
- [ ] Ne pas utiliser la couleur comme seul porteur d’information.
- [ ] Vérifier le contraste des textes et badges ainsi que l’absence de défilement horizontal.
- [ ] Garder des cibles tactiles d’environ 44 px pour les actions principales mobiles.

**Critères :** toutes les actions essentielles restent accessibles au clavier et sur mobile.

### T7 — Tests et recette finale

- [ ] Adapter uniquement les tests qui dépendent de libellés/classes HTML modifiés.
- [ ] Ajouter des tests de présence des nouveaux composants si utile, sans tester uniquement le style.
- [x] Exécuter `docker compose run --rm app pytest`.
- [ ] Vérifier `/health` et chaque page avec une base vide et une base contenant des annonces.
- [ ] Tester recherche, filtres combinés, tri, pagination, export CSV, fiche et 404.
- [ ] Tester import valide/invalide/doublon sans perdre les messages d’erreur.
- [ ] Tester création/téléchargement d’une sauvegarde ; ne tester une restauration que sur une copie.
- [ ] Comparer visuellement les écrans à la maquette sans importer ses données.
- [ ] Supprimer les fichiers temporaires créés pendant les tests ; conserver la maquette comme référence.

**Definition of Done :** suite de tests verte, parcours principaux vérifiés sur desktop et mobile, aucune donnée fictive, aucune modification du modèle métier.

## 5. Correspondance maquette → application

| Maquette | Intégration réelle |
|---|---|
| Vue d’ensemble | `/` avec les données de `dashboard_data` et `profitability_dashboard_summary` |
| Annonces à analyser | `/catalog`, enrichi par les données de rentabilité déjà disponibles |
| Fiche en panneau latéral | Page `/catalog/<id>` ; pas besoin d’AJAX ni de drawer |
| Filtres/statut/tri | Paramètres GET existants ; conserver les listes blanches backend |
| Prix de référence | Sections existantes de `/profitability` |
| Imports & sauvegardes | Formulaire `/`, `/backups`, `/imports/<id>` |
| Mes achats / portefeuille | `/achats` sur `purchases` ; prix brut de vente facultatif depuis `0021`, pas de gain net réalisé sans frais réels |
| Graphique et donut fictifs | Ne pas intégrer sans série de données réelle |

## 6. Suivi du portefeuille — état courant et suite

Le domaine achats existe depuis `0010` ; `0021_purchase_sale_price.sql` ajoute un prix brut de vente facultatif. `/achats` expose les statuts `commande`, `recu`, `en_vente`, `vendu` et les montants par devise. Ne pas recréer ce modèle lors d'une évolution visuelle.

Les frais/date de revente, transitions historisées, estimation figée à l'achat, attribution et gain net réalisé restent dans [Radar/P6](PLAN_RADAR_OPPORTUNITES.md). La présence d'un prix brut de vente ne suffit pas à calculer un gain net réel.

## 7. Prompt prêt à copier pour un autre modèle

```text
Tu travailles dans /Users/mathieu/Documents/pokebourse.

Commence par lire TASKING_PROJET.md, TASKING_INTEGRATION_DESIGN.md, README.md,
app/templates/base.html, app/web.py et les fichiers app/static/prototype-cible.*.

Ta mission est de maintenir le design Mosaic × Flowbite déjà intégré dans
l’application FastAPI/Jinja existante. La maquette est visible sur :
http://localhost:8000/static/prototype-cible.html#accueil

Vérifie les acquis puis traite les critères ouverts du périmètre demandé. Ne change pas les règles métier, les
routes, les calculs ou la base SQLite pour cette refonte. Ne recopie jamais les
données fictives de la maquette. Réutilise le suivi /achats existant ; les nouvelles données de revente
relèvent de Radar/P6, pas de cette charte.

Préserve les imports, exports, sauvegardes, erreurs et formulaires. Utilise les
composants CSS locaux, sans framework ni dépendance distante. Vérifie le responsive
et l’accessibilité. Lance docker compose run --rm app pytest avant de terminer et
présente les fichiers modifiés, les tests exécutés et les éventuels points restants.
Ne supprime jamais le volume Docker pokemon-data.
```
