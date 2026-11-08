# Plan d’évolution de Pokébourse — Radar et recherches ciblées

Plan initial : 1er novembre 2026. **État au 8 novembre : partiel — socle P1 livré, interface P2 et notifications absentes.**

**Revue du 8 novembre 2026 :** ordre de reprise et état transversal dans [TASKING_PROJET.md](TASKING_PROJET.md). Les cases mises à jour décrivent les critères vérifiés dans le code et les tests ; les contrôles manuels ou critères non démontrés restent ouverts.

Preuves : `0019_radar_observations.sql`, `app/radar/repository.py`, `tests/test_radar_events.py` ; achats/prix brut depuis `0021` ; rapprochement Cardmarket prudent dans `profitability.py`. Les critères non cochés restent à réaliser ou à démontrer. Le « radar » de meilleures affaires dans `/trends` ne constitue pas la page `/radar` spécifiée ici.

## 1. Résultat attendu

Reprendre les principes de CardGoM et Trakdex : un flux d’annonces à examiner, des recherches persistantes, des alertes pertinentes et un suivi jusqu’à la revente. Les données restent issues des canaux de Pokébourse ; aucune extraction des bases de ces applications n’est prévue.

Parcours cible : **configurer une recherche → repérer → vérifier les preuves → ouvrir l’annonce → enregistrer un achat → mesurer la revente**.

La première livraison doit rendre ce parcours utile dès l’étape de décision. Elle doit fonctionner avec les données locales, même lorsqu’une plateforme est indisponible.

## 2. État réel du dépôt et points de départ

| Domaine | Déjà présent | Travail à prévoir |
|---|---|---|
| Veilles | Vinted, Leboncoin, eBay, Wallapop ; mots-clés, prix, fréquence, pause, historique d’exécution | Regrouper plusieurs plateformes sous une recherche métier ; ajouter des critères locaux |
| Identification | Catalogue TCGdex, statuts, preuves et confirmation humaine | Exposer ces informations dans le radar sans confondre identité et qualité du prix |
| Rentabilité | Frais, montants en centimes, ROI en points de base, références et comparables | Décrire la portée réelle de chaque référence et définir l’éligibilité aux alertes |
| Cardmarket | Guide quotidien, catalogue produits, alias multilingues | Réduire les rapprochements par nom seul ; conserver les identifiants utiles et la provenance |
| Interface | Dashboard, catalogue, fiche annonce, veilles | Ajouter un radar compact, des décisions persistantes et un centre de notifications |
| Achats | `purchases`, `/achats`, statuts et prix brut de vente facultatif (`0021`), parseur monétaire exact | Ajouter date/frais réels, transitions historisées, estimation figée et attribution |

Constats réconciliés au 8 novembre 2026 :

- `listing_observations`, `listing_events` et `listing_decisions` existent. Les imports/collecteurs enregistrent les états économiques nouveaux dans la transaction de l'annonce ; réutiliser ce socle, ne pas recréer P1.
- Les prix d'achat des achats vendus sont exclus de `find_price_comparables()`. Le prix brut de vente peut être saisi depuis `0021`, mais cette fonction ne l'exploite pas encore comme preuve de transaction.
- Le repli Cardmarket financier exige maintenant une carte identifiée et un produit unique explicitement lié ; un alias ou un minimum parmi des homonymes ne suffit plus. Le mapping complet, sa provenance et l'historique quotidien restent P4 / Identification/T17.
- Les formulaires d'achat utilisent déjà `parse_euros_to_cents()` ; la conversion flottante ancienne n'est plus à corriger dans ce périmètre. TRK-101 concerne les filtres des collecteurs, distincts des achats.
- `app/cardmarket/guide.py` et la langue de libellé ne prouvent pas à eux seuls la couverture langue/état d'un prix. Conserver les limites et qualifier les correspondances.
- Le schéma courant va jusqu'à `0026`, pas `0018` ; les achats et la navigation sont déjà intégrés. Les nouveaux champs demandent une nouvelle migration après inventaire.
- Les alertes financières P4/P5 doivent réutiliser le contrôle d'admissibilité d'Identification/T09 et les contrats T15–T18 ; ne pas développer deux politiques contradictoires. La page P2 reste indépendante des expérimentations visuelles T11.

