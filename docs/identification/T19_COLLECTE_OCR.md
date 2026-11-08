# T19 — Collecteurs marketplace, parcours des annonces et OCR

**État au 8 novembre :** spécification à réaliser ; pas de file OCR collecte ni de nouveau moteur spatial présent dans le dépôt inspecté. Les captures partielles Chrome ont déjà été corrigées par T08.1 ; les réutiliser. « Jobs 1/2/3 » désigne les périmètres historiques, pas des travaux actuellement en exécution. Voir [le suivi consolidé](../../TASKING_PROJET.md).

Date : **8 novembre 2026**. Statut : **spécification à implémenter**. Le périmètre demandé inclut les collecteurs qui parcourent les annonces Vinted, Leboncoin, eBay et Wallapop, ainsi que la capture Chrome pendant la navigation réelle. Références : [tasking](../../TASKING_IDENTIFICATION_FIABLE.md#t19--adapter-les-collecteurs-marketplace-et-le-traitement-ocr), [plan de validation](PLAN_VALIDATION_LOTS.md#t19), [tracker](../../tracker.md), [SOURCES.md](../../SOURCES.md).

## 1. Point de départ vérifié dans le code

Les termes « worker qui scrolle » désignent ici l'entrée de collecte. Vérifier la méthode réellement utilisée par chaque adaptateur ; une pagination HTTP et un défilement DOM ne sont pas interchangeables.

| Entrée | État observé dans le code du dépôt | Travail attendu |
|---|---|---|
| Vinted | Client `vinted_scraper`, paramètres `page=1`, première page seulement | Adapter contrat de collecte/images et parcours borné applicable, conserver les limites d'accès configurées |
| Leboncoin | Client `lbc`, recherche `page=1`, première page seulement | Même contrôle de pagination, données partielles et photos, sans confondre blocage et fin de résultats |
| eBay | Recherche HTTP de page publique avec parsing opportuniste, pas d'API officielle établie | Vérifier le type de réponse et sa couverture ; ne pas présenter un HTML non compris comme recherche complète vide |
| Wallapop | Recherche HTTP avec `step=0` | Vérifier le mécanisme de page/curseur réellement disponible et les données d'images |
| Navigateur de secours | `BrowserCollector` opt-in, une page, extraction de liens ; pas de boucle de scroll implémentée | Tester le parcours DOM seulement pour le mode explicitement retenu ; son existence n'établit pas son activation |
| Extension Chrome | Capture DOM/JSON-LD et observation des mutations de la page | Capturer les nouvelles annonces/images effectivement chargées pendant navigation, défilement et changement de page |
| Worker Python | Ordonnanceur de veilles, ingestion, recherches TCGdex/sync ; aucun raccordement OCR de collecte observé | Ajouter l'orchestration OCR durable et commune après ingestion, sans ralentir toutes les autres veilles |

Ces constats sont des observations de code, pas une vérification des services déployés ni de la disponibilité actuelle des sites. L'implémentation doit préciser par plateforme l'accès retenu, les capacités activées et les limites selon SOURCES/T15 ; aucun nouveau connecteur navigateur ou accès externe n'est activé par cette rédaction.

## 2. T19.1 — Parcours et contrat des données/images

- Auditer/modifier les adaptateurs existants, normaliseurs et modèles, plus le content script et le service worker Chrome lorsque leurs contrats évoluent. Conserver la compatibilité de `image_url` et des anciens JSONL ; ajouter une galerie optionnelle bornée, sans rendre une extension/identité connue obligatoire pour conserver une capture.
- Conserver source, identifiant externe, URL, titre/description bruts disponibles et leur provenance, langue explicitement déclarée éventuelle, photos et leur rôle lorsqu'il est connu. Une réponse de recherche partielle n'est pas une fiche détail complète ; un champ absent n'efface pas silencieusement une preuve antérieure.
- Préférer les URL de vues détaillées déjà fournies par la source à une miniature lorsque disponibles : `currentSrc`/`srcset`/attributs différés et métadonnées structurées doivent rester rattachés à la bonne annonce. Ne pas inventer une URL d'image haute résolution ni déduire plusieurs exemplaires du seul nombre de photos.
- Pour DOM : gérer mutations après défilement, éléments réutilisés/virtualisés, pagination et navigation interne. L'identité de l'annonce vient de sa source/ID/URL, jamais de la position d'une tuile. La capture Chrome ne déclenche pas un défilement automatique sans mode explicite prévu.
- Pour HTTP/API : traiter page/curseur suivant selon le mécanisme réel. Borner pages, annonces, durée, téléchargements et retries par source ; arrêter sur fin établie, page/curseur répété, absence de nouveaux IDs, annulation ou budget atteint. Une réponse non comprise, un challenge ou un timeout est un état partiel/erreur, pas une fin de catalogue prouvée.
- Toute récupération d'une fiche détail ou d'image utilise le transport autorisé/configuré et ses limites d'hôtes, types, taille, redirections et délais ; aucun accès réseau au nom d'une URL arbitraire dans le matcher. Une photo inaccessible n'annule pas une collecte textuelle valide.
- Conserver prix/port en centimes et filtres monétaires en calcul exact ; corriger les conversions de filtres Vinted/eBay qui passent actuellement par `float`, avec tests sans réseau, sans changer l'arrondi métier.

## 3. T19.2 — Pipeline de collecte en arrière-plan

Le parcours interactif W01–W09 conserve la prévisualisation sans écriture. Une veille suit une autre entrée : **collecter → normaliser → ingérer/conserver → mettre l'analyse en file → OCR/rapprochement commun → publier sous contrôle de révision → fiche/validation**.

| Étape | Traitement et effet attendu |
|---|---|
| C01 — Parcourir | Collecter les annonces et images dans les budgets/modalités de la plateforme ; dédupliquer les IDs et conserver les états partiels |
| C02 — Conserver | Ingérer transactionnellement selon le flux existant, préserver `first_seen_at`, les décisions humaines et les observations originales ; enregistrer une obligation d'analyse durable ou assurer un rattrapage déterministe |
| C03 — Réserver | Réserver un travail dédupliqué, lié à l'annonce, ses preuves, la vue et les versions ; ne pas conserver une transaction pendant téléchargement ou OCR |
| C04 — Analyser | Télécharger si autorisé, valider l'image, appeler les mêmes composants T06/T07 et la même recherche/décision T03/T05 ; pas de second matcher propre à une marketplace |
| C05 — Publier | Vérifier existence, empreinte, révision et classement lot avant application ; ignorer toute réponse périmée et préserver les confirmations humaines applicables |
| C06 — Présenter/suivre | Montrer les mêmes propositions/diagnostics/attributs que la capture interactive ; permettre confirmation/correction sur la fiche ; déclencher T16 seulement depuis une identité effective admissible |

- L'ingestion reste rapide et indépendante d'une image manquante, de l'OCR saturé ou d'une erreur distante. Les autres veilles, heartbeats et files continuent ; définir l'équité entre travaux interactifs et arrière-plan.
- La clé de travail distingue annonce/source, observation/photo sélectionnée et versions d'analyse ; après acquisition, conserver l'empreinte des octets utiles à la déduplication. Même URL ne prouve pas des octets inchangés ; définir la politique de fraîcheur et ses limites. Prix seul modifié : aucun nouvel OCR ; nouvelle preuve image/identité pertinente : réexamen versionné.
- Respecter une concurrence **agrégée** app/worker, avec les limites de T06 (deux analyses, 8 Mo/12 Mpx et budget de calcul global). Un sémaphore séparé dans chaque processus ne démontre pas cette borne globale. Arrêt/reprise, réservation expirée, retry borné et libération des ressources sont testés.
- Images éphémères par défaut ; stockage durable seulement dans le mode T04 explicite. Aucun texte OCR complet/photo envoyé à TCGdex ou enregistré dans les logs ; résultats et observations minimales conservent leur provenance.
- Tout nouveau schéma/file nécessite une migration additive numérotée d'après l'état réel. Pas de broker ni dépendance imposés si les mécanismes locaux existants conviennent.

## 4. T19.3 — Intégrations et critères de validation

**Skill :** aucun skill backend spécialisé approprié disponible ; `build-web-apps:frontend-testing-debugging` pour la capture DOM, le rendu et les interactions utilisateur concernés, selon le plan de validation. Réutiliser Playwright/Chromium et le harnais MV3 existants pour les tests hermétiques.

| Groupe | Scénarios obligatoires et preuve attendue |
|---|---|
| Parcours par plateforme | Fixtures distinctes Vinted/Leboncoin/eBay/Wallapop ; pages/curseurs répétés, fin réelle, plafond et réponse malformée. Vérifier appels, IDs, erreurs et conditions d'arrêt |
| DOM et images différées | Page locale simulant défilement, chargement tardif, changement d'URL et réutilisation d'une tuile ; aucune photo/description affectée à l'annonce voisine, aucune capture perdue parce que nom/extension inconnus |
| Contrat des images | Galerie absente/partielle, miniature et grande vue, image inaccessible/retirée, type/taille/hôte invalides, compatibilité anciens payloads/JSONL ; preuve brute conservée sans attribut inventé |
| Worker et ressources | Collecte suivante non bloquée pendant OCR, limite globale de concurrence, timeouts, arrêt/reprise avant/après commit et réservation, retry borné, aucun travail perdu/dupliqué |
| Révisions et intégrité | Prix seul modifié sans OCR ; photo/identité modifiée pendant analyse, annonce supprimée ou confirmation humaine récente ; résultat ancien non appliqué, `first_seen_at` inchangé et lots protégés |
| Bout en bout | Même annonce par extension et veille simulée : observations équivalentes → même proposition/motif ; champ puis fiche, choix humain conservé, identité effective utilisée par comparaisons locales/T16 |
| Lecture réelle | Petit jeu photographique autorisé et annoté avec Tesseract réel, distinct des tests de transport mockés ; gain/limites documentés selon T01/T10, pas de qualification par une page synthétique seule |

Suites existantes à compléter : `tests/test_collectors.py`, `tests/test_collector_models.py`, `tests/test_watch_ingestion.py`, `tests/test_monitoring_service.py`, `tests/test_supervision.py`, `tests/test_chrome_extension.py`, `tests/test_extension_e2e.py`, `tests/test_pipeline_integration.py`, `tests/test_identification_reviews.py`, `tests/test_migrations.py`, `tests/test_ocr_local.py`, `tests/test_ocr_web.py`.

Fichiers proposés **à créer** : `tests/test_collector_capture_contract.py`, `tests/test_collector_navigation.py`, `tests/test_collector_ocr_queue.py`, `tests/test_collection_ocr_e2e.py`. Les commandes ci-dessous couvrent les bases existantes ; ajouter les nouveaux fichiers une fois créés :

```bash
docker compose run --rm app pytest -ra tests/test_collectors.py tests/test_collector_models.py tests/test_watch_ingestion.py tests/test_monitoring_service.py tests/test_supervision.py
docker compose run --rm app pytest -ra tests/test_chrome_extension.py tests/test_extension_e2e.py tests/test_pipeline_integration.py tests/test_identification_reviews.py tests/test_migrations.py tests/test_ocr_local.py tests/test_ocr_web.py
docker compose run --rm app pytest -ra
```

Aucun réseau externe dans pytest, y compris navigateur/worker ; serveurs et ressources locales du test autorisés. Aucun test sur les données réelles. Chaque défaut, blocage d'intégration et scénario requis sauté va dans tracker.md. Publier par plateforme les modes réellement testés/activés et ceux indisponibles ; une fixture passante n'établit pas un accès réel.

## 5. Coordination des trois jobs

- **Job 1 :** T08.1/T08.3 et contrats d'inconnus, avec tests du moteur actuel.
- **Job 2 parallèle :** nouveaux composants OCR internes et tests dédiés, dans un worktree distinct ; pas de modification des adaptateurs, formulaires, workers ou contrats publics partagés.
- **Job 3 après intégration des deux :** T08.2/T09 et **T19.1/T19.2/T19.3 explicitement**, puis recette J1 étendue/T12/T13. Intégrer les modifications de code des collecteurs/normaliseurs et ordonnanceur, de la capture Chrome et du service worker, pas seulement la documentation. Contrat de sortie T16 et comparaisons locales vérifiés ; capacités de marché J3 qualifiées séparément.

Les constats d'accès, de mise en production ou de qualité non établis restent ouverts dans le tracker. Aucun lot n'est validé sur la seule existence des modules OCR ou du collecteur navigateur de secours.
