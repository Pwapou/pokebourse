# Pokébourse — Plan et tasking : Recherche avancée & Tendances

**Articulation avec le parcours identification → marché :** le [tasking Identification fiable, comparaison de marché et marge](TASKING_IDENTIFICATION_FIABLE.md) ajoute les lots **T14 à T18 / J3**, à réaliser, pour les cartes unitaires non gradées et gradées PSA/PCA. Il pilote la future recherche automatique après enregistrement d'une identité admissible, la confirmation en cas de doute, les comparables et le scénario de marge. Le présent document conserve la recherche externe explicite de `/search` et les métriques de tendances. Réutiliser les mêmes connecteurs et preuves ; ne pas créer deux politiques de comparaison contradictoires. Zone géographique, repli sans prix suffisants, canal de revente et assouplissements de comparabilité restent ouverts dans le registre de décisions du tasking principal.

## 1. Objectif produit

Ajouter deux espaces complémentaires :

1. **Recherche** (`/search`) : un formulaire unique pour rechercher une carte dans le référentiel, les annonces déjà collectées et, sur action explicite, les sources externes autorisées.
2. **Tendances** (`/trends`) : une vue des mouvements de prix, des cartes les plus présentes dans les annonces récentes et des meilleures opportunités d’achat-revente.

Principes non négociables :

- aucun chiffre fictif et aucune valeur inconnue remplacée par zéro ;
- distinguer **prix**, **annonces observées**, **ventes conclues** et **opportunité estimée** ;
- conserver FastAPI, Jinja2, SQLite, HTML/CSS/Vanilla JS et le fonctionnement local ;
- aucun appel réseau dans les tests automatisés ;
- ne jamais attribuer une carte unitaire à un lot ;
- montants en centimes et ratios en points de base ;
- pas de nouvelle collecte marketplace sans cadre d’accès autorisé.

---

## 2. Ce que les données actuelles permettent

| Besoin | Données disponibles | Faisabilité |
|---|---|---|
| Nom, numéro, extension | `pokemon_reference_cards`, `pokemon_reference_sets`, `catalog_items` | Immédiate |
| Rareté | `pokemon_reference_cards.rarity` | Immédiate si la fiche détaillée TCGdex est chargée |
| Année | `pokemon_reference_sets.release_date` | Immédiate ; année de sortie de l’extension |
| État, langue, variante, édition, gradation | `catalog_items` | Immédiate sur les annonces |
| Prix et moyennes 1/7/30 jours | `cardmarket_prices` | Immédiate après synchronisation |
| Meilleures affaires | moteur `app/profitability.py` | Immédiate, sous réserve d’une cote et de frais complets |
| Popularité dans les annonces | `catalog_items`, `listing_observations` | Immédiate comme proxy, à ne pas appeler « ventes » |
| Nombre de cartes vendues sur 30 jours | aucune donnée fiable | Nouvelle source nécessaire |
| Classement des ventes par pays | aucun pays vendeur/transaction normalisé | Nouvelle source et modèle nécessaires |

**Conséquence :** la première version affiche des **tendances de prix** et une **activité des annonces**, pas un faux palmarès des ventes. Le classement des ventes réelles par pays reste un chantier conditionné par une source officielle de transactions conclues.

---

## 3. Parcours fonctionnels

### 3.1 Recherche avancée

#### Portées

- **Tout** : résultats séparés en « Cartes du référentiel » et « Annonces ».
- **Cartes** : identité officielle, visuel, extension, année, rareté, numéro.
- **Annonces** : carte, prix, source, état, langue, variante, édition, gradation, fraîcheur et rentabilité.
- **Externe** : action explicite, limitée aux connecteurs autorisés ; jamais déclenchée automatiquement à chaque frappe.

#### Champs du formulaire

- recherche libre : nom, numéro, identifiant TCGdex, titre d’annonce ;
- extension/collection ;
- année ou intervalle d’années de sortie ;
- rareté ;
- état ;
- langue ;
- variante et édition ;
- société de gradation et note ;
- source et pays lorsque la donnée existe ;
- prix minimum/maximum pour les annonces ;
- statut d’identification et inclusion/exclusion des lots ;
- tri : pertinence, nom, année, prix, nouveauté, gain net ou ROI selon la portée.

#### Règles de résultat

- les filtres carte (`rarity`, `year`) s’appuient sur la carte référencée, jamais sur une supposition tirée du titre ;
- une annonce non identifiée peut être trouvée par texte, mais ne doit pas apparaître dans un filtre de rareté comme si sa rareté était connue ;
- les attributs non applicables à une portée sont désactivés ou ignorés avec explication ;
- URL GET partageable, pagination et remise à zéro des filtres ;
- export CSV des annonces avec exactement les mêmes filtres ;
- affichage explicite des données manquantes et de la date de dernière observation.