## 3. Décisions de périmètre

- Conserver FastAPI, Jinja2, SQLite et JavaScript local. Aucun nouveau framework, bundler ou service cloud.
- Ajouter `/radar` sans remplacer `/`, `/catalog`, `/profitability` ni les routes existantes.
- Conserver les veilles unitaires et leur limite de concurrence par plateforme. Une recherche métier peut regrouper plusieurs veilles.
- Appliquer les critères fins localement si le connecteur ne sait pas les transmettre. L’interface distingue les critères de recherche distante des filtres locaux.
- Ne pas réduire les délais de collecte dans ce chantier ; conserver les suspensions, limites et solutions de repli documentées dans `SOURCES.md`.
- Commencer par les notifications internes, puis les notifications navigateur avec consentement explicite. Leur consultation n’impose aucun canal externe.
- Le scan photo/OCR relève désormais du chantier actif Identification/T06–T08 ; les applications mobiles, le social et le multi-TCG restent hors de ce plan radar.
- Les lots, le scellé et les cartes gradées restent consultables, mais n’obtiennent pas une cote de carte brute unitaire par défaut. Ils ne sont éligibles à une alerte financière que si une référence compatible existe.

## 4. Règles produit communes

### Identité, prix et fraîcheur

Afficher séparément :

1. **Identité** : confirmée, identifiée automatiquement, ambiguë, inconnue ou lot.
2. **Qualité de la cote** : correspondance exacte ou partielle, type de prix, dimensions couvertes et manquantes, date et effectif lorsqu’il est connu.
3. **Intérêt économique** : coût total, revente estimée, gain net et ROI avec les règles existantes.

Une cote agrégée Cardmarket peut concerner le bon produit tout en restant non filtrée par langue et état. Le rattachement exact ne suffit donc pas à qualifier le prix de « FR NM ».

Une donnée inconnue reste inconnue. Aucun état, frais, volume de ventes ou délai de revente ne sera inventé. Un nombre de produits correspondants n’est pas un nombre de ventes.

Pour les alertes prioritaires, exiger une identité non ambiguë, une référence compatible et suffisamment récente, tous les frais nécessaires connus et les seuils de gain/ROI atteints. Une référence agrégée ou approximative reste visible dans « À vérifier » ; elle ne devient pas une alerte prioritaire par son seul montant.

La date « détectée » utilise `first_seen_at`, avec repli explicite sur `imported_at` pour les imports historiques. La date de publication et la dernière observation sont affichées séparément. Une annonce absente d’une recherche n’est pas automatiquement vendue.

Valeurs initiales proposées, configurables et couvertes par les tests : référence datant de 48 h maximum et annonce observée depuis moins de 24 h pour une alerte prioritaire. Une date absente ne satisfait pas ces critères. Ces seuils sont des choix produit à ajuster à l’usage.

### Classement

Pour la première version, trier par gain net, ROI ou date de détection, avec un identifiant comme dernier critère stable. Le tri financier place les valeurs inconnues en dernier.

Conserver deux informations distinctes : intérêt économique et confiance de l’analyse. Reporter le score global sur 100 jusqu’à disposer d’exemples annotés et de critères de qualité évalués. Une éventuelle note devra être versionnée, explicable et ne jamais contourner les conditions d’éligibilité.

### Décisions utilisateur

État local d’une annonce : `nouvelle`, `a_examiner` ou `ecartee`, avec date et motif facultatif. Un achat lié détermine séparément l’état « achetée » ; ne pas dupliquer le cycle de `purchases`.

Écarter masque l’annonce du flux par défaut et des nouvelles alertes ; l’action est réversible. Une ré-ingestion ne réinitialise jamais cette décision. Ouvrir une fiche ne marque pas automatiquement une annonce comme examinée.

