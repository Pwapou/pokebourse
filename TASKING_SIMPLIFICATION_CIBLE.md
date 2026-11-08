# Pokébourse — Maquette et tasking de simplification

**Revue du 8 novembre 2026 :** ordre de reprise et état transversal dans [TASKING_PROJET.md](TASKING_PROJET.md). Les cases mises à jour décrivent les critères vérifiés dans le code et les tests ; les contrôles manuels ou critères non démontrés restent ouverts.

**État : phases 1–3 intégrées pour les écrans et flux existants, recette exhaustive encore ouverte.** Preuves : `tests/test_simplification_navigation.py`, `tests/test_simplification_avancee.py`, suites web/extension/achats et code des templates. T2.2 reste partiel : un guide de progression existe, pas l'assistant à trois questions avec préréglages. Les tests automatisés ne clôturent pas la recette de tous les écrans aux cinq largeurs.

## 1. Cible produit

> **Capturer une annonce, comprendre si elle vaut le coup, décider, puis suivre l’achat.**

La simplification porte sur la navigation, la hiérarchie visuelle et les points d’entrée. **Aucune fonctionnalité existante ne doit être supprimée.** Le moteur de rentabilité, l’identification, les imports, l’extension Chrome, les veilles, les vendeurs, les achats, le pilote ML, la supervision et les sauvegardes restent disponibles.

### Règles non négociables

1. Conserver toutes les routes GET et POST, tous les formulaires, exports et téléchargements existants.
2. Ne pas modifier les règles financières, les seuils d’identification ou les statuts métier pour simplifier l’affichage.
3. Une valeur inconnue reste inconnue : ne jamais la transformer en zéro ou en estimation favorable.
4. Ne jamais présenter une estimation comme une vente confirmée.
5. Ne pas introduire React, Tailwind, un bundler ou une ressource distante.
6. Conserver la compatibilité JSONL entre l’extension Chrome et `app.catalog.parse_jsonl()`.
7. Préserver les confirmations humaines, les doubles lectures aveugles et les règles de révision des preuves.
8. Préserver les confirmations explicites pour les suppressions et restaurations.
9. Aucun appel réseau réel dans les tests.
10. Ne jamais supprimer le volume Docker `pokemon-data`.

## 2. Maquette de référence

- HTML : `app/static/prototype-cible.html`
- CSS : `app/static/prototype-cible.css`
- Interactions : `app/static/prototype-cible.js`
- URL locale : `http://localhost:8000/static/prototype-cible.html#accueil`

La maquette contient des données fictives et des boutons de démonstration. Elle décrit la navigation et la hiérarchie, **pas une source de données à recopier dans l’application**.

## 3. Architecture de navigation cible

### Navigation principale

| Entrée | Contenu | Destination cible |
|---|---|---|
| Accueil | Opportunités prioritaires, éléments à vérifier, achats en cours, activité et état des données | `/` |
| Opportunités | Catalogue et analyse de rentabilité unifiés | `/catalog` |
| Recherche | Référentiel, annonces et recherche externe explicite | `/search` |
| Tendances | Prix et activité des annonces | `/trends` |
| Mes achats | Tous les achats existants et leurs quatre statuts | `/achats` — vue existante |
| Réglages | Frais, seuils, références de prix et synchronisations de marché | `/reglages` — page existante |
| Gestion avancée | Vendeurs, veilles, imports, TCGdex, annotations, agents et sauvegardes | `/gestion` et liens directs conservés |

### Action globale

Le bouton **« Ajouter des annonces »** propose :

1. Capturer avec l’extension Chrome ;
2. Importer un fichier JSONL ;
3. Créer une veille.

La saisie URL (`/ajouter-annonce`) complète ces entrées dans le menu actuel. Ces entrées ouvrent les fonctions existantes. Le formulaire JSONL reste intégralement disponible, y compris son aide de format et ses erreurs.

### Correspondance et conservation des écrans