### 3.2 Recherche externe

- case/bouton **« Rechercher aussi à l’extérieur »**, distinct de la recherche locale ;
- TCGdex reste le référentiel externe prioritaire pour compléter une carte absente du cache ;
- les marketplaces utilisent leurs connecteurs autorisés et leurs limitations existantes ; aucune boucle de scraping ajoutée ;
- délai, annulation, quota et erreur visibles ; une indisponibilité externe ne bloque jamais les résultats locaux ;
- possibilité d’importer les résultats retenus, puis de les identifier et d’en calculer la rentabilité ;
- déduplication par `(source_id, external_id)` et préservation de `first_seen_at`.

### 3.3 Tendances

#### Filtres communs

- période : 7 ou 30 jours selon la métrique ;
- pays : seulement si renseigné par la source, sinon « Non disponible » ;
- extension, rareté, langue, état et devise lorsque applicables ;
- seuil minimal d’observations/produits ;
- source de prix et date de synchronisation.

#### Blocs de la page

1. **Hausses et baisses de prix**
   - comparaison `avg7` vs `avg30`, puis `avg1` vs `avg7` ;
   - variation en centimes et en points de base, calculée avec arrondi `ROUND_HALF_UP` ;
   - prix actuel/tendance, moyennes, produit Cardmarket et date de fraîcheur ;
   - exclure les séries dont le prix de comparaison est nul ou absent.

2. **Cartes les plus actives dans les annonces**
   - nombre d’annonces distinctes observées sur 30 jours ;
   - nombre de nouvelles annonces et, si disponible, d’annonces devenues inactives ;
   - libellé obligatoire : « activité des annonces », jamais « ventes » ;
   - regroupement prioritaire par `reference_card_id`, avec langue/variante séparées si elles changent le marché comparé.

3. **Meilleures affaires**
   - réutilisation de `evaluate_listing` et du profil de frais actif ;
   - annonces actives, cartes unitaires identifiées, cote disponible et calcul complet ;
   - tri par gain net puis ROI, avec prix d’achat, revente estimée, frais, fraîcheur et source de cote ;
   - exclusion des lots, annonces ambiguës, devises incompatibles et cotes trop anciennes selon un seuil configurable ;
   - lien vers la fiche annonce et ses preuves de prix.

4. **Ventes conclues par pays — phase conditionnelle**
   - visible seulement si une source fournit réellement transactions, date et pays ;
   - volume de ventes sur 30 jours glissants, prix médian, nombre minimal d’observations ;
   - pas de déduction du pays à partir de la langue ou de la devise.

---

## 4. Architecture cible

```text
app/
├── search/
│   ├── models.py          # SearchFilters, résultats et validation des tris
│   ├── service.py         # Recherche locale référentiel + annonces
│   └── external.py        # Orchestration externe explicite et erreurs isolées
├── trends/
│   ├── models.py          # Filtres, métriques et niveaux de preuve
│   ├── service.py         # Prix, activité des annonces, pays si disponible
│   └── opportunities.py   # Sélection des meilleures affaires via profitability
├── templates/
│   ├── search.html
│   └── trends.html
└── storage/migrations/
    └── 0020_*.sql         # Seulement si une persistance nouvelle est nécessaire
```

- `app/web.py` expose `GET /search`, `GET /trends` et les actions externes explicites.
- `base.html` ajoute les entrées **Recherche** et **Tendances**.
- Les requêtes SQL utilisent paramètres liés, listes blanches de tri et index adaptés.
- La recherche locale reste entièrement hors ligne.
- Aucun appel réseau dans une route GET locale ordinaire ; les enrichissements TCGdex durables passent par la file worker existante.

---

## 5. Découpage en tâches

### Lot 0 — Cadrage technique et sécurité

#### T0.1 — Baseline et contrat des métriques
- [ ] Exécuter la suite de tests avant développement.
- [ ] Mesurer le volume des annonces, références et prix pour anticiper les index.
- [ ] Valider les libellés « prix », « activité des annonces », « ventes conclues ».
- [ ] Définir la fenêtre glissante en UTC et les seuils minimaux par métrique.
- [ ] Définir la fraîcheur maximale d’une cote éligible aux meilleures affaires.

**Livrable :** règles métier validées et tests initiaux verts.

#### T0.2 — Audit des sources de ventes par pays
- [ ] Vérifier les API officielles encore disponibles pour les ventes conclues.
- [ ] Documenter volumes, pays, quotas, coût, historique et droit de stockage.
- [ ] Ne retenir aucune source qui ne fournit pas réellement les trois dimensions : transaction, date, pays.
- [ ] Mettre à jour `SOURCES.md` avant tout connecteur.

**Livrable :** décision go/no-go ; ce chantier ne bloque pas les lots 1 à 3.