## 5. Livraisons et ordre d’exécution

### Livraison 1 — Un radar utilisable

#### P0 — Établir la référence et corriger les preuves de prix

- [x] Relever les changements en cours, les migrations présentes et les tests initiaux, sans modifier les données utilisateur.
- [x] Exécuter la suite Docker avant les changements fonctionnels pour identifier les éventuels échecs préexistants.
- [x] Retirer les prix d’achat des preuves présentées comme reventes ; un ancien achat `vendu` sans prix de vente reste un achat d’un objet revendu, sans montant de vente connu.
- [x] Produire `reference_quality` dans le moteur existant : nature, date/effectif, dimensions manquantes ; la qualification demeure partielle.
- [ ] Compléter la politique d’admissibilité et son usage par les alertes avec Identification/T09/T17 ; la présence de métadonnées ne vaut pas qualification complète.
- [ ] Documenter la portée agrégée des prix Cardmarket, les correspondances approximatives et les dates inconnues.

**Fichiers principaux :** `app/profitability.py`, `app/templates/catalog_detail.html`, `tests/test_profitability.py`, `tests/test_web.py`.

**Validation :** aucune ligne de preuve de revente ne reprend `price_paid_cents` ; les estimations partielles sont identifiées comme telles ; les tests existants de calcul restent valides.

#### P1 — États de décision et observations d’annonces

- [x] Créer les tables de décision, d’observations et d’événements dans de nouvelles migrations.
- [x] Enregistrer une première observation réelle puis les changements de prix, de port ou de disponibilité connue. Un passage inchangé ne crée pas de nouvelle observation économique.
- [x] Conserver `last_seen_at` pour les passages inchangés et préserver `first_seen_at`.
- [x] Vérifier la conformité de la ré-ingestion à la règle 5 d’`AGENTS.md` : mises à jour limitées à `last_seen_at`, `price_cents`, `shipping_cents`, `url` et `raw_data`. L’actualisation des preuves et les corrections d’identité restent des opérations distinctes et traçables ; ne pas étendre implicitement les champs écrasés.
- [x] Écrire observation et événement dans la même transaction que la mise à jour de l’annonce. Un rollback ne laisse aucun événement orphelin.
- [x] Brancher les collecteurs, la capture par extension et les imports JSONL sur ces primitives communes, en conservant leurs contrats de déduplication et de rejet actuels.
- [x] Pour les annonces historiques, créer au plus un point initial explicitement étiqueté comme état connu lors de la migration ; ne pas reconstruire un historique fictif et ne pas générer d’alerte rétroactive.
- [x] Conserver les événements économiques indépendants des révisions d’identité : une correction d’identification ne constitue pas une baisse de prix.

**Fichiers principaux :** nouveau domaine `app/radar/`, `app/collectors/service.py`, `app/catalog.py`, migrations et tests d’ingestion.

**Validation :** répétition d’une capture sans variation = aucune nouvelle variation ; une baisse réelle = un événement ; décisions et première détection survivent aux ré-ingestions et au redémarrage.

#### P2 — Page Radar et actions rapides

- [ ] Ajouter `/radar`, son entrée de navigation et un lien depuis le dashboard.
- [ ] Afficher photo d’annonce lorsqu’elle est disponible, identité, plateforme, coût total, estimation, gain net, ROI, confiance et dates utiles. Prévoir un visuel local de repli ; distinguer une image de référence d’une photo de l’annonce.
- [ ] Ajouter les vues « Nouvelles », « À examiner », « Baisses de prix », « Écartées » et les filtres plateforme, langue, état, type de produit, budget total, marge et qualité de correspondance.
- [ ] Définir « Nouvelles » comme les annonces sans décision ni achat lié ; « Baisses de prix » exige un événement de baisse réellement observé.
- [ ] Ajouter les actions examiner, écarter, rétablir, ouvrir la fiche et ouvrir l’annonce source.
- [ ] Conserver les filtres et la page après une action ; autoriser uniquement des retours vers des chemins locaux validés.
- [ ] Appliquer filtres et tri à l’ensemble des résultats avant pagination. Les compteurs et l’export utilisent les mêmes critères.
- [ ] Ajouter l’export du radar sans modifier le contrat de `/catalog/export.csv`.
- [ ] Prévoir des formulaires utilisables sans JavaScript. Un rafraîchissement léger peut signaler de nouveaux résultats sans déplacer une ligne sous le curseur.

