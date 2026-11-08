# Pokébourse — Recherche approfondie et confirmation des cartes

Plan initial : **1er novembre 2026**. **Socle réalisé et testé sur les annonces enregistrées** ; le chiffre de 311 tests appartient à la livraison historique et ne décrit pas la suite courante.

**Revue du 8 novembre 2026 :** ordre de reprise et état transversal dans [TASKING_PROJET.md](TASKING_PROJET.md). Les cases mises à jour décrivent les critères vérifiés dans le code et les tests ; les contrôles manuels ou critères non démontrés restent ouverts.

Recherche/confirmation sur fiche et file worker sont présentes ; la confirmation transitoire avant ajout et le nouveau raccordement OCR relèvent désormais d’Identification/T08.2/T09. Les limites anciennes ci-dessous décrivent le périmètre initial, pas toutes les capacités actuelles.

## 1. Résultat attendu

Quand l’extension ou un collecteur importe une carte sans correspondance, Pokébourse doit pouvoir compléter son référentiel, relancer la recherche, montrer les candidats et permettre à l’utilisateur de confirmer la bonne carte. La confirmation doit résister aux prochaines collectes et aux réexamens automatiques.

Exemple de parcours : une carte absente des données locales est importée ; l’annonce est conservée immédiatement ; une recherche TCGdex est mise en file ; les références trouvées sont enregistrées ; l’utilisateur voit les candidats avec leur photo, leur extension et leur numéro, puis confirme une carte si les preuves permettent de la reconnaître.

« Forcer la recherche » déclenche une recherche plus complète. Cela n’autorise jamais à rattacher automatiquement une carte sur un simple nom, ni à choisir une carte unitaire pour un lot.

**Deux problèmes distincts doivent être visibles :**

| Situation | Message et action |
|---|---|
| Carte non identifiée | « Carte à identifier » → rechercher / confirmer |
| Carte identifiée, prix de revente absent | « Carte identifiée · cote non renseignée » → renseigner une cote |
| Plusieurs références plausibles | « Plusieurs cartes possibles » → comparer les candidats |
| Requête TCGdex en échec | « Recherche en ligne indisponible » → conserver les résultats locaux et réessayer |

Trouver une référence TCGdex ne fournit pas à lui seul une cote de revente.

## 2. Constats de départ historiques — avant implémentation

- `app/tcgdex/data/seed_data.py` fournit **15 cartes**. Le volume réel installé doit être mesuré : il ne se déduit pas de ce seed.
- `CardMatcher.identify()` consulte uniquement SQLite ; il n’effectue aucune recherche distante.
- `TcgdexCache.sync_set()` existe, mais aucun parcours applicatif de synchronisation ne l’appelle actuellement.
- « Réexaminer l’identification » relance le matcher sur le même cache local.
- `find_cards()` normalise la requête sans appliquer la même normalisation aux valeurs SQL ; les accents peuvent empêcher une correspondance.
- Le repli par nom est limité à 20 candidats, ordonnés par identifiant interne avant scoring.
- Le détecteur contient des listes figées de noms et d’extensions. Le client distant cible le français ; le schéma actuel n’isole pas les langues du référentiel.
- L’ingestion des collecteurs et `reidentify_catalog_item()` réécrivent l’identification. Une confirmation humaine nécessite une résolution commune à ces chemins.
- L’import de l’extension passe par `POST /imports` avec une réponse JSON. Celle-ci expose déjà `identification_status`, `identification_reason` et `has_reference_price` ; le popup met surtout en avant la cote.
- Une migration locale `0011_create_cardmarket_prices.sql` et des travaux Cardmarket sont déjà présents. Ne pas les écraser. Le prochain numéro semble être **0012**, à vérifier au moment de coder.