| Existant | Cible | Fonctions conservées |
|---|---|---|
| `/` | Accueil simplifié | KPIs, meilleures opportunités, import, lots, erreurs et rapports accessibles par liens |
| `/catalog` | Opportunités, vue unifiée | Recherche, extension, source, identification, tri, pagination, export, réexamen |
| `/profitability` | Vue unifiée + route de compatibilité | Tous les verdicts, tris, calculs, préremplissages, références et paramètres |
| `/catalog/<id>` | Fiche décisionnelle progressive | Calcul, comparables, Cardmarket, vendeur, achat, identification et validation humaine |
| Achats sur fiches annonce/vendeur | `/achats` + formulaires existants | Enregistrement, notes, prix, port, statuts et historique vendeur |
| `/sellers` et `/sellers/<id>` | Gestion avancée → Vendeurs | Filtres, classements, favoris, notes, achats et annonces du vendeur |
| `/watches` | Gestion avancée → Veilles | Création, contrôle, pause, reprise, historique et suppression |
| `/tcgdex` | Gestion avancée → Référentiel | Extensions, enrichissement, détails, pause/reprise, suivi et diagnostic |
| `/annotations` et routes associées | Gestion avancée → Annotations ML | Tirage, file, doubles lectures, arbitrage, statistiques et export |
| `/identification/diagnostics` | Identification et Annotations ML | Diagnostic JSON et filtres existants |
| `/agents` et `/agents/<id>` | Gestion avancée → Agents | Filtres, IP, incidents, historique et reprise manuelle |
| `/backups` | Gestion avancée → Sauvegardes | Création, téléchargement, restauration et contrôle d’intégrité |
| `/imports/<id>` | Accueil → Activité et Gestion avancée → Imports | Contenu du lot, empreinte, rapport d’erreur et suppression |
| Extension Chrome | Entrée principale de capture | Extraction, panier, envoi local, exports JSONL/presse-papier et badges |
| CLI | Inchangée | Toutes les commandes d’administration et d’export |

## 4. Phase 1 — Clarifier la navigation et unifier les décisions

**Objectif :** obtenir la cible visible sans changer les données ni les règles métier.

### T1.1 — Sécuriser l’existant

- [x] Exécuter `docker compose run --rm app pytest` avant modification.
- [ ] Relever les routes, formulaires, paramètres GET, ancres et redirections de `app/web.py`.
- [ ] Constituer une matrice de parcours : base vide, annonces identifiées/ambiguës/lots, cotes présentes/absentes, achats et erreurs d’import.
- [x] Vérifier spécifiquement `tests/test_chrome_extension.py` avant toute retouche de l’extension.

**Livrable :** référence de non-régression validée.

### T1.2 — Installer la nouvelle navigation

- [x] Modifier `app/templates/base.html` pour afficher Accueil, Opportunités, Recherche, Tendances, Mes achats, Réglages et « Gestion avancée ».
- [x] Conserver des liens réels vers toutes les pages avancées ; ne pas les rendre accessibles uniquement par JavaScript.
- [x] Ajouter le menu global « Ajouter des annonces » vers l’import, le guide de capture et les veilles.
- [x] Conserver l’indicateur local, l’état de la base, le fil d’Ariane et la navigation mobile.
- [x] Marquer correctement l’entrée active pour toutes les routes secondaires.

**Fichiers :** `base.html`, `style.css`, `forms.js`, `app/web.py` uniquement pour les contextes de navigation.

### T1.3 — Fusionner catalogue et analyse dans `/catalog`

- [x] Ajouter le filtre `verdict` : `opportunite`, `surveiller`, `non_rentable`, `sans_cote`, `all`.
- [x] Ajouter les tris de rentabilité existants : gain net, ROI et prix d’achat.
- [x] Réunir les filtres actuels du catalogue et de l’analyse : recherche, extension, source, identification, verdict et tri.
- [x] Conserver la pagination du catalogue ; ne pas charger seulement 200 lignes puis paginer visuellement.
- [x] Effectuer le filtrage et le tri côté service/backend afin que les compteurs et pages soient exacts.
- [x] Afficher par ligne : identité, achat total, revente estimée/source, gain net, ROI et verdict.
- [x] Garder les autres métadonnées disponibles dans la fiche ou une ligne secondaire.
- [x] Préserver `/catalog/export.csv` et ses filtres actuels ; conserver les liens profonds et la réidentification globale.

**Attention technique :** ne pas assembler côté template deux listes déjà paginées. Extraire si nécessaire un service de requête commun à `app.catalog` et `app.profitability`, sans dupliquer les calculs.

### T1.4 — Assurer la compatibilité de `/profitability`

- [x] Rediriger les liens d’analyse avec `verdict`, `q`, `set_name` et `sort` vers leur équivalent `/catalog`.
- [x] Rediriger les préremplissages de références vers la nouvelle section Réglages en conservant **tous** les paramètres.
- [x] Maintenir une page de compatibilité pour les liens sans paramètres et les ancres `#parametres` / `#cotes`, ou préserver explicitement ces ancres dans la cible.
- [x] Ne modifier aucun endpoint POST : `/profitability/settings`, `/profitability/references`, imports et suppressions restent fonctionnels.
- [x] Après un POST, rediriger vers la nouvelle page avec les mêmes messages et le même préremplissage.