**Fichiers principaux :** `app/radar/models.py`, `repository.py`, `service.py`, `app/web.py`, nouveau `app/templates/radar.html`, `base.html`, `dashboard.html`, `app/static/style.css`, `forms.js`.

**Validation :** mêmes données financières que la fiche ; filtres combinés et pagination corrects ; aucune valeur inconnue transformée en zéro ; parcours clavier et mobile utilisable à 390 et 320 px.

#### P3 — Recherches métier sur plusieurs plateformes

- [ ] Ajouter une recherche nommée qui regroupe des veilles unitaires sans casser la CLI ni les anciennes veilles.
- [ ] Ajouter les critères locaux : carte ou extension ciblée, langues, états, mots exclus, type de produit, budget total, gain minimal et ROI minimal. Conserver les seuils en centimes et points de base.
- [ ] Distinguer le plafond de prix brut transmis à la plateforme du plafond de coût total appliqué localement.
- [ ] Pour les critères explicites, traiter une langue ou un état inconnu comme « non confirmé », sans le considérer comme conforme. Afficher les candidats à vérifier à part.
- [ ] Sauvegarder les règles, proposer modification/pause/reprise et afficher les résultats par recherche.
- [ ] Tracer les annonces observées par chaque veille pour distinguer les annonces effectivement remontées par la recherche des correspondances trouvées dans le stock local.
- [ ] Associer aux recherches les futurs événements des imports et captures compatibles avec leurs critères locaux ; ne pas les attribuer fictivement à une exécution de veille.
- [ ] Réutiliser les verrous et suspensions par plateforme. Supprimer une recherche ne supprime pas les annonces ou les achats ; supprimer une veille conserve la provenance nécessaire à l’historique.

**Fichiers principaux :** `app/monitoring/models.py`, `repository.py`, `service.py`, `scheduler.py`, `app/radar/`, `app/web.py`, `app/templates/watches.html`, tests de veilles et CLI.

**Validation :** une recherche crée les veilles attendues ; les filtres fins sont respectés ; les anciennes commandes fonctionnent ; une plateforme en échec ne masque pas les résultats des autres.

**Sortie de livraison 1 :** on peut configurer une recherche, consulter les annonces pertinentes, vérifier les preuves, décider et retrouver sa sélection après redémarrage. Aucune notification prioritaire automatique à ce stade.

### Livraison 2 — Des alertes fiables

#### P4 — Correspondances de marché et historique exploitable

- [ ] Conserver les identifiants produit/extension fournis par Cardmarket et la provenance de chaque correspondance.
- [ ] Prévoir une correspondance vérifiable entre carte TCGdex et produit Cardmarket, avec source de preuve, date et statut. Une correspondance manuelle validée peut compléter les données publiques.
- [ ] Ne pas supposer qu’une API fermée ou que les fichiers publics fournissent toutes les données nécessaires. Sans preuve suffisante, conserver le statut partiel et permettre la saisie d’une référence compatible.
- [ ] Séparer langue du nom, couverture linguistique du prix, état et variante ; ne pas convertir l’actuel `en` en certitude sur les exemplaires vendus.
- [ ] Historiser les valeurs quotidiennes effectivement reçues, avec la date du fournisseur et la date de récupération. Recharger le même guide ne crée pas un nouveau jour de marché.
- [ ] Afficher séparément l’évolution du prix demandé et celle des références ; aucune courbe avant le début réel de l’historisation. Les moyennes 7/30 jours ne reconstituent pas des points quotidiens passés.
- [ ] Rendre la politique de fraîcheur et l’éligibilité aux alertes testables avec une horloge injectée.