Les défauts de recherche, normalisation et priorité humaine ci-dessus ont été traités par les tâches cochées T1–T4. Le schéma courant va jusqu’à `0026`, les localisations sont isolées depuis `0024`, et la synchronisation progressive est décrite dans [docs/TCGDEX_SYNC.md](docs/TCGDEX_SYNC.md). Ne pas réutiliser le numéro `0012` comme prochaine migration.

## 3. Périmètre et règles de conception

### Version livrable

- Recherche locale corrigée, structurée et paginée.
- Recherche distante ciblée et synchronisation d’une extension à la demande.
- Enrichissement automatique des annonces unitaires non résolues, activable par configuration.
- File SQLite persistante traitée par le worker existant.
- Comparaison des candidats, saisie d’un identifiant TCGdex et confirmation manuelle révisable.
- Protection des décisions contre la réingestion et les résultats asynchrones obsolètes.
- Parcours cohérent entre fiche web, extension et collecteurs.

### Contraintes

1. Respecter `AGENTS.md`, `SOURCES.md`, `TASKING_INTEGRATION_DESIGN.md` et les principes de `MACHINE_LEARNING_DESIGN.md` concernant les preuves et les corrections humaines.
2. Conserver Python 3.12, FastAPI, Jinja, Vanilla JS, SQLite WAL et Docker. Pas de nouvelle dépendance requise pour cette version.
3. Aucun réseau dans le matcher ni dans les transactions d’ingestion. Un échec d’enrichissement ne doit jamais annuler un import valide.
4. Préserver les quatre statuts publics `identified`, `ambiguous`, `unidentified`, `lot`. Stocker séparément l’état technique de recherche et la provenance de la décision.
5. Conserver les montants en centimes et les taux en points de base. Ne pas changer les formules de rentabilité.
6. Préserver `first_seen_at`, les preuves originales et les confirmations applicables. Les champs de recherche corrigés par l’utilisateur ne remplacent pas le titre d’origine.
7. Interdire tout rattachement unitaire tant que l’annonce est classée comme lot. Un faux positif de détection doit être corrigé explicitement et historisé avant confirmation.
8. Une confirmation établit l’identité choisie ; elle ne certifie ni authenticité, ni état, ni variante, ni langue, ni prix. Ne pas lui attribuer artificiellement un score automatique de 100 %.
9. Le fonctionnement local reste disponible sans Internet. Aucun appel TCGdex direct depuis l’extension ; les requêtes passent par le backend.
10. Ne pas transmettre titres bruts, descriptions ou informations vendeurs à TCGdex : seulement les critères de carte utiles.

### Limites de la livraison initiale

Pas d’OCR, d’embeddings, de LightGBM, de recherche web générale ni d’import massif de tout TCGdex. La première version complète le référentiel français. Une langue étrangère explicite reste signalée et ne doit pas être transformée silencieusement en version française. Les alias servent à retrouver des candidats, sans certifier leur langue.

Depuis Identification/T05, le stockage de localisations et la file par locale existent (`0024`–`0026`). Cela ne qualifie pas encore l’identification et la rentabilité complètes dans toutes ces langues ; vérifier couverture et portée avant activation. Ne pas écraser une référence française en important une autre langue sous le même `tcgdex_id`.

## 4. Architecture et contrats proposés

### Traitement commun

1. Capturer les données observées et calculer une empreinte des preuves d’identité.
2. Chercher localement ; appliquer une éventuelle décision humaine encore valable.
3. Si la carte unitaire reste non résolue et que l’enrichissement est activé, créer une demande persistante dédupliquée.
4. Dans le worker : réserver la demande, fermer la transaction, interroger TCGdex, valider les réponses, enregistrer le référentiel en transactions courtes.
5. Relancer le matcher local, puis vérifier l’empreinte et la révision de décision avant d’appliquer le résultat. Une ancienne recherche ne doit pas écraser une confirmation plus récente.

Créer un petit service d’orchestration dans `app/identification/`, utilisé par l’import de l’extension, les collecteurs et le réexamen web. Garder extraction, recherche de candidats, décision automatique et résolution humaine distinctes dans ce service.