### Lot 1 — Recherche locale avancée

#### T1.1 — Modèle de filtres et normalisation
- [ ] Créer `SearchFilters` avec bornes, longueurs maximales et listes blanches.
- [ ] Normaliser langue, devise, état et années sans écraser les valeurs inconnues.
- [ ] Définir les tris autorisés et la pertinence exacte/approchée.
- [ ] Refuser les intervalles incohérents (`min > max`) avec un message clair.

**Dépendance :** T0.1.  
**Tests :** validation, bornes, valeurs vides, paramètres inconnus.

#### T1.2 — Service de recherche du référentiel
- [ ] Étendre la recherche existante sans casser `search_references`.
- [ ] Filtrer par nom/numéro/ID, extension, rareté et année via `release_date`.
- [ ] Ajouter pagination, total, tri et suggestions orthographiques séparées.
- [ ] Signaler quand la rareté ou l’année n’est pas chargée localement.

**Dépendance :** T1.1.  
**Tests :** correspondances exactes, fuzzy, filtres combinés, données absentes.

#### T1.3 — Service de recherche des annonces
- [ ] Factoriser les filtres catalogue réutilisables sans dupliquer la logique métier.
- [ ] Ajouter état, langue, rareté référencée, année, variante, édition, grade et prix.
- [ ] Joindre la référence uniquement pour les attributs officiels.
- [ ] Ajouter tris, pagination, compteur et requêtes paramétrées.
- [ ] Préserver le comportement actuel de `/catalog` et de son export.

**Dépendance :** T1.1.  
**Tests :** combinaisons, lots, annonces non identifiées, SQL injection, pagination.

#### T1.4 — Index SQLite
- [ ] Profiler les requêtes avec `EXPLAIN QUERY PLAN` sur un volume représentatif.
- [ ] Ajouter uniquement les index justifiés dans une migration `0020_search_indexes.sql` si nécessaire.
- [ ] Respecter `BEGIN IMMEDIATE;`, `COMMIT;` et `schema_migrations`.
- [ ] Mettre à jour les migrations attendues dans les tests.

**Dépendance :** T1.2 et T1.3.  
**Tests :** idempotence, migration depuis `0019`, non-régression.

#### T1.5 — Routes et interface `/search`
- [ ] Ajouter la route GET, le template et l’entrée de navigation.
- [ ] Construire le formulaire complet et les sections de résultats.
- [ ] Conserver tous les filtres dans l’URL, la pagination et l’export.
- [ ] Prévoir états vide, aucun résultat, erreur et référentiel incomplet.
- [ ] Respecter Mosaic × Flowbite, clavier, responsive et absence de dépendances distantes.

**Dépendance :** T1.2 et T1.3.  
**Tests :** routes, contextes, échappement HTML, 320/390/768/1024/1440 px.

#### T1.6 — Export cohérent
- [ ] Réutiliser les mêmes filtres que la recherche annonces.
- [ ] Ajouter les colonnes utiles sans exposer de données vendeur interdites.
- [ ] Vérifier que le nombre exporté correspond au résultat affiché hors pagination.

**Dépendance :** T1.3 et T1.5.

### Lot 2 — Recherche externe contrôlée

#### T2.1 — Orchestrateur externe
- [ ] Définir un contrat commun : résultats, source, erreurs, fraîcheur et durée.
- [ ] Exécuter la recherche uniquement après action explicite.
- [ ] Isoler les erreurs par source et conserver les résultats locaux.
- [ ] Appliquer timeouts, limites, backoff et `Retry-After`.

**Dépendance :** Lot 1 et audit `SOURCES.md`.

#### T2.2 — Complétion TCGdex
- [ ] Réutiliser la file persistante et le cache existants.
- [ ] Ne transmettre que les critères de carte nécessaires.
- [ ] Rafraîchir les résultats locaux après traitement worker.
- [ ] Ne jamais faire d’appel TCGdex dans les tests.

**Dépendance :** T2.1.

#### T2.3 — Import des résultats externes retenus
- [ ] Dédupliquer via `(source_id, external_id)`.
- [ ] Préserver `first_seen_at` et actualiser uniquement les champs autorisés.
- [ ] Enregistrer les observations de prix.
- [ ] Lancer identification puis rentabilité selon les règles existantes.

**Dépendance :** T2.1.  
**Tests :** doublons, timestamps, indisponibilité, aucune requête réelle.

### Lot 3 — Tendances et meilleures affaires

#### T3.1 — Service de variations de prix
- [ ] Calculer les variations 7/30 et 1/7 jours en entiers.
- [ ] Fournir hausses, baisses, prix, fraîcheur et taille de l’échantillon disponible.
- [ ] Exclure les comparaisons impossibles et signaler les rattachements partiels.
- [ ] Paginer et borner les résultats.