### T1.5 — Simplifier l’accueil sans perdre l’historique

- [x] Mettre en avant trois indicateurs : opportunités, éléments à vérifier, achats en cours.
- [x] Conserver les meilleures opportunités et leurs montants réels.
- [x] Regrouper imports récents et échecs dans « Activité récente » avec liens vers les lots et rapports.
- [x] Conserver le formulaire d’import et ses retours de succès/erreur.
- [x] Ajouter des états vides qui orientent vers capture, import ou veille.

### T1.6 — Réorganiser la fiche annonce

- [x] Placer en tête : verdict, achat total, revente estimée, gain net, ROI et actions principales.
- [x] Afficher ensuite trois vérifications factuelles : identité, prix de marché, éléments à contrôler humainement.
- [x] Regrouper dans des `<details>` : calcul, comparables/Cardmarket, vendeur/données importées, identification/validation.
- [x] **Ne supprimer aucun formulaire** : achat, réexamen, recherche, confirmation, retrait, reclassement et validation humaine.
- [x] Conserver toutes les hypothèses, limites, dates, sources et alertes de calcul incomplet.
- [x] Sur mobile, garder les actions principales visibles et les sections avancées repliables.

### T1.7 — Recette de la phase 1

- [ ] Tester les anciennes URL et les nouvelles, avec paramètres et ancres.
- [ ] Comparer à données identiques les évaluations avant/après fusion.
- [ ] Vérifier chaque formulaire de la fiche annonce.
- [ ] Vérifier export CSV, import JSONL, rapports d’erreur et lots.
- [ ] Contrôler 1440, 1024, 768, 390 et 320 px, clavier, Échap et focus visible.
- [x] Exécuter `docker compose run --rm app pytest`.

**Definition of Done :** navigation cible disponible, catalogue unifié exact, toutes les fonctions existantes accessibles, aucune régression de calcul ou de route.

## 5. Phase 2 — Fluidifier la configuration, la capture et les achats

**Objectif :** réduire le nombre de décisions techniques demandées à l’utilisateur, sans appliquer d’hypothèses silencieuses.

### T2.1 — Créer `/reglages`

- [x] Regrouper frais/seuils, références de prix et données de marché dans des sections distinctes.
- [x] Réutiliser les formulaires et endpoints actuels ; ne pas dupliquer leur logique de validation.
- [x] Conserver tous les champs de référence : identité, langue, état, variante, édition, grading, certificat, provenance, nature, date, observations, URL et note.
- [x] Conserver les trois actions Cardmarket : cotes + alias, cotes seules, alias seuls.
- [x] Afficher l’état de synchronisation sans masquer les erreurs ni la dernière tentative.

### T2.2 — Ajouter une configuration guidée explicite

- [ ] Proposer un parcours en trois questions : plateforme de revente, gain net minimum, ROI minimum.
- [ ] Afficher les préréglages proposés avant enregistrement et permettre de les modifier.
- [ ] Préremplir le formulaire existant ; ne jamais transformer un frais inconnu en frais nul.
- [ ] Garder le formulaire complet accessible via « Options avancées ».
- [ ] Ajouter un lien permanent vers ce parcours depuis Réglages et les états vides.
- [ ] Ne pas créer de préférence persistante nouvelle sans nécessité ; utiliser le profil de frais existant.

### T2.3 — Faire de la capture Chrome le parcours recommandé

- [x] Ajouter dans l’application un guide court d’installation et d’envoi d’une capture.
- [ ] Ajouter dans la popup un raccourci « Analyser l’annonce affichée » qui utilise l’extracteur et le pipeline d’envoi existants.
- [x] Conserver le panier, la sélection, l’envoi groupé, les exports et le presse-papier.
- [x] Ne pas créer un second format de capture : réutiliser le JSONL actuel.
- [x] Après envoi, fournir un lien vers l’annonce ou le catalogue lorsque la réponse contient l’information nécessaire.

### T2.4 — Préserver les derniers garde-fous d’extraction Chrome

Les fonctions suivantes sont **dans le périmètre obligatoire de non-régression**. Leur comportement ne doit pas être simplifié ou contourné par le nouveau raccourci :