### Données persistantes minimales

Le développeur doit préciser les tables et leurs contraintes avant de créer la migration. Couvrir les besoins suivants sans déployer toute la plateforme d’annotation ML :

| Donnée | Contenu et contraintes |
|---|---|
| Preuves d’identité | Annonce, titre/description explicitement observés, attributs structurés fournis, référence d’image disponible, empreinte et date. Ne pas recopier tout le JSON vendeur. Les anciennes preuves incomplètes doivent être signalées. |
| Décisions humaines | Annonce, empreinte des preuves, action confirmer/retirer/reclasser, référence choisie, identifiant TCGdex, date, opérateur local, motif et révision précédente. Historique en ajout seulement. |
| Recherches | Critères normalisés, langue, version de stratégie, statut, tentatives, prochaine tentative, réservation avec expiration, résultats, erreur technique et dates. |
| Association recherche–annonces | Relier une recherche mutualisée aux annonces et empreintes concernées ; éviter les requêtes réseau répétées pour la même carte. |
| Index de recherche | Noms et extensions normalisés de façon identique à l’écriture et à la lecture ; reprise des références existantes. |

Prévoir les clés étrangères et le comportement à la suppression d’un import. Aucune table ajoutée ne doit empêcher les suppressions existantes ni laisser une file réappliquer une décision à une annonce supprimée. La sauvegarde/restauration SQLite doit emporter ces données.

### Validité d’une confirmation

- Priorité : confirmation humaine applicable → décision automatique admissible → abstention.
- Une modification de prix, port, URL ou date de passage ne retire pas une confirmation.
- Une modification des preuves d’identité ou une nouvelle détection de lot suspend son application et affiche « Confirmation à revoir » ; son historique est conservé.
- Définir une empreinte stable des seules preuves d’identité, avec normalisation documentée. Un champ manquant lors d’une capture partielle ne doit pas effacer automatiquement une preuve auparavant disponible ; un conflit explicite demande révision.
- L’enregistrement de la confirmation vérifie à nouveau l’empreinte et la révision attendues dans une transaction courte. En cas de conflit, demander de recharger les preuves.
- Le retrait est une nouvelle décision ; il réactive la résolution automatique sans ressusciter une ancienne confirmation.

### Routes proposées, à adapter aux conventions existantes

| Action | Contrat |
|---|---|
| Recherche locale / lecture des candidats | `GET /catalog/{id}/identification` avec critères et pagination ; aucune écriture ni requête distante |
| Recherche en ligne | `POST /catalog/{id}/identification/search` : valider les critères, mettre en file et retourner un identifiant de recherche |
| Suivi | `GET /catalog/{id}/identification/search/{search_id}` : état et résultats, en vérifiant l’association à l’annonce |
| Confirmation | `POST /catalog/{id}/identification/confirm` : référence locale, empreinte et révision attendues |
| Retrait | `POST /catalog/{id}/identification/revoke` : nouvelle décision historisée |
| Correction du classement lot | Action POST dédiée, motif explicite et contrôle de concurrence |

Le bouton « Recherche approfondie » peut réessayer après un résultat vide récent, avec délai minimal et déduplication des demandes déjà actives. Il ne contourne ni un 429, ni une réservation en cours, ni la limite de tentatives. Sans worker, montrer « En attente du worker », sans annoncer une recherche terminée.

## 5. Tâches ordonnées

### T0 — État initial et cas de reproduction — P0

- [x] Lire les documents cités et relever les modifications déjà présentes avec `git status`.
- [x] Inventorier les entrées : collecteurs, import extension, import manuel/CLI et réexamen web.
- [x] Mesurer, sur une copie si nécessaire, le nombre de références locales et les extensions présentes ; ne pas lancer de migration sur les données réelles pour ce diagnostic.
- [x] Constituer des fixtures anonymisées : carte absente du seed, accents, nom inhabituel, numéro promotionnel, suffixe ex/VMAX, titre pauvre, langue étrangère et lot.
- [x] Exécuter la suite initiale dans Docker ; noter les échecs préexistants, notamment un éventuel décalage entre migration `0011` et attentes des tests.

