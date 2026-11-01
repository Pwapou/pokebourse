# Pokébourse — Intégration du design Mosaic × Flowbite

## 1. Objectif

Intégrer dans l’application réelle le langage visuel validé dans la maquette :

- **Mosaic** pour le pilotage : indicateurs, état des données, synthèses et priorités ;
- **Flowbite** pour les listes : catalogue dense, filtres explicites, tris et fiches produit ;
- interface épurée, responsive et accessible, sans framework frontend supplémentaire.

La maquette est une référence visuelle et interactive, **pas une source de données**. Ne jamais recopier ses montants, achats, annonces ou statuts fictifs dans les pages réelles.

## 2. Ressources à fournir au développeur

### Maquette de référence

- URL locale : `http://localhost:8000/static/prototype.html?v=2#dashboard`
- Structure HTML : `app/static/prototype.html`
- Direction visuelle et responsive : `app/static/prototype.css`
- Interactions de démonstration : `app/static/prototype.js`

### Application à modifier

- Layout commun : `app/templates/base.html`
- Tableau de bord : `app/templates/dashboard.html`
- Catalogue et fiche produit : `app/templates/catalog.html`, `app/templates/catalog_detail.html`
- Analyse de rentabilité : `app/templates/profitability.html`
- Veilles : `app/templates/watches.html`
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
7. Les achats et statuts de portefeuille présents dans la maquette ne sont pas encore une fonctionnalité réelle : ne pas les simuler.
8. Travailler sur une copie de sauvegarde si des essais sur les données sont nécessaires ; l’intégration CSS/HTML ne doit pas écrire dans la base.
9. Préserver l’autonomie hors ligne : pas de police, script, icône ou image distant obligatoire.

## 4. Découpage des tâches

### T0 — Relever l’existant et sécuriser la reprise

- [ ] Lire ce document, le `README.md`, la maquette et les templates.
- [ ] Lancer l’application et la suite de tests avant toute modification.
- [ ] Faire l’inventaire des pages, formulaires, états vides, erreurs et paginations.
- [ ] Créer une sauvegarde depuis l’interface existante si une vérification sur les données réelles est nécessaire.
- [ ] Noter les résultats initiaux pour distinguer toute régression des problèmes déjà présents.

**Livrable :** application démarrée, tests initiaux exécutés, aucun changement fonctionnel.

### T1 — Poser le système visuel commun

- [ ] Transposer les tokens de `prototype.css` dans `style.css` : couleurs, espacements, rayons, bordures, typographie et états.
- [ ] Reprendre la sidebar sombre, le logo, les groupes de navigation et l’indicateur local.
- [ ] Adapter la topbar : fil d’Ariane/titre contextualisé, état de la base, emplacement de recherche seulement s’il est réellement utilisable.
- [ ] Créer les composants CSS réutilisables : boutons, cartes métriques, panneaux, badges, tableaux/listes, formulaires, alertes et pagination.
- [ ] Prévoir les états `hover`, `focus-visible`, `disabled`, erreur et succès.
- [ ] Incrémenter la version des assets dans `base.html` pour éviter le cache navigateur.

**Critères :** toutes les pages utilisent le même layout ; aucun style critique ne dépend de `prototype.css`.

### T2 — Refondre le catalogue avec le modèle Flowbite

- [ ] Transformer chaque annonce en ligne produit dense : identité, extension/état, achat, revente estimée, gain net, ROI et verdict.
- [ ] Conserver les filtres existants : recherche, extension, source, tri et pagination.
- [ ] Conserver les liens `/catalog/<id>` et l’export CSV avec les filtres actifs.
- [ ] Afficher clairement les données manquantes sans fabriquer de rentabilité.
- [ ] Conserver les compteurs de résultats et l’état vide avec action de réinitialisation.
- [ ] Ajouter une version mobile en cartes/lignes à deux colonnes, sans débordement horizontal.

**Critères :** à filtres identiques, les résultats et les chiffres sont strictement identiques à ceux d’avant refonte.

### T3 — Refondre la fiche annonce

- [ ] Utiliser la hiérarchie du drawer de la maquette dans la page réelle : identité, verdict, quatre indicateurs, calcul détaillé et hypothèse de prix.
- [ ] Afficher le vendeur, l’URL source et les métadonnées utiles déjà disponibles.
- [ ] Détailler prix d’achat, port, revente estimée, commission, frais fixes, expédition et gain net.
- [ ] Expliquer l’origine et la fraîcheur de la référence lorsque les données existent.
- [ ] Préserver le comportement 404 pour une annonce inexistante.