**Dépendance :** T0.1.  
**Tests :** arrondis, zéro, null, devises, doublons de produits.

#### T3.2 — Service d’activité des annonces sur 30 jours
- [ ] Compter annonces distinctes et nouvelles annonces par carte identifiée.
- [ ] Utiliser les observations et `first_seen_at` sans écraser l’historique.
- [ ] Séparer clairement activité et disparition d’annonce d’une vente conclue.
- [ ] Ajouter filtres extension/rareté/langue et seuil minimal.

**Dépendance :** T0.1.  
**Tests :** ré-ingestion, doublons, fenêtre exacte, lots et ambiguïtés.

#### T3.3 — Classement des meilleures affaires
- [ ] Réutiliser `enrich_catalog_items`/`evaluate_listing`, sans dupliquer les calculs.
- [ ] Filtrer annonces actives, identifiées, unitaires et complètes.
- [ ] Appliquer fraîcheur de cote, devise et seuils du profil de frais.
- [ ] Trier par gain net puis ROI et fournir les preuves de prix.

**Dépendance :** T0.1.  
**Tests :** centimes/bps, exclusions, égalités, absence de cote/frais.

#### T3.4 — Page `/trends`
- [ ] Ajouter filtres, date de calcul et quatre états : chargé, vide, partiel, données insuffisantes.
- [ ] Afficher variations de prix, activité des annonces et meilleures affaires.
- [ ] Ajouter liens vers recherche préfiltrée et fiches annonces.
- [ ] Ne pas afficher de bloc « ventes par pays » sans données réelles.
- [ ] Ajouter navigation, responsive et accessibilité.

**Dépendance :** T3.1 à T3.3.

### Lot 4 — Ventes conclues par pays, uniquement si T0.2 est concluant

#### T4.1 — Persistance des transactions
- [ ] Créer une migration pour les ventes conclues : source, identifiant externe, carte, date, prix, devise, pays et quantité.
- [ ] Stocker les montants en centimes et pays en code normalisé.
- [ ] Ajouter unicité et index `(reference_card_id, sold_at, country)`.
- [ ] Conserver les preuves/source sans données personnelles.

#### T4.2 — Connecteur et synchronisation
- [ ] Implémenter la source officielle validée par T0.2.
- [ ] Planifier une synchronisation bornée et reprenable.
- [ ] Gérer quotas, erreurs et couverture géographique incomplète.
- [ ] Tester exclusivement avec réponses simulées.

#### T4.3 — Classement des ventes sur 30 jours
- [ ] Calculer quantités, transactions et prix médian par carte et pays.
- [ ] Appliquer un seuil minimal et afficher la couverture réelle.
- [ ] Ajouter le bloc à `/trends` sans mélanger les pays inconnus à un pays supposé.

### Lot 5 — Recette et documentation

#### T5.1 — Tests automatisés
- [ ] Tests unitaires des filtres, calculs, tris et exclusions.
- [ ] Tests de migration et d’intégrité SQLite.
- [ ] Tests des routes, exports, formulaires et états vides.
- [ ] Mocks systématiques pour toutes les sources externes.
- [ ] Exécution complète : `docker compose run --rm app pytest`.

#### T5.2 — Recette fonctionnelle et performance
- [ ] Vérifier recherche simple puis tous les filtres combinés.
- [ ] Comparer les meilleures affaires avec le moteur de rentabilité existant.
- [ ] Vérifier l’absence de « ventes » inférées des annonces disparues.
- [ ] Tester base vide, données partielles, source externe indisponible et cote expirée.
- [ ] Mesurer les requêtes principales sur volume représentatif.

#### T5.3 — Documentation
- [ ] Mettre à jour `README.md` pour les deux écrans.
- [ ] Documenter les métriques, limites et sources dans `SOURCES.md`.
- [ ] Documenter toute migration et toute commande worker ajoutée.

---

## 6. Ordre de livraison recommandé

1. **Version 1 :** recherche locale complète + meilleures affaires + variations de prix.
2. **Version 1.1 :** activité des annonces sur 30 jours + exports et optimisations.
3. **Version 1.2 :** recherche externe explicite et import contrôlé.
4. **Version 2 :** ventes conclues par pays seulement après validation d’une source adaptée.

## 7. Definition of Done globale

- recherche et filtres reproductibles via URL, pagination et export cohérent ;
- aucune attribution de rareté/année sans rattachement fiable à une carte ;
- tendances accompagnées de leur source, période, fraîcheur et niveau de preuve ;
- meilleures affaires strictement alignées sur le moteur de rentabilité ;
- aucune métrique de vente ou de pays fabriquée à partir de proxies ;
- application utilisable hors ligne pour les données locales ;
- tests 100 % verts, aucun appel réseau automatisé, aucune régression SQLite ;
- interface responsive, accessible et conforme à la charte existante.