**Validation :** diagnostic reproductible, distinction identification/cote confirmée, état initial documenté.

### T1 — Corriger la recherche locale — P0, après T0

- [x] Unifier la normalisation Unicode, casse, accents, espaces et ponctuation des requêtes et des références.
- [x] Dériver les noms et extensions du catalogue local ; maintenir seulement les alias explicites nécessaires. Préserver les suffixes distinctifs et les noms de dresseurs ou objets.
- [x] Comparer les numéros selon leur structure : `004` et `4` peuvent être équivalents ; `4`, `14` et `104` ne le sont pas. Préserver les préfixes alphanumériques.
- [x] Exploiter le couple numéro/extension et le total d’une fraction lorsqu’il est disponible et compatible ; ne pas traiter une extension absente comme une contradiction.
- [x] Supprimer la troncature arbitraire avant classement. Pour la recherche libre, proposer pagination et ordre stable ; pour le matcher, récupérer un ensemble borné mais justifié par les critères, avec élargissement explicite.
- [x] Proposer des candidats proches si utile, sans les accepter sur la seule similarité. Une contradiction explicite fiable sur extension, numéro, suffixe ou langue interdit l’acceptation automatique.
- [x] Revoir les ex æquo : plusieurs références plausibles restent ambiguës, y compris lorsque leur score est élevé. Ne pas baisser les seuils pour augmenter artificiellement le taux d’identification.

**Validation :** une référence locale pertinente est retrouvée malgré accents ou zéros initiaux ; les numéros différents et variantes concurrentes ne créent pas de fausses identifications.

### T2 — Persister preuves, décisions et file — P0, après T0

- [x] Définir les modèles typés, les actions humaines, les états de recherche et leurs transitions.
- [x] Ajouter les nouvelles migrations à partir du prochain numéro disponible : `BEGIN IMMEDIATE`, enregistrement dans `schema_migrations`, `COMMIT`.
- [x] Ajouter les index normalisés et leur reprise ; préserver les identifiants des références existantes.
- [x] Implémenter l’historique et la résolution des confirmations, y compris retrait et correction explicite d’un faux lot.
- [x] Implémenter déduplication, associations aux annonces, réservation atomique, bail expirant et reprise après arrêt du worker.
- [x] Éviter les commits implicites imbriqués : le seed et les écritures du cache ne doivent pas interrompre une transaction d’import.

**Validation :** migration neuve et mise à niveau idempotentes ; intégrité des clés étrangères ; confirmation durable ; recherche récupérable après redémarrage.

### T3 — Ajouter la recherche distante ciblée — P0, après T1 et T2

- [x] Étendre `TcgdexClient` avec recherche filtrée et pagination, en s’appuyant sur la documentation officielle citée plus bas.
- [x] Essayer dans l’ordre les critères disponibles : identifiant TCGdex exact ; extension + numéro ; nom + numéro ; nom avec filtres élargis. Aucun parcours sans critère utile.
- [x] Proposer la synchronisation d’une extension ciblée, avec progression et reprise ; aucune synchronisation globale au démarrage.
- [x] Distinguer résultats résumés et fiches détaillées. Enregistrer l’extension avant ses cartes ; charger les détails nécessaires avant confirmation d’une référence distante.
- [x] Préserver les détails déjà connus lors d’un upsert de résumé. Une valeur absente de la réponse ne doit pas effacer une rareté ou une image existante.
- [x] Encoder les paramètres ; accepter un identifiant structuré, pas une URL réseau arbitraire fournie par l’utilisateur.
- [x] Borner requêtes, pages et tentatives ; conserver les résultats partiels avec un indicateur explicite. Valeurs initiales proposées : 1 requête distante simultanée, 3 tentatives au plus par opération, délai HTTP de 10 s, cache des recherches vides de 24 h, délai minimal de relance manuelle de 30 s. Ce sont des paramètres du projet, pas des quotas annoncés par TCGdex.
- [x] Respecter `Retry-After` en replanifiant la demande ; ne pas immobiliser le worker pendant une longue attente. Distinguer 404, réponse vide, données invalides, délai dépassé, 429 et erreur serveur.