**Fichiers principaux :** `app/cardmarket/guide.py`, `app/cardmarket/service.py`, `app/cardmarket/daily.py`, `app/profitability.py`, `app/radar/`, fiche annonce et tests Cardmarket.

**Validation :** deux cartes homonymes d’extensions distinctes ne partagent pas une cote dite exacte ; absence de mapping = incertitude visible ; une synchronisation répétée est idempotente ; carte gradée et carte brute restent distinctes.

#### P5 — Centre de notifications puis navigateur

- [ ] Ajouter un centre local avec notifications non lues/lues, annonce, recherche, motif et détail financier au moment du déclenchement.
- [ ] Déclencher sur une nouvelle annonce éligible ou une baisse significative après une précédente alerte. Une simple synchronisation de cote ou modification des règles ne provoque pas une rafale de notifications sur le stock historique.
- [ ] À l’activation d’une recherche, poser un point de départ ; les annonces déjà présentes restent consultables sans notification rétroactive par défaut.
- [ ] Proposition initiale pour une nouvelle alerte de baisse : coût total inférieur d’au moins 500 centimes **et** 500 bps au coût total lors de la dernière alerte. Ces seuils sont modifiables. Coût inconnu ou devise différente = absence de comparaison financière.
- [ ] Dédupliquer par annonce, événement et canal, en regroupant les recherches correspondantes. Un prix déjà alerté puis remonté puis revenu au même niveau ne produit pas une nouvelle alerte de baisse.
- [ ] Utiliser une file persistante traitée par le worker après ingestion ; prise en charge atomique, reprise après arrêt et nombre de tentatives borné. Une panne de notification n’annule pas une collecte réussie.
- [ ] Réévaluer l’éligibilité juste avant émission ; conserver la version des règles, des preuves et du profil de frais. Une annonce écartée ou achetée n’émet plus d’alerte.
- [ ] Ajouter ensuite les notifications navigateur après une action explicite de l’utilisateur. Refus ou absence de support = centre interne fonctionnel.
- [ ] Limiter les doublons entre onglets par prise en charge locale persistante ; documenter les rares limites de livraison après un crash, sans promettre un affichage navigateur « exactement une fois ».
- [ ] Afficher clairement que l’affichage navigateur dépend d’une page locale ouverte et des permissions du système. Le worker conserve les notifications lorsque le navigateur est fermé ; aucun push mobile à distance n’est promis.

**Fichiers principaux :** nouveau `app/notifications/`, `app/monitoring/scheduler.py`, `app/radar/`, `app/web.py`, `base.html`, nouveau template de notifications et JavaScript local.

**Validation :** mêmes résultats après redémarrage ; absence de spam lors de passages inchangés, synchronisations, règles modifiées ou doublons entre recherches ; navigateur refusé/fermé sans perte du centre interne.

**Sortie de livraison 2 :** les alertes sont justifiées, dédupliquées, persistantes et fondées sur des données assez précises. Les annonces incertaines restent accessibles dans le radar.

### Livraison 3 — Mesurer ce que le radar rapporte

#### P6 — Achats, reventes et attribution

- [ ] Réutiliser `/catalog/{item_id}/purchase` et `purchases`, avec protection contre un double envoi du formulaire. Une seconde acquisition volontaire doit rester possible et explicite.
- [x] Remplacer les conversions monétaires par `float` dans les formulaires d’achat concernés par le parseur exact existant, avec arrondi demi-supérieur.
- [ ] Ajouter un enregistrement de revente par achat : prix de vente brut, frais réels détaillés, port facturé à l’acheteur si applicable, port payé, devise et date effective. Distinguer frais nuls confirmés et frais inconnus.
- [ ] Historiser les transitions et corrections ; conserver la possibilité de marquer un achat vendu sans montant renseigné, avec résultat financier inconnu.
- [ ] Figer à l’achat l’estimation, sa provenance et le profil de frais afin qu’une cote future ne réécrive pas la prévision d’origine.
- [ ] Définir le gain réalisé comme les recettes effectives moins les dépenses réelles d’achat et de revente, sans compter deux fois le port. Comparaison en même devise uniquement.
- [ ] Réintroduire comme preuves les seules reventes dont le prix est réellement saisi et dont l’identité est compatible ; afficher la date de vente plutôt que celle de l’achat.
- [ ] Attribuer les acquisitions aux recherches ayant mené à la décision. Une acquisition et son gain ne sont comptés qu’une fois dans les totaux globaux ; afficher les contributions multiples sans les additionner.
- [ ] Afficher capital immobilisé connu, nombre d’achats, délai achat/vente et écarts entre prévisions et réalisations. Une statistique sans données affiche « indisponible ».