**Critères :** le calcul affiché correspond exactement à l’objet `evaluation` fourni par le backend.

### T4 — Adapter le tableau de bord avec le modèle Mosaic

- [ ] Organiser la page en synthèse, priorités et activité récente.
- [ ] Ne montrer que des métriques réellement disponibles : annonces, opportunités, imports, échecs et indicateurs de rentabilité existants.
- [ ] Transformer les meilleures opportunités en liste produit compacte avec liens réels.
- [ ] Conserver les formulaires d’import et leurs retours de succès/erreur.
- [ ] Ne pas reprendre le graphique, le donut, la valorisation ou « Mes achats » sans données backend correspondantes.
- [ ] Créer un état vide utile pour une base sans annonce.

**Critères :** aucune métrique fictive ; les erreurs et imports récents restent accessibles.

### T5 — Harmoniser les pages secondaires

- [ ] Appliquer les mêmes panneaux et formulaires à l’analyse de rentabilité.
- [ ] Harmoniser veilles, références, sauvegardes, imports et détails de lot.
- [ ] Conserver les confirmations explicites de suppression/restauration.
- [ ] Refondre la page 404 avec le layout commun et un retour au catalogue.
- [ ] Vérifier qu’aucun bouton décoratif ou non fonctionnel de la maquette n’a été recopié.

**Critères :** aucune régression sur les actions POST, redirections et téléchargements.

### T6 — Responsive et accessibilité

- [ ] Vérifier aux largeurs 1440, 1024, 768, 390 et 320 px.
- [ ] Ajouter la navigation mobile avec bouton libellé, fermeture après navigation et gestion d’Échap.
- [ ] Garantir des libellés de formulaire, une navigation clavier et un focus visible.
- [ ] Ne pas utiliser la couleur comme seul porteur d’information.
- [ ] Vérifier le contraste des textes et badges ainsi que l’absence de défilement horizontal.
- [ ] Garder des cibles tactiles d’environ 44 px pour les actions principales mobiles.

**Critères :** toutes les actions essentielles restent accessibles au clavier et sur mobile.

### T7 — Tests et recette finale

- [ ] Adapter uniquement les tests qui dépendent de libellés/classes HTML modifiés.
- [ ] Ajouter des tests de présence des nouveaux composants si utile, sans tester uniquement le style.
- [ ] Exécuter `docker compose run --rm app pytest`.
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
| Mes achats / portefeuille | **Hors périmètre** tant que le domaine n’existe pas |
| Graphique et donut fictifs | Ne pas intégrer sans série de données réelle |

## 6. Suivi du portefeuille — chantier ultérieur distinct

La demande cible inclut les achats et leurs statuts, mais l’application actuelle ne fournit pas encore ce domaine. Ne pas l’ajouter au milieu de la refonte CSS.

Pour une phase ultérieure, spécifier d’abord :

- modèle `purchase` : annonce/carte, date, prix payé, frais, quantité et provenance ;
- statuts métier et transitions autorisées : collection, à vendre, en vente, vendu ;
- prix de vente réel séparé de l’estimation ;
- historique des changements de statut ;
- règles de valorisation et comportement lorsque la référence manque ;
- migrations SQLite, routes, formulaires, tests et sauvegarde/restauration ;
- seulement ensuite graphiques et métriques de portefeuille.

## 7. Prompt prêt à copier pour un autre modèle

```text
Tu travailles dans /Users/mathieu/Documents/pokebourse.

Commence par lire TASKING_INTEGRATION_DESIGN.md, README.md, app/templates/base.html,
app/web.py et les trois fichiers app/static/prototype.*.

Ta mission est d’intégrer le design Mosaic × Flowbite validé dans la maquette à
l’application FastAPI/Jinja existante. La maquette est visible sur :
http://localhost:8000/static/prototype.html?v=2#dashboard

Exécute les tâches T0 à T7 dans l’ordre. Ne change pas les règles métier, les
routes, les calculs ou la base SQLite pour cette refonte. Ne recopie jamais les
données fictives de la maquette. Le suivi « Mes achats » et les graphiques de
portefeuille sont hors périmètre tant qu’aucune donnée réelle n’existe.

Préserve les imports, exports, sauvegardes, erreurs et formulaires. Utilise les
composants CSS locaux, sans framework ni dépendance distante. Vérifie le responsive
et l’accessibilité. Lance docker compose run --rm app pytest avant de terminer et
présente les fichiers modifiés, les tests exécutés et les éventuels points restants.
Ne supprime jamais le volume Docker pokemon-data.
```