**Validation :** une carte absente localement devient recherchable après une réponse distante simulée ; une panne ne perd ni annonce, ni confirmation, ni données de référence déjà connues.

### T4 — Brancher le pipeline et le worker — P0, après T2 et T3

- [x] Appliquer le même service de résolution aux collecteurs, à l’extension et au réexamen. Couvrir également les chemins d’import manuel pouvant créer ou réécrire une identification.
- [x] Garder l’import immédiat et local. Enregistrer la mise en file sans appeler le réseau ; empêcher qu’une panne TCGdex invalide l’import.
- [x] Exposer un réglage documenté, désactivé par défaut, pour l’enrichissement automatique en ligne. Une recherche manuelle explicite reste possible si l’automatisme est désactivé.
- [x] Déclencher cet enrichissement pour les annonces unitaires `unidentified` ou `ambiguous` disposant de critères utiles, hors confirmation humaine applicable. Aucun enrichissement unitaire automatique pour les lots.
- [x] Intégrer un traitement borné dans le worker, avec connexion SQLite propre au traitement ; ne pas partager une connexion entre threads. Préserver l’ordonnancement des veilles et l’arrêt propre.
- [x] Recontrôler empreinte, existence de l’annonce, classement lot et révision humaine avant publication du résultat.
- [x] Proposer depuis la fiche de rejouer les annonces concernées par une nouvelle extension ; dédupliquer et traiter par petits lots, sans écraser les confirmations.

**Validation :** addon et collecteurs convergent vers la même décision ; redémarrage, double clic et retour tardif d’une recherche restent sans effet indésirable.

### T5 — Construire le parcours sur la fiche annonce — P1, après T1 à T4

- [x] Afficher les preuves originales disponibles, la photo, les informations détectées et le motif précis de non-identification.
- [x] Ajouter les champs nom, numéro, extension et identifiant TCGdex ; distinguer leur provenance détectée ou saisie. Préserver les critères lors d’un retour d’erreur.
- [x] Afficher les candidats avec photo facultative, nom, extension, numéro, langue du référentiel, identifiant, raisons et éventuelles contradictions.
- [x] Fournir recherche locale paginée, « Recherche approfondie », « C’est cette carte », modification et retrait d’une confirmation.
- [x] Afficher source de décision, date et historique utile. Séparer le score automatique du libellé « Confirmée manuellement ».
- [x] Prévoir file d’attente, recherche en cours, résultats partiels, aucun résultat, panne, mode hors ligne et conflit de révision. Un résultat vide reste « Aucune référence trouvée pour ces critères », jamais une preuve d’inexistence.
- [x] Respecter Mosaic × Flowbite, navigation clavier, libellés et affichage mobile. Une image distante indisponible ne bloque aucune action.

**Validation :** on peut rechercher une carte hors des premiers candidats, la confirmer puis retirer la confirmation sans modifier le titre original.

### T6 — Relier le popup de l’extension — P1, après T4 et T5

- [x] Afficher deux informations indépendantes : identité de la carte et disponibilité d’une cote.
- [x] Pour une identité non résolue, ajouter « Identifier cette carte » vers la fiche importée ; afficher séparément une recherche en attente si cette information est disponible.
- [x] Pour une carte identifiée sans prix, conserver « Renseigner une cote ». Pour un lot, afficher son statut sans proposer de confirmation unitaire.
- [x] Garder la réponse JSON existante compatible ; ajouter seulement les champs nécessaires et un lien de recherche. Ne pas casser la correspondance des résultats avec les captures.
- [x] Conserver Manifest V3 et JSONL ; ne pas ajouter de permission distante. Le popup peut se fermer : le traitement backend continue et le lien vers la fiche reste utilisable.