**Fichiers principaux :** `app/sellers/models.py`, `repository.py`, `service.py`, `app/profitability.py`, `app/web.py`, templates achats/vendeurs/dashboard et tests achats/rentabilité.

**Validation :** aucun prix d’achat utilisé comme prix de vente ; montants exacts, date de vente correcte, prévision stable après mise à jour des cotes, achats historiques conservés sans gains inventés.

## 6. Schéma cible à préciser dans les migrations

Ces noms sont des propositions de travail ; finaliser les colonnes et contraintes lors de chaque lot.

| Données | Rôle et contraintes principales |
|---|---|
| `listing_decisions` | Une décision courante par annonce, état contrôlé, motif, date ; achat dérivé de `purchases` |
| `listing_observations` | Prix, port nullable, devise, dates et origine ; points initiaux distingués des variations réellement observées |
| `listing_events` | Création/baisse/changement économique, observation liée, séquence stable ; consommation idempotente |
| `radar_searches` | Critères validés et versionnés, seuils, état et point de départ des alertes |
| `radar_search_watches` | Lien vers les veilles existantes ; gestion des veilles autonomes et suppression sans perte du catalogue |
| `watch_listing_observations` | Provenance d’une annonce observée dans une exécution, sans doublon ; historique utile conservé après suppression d’une veille |
| `cardmarket_card_mappings` | Lien prouvé TCGdex/produit, dimensions couvertes, provenance et état de validation |
| `cardmarket_price_history` | Un snapshot par produit/date fournisseur/type de prix ; pas de réécriture d’un passé inconnu |
| `notifications` et file de traitement | Événement, canal, état, tentatives, dates et clé unique ; rattachements multiples aux recherches |
| Reventes et prévisions d’achat | Lien à `purchases`, recettes/frais réels, date de vente et snapshot de prévision |

Pour chaque lot : nouvelle migration séquentielle, `BEGIN IMMEDIATE;`, insertion du nom dans `schema_migrations`, puis `COMMIT;`. Au relevé initial, la dernière migration présente est `0018` ; vérifier à nouveau avant d’attribuer le prochain numéro. Ne modifier aucune migration déjà appliquée.

Les anciennes lignes sont préservées ; les informations historiquement absentes restent nulles. Définir les clés étrangères et comportements de suppression avec les parcours existants de suppression d’imports/veilles. Conserver les achats même si l’annonce d’origine disparaît.

## 7. Architecture et exploitation

- Le domaine radar compose l’identification et la rentabilité ; il ne recopie pas leurs algorithmes dans les routes ou les templates.
- Les routes GET lisent les données ; décisions, prises en charge et changements d’état passent par des actions explicites validées. Réutiliser les protections des formulaires existants et les renforcer sur les nouvelles mutations locales si nécessaire.
- Les écritures d’annonce, observation et événement sont courtes et atomiques. Aucun réseau n’est effectué sous transaction SQLite.
- Identifier les points de commit existants, notamment dans le repository achats, pour éviter les transactions imbriquées validées prématurément.
- Les filtres et tris utilisent des listes blanches et des requêtes paramétrées. Ajouter les index après vérification des requêtes réelles.
- Éviter le chargement intégral des annonces à chaque rafraîchissement et les appels SQL par ligne. Tester sur un jeu local représentatif, par exemple 10 000 annonces ; mesurer les délais avant de fixer un objectif de performance sur la machine cible.
- Conserver WAL, `busy_timeout`, clés étrangères, fonctionnement hors ligne et sauvegarde SQLite existante. Les nouvelles tables font partie des sauvegardes ordinaires.
- Prévoir une rétention documentée pour observations et notifications ; ne pas supprimer l’historique financier des achats lors d’un nettoyage.
- Aucune donnée vendeur supplémentaire n’est nécessaire à ces phases. Conserver la liste blanche et ne pas transformer la réputation du vendeur en garantie d’authenticité.