- [x] `normalizePlainText` : conserver Unicode NFKD, suppression des accents, transformation des apostrophes en espaces et passage en minuscules.
- [x] `escapeRegExp` : conserver l’échappement de tous les métacaractères regex avant les recherches par mot entier.
- [x] `hasPotentialCardName` : conserver l’exigence d’un nom plausible, hors mots génériques, avant d’accepter un numéro isolé.
- [x] `extractCardNumber` : conserver la priorité fraction → préfixe `#`/`n°` → numéro isolé avec garde-fous alignés sur le backend.
- [x] `extractSetName` : conserver la normalisation insensible aux accents et les bornes `\b`, notamment pour « set de base », « evolutions » et la prévention des correspondances partielles sur « 151 ».
- [ ] Faire passer le raccourci de capture par ces mêmes fonctions, sans extraction parallèle allégée.
- [x] Exécuter `test_extension_extract_card_number_parsing_and_guardrails` et `test_extension_jsonl_with_isolated_number_is_valid_and_honest`.
- [x] Ajouter des tests directs pour `normalizePlainText`, `escapeRegExp`, `hasPotentialCardName` et `extractSetName` s’ils ne sont pas déjà couverts individuellement.
- [x] Couvrir au minimum : accents, apostrophes, regex littérales, mots génériques, fractions, `#`, `n°`, numéro isolé valide/refusé, `151` exact et faux positif partiel.

**Fichiers concernés :** `extension/content/content.js`, `extension/popup/`, `tests/test_chrome_extension.py`. Aucun changement de ces extracteurs n’est nécessaire pour la refonte visuelle ; toute modification doit rester un correctif testé séparément.

### T2.5 — Créer `/achats` sur les données existantes

- [x] Ajouter une route GET qui appelle `seller_repository.list_purchases()`.
- [x] Afficher carte, vendeur, date, prix payé, port, statut et notes.
- [x] Ajouter les filtres : tous, commandé, reçu, en vente, vendu.
- [x] Calculer les compteurs et coûts en centimes entiers.
- [x] Ne pas afficher de gain net réalisé : `sale_price_cents` existe depuis `0021`, mais les frais réels complets de revente ne sont pas collectés. Afficher le prix brut saisi séparément.
- [x] Conserver les liens vers l’annonce et le vendeur lorsque leurs identifiants existent.
- [x] Conserver les deux points d’enregistrement actuels : fiche annonce et fiche vendeur.
- [x] Prévoir un état vide qui explique comment enregistrer un achat.

**Base de données :** la vue réutilise les tables existantes ; `0021_purchase_sale_price.sql` porte le prix brut de vente. Toute nouvelle donnée de revente relève de Radar/P6 et demande sa propre migration.

### T2.6 — Recette de la phase 2

- [ ] Vérifier qu’un préréglage confirmé produit exactement les mêmes valeurs que le formulaire complet.
- [ ] Vérifier capture unitaire, panier, envoi groupé, JSONL et presse-papier.
- [ ] Vérifier la matrice complète des garde-fous d’extraction et l’identification prudente d’un numéro isolé.
- [ ] Vérifier les achats créés depuis les deux écrans, leurs filtres et leurs liens.
- [ ] Exécuter `docker compose run --rm app pytest tests/test_chrome_extension.py tests/test_sellers_directory_and_purchases.py tests/test_sellers.py tests/test_web.py -v`.
- [ ] Exécuter ensuite toute la suite.

**Definition of Done :** configuration plus courte mais explicite, capture recommandée sans perte d’extraction, achats consultables centralement, toutes les fonctions précédentes intactes.

## 6. Phase 3 — Harmoniser l’espace avancé et finaliser la cohérence

**Objectif :** donner le même niveau de clarté aux fonctions secondaires sans les mélanger au parcours quotidien.

### T3.1 — Créer un accueil de gestion avancée

- [x] Ajouter une page d’index avec des cartes Vendeurs, Veilles, Imports, TCGdex, Annotations, Agents et Sauvegardes.
- [x] Afficher uniquement des états réellement disponibles : erreurs d’import, jobs actifs, incidents, dernière sauvegarde.
- [x] Conserver les URL existantes ; la page d’index ne remplace pas les écrans spécialisés.
- [x] Ajouter un retour clair vers Accueil et Opportunités.

### T3.2 — Harmoniser vendeurs et veilles

- [x] Appliquer les mêmes en-têtes, filtres, états vides et panneaux que le reste de la cible.
- [x] Conserver classements, favoris, notes, achats, réputation et inventaire vendeur.
- [x] Conserver création, contrôle, pause, reprise, historique, erreurs et suppression des veilles.
- [x] Ajouter des liens contextuels vendeur ↔ annonces ↔ achats et veille ↔ agents ↔ catalogue.