**Validation :** « Sans cote » ne suggère plus que la carte est absente du catalogue ; une capture mène au bon écran d’identification.

### T7 — Recette, documentation et livraison — P0, après T1 à T6

- [x] Exécuter les tests ciblés pendant chaque étape, puis toute la suite Docker.
- [x] Vérifier le rendu de la fiche et du popup : carte connue, absente du seed, ambiguë, lot, cote manquante, panne distante et worker arrêté.
- [x] Mettre à jour `README.md`, `extension/README.md`, `SOURCES.md` et `SUIVI.md` avec les comportements réellement livrés, les réglages et les limites de langue.
- [x] Documenter activation/désactivation, état de la file, relance et retrait de confirmation ; aucune commande destructive sur le volume utilisateur.
- [x] Livrer un relevé des tests, des échecs initiaux éventuels et des limites restantes. Les essais réseau réels restent manuels et distincts de pytest.

**Validation :** parcours complet reproductible, suite verte ou blocage préexistant précisément identifié, migrations et sauvegardes compatibles, aucune dépendance non sollicitée.

## 6. Matrice de tests obligatoire

Tous les scénarios automatisés utilisent des fixtures locales et des mocks réseau.

| Cas | Attendu |
|---|---|
| Carte présente localement avec accents différents | Candidat retrouvé ; aucune requête distante nécessaire |
| Nom/extension hors listes historiques | Détection issue du référentiel ; candidat recherché |
| Numéros `004`, `4`, `14`, `104`, préfixes promo | Équivalences contrôlées ; aucune correspondance par simple suffixe numérique |
| Bonne carte au-delà des 20 premiers anciens résultats | Accessible à la recherche et éligible au classement |
| Plusieurs cartes au score maximal élevé | Ambiguïté conservée |
| Numéro ou extension explicitement contradictoire | Pas d’acceptation automatique |
| Carte absente du cache, réponse TCGdex valide | Référence importée, recherche locale rejouée, candidat présenté |
| Résumé sans rareté après fiche détaillée | Rareté connue préservée |
| Réponse vide / 404 / timeout / 429 / JSON invalide | États distincts ; import conservé ; reprises bornées |
| Double demande et plusieurs annonces pour la même recherche | Pas de rafale réseau ; résultats distribués aux associations valides |
| Arrêt après réservation d’une demande | Reprise après expiration du bail ; pas de double application |
| Confirmation puis réingestion avec nouveau prix | Carte confirmée et `first_seen_at` préservés |
| Confirmation pendant une recherche en cours | Le résultat tardif ne l’écrase pas |
| Preuves d’identité modifiées / capture partielle | Conflit explicite à revoir ; absence seule gérée sans effacement aveugle |
| Lot et faux positif de lot | Aucun rattachement unitaire tant que le lot est actif ; reclassement explicite historisé |
| Retrait / remplacement / confirmation concurrente | Historique conservé, décision applicable unique, conflit signalé |
| Annonce supprimée pendant une recherche | Pas de recréation ni de mise à jour orpheline |
| Carte étrangère explicite | Pas de substitution silencieuse par la version française |
| Carte identifiée sans cote / non identifiée avec prix disponible | Deux états présentés indépendamment ; aucun gain inventé |
| Migration, base existante et sauvegarde restaurée | Clés valides, décisions et file conservées, migrations rejouables |
| Réseau interdit pour toute la suite | Aucun appel externe, même si l’enrichissement automatique est activé dans un test |