## 8. Vérification et critères de fin

### Tests ciblés par lot

| Lots | Suites existantes à exécuter ou compléter | Nouvelles suites proposées |
|---|---|---|
| P0 | `tests/test_profitability.py`, `tests/test_web.py` | Cas distinguant achat et revente réelle |
| P1 | `tests/test_watch_ingestion.py`, `tests/test_imports.py`, `tests/test_chrome_extension.py`, `tests/test_migrations.py` | `tests/test_radar_events.py` |
| P2 | `tests/test_web.py`, `tests/test_catalog_export.py` | `tests/test_radar.py`, `tests/test_radar_web.py` |
| P3 | `tests/test_monitoring_service.py`, `tests/test_watches_web.py`, `tests/test_watch_cli.py`, `tests/test_supervision.py` | `tests/test_radar_searches.py` |
| P4 | Tests `test_cardmarket*`, `tests/test_profitability.py`, `tests/test_identification.py` | Mapping, couverture et historique dans les suites concernées |
| P5 | `tests/test_monitoring_service.py`, `tests/test_web.py` | `tests/test_notifications.py` |
| P6 | `tests/test_sellers_directory_and_purchases.py`, `tests/test_sellers.py`, `tests/test_profitability.py` | Cas de revente, frais réels et attribution |

Exécuter toutes les commandes dans Docker. Aucun test ne contacte réellement les marketplaces, Cardmarket ou TCGdex ; utiliser mocks, fixtures et horloge contrôlée.

```bash
docker compose run --rm app pytest tests/test_profitability.py tests/test_web.py
docker compose run --rm app pytest tests/test_migrations.py
docker compose run --rm app pytest
```

### Recette de chaque livraison

- [ ] Base vide, base historique migrée et données locales représentatives.
- [ ] Recherche, filtres combinés, tri global avant pagination, export et navigation de retour.
- [ ] Décisions persistantes et réversibles, sans achat accidentel ni perte d’annonce.
- [ ] Annonce ambiguë, lot, scellé, carte gradée, port inconnu, devise incompatible et référence périmée.
- [ ] Ré-ingestion et reprise après arrêt sans doublon ; `first_seen_at` inchangé.
- [ ] Plateforme suspendue ou inaccessible avec affichage honnête de la dernière collecte.
- [ ] Notifications désactivées, permissions refusées, onglets multiples et navigateur fermé pour la livraison 2.
- [ ] Responsive desktop/mobile, navigation clavier, focus visible, images absentes et erreurs de formulaire.
- [ ] Sauvegarde/restauration testée uniquement sur une copie de base, avec conservation des nouvelles tables.
- [ ] Documentation utilisateur mise à jour dans `README.md`, historique dans `SUIVI.md` et `SOURCES.md` uniquement si les méthodes d’accès changent.
- [ ] Suite Docker complète verte, sans nouvelle dépendance externe non sollicitée.

## 9. Ordre de travail recommandé

**P0 → P1 → P2 → P3 → P4 → P5 → P6.**

Premier chantier radar restant : réutiliser les décisions/événements déjà posés, compléter P0 sur la qualité des cotes, puis livrer `/radar` (P2) et les recherches groupées (P3). Le premier jalon utilisable est la livraison 1 ; les notifications prioritaires dépendent de la fiabilité apportée par P4.

Le score global sur 100 reste conditionnel à des mesures. La reconnaissance photo possède désormais son propre plan Identification/T06–T11 ; elle n’attend pas la livraison du radar.