### T3.3 — Harmoniser TCGdex, Cardmarket et identification

- [x] Regrouper les informations techniques sous des sections explicites sans retirer de statistiques.
- [x] Conserver sélection d’extensions, détails, files, pause/reprise, inventaires partiels et diagnostics.
- [x] Conserver les explications de correspondance approximative Cardmarket et les limites de langue/état/date.
- [x] Conserver tous les parcours de confirmation, retrait, correction de lot, recherche approfondie et diagnostic lexical.
- [x] Après enrichissement, proposer le réexamen des annonces sans déclencher d’action implicite.

### T3.4 — Isoler clairement le pilote ML

- [x] Présenter Annotations comme un espace de préparation ML, distinct de la validation quotidienne simple.
- [x] Conserver tirage stratifié, quotas, doubles lectures, opérateurs distincts, masquage des suggestions, arbitrage et exports.
- [x] Ne pas transformer une annotation pilote en décision de production sans le flux final existant.
- [x] Harmoniser les tableaux, filtres, pagination, états bloqués et messages sans changer leur logique.

### T3.5 — Harmoniser imports, agents et sauvegardes

- [x] Créer des vues cohérentes pour lots, erreurs, agents, incidents et sauvegardes.
- [x] Conserver checksums, suppressions confirmées, rapports, filtres, reprise manuelle et rafraîchissement.
- [x] Conserver création/téléchargement/restauration et tous les contrôles d’intégrité.
- [x] Tester une restauration uniquement sur une copie de données.

### T3.6 — Accessibilité, responsive et cohérence globale

- [ ] Vérifier tous les écrans principaux et avancés aux cinq largeurs de référence.
- [ ] Garantir libellés, focus, navigation clavier, fermeture Échap et cibles tactiles.
- [ ] Ne pas utiliser la couleur comme seul indicateur de statut.
- [ ] Supprimer les styles inline lorsque les composants communs suffisent.
- [x] Incrémenter les versions des assets locaux.

### T3.7 — Documentation et recette finale

- [x] Mettre à jour `README.md` avec la nouvelle navigation et le parcours capture → décision → achat.
- [x] Documenter que les fonctions avancées sont déplacées, non supprimées.
- [x] Mettre à jour `TASKING_INTEGRATION_DESIGN.md` pour désigner la nouvelle maquette cible.
- [ ] Vérifier l’inventaire complet des routes et formulaires par rapport à T1.1.
- [x] Exécuter `docker compose run --rm app pytest`.
- [ ] Vérifier `/health`, une base vide et une base remplie.

**Definition of Done :** parcours principal simple, espace avancé cohérent, documentation à jour, suite verte et couverture fonctionnelle intégrale démontrée.

## 7. Matrice finale de non-régression

| Domaine | Vérification obligatoire |
|---|---|
| Rentabilité | Mêmes montants en centimes, mêmes verdicts, frais inconnus bloquants, ROI et seuils inchangés |
| Catalogue | Recherche, filtres combinés, tri, pagination, export et réexamen |
| Identification | Identifiée, ambiguë, lot, non identifiée ; aucun lot rattaché arbitrairement |
| Validation humaine | Preuves, révisions, confirmations, retraits, double lecture et arbitrage |
| Prix de marché | Références, comparables, Cardmarket, alias, dates et limites |
| Extension | Extraction complète, garde-fous récents, panier, envoi et exports JSONL |
| Imports | Validation transactionnelle, doublons, `first_seen_at`, lots et rapports |
| Achats/vendeurs | Deux formulaires d’achat, quatre statuts, notes, favoris, réputation et historique |
| Veilles/agents | Contrôle, pause/reprise, suppression, incidents, IP et reprise manuelle |
| TCGdex | Enrichissement progressif, détails, cache, pause/reprise et diagnostics |
| Sauvegardes | Création, intégrité, téléchargement, restauration et migrations |
| Responsive/accessibilité | Clavier, focus, Échap, mobile, absences de débordement |

## 8. Ordre de livraison recommandé

1. **Phase 1** d’abord : elle apporte l’essentiel de la simplification sans nouvelle donnée.
2. **Phase 2** ensuite : elle entretient les vues `/reglages` et `/achats` déjà livrées ; l’assistant à trois questions reste à compléter.
3. **Phase 3** enfin : elle harmonise les modules avancés une fois la navigation stabilisée.

Chaque phase doit être livrée avec la suite de tests verte. Ne pas regrouper les trois phases dans une seule modification impossible à relire.