Suites à compléter : `test_identification.py`, `test_tcgdex_cache.py`, `test_watch_ingestion.py`, `test_catalog.py`, `test_imports.py`, `test_pipeline_integration.py`, `test_web.py`, `test_chrome_extension.py`, `test_config.py`, `test_migrations.py`, `test_backups.py`. Ajouter une suite dédiée aux recherches persistantes et à leur concurrence ; conserver les contrôles existants sur la rentabilité.

Commandes à exécuter pendant l’implémentation :

```bash
docker compose run --rm app pytest tests/test_identification.py tests/test_tcgdex_cache.py
docker compose run --rm app pytest tests/test_migrations.py tests/test_watch_ingestion.py tests/test_catalog.py tests/test_imports.py
docker compose run --rm app pytest tests/test_web.py tests/test_chrome_extension.py tests/test_config.py tests/test_backups.py
docker compose run --rm app pytest
```

## 7. Ordre de livraison et définition de terminé

1. **Fondations fiables :** T0, T1 et T2 ; recherche locale et décisions protégées.
2. **Recherche complète :** T3 et T4 ; enrichissement ciblé, file durable, résolution commune.
3. **Parcours utilisateur :** T5 et T6 ; recherche, comparaison, confirmation et distinction identité/cote.
4. **Livraison :** T7 ; recette, tests et documentation.

La fonctionnalité est terminée quand une carte absente du seed peut être retrouvée via TCGdex simulé, choisie depuis la fiche, puis réingérée et réexaminée sans perdre la confirmation ; quand un lot ne reçoit aucune référence unitaire ; et quand une panne TCGdex laisse l’import et la recherche locale utilisables. Les cases cochées consignent les acquis de cette livraison, recontrôlés par les suites courantes ; les nouvelles exigences restent dans Identification, sans rouvrir artificiellement cette ancienne liste.

## 8. Références et modèle de développement

- Documents du dépôt : `AGENTS.md`, `README.md`, `SOURCES.md`, `SUIVI.md`, `TASKING_INTEGRATION_DESIGN.md`, `MACHINE_LEARNING_DESIGN.md`, `extension/README.md`.
- [Recherche de cartes TCGdex](https://tcgdex.dev/rest/cards) : liste de résultats résumés ; compléter par les détails utiles.
- [Filtres, tri et pagination TCGdex](https://tcgdex.dev/rest/filtering-sorting-pagination) : construire des requêtes ciblées et paginées, avec paramètres encodés.
Le choix d’un modèle de développement n’est pas une dépendance du projet. Ce plan ne prévoit aucun appel à un LLM à l’exécution.

## 9. Prompt de lancement prêt à copier

```text
Tu travailles dans /Users/mathieu/Documents/pokebourse.

Lis TASKING_PROJET.md puis vérifie les acquis de TASKING_RECHERCHE_CARTES.md.
Traite uniquement les écarts démontrés ou le périmètre explicitement demandé. Lis AGENTS.md et les documents métier/UI cités avant de modifier
les modules concernés. Ne rejoue pas les tâches cochées comme des fonctionnalités manquantes.

Avance dans l’ordre des dépendances, avec des changements cohérents et des
tests Docker ciblés à chaque étape, puis la suite complète. Ne coche une
tâche qu’après avoir vérifié son résultat. Préserve les travaux déjà présents,
notamment app/cardmarket/ et toutes les migrations publiées ; vérifie le prochain numéro.

Priorités : recherche locale correcte ; confirmation humaine persistante ;
recherche TCGdex ciblée en arrière-plan ; absence de réseau dans pytest et
dans les transactions d’ingestion ; gestion des résultats obsolètes ;
interdiction de rattachement unitaire pour les lots ; distinction entre
identification et cote de revente dans la fiche et le popup.

Garde le fonctionnement hors ligne, les montants entiers et first_seen_at.
N’ajoute ni framework frontend, ni dépendance ML, ni appel LLM. Ne lance
jamais docker compose down -v. Termine par les changements livrés, les
vérifications exécutées et les limites restantes.
```
