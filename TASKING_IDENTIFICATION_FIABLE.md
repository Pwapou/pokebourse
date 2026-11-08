# Pokébourse — Identification fiable, comparaison de marché et marge

Plan initial : **2 novembre 2026** ; état réconcilié le **8 novembre 2026**. **J1/J2/J3 restent ouverts.** Acquis : T00 comme inventaire, T02/T03/T04 et T08.1 testés ; socle T05 livré sauf alias non vérifié ; T01 et T08.3 partiels. T15 possède sa matrice documentaire datée du 3 novembre, sans accès marché nouvellement établi. T06/T07/T08.2/T09 et T14/T16–T19 restent à compléter selon les critères ci-dessous. La rédaction d'une cible ne vaut pas réalisation.

**Pilotage transversal :** [TASKING_PROJET.md](TASKING_PROJET.md) donne l'état de tous les chantiers, les preuves et l'ordre de reprise. Les paragraphes datés de livraison restent historiques ; l'état courant est cette synthèse et les critères de chaque lot. Les 834 tests passants du 8 novembre qualifient le code existant, pas les lots futurs ni la précision OCR.

**Recadrage produit :** ajout du parcours de comparaison et d'estimation (J3, T14 à T18). Ces lots sont à réaliser ; leur ajout ne modifie pas l'état des travaux d'identification existants.

**Adaptation OCR confirmée le 3 novembre 2026 :** renforcer T06/T07 autour de trois objectifs : **repérer et redresser la carte avant lecture, conserver la position des textes, produire plusieurs hypothèses de numéro**. Conserver Tesseract local comme point de départ ; mesurer les gains avant tout changement de moteur. Ces travaux restent à réaliser. Le pHash reste une expérience conditionnelle de T11, sans activation par cette adaptation.

**Procédure de développement T06/T07 :** suivre [Cadrage, OCR spatial et hypothèses de numéro](docs/identification/T06_T07_PROCEDURE_OCR.md) pour le découpage des modules, les contrats, les algorithmes, les limites, l'intégration T03 et les tests. Cette spécification détaillée ne constitue pas une livraison du moteur.

**Complément de périmètre — 8 novembre 2026 :** le cas de capture « carte Pokémon ancienne Tortant obscur » impose une livraison commune **lecture photo → recherche de référence → champs proposés utilisables** (T06/T07/T08). Corriger séparément, sans attendre le nouvel OCR, la copie du titre dans le nom de carte et le préremplissage qui la conserve (T08.1). Ajouter une suggestion de langue étayée par le texte de la carte. Le correctif déterministe T08.1 et les contrôles T08.3 du moteur actuel sont depuis livrés/testés ; les nouvelles lectures, la suggestion de langue et la recette photographique complète restent ouvertes. Voir [le bilan T08](docs/identification/T08_CONTROLES_MOTEUR_ACTUEL.md). La comparaison directe entre images reste conditionnelle en T11 ; la recherche d'offres et de prix reste portée par T16/T17.

## 1. Objectif et définition de « terminé »

Livrer un parcours utilisable : **capturer une annonce et sa photo → identifier la carte et ses attributs → demander confirmation en cas de doute → enregistrer → rechercher les offres comparables et les ventes documentées accessibles → estimer un prix de revente et une marge lorsque les données le permettent**. Identification et calcul restent locaux ; la recherche de marché utilise uniquement les sources externes autorisées et configurées.

Une annonce imparfaite doit toujours aboutir à un résultat explicite et à une action disponible. Une photo illisible ou une référence absente peut empêcher l'identification exacte ; le logiciel doit alors conserver l'annonce et proposer la bonne suite, sans fabriquer d'identité.

Trois jalons de livraison :

- **J1 — parcours complet assisté** : T00 à T09, T12 et T19 réalisés sur le périmètre de capture et de collecte annoncé, tests et recette fonctionnelle passants. L'utilisateur peut terminer les cas résolubles, conserver les cas indéterminables et enrichir le référentiel. Les nouvelles preuves OCR restent des suggestions soumises à vérification ; aucun gain statistique n'est annoncé sans mesure. Les modes de collecte non établis/indisponibles ne sont pas présentés comme livrés ; toute portée non réalisée reste explicite.
- **J2 — qualité mesurée et extension éventuelle de l'automatisation** : T10 réalisé sur un jeu indépendant. T11 est une expérience conditionnelle, à réaliser seulement si le diagnostic justifie la vision. Une conclusion documentée « vision non retenue » clôt ce lot ; une expérience négative n'empêche pas J1. Toute nouvelle automatisation passe les critères de T10 avant activation.
- **J3 — comparaison de marché et estimation expliquée** : T14 à T18 réalisés, recette T13 étendue passante, T12 réactualisé. Après enregistrement d'une identité admissible, recherche automatique bornée sur les sources activées, offres en cours et ventes conclues séparées, prix et marge accompagnés de leurs preuves et limites. En cas d'identité incertaine, demander une confirmation avant tout calcul. Les choix ouverts ci-dessous doivent être tranchés avant activation des comportements concernés. Une source de ventes indisponible n'est pas une fonctionnalité livrée : documenter la couverture réelle et faire valider toute réduction du périmètre demandé.

Le chantier couvre l'identification, ses entrées et ses conséquences. Il ne demande ni réécriture générale de Pokébourse, ni automatisation du contournement des marketplaces, ni certification des faux, ni estimation automatique de l'état à partir d'une photo.

### 1.1 Périmètre confirmé avec l'utilisateur

- **Produits :** cartes à l'unité non gradées et cartes gradées **PSA ou PCA**. Les autres certificateurs, lots et produits scellés restent enregistrables selon les parcours existants, mais hors du nouveau périmètre de comparaison qualifiée ; conserver leurs garde-fous et données.
- **Résultat attendu après envoi de la capture :** analyse photo, recherche de référence et propositions de champs enchaînées sans recherche ni recopie manuelle dans le cas nominal ; identité suffisamment étayée, offres ailleurs, estimation et marge si admissibles. Les confirmations explicitement requises en J1 restent visibles ; une acceptation entièrement automatique fondée sur l'OCR exige T10. La présence d'une annonce et d'une photo ne garantit jamais l'identification ni la disponibilité d'un prix.
- **Prix :** afficher séparément les offres actuellement disponibles et les ventes réellement conclues documentées ; une cote agrégée constitue une troisième catégorie, pas une liste de transactions.
- **Doute sur l'identité/version :** interrompre la valorisation et demander un choix ou une confirmation humaine. Une recherche TCGdex peut aider à résoudre l'identité ; un prix plausible ne prouve pas cette identité.
- **Choix des sources :** confié au cadrage technique. Proposition initiale : guide Cardmarket pour les cotes, eBay pour les offres si accès établi, captures locales et reventes personnelles documentées en complément ; vérifier les capacités en T15, notamment pour les gradées et les ventes conclues.

### 1.2 Choix encore ouverts — ne pas les transformer en décisions implicites

| Choix | État / décision attendue | Partie dépendante |
|---|---|---|
| Zone géographique | France, UE ou monde ; pays de livraison et traitement des devises/importations à préciser | Requêtes, coût livré et comparabilité T16/T17 |
| Données de prix insuffisantes | Estimation indicative, absence d'estimation ou scénario saisi par l'utilisateur : pas encore choisi | Repli et affichage financier T18 |
| Canal de revente | Plateforme choisie par l'utilisateur ou comparaison des canaux : pas encore choisi | Frais et scénario de marge T18 |
| Niveau de comparabilité | Proposition conservatrice : même version/langue/finition/état ; pour les gradées, même certificateur et même note. Assouplissements éventuels à valider | Sélection des preuves T17 |
| Source complémentaire éventuellement payante | Aucun abonnement ni budget validé ; ne pas engager de coût pour obtenir des ventes conclues | Capacités et arbitrage T15 |

Les contrats, interfaces et tests simulés peuvent avancer indépendamment. Un choix manquant ne se remplace pas par une hypothèse silencieuse en production ; consigner les propositions et demander les réponses avant d'activer le comportement dépendant.

### 1.3 Résultat attendu sur une capture au titre imprécis

Cas de recette fourni le 8 novembre 2026 : titre « carte Pokémon ancienne Tortant obscur », description « Ancienne carte de 1995 », photo sur laquelle se lisent « Tortank obscur », `20/82` et du texte français. Le formulaire observé recopie le titre comme nom, laisse l'extension et la langue vides et propose `n` comme numéro. Ne pas attribuer une cause précise à ce dernier résultat avant reproduction.

- Conserver exactement le titre et la description d'origine ; proposer séparément le nom canonique de la référence compatible, ici « Tortank obscur » si la fixture indépendante le confirme.
- Lire le numéro imprimé `20/82`, chercher les références compatibles et proposer leur extension depuis le catalogue, même si le vendeur ne l'a pas écrite. Étiqueter cette extension « issue du référentiel », jamais « extraite de l'annonce ». Vérifier et figer l'extension et l'identifiant attendus dans la fixture, sans les déduire du premier résultat du matcher.
- Proposer « Français — à confirmer » si les mots lus sur la carte étayent cette langue. Le site, le vendeur, le nom seul, les langues installées dans Tesseract et la locale du catalogue ne suffisent pas.
- Présenter les candidats et permettre de confirmer l'identité et les attributs utiles dans la prévisualisation, sans recopier manuellement leurs champs ni importer d'abord une identité incorrecte. Une correction ou une suggestion OCR reste distincte d'une confirmation.
- Après confirmation et enregistrement, réutiliser l'identité retenue pour la recherche et les comparaisons ; T16/T17 ajoutent le déclenchement de marché et la sélection des comparables. Aucun calcul financier sur une simple proposition.

La recette doit prouver le résultat dans le formulaire, puis sur la fiche enregistrée. Une réponse OCR contenant le bon nom/numéro mais inutilisée par l'écran ne satisfait pas ce contrat. Une réussite sur cet exemple ne démontre pas une précision générale.

## 2. Documents de référence et état de départ

Lire [AGENTS.md](AGENTS.md), [README.md](README.md), [SOURCES.md](SOURCES.md), [SUIVI.md](SUIVI.md), [TASKING_RECHERCHE_CARTES.md](TASKING_RECHERCHE_CARTES.md), [TASKING_RECHERCHE_TENDANCES.md](TASKING_RECHERCHE_TENDANCES.md), [docs/IDENTIFICATION_LEXICALE.md](docs/IDENTIFICATION_LEXICALE.md), [docs/TCGDEX_SYNC.md](docs/TCGDEX_SYNC.md), [docs/ML_PHASE0.md](docs/ML_PHASE0.md) et [MACHINE_LEARNING_DESIGN.md](MACHINE_LEARNING_DESIGN.md).

Le présent document pilote le nouvel enchaînement automatique après identification. La recherche externe générale de `/search` reste explicite comme décrit dans le tasking Recherche/Tendances ; T16 réutilise ses capacités sans déclencher de requêtes à chaque frappe ou consultation d'une fiche.

Pour l'interface : [TASKING_INTEGRATION_DESIGN.md](TASKING_INTEGRATION_DESIGN.md). Pour la capture : [extension/README.md](extension/README.md) et [PROMPT_PATCH_EXTRACTION.md](PROMPT_PATCH_EXTRACTION.md).

Les taskings historiques contiennent des constats antérieurs à leurs implémentations. Vérifier le code courant avant de recréer une fonction ou de reprendre un ancien numéro de migration.

Constats de préparation réconciliés au 8 novembre (les autres inventaires gardent leur date) :

| Existant | Conséquence pour ce chantier |
|---|---|
| `detector.py` reçoit les noms de cartes et d'extensions du cache, avec alias historiques en repli | Compléter les alias et la couverture ; conserver ce qui fonctionne |
| `listing_preview.py` ajoute les noms/numéros OCR seulement lorsque les preuves textuelles correspondantes manquent | Préserver cette priorité et éviter de perdre la provenance dans une chaîne concaténée |
| `ocr.py` lit l'image entière puis, si nécessaire, les 20 % supérieurs et 15 % inférieurs de la photo ; retourne du texte sans positions ; délai de 20 secondes par appel Tesseract | Localiser/redresser la carte avant de définir ses régions, conserver les positions et instaurer un budget global couvrant les essais de secours ; mesurer avant/après |
| T08.1 livré : titre conservé séparément, nom canonique proposé depuis un candidat admissible ; corrections humaines préservées | Réutiliser ce contrat pour T06/T07/T08.2, ne pas refaire le correctif |
| L'OCR transporte encore noms/numéros ; la capture accepte désormais la langue inconnue explicite `und` | Ajouter la suggestion de langue avec preuve photo et confirmation distincte ; préserver `und` et les anciens JSONL |
| `resolution.py`, `reviews.py` et le pilote gèrent déjà décisions, snapshots, révisions et export | Étendre les contrats existants plutôt que créer une seconde vérité humaine |
| T04 livré : magasin explicite de preuves visuelles, provenances `image`/`both`, sauvegarde avec sidecar ; anciennes photos de campagne séparées | Rattacher les preuves explicitement ; une simple analyse OCR ou une photo de campagne ne devient pas une preuve durable du pilote |
| T05 livré : unicité `(tcgdex_id, reference_language)` et sync par locale (`0024`–`0026`) | Conserver identifiants/liens ; chargement d’une locale distinct de qualification de son identification |
| `validation/ocr/marketplaces/run_30_liens.py` compare titre/OCR/combiné ; le résumé compte des statuts | Ajouter les labels indépendants, la description et les mesures de justesse |
| L'espace de travail contient des changements en cours | Inventorier et préserver les modifications ; ne jamais réinitialiser le dépôt pour ce chantier |
| `profitability.py` exploite références enregistrées, annonces locales et guide Cardmarket lié ; `search/external.py` porte une recherche externe distincte | Ne pas présenter l'identification comme une recherche de marché automatique déjà acquise |

Les performances et le volume de catalogue installé ne sont pas déduits du seed, des anciens rapports ou des compteurs de statuts. Les établir en T00/T01.

## 3. Contrat produit et règles invariantes

### 3.1 Résultats et actions

Conserver les statuts compatibles `identified`, `ambiguous`, `unidentified`, `lot`. Ajouter des raisons structurées et une origine de décision, plutôt que multiplier les statuts incompatibles.

| Situation | Résultat visible | Action suivante |
|---|---|---|
| Preuves textuelles suffisantes dans le périmètre qualifié | Identité proposée automatiquement, preuves accessibles | Enregistrer ou vérifier |
| Identité confirmée par l'utilisateur | Confirmation humaine applicable à ces preuves | Corriger ou retirer la confirmation |
| Plusieurs impressions plausibles | À vérifier, différences entre candidats | Comparer et choisir si déterminable |
| Preuves insuffisantes ou contradictoires | Non identifiée/à vérifier, raison précise | Compléter, joindre/recadrer une photo, ou conserver non résolu |
| Référence non chargée | Référentiel local incomplet, si cette cause est établie | Charger l'extension ou lancer la recherche existante |
| Recherche distante sans résultat | Référence non trouvée dans le périmètre interrogé | Recherche manuelle ; ne pas conclure à une absence mondiale |
| Langue/impression hors périmètre | Périmètre non couvert | Recherche dans la locale adaptée ou maintien non résolu |
| Lot ou scellé | Lot/coffret, aucune identité unitaire effective | Conserver et suivre comme lot |
| Service OCR indisponible | Analyse indisponible, annonce conservée | Saisie manuelle ou réessai |
| Identité correcte mais attributs/cote insuffisants | Identité connue, estimation limitée ou indisponible | Compléter les attributs ou la cote |

La confirmation d'ajout d'une annonce, la correction d'un champ et la confirmation de son identité sont des actions distinctes. Une suggestion préremplie ne devient pas une validation humaine par simple enregistrement.

### 3.2 Invariants bloquants

- Aucun lot/scellé ne reçoit une identité unitaire effective, même si une carte principale est reconnaissable. Une erreur de classification peut être corrigée explicitement et auditée avant le choix d'une carte.
- Le titre et la description ne sont jamais remplacés par l'OCR. Une contradiction significative avec la photo est exposée et bloque la nouvelle acceptation automatique.
- Un champ inconnu reste inconnu. Langue du vendeur, langue du site et locale du catalogue ne prouvent pas la langue de l'exemplaire.
- Une langue proposée depuis des fragments discriminants de la carte reste indicative jusqu'à confirmation en J1. Le contrat distingue proposition, déclaration explicite et confirmation ; il ne transforme pas une sortie Tesseract `fra+eng` en détection de langue.
- Une identité de catalogue situe une carte dans une extension ; une extension inférée depuis le candidat n'est pas une mention d'extension observée dans l'annonce.
- Nom, suffixes significatifs (`V`, `VMAX`, `GX`, `EX`/`ex`), numéro et extension contribuent à l'identité. Langue de l'exemplaire, finition, édition et état ont leurs preuves propres. Une traduction n'est pas automatiquement une autre impression équivalente.
- `Near Mint` extrait du texte est un état déclaré. Une identité ou une photo générique ne vérifie ni état, ni finition, ni authenticité.
- Un score historique n'est pas un pourcentage de probabilité. Conserver sa compatibilité, afficher son sens, séparer toute probabilité calibrée future.
- Une suggestion OCR, une réparation ou un résultat visuel n'autorise pas à lui seul une nouvelle acceptation automatique en J1. Une identité déjà justifiée indépendamment par le texte conserve son traitement, sauf contradiction significative.
- Préserver `first_seen_at`, décisions humaines applicables, audit, clés étrangères, sauvegardes et calculs monétaires en centimes/bps.
- Traitement des photos et inférence exclusivement locaux. Aucun poids ni image n'est téléchargé pendant une identification hors ligne. Les références publiques peuvent être enrichies par les mécanismes autorisés ; aucune photo ni texte d'annonce n'est envoyé à TCGdex.
- Tests hermétiques : aucun accès distant, y compris téléchargement de modèle, d'image de référence ou requête indirecte depuis un worker.
- Carte gradée : séparer identité de la carte, certificateur, note et numéro de certificat éventuel. PSA/PCA et notes différentes ne sont pas interchangeables ; une cote non gradée ne valorise pas automatiquement un exemplaire gradé.
- Une annonce retirée/inactive n'est pas une vente conclue ; un prix affiché, une enchère en cours ou un montant d'offre négociée non connu ne sont pas un prix de vente réalisé.
- Aucune marge calculée sur une identité incertaine. Après confirmation, les données de prix et les frais doivent encore être admissibles ; ni identité confirmée ni estimation ne garantissent la revente.

## 4. Architecture cible minimale

Réutiliser les modules actuels et extraire uniquement les responsabilités nécessaires :

1. **Observations** : texte brut, champs structurés et leur origine, indices photographiques liés à une image/région. Un champ peut porter plusieurs observations contradictoires.
2. **Qualification produit** : unitaire, lot/scellé ou quantité incertaine. Séparer les objets photographiés des objets effectivement vendus.
3. **Extraction** : noms, numéros, extensions et attributs, sans décision d'identité.
4. **Récupération** : union dédupliquée des candidats structurés et lexicaux, puis des candidats visuels expérimentaux si retenus.
5. **Vérification/classement** : accords, contradictions, couverture et qualités de preuve. Un champ absent n'est pas une contradiction.
6. **Décision commune** : règles d'acceptation, abstention, priorité des décisions humaines et contrôle des révisions.
7. **Projection UI/export/rentabilité** : même identité effective et mêmes restrictions dans tous les parcours.
8. **Recherche de marché** : tâches bornées rattachées à l'identité et à sa révision ; lecture des données locales puis des sources activées, sans bloquer l'enregistrement.
9. **Comparabilité et estimation** : sélection expliquée des preuves, séparation offres/transactions/cotes, scénario de revente et frais explicites.

Le contrat d'une preuve doit pouvoir porter : champ, valeur brute, valeur normalisée, origine, extrait ou image/région, version d'extracteur, qualité technique et éventuelle transformation. Distinguer extrait, déclaré, inféré, corrigé et vérifié. Une confiance qualitative n'est pas une probabilité.

Pour l'OCR spatial de T06/T07, relier chaque fragment à l'image, à l'objet/région et à sa boîte englobante. Documenter les repères photo orientée EXIF, carte redressée et sous-région OCR ainsi que les transformations entre eux. Une hypothèse de numéro référence ses fragments d'origine, les opérations appliquées et son rang ; elle ne remplace jamais la lecture brute. Ces ajouts restent compatibles avec les consommateurs actuels de `recognized.names` et `recognized.numbers` et n'accordent aucune autorité supplémentaire à la provenance OCR.

Conserver une représentation transitoire en mémoire pour l'OCR éphémère. La persistance durable des preuves visuelles est un mode explicite distinct, décrit en T04. Ne jamais conserver silencieusement toutes les images analysées.

### 4.1 Workflow d'exécution de la capture aux comparaisons

**Statut : cible à implémenter et à recetter**, consolidée le 8 novembre 2026. Cette section fixe l'ordre d'exécution utilisateur ; elle ne correspond pas à l'ordre de développement des lots de §5. Réutiliser les points d'entrée/services existants et la décision commune, sans imposer un nouveau moteur de workflow.

Deux recherches ont des rôles distincts : **rechercher la référence de la carte dans TCGdex** sert à proposer son identité et les champs du formulaire ; **rechercher des offres/prix** utilise ensuite l'identité effective enregistrée et ses attributs admissibles. La première recherche ne dépend pas d'un formulaire déjà entièrement rempli.

| Étape | Déclencheur et traitement | Sortie et condition de passage | Responsable / lots |
|---|---|---|---|
| W01 — Capturer l'annonce | Navigation réelle et capture des données déjà disponibles : titre, description, URL, prix, vendeur public et photos accessibles. | Capture conservée dans l'extension ; titre distinct du nom de carte. Aucune annonce écrite en base. | Extension, T08.1 |
| W02 — Préparer les observations | « Envoyer à Pokébourse », ouverture d'une prévisualisation ou réanalyse : ouvrir rapidement l'écran de progression, valider entrées/provenances, extraire les indices textuels et qualifier unitaire/lot. Séparer les erreurs financières des preuves d'identité. | Valeurs brutes conservées, indices exploitables et inconnus identifiés. Prix/port/devise absents ou invalides n'empêchent pas W03 à W08 ; un lot sort du rapprochement unitaire. | Adaptateurs de capture, détecteur, T02/T03/T08 |
| W03 — Préparer la photo choisie | Pour le parcours avec analyse photo : récupération autorisée par l'extension ou téléversement, validation, orientation, localisation/recadrage et redressement. | Image/région identifiée, limites vérifiées ; si nécessaire choix manuel. Sans image exploitable, poursuite textuelle possible avec diagnostic. | Extension, géométrie OCR, T06.1/T08.2 |
| W04 — Lire la carte | Photo/région prête ou commande explicite de réanalyse de l'image. Exécuter l'OCR local borné et reconstruire fragments, noms, numéros et indices de langue. | Lectures originales et hypothèses avec provenance ; aucun champ confirmé, aucun texte vendeur remplacé. En mode texte seul, étape sautée explicitement. | `/ocr/suggestions`, T06/T07 |
| W05 — Rechercher les références | Indices textuels/OCR disponibles et validés : recherches structurées puis replis lexicaux bornés dans le catalogue local, union et classement par la décision commune. | Candidats compatibles ou contradictoires distingués, couverture/limites et critères utilisés visibles. Aucun appel marketplace ni téléchargement TCGdex depuis le matcher/OCR. | Matcher, recherche locale, T03/T05/T07 |
| W06 — Proposer dans le formulaire | Résultat W05 et proposition admissible ou choix de candidat : projeter nom canonique, extension de référence, numéro et suggestion de langue séparée. | Champs proposés avec origine, photo/référence comparables ; plusieurs candidats ne sont pas fusionnés en une identité. Saisies humaines préservées. | Prévisualisation, T08.1/T08.2 |
| W07 — Contrôler les champs | Chaque projection ou correction : validation de forme, cohérence entre champs/référence et diagnostic T08.3. | Propositions exploitables ou erreurs expliquées ; recherche partielle et correction accessibles. Aucun gain de confiance par recopie des propriétés du candidat. | Validation serveur et décision commune, T08.3 |
| W08 — Résoudre le choix | Vérification de la référence et des attributs lorsque requise. Un titre explicitement faux peut être qualifié comme tel par une résolution humaine motivée, sans modifier l'original. Préparer la sélection/confirmation liée aux preuves courantes, distincte de l'ajout. | Choix applicable ou annonce laissée non résolue ; pas de choix forcé parmi des références erronées. La prévisualisation ne crée ni annonce provisoire ni review persistante ; les règles T03/T04 restent applicables. | Prévisualisation/résolution, T03/T08/T09 |
| W09 — Enregistrer | Action finale d'ajout : revalider référence, attributs, preuves et révision, puis ingestion/déduplication et application du choix humain dans une unité atomique. Vérifier ici les champs requis par le contrat de stockage. | Même identité effective sur la fiche, confirmation explicite conservée, `first_seen_at` préservé. Inconnus d'identité enregistrables avec représentation dédiée ; montants invalides refusés sans perdre les résultats. Aucun OCR/réseau dans la transaction. | `/previsualiser-capture/confirmer`, ingestion/résolution/reviews, T08/T09 |
| W10 — Rechercher le marché | Après commit W09 et identité admissible : une demande dédupliquée, lecture des données locales puis sources autorisées/activées. | État en attente/en cours/résultat partiel/indisponible avec date et portée ; aucun prix promis en l'absence de source adaptée. | Worker et orchestration T15/T16 |
| W11 — Comparer et estimer | Résultats W10 : filtrer les comparables selon identité/version/langue/finition/état/gradation nécessaires, puis calculer seulement si les données sont admissibles. | Offres, ventes documentées et cotes séparées ; attributs manquants et limites visibles ; marge en centimes/bps ou absence d'estimation motivée. | T09/T17/T18 |

Le formulaire peut déjà présenter les champs capturés avant l'OCR ; **son nom canonique et son extension proposés proviennent de W05/W06**. Les étapes W02 à W08 restent sans écriture durable d'annonce ni job de marché ; la conservation explicite T04 et les actions dédiées d'enrichissement gardent leurs contrats distincts. Les estimations indicatives locales déjà disponibles conservent les restrictions T09 ; elles ne constituent ni une recherche marketplace W10 ni une confirmation d'identité. Une confirmation préparée dans la prévisualisation est revalidée et enregistrée avec l'ajout final, sans faire passer un simple clic d'ajout pour une confirmation d'identité.

### 4.2 Reprises, branches d'erreur et absence de boucles

- **Correction de nom/numéro/extension/langue :** retour W02 puis W05 à W07 avec les indices OCR encore valides pour la même image/configuration ; pas de nouvel OCR automatique sur un simple changement de champ. Conserver les règles T03 pour le réexamen d'un choix humain.
- **Autre photo, nouveau cadrage ou demande explicite de relire :** retour W03/W04, nouvelle référence de requête/image ; réponses anciennes écartées et contrôle W07 repris.
- **Plusieurs références ou contradiction :** conserver W05/W06 en diagnostic et demander le choix/la correction W08 ; pas d'enregistrement comme identité certaine ni de passage financier fondé sur cette seule proposition. Une annonce non résolue reste enregistrable selon son contrat.
- **Titre explicitement faux :** permettre en W08 de choisir une référence du diagnostic et de déclarer, avec motif, quelle observation est erronée. Conserver les valeurs brutes et le désaccord dans l'audit ; revalider le choix et les autres attributs. Cette résolution humaine ne transforme pas des champs incohérents en concordance automatique ni ne prouve la langue, la finition ou l'état.
- **Référentiel local incomplet établi :** proposer l'action d'enrichissement T05, distincte de la prévisualisation ; suivre sa clé de critères/locale et son résultat sans imposer une annonce identifiée préalable. Après succès, relancer W05 avec les lectures encore valides et vérifier les versions ; aucun téléchargement implicite ni nouvelle lecture photo systématique. Réseau indisponible : garder les candidats locaux et le formulaire, avec réessai explicite.
- **Lot/scellé, photo absente/illisible, OCR indisponible ou aucun candidat :** état et action adaptés ; parcours lot ou saisie/texte/non résolu disponibles. Un échec OCR ne supprime pas une identité textuelle indépendamment admissible et non contredite.
- **Modification après enregistrement :** revalider W07/W08/W09 ; invalider les résultats de marché devenus inapplicables et déclencher W10 seulement pour la nouvelle identité/révision admissible, avec déduplication et rejet des anciens résultats.
- **Préremplissage ou rechargement seul :** aucune boucle W06 → W05, aucun OCR répété ni recherche marketplace supplémentaire. Les reprises sont déclenchées par une action ou un changement pertinent, tracées par requête/image, empreinte des preuves et versions ; les bornes et délais de la procédure OCR restent applicables.
- **Fermeture du popup ou interruption :** la capture et les corrections restent récupérables, l'exécution et les résultats ne dépendent pas du maintien du popup ouvert. Distinguer reprise d'un résultat encore valide et nouvelle tentative ; une photo téléversée éphémère devenue indisponible doit être demandée à nouveau, jamais prétendue conservée. Une nouvelle version du catalogue relance si nécessaire W05, sans rejouer W04 à lectures inchangées.

**Recette du workflow :** les tests T13 vérifient les transitions, résultats et effets de bord de W01 à W11, y compris les étapes sautées, les retours et les erreurs. Une réussite du matcher isolé ou de l'OCR isolé ne valide pas cet enchaînement.

### 4.3 Revue d'adéquation au besoin — 8 novembre 2026

**Verdict de conception : adapté après les précisions ci-dessous ; fonctionnement complet non validé.** Revue en lecture seule du code et des contrats, sans appel marketplace ni changement du moteur. Les écarts observés dans le code restent des travaux à réaliser, pas des correctifs livrés par ce tasking.

| Point contrôlé | Écart ou risque identifié | Adaptation et preuve attendue |
|---|---|---|
| Identifier avant de connaître tous les prix/attributs | `_analyse()` parse prix/port avant le matcher ; une saisie financière invalide peut empêcher l'identification. | W02/T08.3 : erreurs indépendantes, recherche et OCR disponibles ; correction du prix sans perte de candidat ni nouvel OCR. |
| Continuer après fermeture du popup | `runAutomaticPreview()` attend actuellement l'OCR avant d'ouvrir la prévisualisation. | W02/§4.2/T08.2 : écran de progression disponible rapidement, propriétaire de l'exécution défini, capture/reprise testées sans popup maintenu ouvert. |
| Résoudre un titre vendeur faux | Bloquer toute confirmation en présence d'un conflit tout en préservant le titre laisserait l'utilisateur sans issue. | W08/T08.3 : résolution humaine motivée depuis le diagnostic, titre et désaccord conservés ; aucune levée automatique du conflit. |
| Conserver le choix de carte avant/après ajout | `confirm_capture()` réimporte les champs ; `save_review()` exige une annonce persistée. Un choix préparé en prévisualisation ne se conserve pas par le seul préremplissage. | W08/W09/T09 : sélection transitoire revalidée puis identité et décision appliquées atomiquement, doublon/concurrence/rollback testés. |
| Enregistrer sans inventer de langue | Le formulaire impose une langue ; `CatalogItem` possède encore le défaut `fr`. | T08.2/W09 : représentation explicite de l'inconnu commune à tous les chemins, pas de défaut français appliqué aux captures inconnues ; migration additive si nécessaire. |
| Rechercher les références absentes | Le matcher est local ; l'enrichissement est une action séparée, à relier au formulaire/résultat sans confusion avec la recherche de prix. | §4.2/T05/T08.2 : suivi de la demande, reprise de W05 et critères conservés ; panne distante sans perte de la capture. |
| Déclencher les comparaisons après ajout | Une interruption entre l'ajout et sa mise en file pourrait perdre la recherche de marché ; les sources requises peuvent aussi être absentes. | T16 : reprise durable et dédupliquée après commit ; capacités de T15 affichées. Absence de source de prix distincte d'un échec d'identification. |

Les tests d'acceptation de T13 doivent démontrer ces adaptations sur le cas §1.3 et ses variantes. La matrice T15 datée du 3 novembre ne démontre pas une source automatique d'offres/ventes configurée : une identification correcte permet la suite du parcours, sans garantir ces données de marché. La comparaison directe d'images reste une expérience T11 ; ce workflow nominal repose sur lecture photo puis rapprochement catalogue.

### 4.4 Entrée des collecteurs marketplace et OCR en arrière-plan

Le périmètre comprend explicitement les collecteurs qui parcourent Vinted, Leboncoin, eBay et Wallapop, y compris pagination/curseur ou défilement DOM selon le mode réellement utilisé. Leur code, celui des normaliseurs et celui du worker doivent être adaptés en **T19**, avec la capture Chrome et son service worker quand le contrat change. Suivre la [spécification T19](docs/identification/T19_COLLECTE_OCR.md) ; une source non activée ne l'est pas implicitement par ces travaux.

W01–W09 décrit le parcours interactif sans écriture avant ajout. Une veille utilise **C01 collecte → C02 ingestion/conservation → C03 file OCR durable → C04 lecture et rapprochement commun → C05 publication avec contrôle des révisions → C06 fiche/confirmation/comparaisons**. Elle réutilise les composants purs W03–W08 sans imposer une prévisualisation avant chaque ingestion. OCR et réseau restent hors transaction ; une analyse lente ne bloque pas les autres veilles. L'absence de photo conserve l'annonce et ses indices textuels.

Le contrôle de concurrence OCR doit être commun à l'app et au worker, les jobs dédupliqués et les confirmations/`first_seen_at` préservés. Le job 3 reprend explicitement ce raccordement après les jobs champs et composants OCR ; l'extension seule ne valide pas les entrées de collecte. Les erreurs/capacités manquantes sont suivies dans [tracker.md](tracker.md).

## 5. Ordre d'exécution

| Lot | Priorité | Dépendances | Résultat |
|---|---|---|---|
| T00 — Inventaire et point de départ | P0 | Aucune | Périmètre, divergences et état initial connus |
| T01 — Vérité terrain et comparateur | P0 | T00 pour outillage ; T04 pour preuves visuelles durables | Premières mesures reproductibles |
| T02 — Corrections déterministes | P0 | T00 ; mesure avec T01 | Lots, langues et états fiables sur les cas ciblés |
| T03 — Contrat de preuves et décision commune | P0 | T00, T02 | Même décision de tous les points d'entrée |
| T04 — Preuves visuelles et annotations | P0 | Outillage T01, T03 ; ne pas attendre les volumes d’annotation | Benchmark photos et confirmations reproductibles |
| T05 — Alias et couverture du référentiel | P0 | T02, T03 | Recherche et enrichissement explicables |
| T06 — Cadrage, OCR spatial et indices de langue | P0 pour J1 | T04, T05 | Nom/numéro lus sur la carte, langue proposée si étayée, gain mesuré |
| T07 — Hypothèses de numéro et rapprochement catalogue | P0 pour J1 | T03, T05, T06 | Candidats et champs canoniques proposés, alternatives auditables |
| T08 — Parcours utilisateur et capture | P0 | T08.1/T08.3 moteur actuel : T03/T05 ; intégration OCR T08.2/T08.3 : T06/T07 + contrats T09 | Titre/nom séparés, champs revalidés, capture → confirmation → enregistrement cohérents |
| T09 — Persistance et usage métier | P0 | Contrats : T03/T04/T05 ; intégration conjointe avec T08.2, sans attente circulaire | Décisions durables et rentabilité admissible |
| T10 — Qualification indépendante | P0 | T01 à T09 | Rapport de qualité et périmètre d'automatisation |
| T11 — Vision et fusion expérimentales | Conditionnel | T10 et besoin visuel démontré | Gain démontré ou abandon motivé |
| T12 — Livraison et exploitation | P0 | Outillage/fixtures T01, T02–T09 et T19 pour J1 ; qualification complète T01/T10 pour J2 ; T14–T18 pour J3 | Version utilisable, documentée et réversible |
| T14 — Cartes non gradées et gradées PSA/PCA | P0 pour J3 | T03, T06, T08, T09 | Attributs et confirmation adaptés aux deux parcours |
| T15 — Capacités réelles des sources de prix | P0 pour J3 | T00 ; indépendant des améliorations OCR | Matrice offres/ventes/cotes, accès et limites vérifiés |
| T16 — Recherche de marché après identification | P0 pour J3 | T03, T09, T14, T15 | Orchestration automatique, dédupliquée et révisable |
| T17 — Comparables et preuves de prix | P0 pour J3 | T14, T15, T16 | Offres, ventes et cotes séparées et justifiées |
| T18 — Estimation, marge et parcours complet | P0 pour J3 | T17, choix produit dépendants résolus | Scénario expliqué, recette et limites visibles |
| T19 — Collecteurs marketplace et OCR de collecte | P0 pour J1 étendu | T19.1 : T03/T05 ; T19.2/T19.3 : T06/T07/T08/T09 | Parcours/images fiables, file OCR commune et fiche/validation cohérentes |

Commencer T01 sur les données disponibles pendant les corrections. Ne pas attendre mille annotations pour corriger un bug déterministe. Ne pas attendre T11 pour livrer J1.

T08.1 et les contrôles T08.3 du moteur actuel sont acquis ; les préserver sans attendre T06/T07. Livrer ensuite T06/T07 avec leur raccordement T08.2 et la recette §1.3 : le lot « Améliorer l'OCR » ne peut pas être présenté comme résolvant le parcours de capture après la seule amélioration des lectures techniques.

T13 reste la matrice de recette de tous les lots, y compris J3 ; sa numérotation ne désigne pas une étape d'implémentation. Réactualiser la matrice T15 déjà établie avant toute activation dépendante ; l’absence d’accès aux ventes y est explicite. J3 peut avancer sans T11, en conservant les confirmations requises en J1 ; il ne dépend d'aucun nouveau modèle visuel imposé.

### T00 — Inventorier et figer le point de départ

**Skills, tests et intégrations :** [fiche T00](docs/identification/PLAN_VALIDATION_LOTS.md#t00).

- [x] Relever les modifications de travail, versions, migrations et tests existants ; ne pas écraser les travaux en cours.
- [x] Exécuter les tests Docker sur les bases temporaires et consigner les échecs initiaux sans les attribuer au chantier.
- [x] Auditer les entrées : URL, extension, JSONL, saisie, collecte, prévisualisation, fiche, réidentification, worker et validation.
- [x] Comparer code, documentation et Compose : autorisations réseau réellement actives, persistance des photos, limites OCR, locales et sources de vérité.
- [x] Inventorier le catalogue sur copie/sauvegarde : cartes/extensions/locales, fiches partielles, images disponibles et manquantes. Ne pas modifier la base réelle pour établir cet inventaire.
- [x] Figer la version initiale, le catalogue et les rapports existants avant toute comparaison.

**Livrable :** rapport initial versionné, matrice des entrées et lacunes ; liste des acquis à réutiliser. **Acceptation :** aucune référence absente n'est présentée comme un défaut OCR sans vérification.

**Livraison T00 — 3 novembre 2026 :** inventaire consigné dans [validation/ocr/evaluation/STATUS_T00_T01.md](validation/ocr/evaluation/STATUS_T00_T01.md) avec manifeste figé, inventaire catalogue sur sauvegarde cohérente et baseline tests. Actualisation du soir : la suite complète est verte sur l'état courant (749 réussites, 0 échec) ; les 21 échecs historiques consignés au contrôle initial sont résolus par la livraison T03. Verdict : terminé comme inventaire, avec la réserve que l'état antérieur aux changements déjà présents n'est pas reconstituable.

### T01 — Construire la vérité terrain et le benchmark hors ligne

**Skills, tests et intégrations :** [fiche T01](docs/identification/PLAN_VALIDATION_LOTS.md#t01).

- [x] Reprendre les 30 annonces existantes : conserver titre ET description disponibles, photos exactes, provenance et données manquantes. Ne pas compléter les absences par invention.
- [ ] Annoter indépendamment type de produit, identité/impression déterminable, présence dans le catalogue figé, attributs observables, suffisance texte seul puis apport des images.
- [x] Permettre une identité externe documentée si la carte manque au référentiel, sans lui fabriquer un ID TCGdex ; un ID absent n'est pas une mauvaise prédiction exacte.
- [ ] Séparer annotation indépendante et décision appliquée. Rechercher au-delà des candidats automatiques, arbitrer les désaccords, conserver les lectures initiales.
- [x] Versionner un manifeste avec empreintes, catalogue, règles, moteur OCR/langues, configurations, partitions et groupes de doublons ; y joindre les images via T04.
- [x] Séparer acquisition réseau manuelle et rejeu strictement local. Le rejeu refuse un artefact manquant et ne le télécharge pas implicitement.
- [x] Produire des rapports texte seul, OCR seul, texte+OCR ; ajouter ensuite les variantes de cadrage et de vision sans changer les labels.
- [ ] Étendre à 300 cas diagnostiques, dont au moins 20 % en double lecture indépendante, puis environ 1 000 cas pour les comparaisons. Réutiliser le pilote existant ; ne pas déclarer ces volumes acquis.
- [ ] Constituer séparément un audit aléatoire représentatif du flux local admissible et un jeu difficile. Documenter les probabilités de sélection ; ne pas assimiler le flux local à tout le marché.

**Livrable :** jeu de développement annoté, protocole, comparateur et rapport initial. **Acceptation :** les compteurs `identified` sont distingués des identités correctes ; toutes les métriques donnent leur dénominateur et leurs exclusions.

**Livraison partielle T01 — 3 novembre 2026 :** manifeste figé, squelette de labels (30 URL, 0 annotation préremplie), comparateur, rapport initial à 0 annotation et **rejeu strictement local hermétique** (`validation/ocr/marketplaces/replay_local.py`, tests dédiés) livrés ; le rejeu du 3 novembre reproduit le rapport historique du 2 novembre avec zéro changement de statut ou d'identité (voir STATUS_T00_T01.md). **Non terminé :** les annotations humaines indépendantes, la double lecture/arbitrage, le rapport de justesse, les volumes 300/1 000, l'audit aléatoire et la résolution des quasi-doublons restent ouverts ; aucun volume n'est déclaré acquis.

### T02 — Corriger les règles de détection

**Skills, tests et intégrations :** [fiche T02](docs/identification/PLAN_VALIDATION_LOTS.md#t02).

- [x] Reconnaître `nearmint`, `near-mint`, `near mint` et variantes d'espaces/casse ; éviter que `mint` interne annule `near mint`.
- [x] Conserver l'état déclaré brut. Ne pas convertir automatiquement « très bon état », « neuf » ou une note de gradation en état physique vérifié.
- [x] Résoudre les collisions `EX` état/suffixe de carte avec le contexte ; préserver les suffixes discriminants.
- [x] Retirer `en` isolé comme preuve générale d'anglais. Réserver les codes courts à des champs ou contextes explicites ; `VO` seul laisse la langue inconnue.
- [x] Détecter les langues multiples ou contradictoires sans choisir arbitrairement le premier motif. La langue du texte français ne suffit pas à déduire celle de la carte.
- [x] Détecter cadeaux et quantités réellement incluses : « vendu avec 3 cartes en plus », « + 3 cartes offertes », formulations équivalentes retenues par les fixtures.
- [x] Traiter les contre-exemples : « sans lot », « pas un lot », « 3 photos », « avec protection », « une carte au choix parmi 3 ». Une vente au choix ne justifie pas une identité unique de l'annonce.
- [x] Ne pas interpréter le dénominateur, un numéro de série ou un nom d'extension comme une quantité ; ne pas classer « Gem Pack 2 » comme produit scellé sur le seul mot `pack` hors contexte.
- [x] Ajouter les mêmes contre-exemples côté extension et backend ; le backend reste l'autorité de décision.

**Fichiers :** `app/identification/detector.py`, `matcher.py`, modèles, `extension/content/content.js`, suites d'identification et extension. **Acceptation :** lignes T13 du périmètre déterministe T02 passantes, sans baisse des seuils pour masquer les erreurs ; la recette globale du parcours reste attachée au jalon livré.

**Livraison T02 — 2 novembre 2026 :** règles déterministes réalisées et validées sur les fixtures de leur périmètre. `languages` conserve les valeurs explicites reconnues (français, anglais, japonais), `language` reste inconnu en cas de conflit et le matcher s'abstient ; le diagnostic distingue ce conflit d'une référence absente. `condition_raw` conserve l'extrait déclaré exact, sans modifier les équivalences historiques ni vérifier l'état physique. Le contexte de produit est exigé pour `pack` ; les noms d'extensions effectivement présents dans le cache et les numéros étiquetés comme séries sont protégés. Aucun alias « Gem Pack 2 », réparation OCR, changement de seuil, migration, dépendance ou appel distant n'a été ajouté.

**Fichiers de cette livraison :** `app/identification/{detector,models,matcher,diagnostics}.py`, `extension/content/content.js`, `tests/test_identification_reliability.py`, `tests/test_chrome_extension.py`, `tests/test_pipeline_integration.py`, `tests/test_lexical_identification.py`, `docs/IDENTIFICATION_LEXICALE.md`, `extension/README.md` et ce tasking. Les modifications du premier lot T02 restent conservées.

**Vérification Docker :** 297 tests ciblés passants (identification, fiabilité, numéros, lexical/diagnostic, extension, pipeline, prévisualisation, validations humaines et annotation), puis `docker compose run --rm app pytest` : **713 passants**, un avertissement de dépréciation FastAPI/Starlette/httpx déjà présent. Les cas comprennent ingestion et réidentification de lots sans identité unitaire/cote, langues contradictoires et exemple « Evoli V 0113/15 gempack 2 nearmint » conservé non résolu dans le cache de test incomplet.

**Limites et suite :** validation des lignes T13 relevant des règles T02 ; la recette T13 entière, qui dépend des autres lots, n'est pas déclarée acquise. Les règles restent lexicales et bornées aux formulations testées, sans mesure globale de précision. L'extrait d'état et les langues sont exposés dans le résultat compatible ; le contrat de preuves durable complet relève de T03. Les annotations indépendantes et la qualification restent à établir en T01/T10. Aucun autre lot n'est lancé par cette livraison.

### T03 — Séparer preuves, recherche et acceptation

**Skills, tests et intégrations :** [fiche T03](docs/identification/PLAN_VALIDATION_LOTS.md#t03).

- [x] Ajouter un contrat de preuves compatible avec les snapshots existants ; conserver les observations concurrentes et la provenance après fusion.
- [x] Retirer la dépendance à la concaténation de textes comme seule trace d'origine ; distinguer champs saisis, extraits, préremplis et explicitement confirmés.
- [x] Conserver les contrats JSON/JSONL existants avec ajouts compatibles et validation des nouveaux champs. Une provenance déclarée par le client ne lui confère pas une autorité humaine.
- [x] Centraliser les règles réutilisées par prévisualisation, import, collecte, fiche et réidentification. Séparer la pure proposition de l'application transactionnelle à une annonce.
- [x] Exposer les motifs : preuve insuffisante, contradiction, plusieurs candidats, lot, référence locale absente, périmètre non couvert, service indisponible.
- [x] Conserver les candidats utiles mais contradictoires dans un espace de diagnostic explicitement marqué, sans les promouvoir parmi les suggestions admissibles ni masquer leur contradiction.
- [x] Vérifier en particulier qu'un nom/numéro apporté par OCR ne transforme pas silencieusement une proposition en confirmation humaine ou en nouvelle acceptation automatique J1.
- [x] Introduire des versions de pipeline/normalisation et une politique explicite de réexamen ; aucune mise à jour ne supprime l'audit.

**Fichiers :** `models.py`, `pipeline.py`, `matcher.py`, `resolution.py`, `reviews.py`, `app/listing_preview.py`, `capture_preview.py`, `manual_listing.py`, `catalog.py`, services d'ingestion. **Acceptation :** à observations et versions identiques, mêmes candidats/statut/motifs sur tous les points d'entrée ; une prévisualisation ne fait aucune écriture.

**Livraison T03 — 3 novembre 2026 :** contrat optionnel `identity_evidence`, observations brutes/normalisées avec provenance, proposition locale commune et motifs structurés. Les candidats contradictoires sont séparés des suggestions admissibles. L'OCR et le préremplissage restent indicatifs, y compris après réanalyse/enregistrement ; la confirmation d'identité reste une action distincte. La migration additive `0022_identification_observations.sql` conserve les preuves/snapshots et leurs versions sans supprimer l'audit. Les empreintes historiques restent stables à preuves égales, les changements explicites de preuves demandent réexamen. Le pilote textuel filtre les attributs seulement indicatifs et garde la provenance dans l'audit.

**Validation :** 386 tests ciblés Docker ; suite complète et recette Chromium locale détaillées dans [le guide T03](docs/identification/T03_EVIDENCE.md). Les cas couvrent la cohérence entre façades, l'absence d'écriture en prévisualisation, la réingestion partielle, les confirmations et les cotes existantes. Aucun seuil abaissé, dépendance ajoutée ou accès distant nouveau. Les essais utilisent uniquement des bases temporaires ; l'instance réelle n'est pas redémarrée par ce lot.

**Dépendances et limites :** réalisé indépendamment de la finalisation de T00/T01 à la demande de l'utilisateur. Leur inventaire/annotation et leur benchmark restent à confronter à la version `evidence-rules-v1`. La conservation des images relève de T04, la qualification statistique de T10 ; ni leurs critères, ni la recette T13 globale ne sont déclarés acquis. Le contrat, les fichiers modifiés et la politique de réexamen sont décrits dans le guide T03.

### T04 — Rendre les preuves visuelles reproductibles

**Skills, tests et intégrations :** [fiche T04](docs/identification/PLAN_VALIDATION_LOTS.md#t04).

- [x] Garder l'OCR courant éphémère par défaut. Créer un mode explicite de conservation locale pour benchmark/annotation ou confirmation durable sur photo, distinct d'une simple analyse.
- [x] Nettoyer les métadonnées ; stocker les images dans un espace contrôlé persistant, non dans une URL publique ou un répertoire temporaire de conteneur.
- [x] Rattacher chaque preuve à ses octets exacts par empreinte, à une observation et à la version des transformations ; identifier image et région pour chaque lecture.
- [x] Prévoir stockage atomique, déduplication, quotas, suppression des temporaires/orphelins, rétention et purge. Une photo peut contenir des contacts : limiter l'archivage aux preuves nécessaires et ne pas l'exporter par défaut.
- [x] Étendre le pilote et l'export pour les provenances `image` et `both`, en conservant les anciennes annotations textuelles et leurs règles d'éligibilité.
- [x] Sauvegarder/restaurer ensemble base, manifeste et preuves ; tester la vérification d'intégrité et les fichiers manquants.
- [x] Si la preuve durable n'est pas conservée, ne pas créer de label visuel reproductible ; signaler les limites de la confirmation opérationnelle. Une preuve supprimée/indisponible rend son label visuel inéligible et demande un réexamen des décisions qui en dépendent.
- [x] Une simple analyse ne change pas l'identité. Remplacement explicite d'une preuve, ajout de contradiction, décision et invalidation sont des opérations distinctes et auditables.

**Fichiers :** `ocr.py`, `reviews.py`, `dataset.py`, `annotation_pilot.py`, stockage et `backups.py`. **Acceptation :** scénario sauvegarde → restauration → rejeu identique ; fonctionnement éphémère sans persistance implicite ; aucun accès à un fichier hors de l'espace de preuves.

**Réalisé (3 novembre 2026) :** migrations `0023_visual_evidence.sql` (tables `listing_image_evidence` + lectures régionnées, reconstruction additive des reviews), `app/identification/evidence_store.py` (stockage atomique dédupliqué sans EXIF, quota, statuts présent/manquant/corrompu/supprimé, purges, sauvegarde sidecar dans `backups.py`), provenances `image`/`both` dans `reviews.py` et éligibilité visuelle + `needs_reexamination` dans `dataset.py` (manifeste inchangé `identity-pilot-v2`). Couvert par `tests/test_visual_evidence.py`.

### T05 — Alias, couverture et langues du référentiel

**Skills, tests et intégrations :** [fiche T05](docs/identification/PLAN_VALIDATION_LOTS.md#t05).

- [x] Alimenter les noms depuis le référentiel déjà utilisé ; créer des alias contrôlés portant cible, langue/périmètre, provenance et version.
- [x] Conserver les collisions d'alias et les fautes approchées comme suggestions. Ne pas utiliser une correspondance floue unique comme preuve exacte.
- [ ] Vérifier la cible de « gempack 2 » sur une source de référence et les photos disponibles avant de l'ajouter ; ne pas inventer une équivalence française ou un ID attendu pour le cas B.
- [x] Distinguer répertoire d'extensions, manifestes, cartes détaillées et images ; afficher ce qui manque et ce qui est effectivement couvert.
- [x] Réutiliser les files `research.py`/`tcgdex/sync.py`, déduplication, pause/reprise, erreurs et cadence. Pas de seconde file ad hoc, pas d'appel réseau depuis le matcher.
- [x] Étendre le modèle pour isoler identité et localisations. Préserver les identifiants SQLite, relations humaines, liens Cardmarket et anciennes clés externes lors de la migration.
- [x] Charger les locales utiles à la demande, sans supposer que les IDs, numéros ou impressions coïncident entre langues/régions. Les rapprochements inter-impressions exigent un lien vérifié séparé.
- [x] Versionner périmètres et locales réellement pris en charge. Une locale ajoutée n'active pas automatiquement son identification ni sa rentabilité.
- [x] Conserver la langue de l'exemplaire inconnue si elle n'est pas observée ; la langue d'une fiche de référence est une propriété distincte.

**Fichiers :** `tcgdex/cache.py`, client/modèles/sync, recherche locale, `identification/research.py`, alias Cardmarket et migrations. **Acceptation :** ajout d'une localisation sans écrasement d'une autre ; cas absent conservé et enrichissable ; confirmations et liaisons financières préservées.

**Réalisé (3 novembre 2026) :** migrations `0024_reference_localizations.sql` (unicité par `(tcgdex_id, reference_language)`, données et identifiants internes préservés), `0025_reference_aliases.sql`, `0026_tcgdex_sync_locale.sql` (locale par file de sync, clé historique conservée pour `fr`) ; `app/identification/aliases.py` (alias contrôlés, collisions dégradées en suggestions, suggestions floues sans écriture), résolution d'alias dans `reference_search.py`, clé `catalog.localization` dans `diagnostics.py`. « gempack 2 » reste volontairement non résolu (aucun alias inventé, cas enrichissable). Couvert par `tests/test_reference_aliases_localizations.py`.

### T06 — Repérer/redresser la carte et conserver la position des textes

**État au 8 novembre :** moteur spatial à réaliser ; `ocr.py` reste la baseline texte avec recadrages fixes. Les contrôles T08 du moteur actuel ne livrent ni TSV, ni redressement, ni langue photographique.

**Skills, tests et intégrations :** [fiche T06](docs/identification/PLAN_VALIDATION_LOTS.md#t06).

**Méthode et développement :** [procédure T06/T07, étapes A à D et F](docs/identification/T06_T07_PROCEDURE_OCR.md). Elle précise les repères EXIF/CSS, contours/quadrilatères, homographie et reprojection, parsing TSV, ordre des passes et budget global. OpenCV headless est un backend expérimental pour l'automatique ; le manuel reste utilisable avec les dépendances actuelles.

**Ordre de réalisation :** recadrage manuel et repères de coordonnées → lecture Tesseract avec positions → localisation/redressement automatiques comparés au manuel. Les bandes sont définies relativement à la carte sélectionnée, pas à la photo entière. Conserver le parcours actuel comme baseline de comparaison.

#### T06.1 — Repérer et redresser la carte avant lecture

**Avancement du 8 novembre 2026 :** sur la fiche d'une annonce unitaire, une photo téléversée est orientée côté serveur puis sélectionnée par rectangle au pointeur ou champs numériques, avec rotation par quarts de tour avant OCR. Le changement de sélection invalide les résultats ; la photo entière reste disponible. Tests synthétiques EXIF et Chromium ciblés. Ce socle ne réalise pas encore le choix parmi les photos capturées, le cadrage dans la prévisualisation, la localisation automatique ou la comparaison sur photographies annotées ; T06.1 reste ouvert (TRK-017). Aucun gain de précision n'est revendiqué.

**Skills, tests et intégrations :** [fiche T06.1](docs/identification/PLAN_VALIDATION_LOTS.md#t061).

- [ ] Comparer photo entière, recadrage manuel et recadrage automatique sur les mêmes images ; conserver la baseline existante.
- [ ] Introduire d'abord le recadrage manuel utilisable au clavier/avec alternative de saisie ; transmettre ses coordonnées dans le repère correct après orientation EXIF.
- [ ] Analyser la meilleure résolution déjà disponible dans la capture ou une photo téléversée, plutôt qu'une miniature si une vue plus détaillée est accessible. Permettre le choix d'une autre photo capturée et le recadrage dans la prévisualisation ; conserver la photo/région réellement analysée. Changement de photo = nouvelle analyse, sans réutilisation silencieuse des résultats précédents ni assemblage de cartes différentes.
- [ ] Localiser les contours/quadrilatères plausibles ; corriger orientation et perspective pour produire une vue rectangulaire de la carte. Versionner les transformations et borner les dimensions/pixels de sortie, y compris après agrandissement.
- [ ] Rejeter les quadrilatères dégénérés, hors image, trop petits ou insuffisamment étayés ; signaler l'échec et proposer le cadrage manuel ou la lecture de la photo entière. Ne jamais présenter le repli comme une localisation réussie.
- [ ] Séparer carte, boîtier et étiquette de gradation. Plusieurs régions/cartes restent séparées ; ne pas combiner le nom d'une carte et le numéro d'une autre.
- [ ] Une carte détectée sur plusieurs photos ne prouve pas l'absence d'autres objets vendus. Plusieurs vues recto/verso ne deviennent pas un lot par simple comptage d'images.

#### T06.2 — Conserver et exploiter la position des textes

**Skills, tests et intégrations :** [fiche T06.2](docs/identification/PLAN_VALIDATION_LOTS.md#t062).

- [ ] Utiliser la sortie structurée TSV de Tesseract pour conserver mots, lignes reconstituées, boîtes englobantes et scores techniques disponibles ; un score absent reste inconnu et un score OCR n'est pas une probabilité d'identité.
- [ ] Associer chaque fragment à l'image, à la carte/étiquette et à la région analysée ; conserver coordonnées en pixels, dimensions du repère, coordonnées normalisées et transformations permettant le retour à la photo orientée EXIF.
- [ ] Prioriser les noms dans le haut et les numéros dans le bas de la carte redressée, sans exclure définitivement les autres positions. Paramétrer/versionner les zones et garder un repli pour les mises en page atypiques.
- [ ] Rapprocher les fragments voisins d'un numéro séparé par l'OCR (par exemple `025`, `/`, `165`) uniquement dans une même région/objet et avec une cohérence spatiale ; ne pas concaténer toute la bande basse sans contrôle.
- [ ] Lire les régions nom/numéro/code/symbole avec quelques échelles et modes de segmentation adaptés ; conserver la lecture originale et éviter les traitements destructifs systématiques.
- [ ] Employer des jeux de caractères adaptés uniquement sur les régions correspondantes ; préserver lettres, préfixes, zéros et suffixes valides selon le référentiel.
- [ ] Réutiliser le matcher commun avec les observations spatiales ; ne pas créer un moteur d'acceptation OCR distinct ni supprimer les contradictions avec titre/description.

#### T06.3 — Mesurer et borner le traitement

**Skills, tests et intégrations :** [fiche T06.3](docs/identification/PLAN_VALIDATION_LOTS.md#t063).

- [ ] Comparer baseline, cadrage manuel, cadrage/redressement automatique et lecture spatiale à labels/catalogue figés. Mesurer noms/numéros exacts, rappel top-3 des références et identité finale ; distinguer échec de localisation et échec OCR sur cadrage humain.
- [ ] Publier les effectifs par segment (carte décentrée/inclinée, boîtier PSA/PCA, reflet, texte fragmenté, plusieurs cartes) et la latence p50/p95 de bout en bout ; les cas refusés et les replis restent dans le bilan.
- [ ] Préserver taille maximale 8 Mo, 12 millions de pixels et deux analyses simultanées ; ajouter un budget global de 20 secondes de calcul OCR par image, cancellation et limites mémoire. Ce budget inclut les essais de secours, hors téléversement.
- [ ] Langue OCR non installée, image inexploitable ou délai dépassé : réponse explicite et saisie manuelle, sans boucle infinie ni téléchargement implicite.

#### T06.4 — Proposer la langue à partir du texte de l'exemplaire

**Skills, tests et intégrations :** [fiche T06.4](docs/identification/PLAN_VALIDATION_LOTS.md#t064).

- [ ] Définir et mesurer une méthode locale bornée utilisant des mots/expressions discriminants dans les régions de texte de la carte ; ne pas utiliser uniquement le nom du Pokémon, un code de langue du site ou la locale de recherche.
- [ ] Retourner la langue candidate, les fragments utiles, leur objet/région, la méthode/version et le motif d'abstention. Lectures insuffisantes, plusieurs langues plausibles ou textes d'objets différents : langue inconnue et choix manuel disponible.
- [ ] Faire évoluer explicitement le contrat OCR aujourd'hui limité à nom/numéro, ses validations et ses adaptateurs ; conserver la compatibilité des anciens clients. Une suggestion n'alimente pas le champ de langue confirmée sans action distincte, et tout désaccord avec une langue déclarée reste visible.
- [ ] Recetter français, anglais, nom identique entre langues, texte trop court et conflit texte/photo. Publier qualité et abstention séparément des métriques d'identité ; ne pas étendre le périmètre qualifié aux langues non testées.

**Fichiers :** `ocr.py`, contrat d'observations/modèles, `app/static/ocr.js`, templates concernés, tests OCR locaux/web et Dockerfile si nécessaire. **Acceptation :** repères et transformations vérifiés sur fixtures, fragments rattachés au bon objet, suggestions de langue étayées ou abstention, replis utilisables et rapport de comparaison avec latence sur machine décrite ; raccordement T08.2 et recette §1.3 passants pour la livraison du parcours ; aucune régression des garde-fous ni changement de moteur imposé sans gain démontré.

### T07 — Produire plusieurs hypothèses de numéro et des réparations contrôlées

**Skills, tests et intégrations :** [fiche T07](docs/identification/PLAN_VALIDATION_LOTS.md#t07).

**Méthode et développement :** [procédure T06/T07, étapes E/F et sections 7 à 10](docs/identification/T06_T07_PROCEDURE_OCR.md). Elle distingue lectures originales et alternatives d'une même lecture, fixe des plafonds initiaux versionnés et décrit la recherche/unification des candidats. Les alternatives ne doivent pas devenir des assertions simultanées dans `decision._conflicts()` ; les vrais désaccords avec les preuves restent visibles.

- [ ] Extraire plusieurs lectures de numéro depuis les fragments spatiaux de T06 ; conserver la lecture brute, le numéro complet (préfixe, numérateur, dénominateur, suffixe lorsqu'ils existent), la région et la version d'extraction.
- [ ] Générer des hypothèses bornées à partir d'erreurs observées : slash Unicode, espaces/fragments séparés, confusions `O/0` ou `I/1`, insertion éventuelle d'un caractère. Garder original, opération et alternatives ; ne pas appliquer de substitution globale aux noms ou aux préfixes alphanumériques valides.
- [ ] Fixer et versionner avant expérimentation les plafonds de fragments, variantes par lecture et recherches par image ; dédupliquer par numéro canonique en conservant toutes les provenances. Classer par qualité de lecture, cohérence spatiale et coût de correction, sans présenter ce rang comme une certitude.
- [ ] Vérifier les hypothèses dans le catalogue et les extensions compatibles, en préservant promos, sous-séries et numéros secrets. Ne pas recopier une règle universelle `numéro ≤ 1,6 × total`, ni les seuils du scanner de référence, sans validation sur notre périmètre.
- [ ] Examiner les hypothèses admissibles dans le budget puis unir les candidats ; ne pas s'arrêter à la première lecture ayant un résultat. Utiliser nom, extension et autres observations pour départager, garder les alternatives plausibles et tracer les contradictions.
- [ ] Rechercher aussi avec les lectures originales nom/numéro, même si l'annonce ne mentionne pas d'extension ; réutiliser les recherches structurée et lexicale communes de T05. Une faute du titre peut aider à retrouver des candidats sans devenir une preuve exacte ni masquer un désaccord avec la photo.
- [ ] Projeter depuis chaque candidat son identifiant/localisation, nom canonique, extension, numéro et image disponible. Distinguer propriétés de référence et attributs observés de l'exemplaire ; le numéro complet conserve son dénominateur lu/attesté, jamais reconstruit depuis un effectif total générique. Une extension ou langue inconnue ne doit pas empêcher de montrer des candidats ; elle peut empêcher leur confirmation ou leur comparaison exacte.
- [ ] Reproduire et filtrer le cas `n` proposé comme numéro : aucune valeur sans structure reconnue ou attestation dans le référentiel n'est préremplie comme numéro exploitable. Garder le fragment brut au diagnostic et préserver les numéros alphanumériques légitimes ; une valeur valide syntaxiquement ne prouve pas l'identité.
- [ ] Ne pas modifier silencieusement un numéro du titre/de la description ; exposer toute contradiction avec une hypothèse OCR et conserver la priorité des preuves et confirmations existantes.
- [ ] Tester `108/59 → 108/159` comme hypothèse d'insertion, jamais comme vérité acquise. Vérifier le numéro imprimé et le périmètre d'extension plutôt qu'un effectif global générique.
- [ ] Rechercher les autres références compatibles et les cas où la bonne réponse est absente ; l'unicité dans un cache partiel ne démontre pas l'unicité réelle.
- [ ] Exiger un indice discriminant supplémentaire pour mettre une réparation en avant ; l'absence de contradiction ne suffit pas.
- [ ] Ne pas compter les essais OCR d'une même image/région comme preuves indépendantes.
- [ ] Garder les réparations soumises à confirmation humaine en J1 et après, sauf chantier ultérieur explicitement qualifié selon T10.
- [ ] Comparer lecture originale seule et hypothèses multiples sur les mêmes cas annotés : numéro exact parmi les hypothèses, rappel top-3, nouvelles erreurs de suggestion, identité finale et temps ajouté. Ne pas confondre présence du bon numéro et confirmation de la bonne carte.

**Fichiers :** `ocr.py`, extraction/normalisation, matcher/recherche locale, modèles/contrat de preuves et tests associés. **Acceptation :** suggestion lisible « lu / proposé / pourquoi / autres possibilités », nom canonique et extension de référence réutilisables dans T08.2, recette §1.3 passante, plafonds testés, provenance spatiale conservée et comparaison appariée publiée ; cas négatifs de réparation passants ; un lot reste lot malgré une réparation plausible.

### T08 — Terminer le parcours utilisateur, y compris les erreurs

**Skills, tests et intégrations :** [fiche T08](docs/identification/PLAN_VALIDATION_LOTS.md#t08).

#### T08.1 — Corriger capture et préremplissage sur le moteur existant

**Skills, tests et intégrations :** [fiche T08.1](docs/identification/PLAN_VALIDATION_LOTS.md#t081).

- [x] Séparer titre d'annonce et nom de carte dans le contrat de capture et le formulaire. Pour les anciennes captures `name == title`, traiter cette valeur comme repli de capture, pas comme un nom canonique extrait ; conserver compatibilité JSONL, titre original et provenance.
- [x] Permettre à une proposition du matcher de remplacer ce repli dans la présentation du nom, sans modifier l'observation d'origine ni écraser une saisie/correction humaine. Sans candidat admissible, laisser le nom non résolu plutôt que déclarer tout le titre comme nom identifié.
- [x] Un préremplissage heuristique ou OCR reste indicatif après « Relancer l'analyse » et après ajout. Corriger les badges pour distinguer extrait, proposé depuis le référentiel, proposé par OCR et confirmé.
- [x] Tester absence de candidat, ancien client, titre contenant une faute, nom corrigé manuellement et réanalyse ; ce correctif ne dépend pas du nouveau moteur spatial.

#### T08.2 — Raccorder lecture photo, choix de référence et enregistrement

**Skills, tests et intégrations :** [fiche T08.2](docs/identification/PLAN_VALIDATION_LOTS.md#t082).

- [ ] Rendre explicite le parcours qui analyse la photo : « Envoyer à Pokébourse » déclenche l'OCR existant ; la prévisualisation textuelle reste distincte. Distinguer à l'écran « annonce capturée », « photo analysée », « carte proposée » et « identité confirmée », sans changer les statuts métier compatibles. Chaque libellé correspond à une étape réellement achevée ; téléchargement/lecture/recherche en cours, photo absente ou échec restent visibles. Une détection de mots-clés ou une photo affichée ne vaut pas identification de carte.
- [ ] Après « Envoyer », enchaîner W02 à W07 sans clic de recherche/recopie dans le cas nominal. Ouvrir rapidement la prévisualisation et sa progression ; définir le responsable de l'exécution, du transport image autorisé et du retour de résultat sans dépendre de la durée de vie du popup. Annulation/interruption n'effacent ni capture ni corrections ; les limites OCR restent effectives et aucun cache durable de photo n'est créé implicitement.
- [ ] Transporter et réutiliser candidats, hypothèses utiles et provenance entre extension, prévisualisation et fiche ; exposer le choix d'une référence et sa confirmation avant l'enregistrement. Prévisualisation sans écriture ; validation finale contre les preuves/révision attendues, sans accepter l'autorité d'un identifiant client.
- [ ] Porter en prévisualisation une sélection/confirmation transitoire liée aux preuves et versions, sans appeler directement une review exigeant un `item_id` inexistant. À l'ajout final, créer/résoudre l'annonce et appliquer le choix explicite dans la même unité atomique ; sur doublon, vérifier la révision et préserver toute décision humaine applicable. Si la vérification finale échoue, ne pas publier une annonce présentée comme confirmée ni supprimer les corrections du formulaire.
- [ ] Proposer ensemble nom canonique, extension issue du référentiel et numéro ; proposer séparément la langue étayée par T06.4, avec confirmation accessible. Aucune reconstruction manuelle de ces champs n'est nécessaire dans le cas nominal ; aucun champ manuel n'est écrasé par un résultat tardif.
- [ ] Donner accès dans la prévisualisation au choix de photo et au recadrage T06.1, avec la vue analysée identifiable et une commande explicite de réanalyse. Les autres images proviennent de la capture autorisée ou d'un téléversement local ; conserver le contrat historique d'image principale et ajouter seulement un transport optionnel borné pour les autres vues. Pas d'analyse en rafale de toute une galerie ni d'association implicite de photos d'exemplaires différents.
- [ ] Afficher côte à côte la photo/région analysée et l'image de référence du candidat, avec agrandissement accessible et détails discriminants : nom, numéro complet disponible, extension, langue de référence distincte de celle de l'exemplaire, édition/finition connues. Une image manquante est signalée sans bloquer la comparaison textuelle. Il s'agit d'une aide à la vérification humaine, sans reconnaissance visuelle automatique T11 implicite.
- [ ] Associer chaque échec établi à une action disponible : numéro illisible → autre photo/recadrage ; couverture locale manquante établie → enrichissement existant T05 ; plusieurs versions → comparaison/choix ; preuves contradictoires → vérification/correction ; moteur indisponible → saisie ou réessai. Un simple résultat vide ne prouve ni l'absence au catalogue ni un défaut OCR ; conserver un diagnostic d'insuffisance lorsque la cause n'est pas établie.
- [ ] Afficher séparément l'état d'identification et l'admissibilité des comparaisons de prix. Une référence confirmée peut rester « comparaison à compléter » pour langue, édition, finition, état ou gradation manquants, ou « indisponible » pour absence de source adaptée. Lister les informations précises à compléter sans les inventer ; seuls les attributs nécessaires au périmètre de comparaison retenu sont bloquants. Réutiliser T09/T17 et les choix de §1.2 pour établir ce diagnostic, sans promettre de prix du seul fait de l'identification.

- [ ] Harmoniser saisie URL, prévisualisation d'extension, import JSONL et fiche : champs détectés préremplis avec provenance, inconnus visibles, aucune confirmation implicite.
- [ ] Afficher texte original, preuves utiles, propositions et attributs séparés ; permettre de corriger sans perdre les originaux.
- [ ] Comparer les candidats sur les détails discriminants : numéro complet, extension, suffixe, langue de référence et images disponibles ; une image absente ne bloque pas la recherche textuelle.
- [ ] Permettre recherche paginée au-delà du top-K, saisie d'un ID vérifié et recherche de référence manquante. Conserver le formulaire pendant les traitements.
- [ ] Ajouter les actions « conserver non identifiée », « classer en lot », « enrichir le référentiel », « confirmer l'identité », « retirer/corriger la confirmation » avec libellés distincts.
- [ ] Permettre « conserver non identifiée » et une langue/état inconnus sans choisir une référence arbitraire : définir la représentation de l'inconnu dans stockage, JSONL, matcher, formulaire et export. Neutraliser pour ces captures tout défaut `fr` ou valeur d'identité inventée ; migration additive si nécessaire. Les champs financiers requis restent contrôlés séparément pour l'enregistrement, sans bloquer l'identification préalable.
- [ ] Afficher progression, indisponibilité, délai dépassé et résultat périmé ; empêcher doubles soumissions, confirmation de mauvaise annonce et application d'une réponse OCR ancienne après modification du formulaire.
- [ ] Conserver les captures si Pokébourse est indisponible ; vérifier compatibilité JSONL, permissions minimales et reprise du service worker MV3.
- [ ] Valider dans le navigateur les parcours nominaux, erreurs, navigation clavier et affichage mobile selon Mosaic × Flowbite ; ressources locales uniquement.

#### T08.3 — Contrôler les champs après préremplissage ou saisie

**État au 8 novembre :** contrôles du moteur actuel testés, voir [bilan T08](docs/identification/T08_CONTROLES_MOTEUR_ACTUEL.md). Les critères exigeant une sélection transitoire, une résolution motivée ou une invalidation restent ouverts jusqu’à T08.2/T09.

**Skills, tests et intégrations :** [fiche T08.3](docs/identification/PLAN_VALIDATION_LOTS.md#t083).

- [ ] Après chaque préremplissage, correction ou choix de candidat, revalider côté serveur les champs avant leur utilisation en recherche, puis la cohérence de la référence avant confirmation/enregistrement. Les contrôles navigateur servent au retour immédiat ; le serveur recalcule normalisations, diagnostic et admissibilité depuis les valeurs/provenances reçues.
- [x] Séparer les validations d'identité, d'enregistrement et de valorisation. Un prix/port mal formé ou une devise absente produit une erreur du champ financier, sans empêcher l'OCR, les candidats TCGdex et leur comparaison. Ne pas convertir une erreur monétaire en zéro ni écraser la saisie ; une correction financière seule ne relance pas l'OCR et ne modifie pas l'empreinte d'identité.
- [x] Contrôler séparément nom canonique ou alias reconnu (suffixes préservés), extension reconnue ou non résolue, structure du numéro complet et langue admise ou inconnue. Un titre recopié, `n` sans attestation, une valeur générique ou une extension non reconnue ne deviennent pas des filtres exacts. Conserver les valeurs brutes et afficher les raisons à côté des champs.
- [ ] Vérifier ensemble nom, extension, numéro (dont dénominateur attesté), identifiant/localisation sélectionné et preuves de langue de l'exemplaire. Des champs valides séparément peuvent désigner des cartes différentes : exposer le conflit, conserver les candidats pertinents pour diagnostic et empêcher confirmation/valorisation de cette combinaison incohérente.
- [ ] Offrir une résolution humaine explicite et motivée pour une observation vendeur erronée, depuis les candidats du diagnostic. Conserver titre/description et contradictions d'origine ; qualifier l'observation écartée dans l'audit, revalider la référence et laisser inconnus les attributs non établis. Aucun clic d'ajout, simple changement de champ ou choix du premier candidat ne résout implicitement le conflit. Un lot actif reste exclu tant qu'il n'a pas été reclassé explicitement selon son parcours.
- [x] Construire les requêtes locales avec les indices exploitables et leur provenance : champ manquant/invalide/proposé n'est pas un filtre exact obligatoire. Autoriser les recherches partielles et les replis lexicaux bornés, expliciter les critères utilisés ou écartés ; une contradiction explicite ne disparaît pas pour obtenir un résultat. Aucun remplissage inventé pour lancer la recherche.
- [x] Ne jamais compter les champs nom/extension/numéro recopiés depuis un candidat comme de nouvelles preuves indépendantes confirmant ce même candidat. Un préremplissage suivi d'une réanalyse reste une proposition ; la langue de référence ne valide pas la langue de l'exemplaire.
- [ ] Lors d'une modification significative des preuves, invalider la sélection/confirmation et les résultats devenus inapplicables selon les empreintes/révisions T03, puis demander réanalyse ou nouvelle confirmation. Après enregistrement, contrôler que la fiche conserve la référence et les attributs revalidés ; T16 utilise cette identité effective pour les comparaisons.

**Fichiers :** `manual_listing.py`, `capture_preview.py`, `web.py`, templates, `forms.js`, `ocr.js`, popup/content/background de l'extension. **Acceptation :** les lignes T13 du périmètre capture/identification W01–W09 sont réalisables dans l'interface sans édition SQL ni script de réparation ; le cas §1.3 conserve le titre et aboutit à des champs proposés cohérents, une confirmation et une fiche réutilisant la même référence. Statuts d'avancement fidèles, choix/recadrage de photo, comparaison visuelle côte à côte, diagnostic avec action et distinction identité/comparabilité sont obligatoires dans cette recette. Les contrôles T08.3 passent aussi avec un formulaire soumis directement sans JavaScript. Le contrat de sortie vers T16 se vérifie sur fixtures ; l'exécution W10/W11 et ses sources sont validées avec J3, sans créer une dépendance circulaire pour T08. Le transport OCR seul ne vaut pas validation de T08.2.

### T09 — Protéger les décisions et leur usage métier

**Skills, tests et intégrations :** [fiche T09](docs/identification/PLAN_VALIDATION_LOTS.md#t09).

- [ ] Relier confirmation, révision, observations et preuves durables ; conserver les décisions humaines applicables lors des réingestions et enrichissements.
- [ ] Tester changement de preuve, retrait, correction, suppression d'import et concurrence ; une ancienne décision ne ressuscite pas après retrait.
- [ ] Ne pas transformer une annotation indépendante en décision active. Ne pas remplacer un choix humain par un nouveau premier candidat automatique.
- [ ] Rejeter les résultats de worker/OCR périmés par version/révision ; ne jamais garder une transaction SQLite pendant le calcul OCR, l'inférence ou le réseau.
- [ ] Mettre en place un contrôle commun d'admissibilité financière : identité effective, portée de langue/impression, attributs nécessaires et source de prix compatible.
- [ ] Préserver les estimations indicatives existantes avec leurs limites ; ne pas les présenter comme rentabilité confirmée si les attributs sont inconnus. Ne pas bloquer l'enregistrement ni le suivi d'achat quand l'estimation est impossible.
- [ ] Empêcher qu'une référence française ou une cote liée seulement par illustration valorise silencieusement une impression étrangère, un lot ou une finition non vérifiée.
- [ ] Appliquer la même décision aux fiches, catalogue, exports, tendances et opportunités ; conserver les formules en centimes/bps.

**Acceptation :** réingestion idempotente sur l'identité et `first_seen_at` ; conflits explicites ; aucun gain net présenté comme établi sur une identité ou portée inadmissible.

### T10 — Qualifier la qualité sans favoriser l'abstention artificielle

**Skills, tests et intégrations :** [fiche T10](docs/identification/PLAN_VALIDATION_LOTS.md#t10).

- [ ] Sceller un test indépendant des cas utilisés pour ajuster règles, alias, réparations et paramètres. Les 30 cas initiaux deviennent un jeu de développement/régression, pas le test final.
- [ ] Regrouper republications, quasi-doublons et images identiques avant partition ; prévoir un test temporel et un segment d'identités non vues à l'entraînement si un modèle est appris. Les références de catalogue restent disponibles pour la recherche.
- [ ] Rapporter métriques globales et par plateforme, langue, qualité photo, extension, lot/unitaire et couverture de catalogue ; publier effectifs, données absentes et intervalles d'incertitude.
- [ ] Comparer de façon appariée sur les mêmes annonces/groupes ; conserver le catalogue fixe pour isoler l'algorithme, puis mesurer séparément l'apport d'un catalogue enrichi.
- [ ] Avant toute nouvelle acceptation automatique OCR/vision, satisfaire les critères ci-dessous. Sinon conserver les suggestions et publier les limites, sans abaisser les seuils.

| Mesure | Définition / critère |
|---|---|
| Précision automatique | Identités exactes correctes / décisions automatiques acceptées ; cible de promotion : borne inférieure unilatérale à 95 % ≥ 99,5 % sur le périmètre qualifié |
| Couverture automatique | Décisions automatiques / toutes les annonces admissibles ; publier avec la précision et le taux d'identités correctes sur toutes les annonces |
| Gain utile | Pour promouvoir une nouvelle voie automatique : gain ponctuel d'au moins 5 points de couverture correcte sur la tranche ciblée, avec borne inférieure à 95 % du gain apparié > 0 ; précision cible maintenue et pas de dégradation globale démontrée |
| Recherche | Rappel@3 et rappel@K avant classement, sur identités déterminables présentes dans le catalogue ; cible de travail rappel@50 ≥ 98 %, à confirmer en T01 selon périmètre |
| Lots | Précision/rappel et matrice de confusion ; zéro lot connu accepté comme carte unitaire dans la recette et le jeu évalué ; ne pas généraliser ce zéro sans intervalle/effectif |
| Attributs | Exactitude par champ, taux de champ inconnu et taux de fausse complétion ; distinguer déclaration vendeur et observation vérifiée |
| Hors catalogue | Taux de fausse acceptation et orientation correcte vers enrichissement/abstention ; ne pas exclure ces cas des métriques de bout en bout |
| Coût utilisateur | Temps de résolution humaine, nombre d'actions, proportion de cas conservés sans blocage ; mesurer avec et sans assistance |
| Ressources | p50/p95, erreurs et mémoire sur matériel/configuration décrits ; budget global OCR de T06 respecté |

Ces cibles sont des critères proposés de promotion, pas des résultats observés. Pour un audit aléatoire indépendant avec zéro erreur, environ 600 décisions acceptées permettent seulement d'approcher une borne de précision de 99,5 % à 95 % unilatéral. Des erreurs, doublons, tirages stratifiés ou qualifications par segment changent les effectifs et le calcul. Ne pas utiliser cette approximation pour certifier chaque langue/extension.

Une qualification insuffisante signifie « non démontré » ; elle n'autorise ni une promesse de précision, ni une généralisation aux segments non observés. Une simple correction déterministe peut être livrée en J1 avec tests et résultats limités honnêtement présentés, sans attendre une nouvelle automatisation.

### T11 — Expérience conditionnelle de reconnaissance visuelle et fusion

**Skills, tests et intégrations :** [fiche T11](docs/identification/PLAN_VALIDATION_LOTS.md#t11).

**Déclencheur :** T10 identifie une tranche significative où l'identité est lisible sur l'image, présente dans le référentiel, mais reste inaccessible après cadrage/OCR améliorés. Documenter effectif, causes et potentiel avant d'installer des dépendances.

- [ ] Comparer un descripteur classique (SIFT ou ORB avec vérification géométrique) et un encodeur image compact figé, par exemple DINOv2 ViT-S/14. Leur intérêt relatif est une hypothèse à mesurer.
- [ ] Réserver le hachage perceptuel à une baseline et à l'aide au regroupement des doublons ; ne pas assimiler illustration proche et impression exacte. CLIP peut être un comparateur, pas un choix imposé.
- [ ] Construire l'index depuis les images de référence autorisées, téléchargées séparément, versionnées et vérifiées ; conserver modèle, licence, paramètres, empreintes et pipeline de normalisation.
- [ ] Comparer carte entière et région d'illustration ; mesurer spécifiquement réimpressions proches, langues, boîtiers, masquages et reflets. Ne pas déduire finition/authenticité de la seule proximité.
- [ ] Commencer avec recherche exacte sur vecteurs locaux ; n'ajouter un index approximatif qu'après mesure de latence/mémoire et perte de rappel.
- [ ] Unir les candidats visuels/textuels puis vérifier leurs contradictions ; une branche visuelle peut proposer malgré un OCR absent, sans confirmer automatiquement.
- [ ] Tester un modèle de fusion simple sur features explicites avant un réseau spécialisé : accords, contradictions, qualité, valeurs manquantes, scores et écarts de classement. Inclure la classe « aucun candidat correct ».
- [ ] Séparer entraînement, validation des paramètres, calibration et test final ; ne pas additionner ou normaliser arbitrairement les scores comme probabilités. Ne pas supposer l'indépendance des preuves dérivées de la même photo.
- [ ] Envisager un entraînement spécialisé seulement si les courbes d'apprentissage et plusieurs milliers d'exemples fiables le justifient ; absence de volume = maintien de la solution simple.
- [ ] Fonctionnement sans poids/index : repli OCR/texte, message explicite, aucun téléchargement ou appel externe à l'exécution. Désactivation et retour à la version précédente sans migration destructive.

**Acceptation :** rapport d'ablation et décision intégrer/abandonner. L'intégration de suggestions exige un gain utile et un coût humain acceptable ; l'automatisation exige en plus T10. Un modèle plus complexe sans gain démontré n'est pas retenu.

### T12 — Livrer et exploiter

**Skills, tests et intégrations :** [fiche T12](docs/identification/PLAN_VALIDATION_LOTS.md#t12).

- [ ] Déployer app et worker compatibles, vérifier migrations sur copie, restauration et parcours nominal. Aucun effacement du volume réel ; sauvegarde vérifiée avant application des migrations à l'instance utilisée.
- [ ] Lire le dernier numéro de migration au moment de coder, ne jamais modifier une migration déjà publiée. Toute nouvelle migration suit `BEGIN IMMEDIATE`, enregistrement dans `schema_migrations`, `COMMIT`, puis tests d'idempotence et conservation des relations.
- [ ] Documenter les dépendances réellement retenues et les modes hors ligne, durées, quotas, stockage/preuves, sauvegarde/purge et solutions de repli. Ajouter seulement les dépendances justifiées par le lot.
- [ ] Mettre à jour README, SOURCES, SUIVI, docs TCGdex/ML et extension selon les fonctions réellement livrées. Résoudre les contradictions documentaires relevées en T00 ; ne pas annoncer une fonctionnalité future comme disponible.
- [ ] Publier une fiche de version : périmètre qualifié, catalogue/modèles, performances observées et limites. Une promotion changeant le rôle indicatif de l'OCR met à jour explicitement contrats, interface, documentation et tests.
- [ ] Prévoir métriques locales agrégées : abstentions, contradictions, corrections humaines, références manquantes, erreurs, latence, taille du stockage. Pas de photos, contacts ou données vendeur privées dans les logs.
- [ ] Prévoir revue des nouvelles erreurs, mises à jour d'alias et réévaluation après modification de modèle/catalogue ; distinguer correction du moteur et nouvelle vérité terrain.
- [ ] Conserver une voie de retour : fonctionnalité désactivable, ancienne version des artefacts, sauvegarde restaurable et données récentes protégées ; ne pas utiliser une restauration ancienne comme rollback automatique qui effacerait les acquisitions récentes.

**Acceptation J1 :** lignes T13 du périmètre identification/capture/persistance W01–W09 et collecte C01–C06/T19 sur les modes annoncés, tests requis, notice utilisateur et restauration passants. **Acceptation J2 :** rapport T10 disponible et décision T11 consignée, y compris si la vision est écartée. Les lignes T13 de recherche de marché et estimation W10/W11 appartiennent à J3. Les acquis de capture déjà validés gardent leur périmètre ; ce complément de collecte ne les réinitialise pas.

**Acceptation J3 :** T14 à T18 et lignes de recette associées passantes ; choix dépendants de §1.2 résolus, capacités des sources documentées, aucune couverture indisponible présentée comme acquise. Réappliquer les contrôles de livraison T12 au nouveau parcours.

### T14 — Identifier les cartes non gradées et gradées PSA/PCA

**Skills, tests et intégrations :** [fiche T14](docs/identification/PLAN_VALIDATION_LOTS.md#t14).

- [ ] Séparer carte de référence, langue, finition/édition, état déclaré, présence d'une gradation, certificateur, note et certificat éventuel. Garder inconnu ce qui n'est pas établi.
- [ ] Sur les boîtiers, tenter une lecture locale distincte de la carte et de l'étiquette PSA/PCA ; rattacher chaque indice à sa région, sans prendre la note ou le numéro de certificat pour le numéro de carte.
- [ ] Conserver valeur brute et valeur normalisée de la note ; utiliser une représentation exacte (entier à échelle fixe ou chaîne canonique), jamais un `float` ni une conversion entre barèmes.
- [ ] Exposer les désaccords titre/étiquette/carte. Demander confirmation de l'identité ou de la gradation incertaine avant la valorisation ; ne pas confirmer implicitement en enregistrant.
- [ ] La lecture du nom PSA/PCA ou d'un certificat ne prouve pas l'authenticité du boîtier. Une éventuelle vérification de certificat distante est une capacité distincte, à cadrer et autoriser séparément.
- [ ] Conserver les certificateurs déjà détectés par le projet, sans conversion vers PSA/PCA ni promesse de comparaison qualifiée pour ces autres certificateurs.
- [ ] Prévoir migrations si nécessaires sans modifier les migrations publiées ; préserver décisions humaines et attributs existants. Ajouter des fixtures non gradées, PSA/PCA et des contre-exemples.

**Acceptation :** carte sous protection non assimilée à une carte gradée ; note absente ou illisible non inventée ; carte/grade/certificat correctement séparés ; PSA 10, PSA 9 et PCA 10 constituent des segments distincts. Aucun prix non gradé utilisé comme prix d'un exemplaire gradé.

### T15 — Vérifier les capacités et l'accès aux sources de prix

**État au 8 novembre :** matrice documentaire livrée le 3 novembre, accès et choix produit toujours à requalifier avant activation. Les cases cochées concernent l’audit, pas la livraison d’offres/ventes automatiques.

**Skills, tests et intégrations :** [fiche T15](docs/identification/PLAN_VALIDATION_LOTS.md#t15).

- [x] Établir une matrice versionnée par source : offres actives, transactions conclues individuelles, cotes agrégées, couverture non gradée/PSA/PCA, langue/état, port/devise, fraîcheur, provenance, accès, coût et quotas. Distinguer disponibilité théorique et accès réellement configuré pour cette installation.
- [x] Prioriser le guide public Cardmarket comme cote agrégée et les capacités eBay d'offres actives sous réserve d'accès établi. Ne pas assimiler le guide à une liste d'offres ni présumer qu'il fournit des prix par certificateur/note.
- [x] Auditer le connecteur eBay existant avant réemploi : bibliothèque ou endpoint présent dans le code ne démontre pas l'accès à une API officielle ni aux ventes conclues. Définir adaptation, authentification et replis nécessaires.
- [ ] Traiter l'historique des ventes comme une capacité distincte : la documentation eBay consultée indique Marketplace Insights restreint et fermé aux nouveaux utilisateurs. Vérifier l'accès effectif avant de promettre un historique automatique. Sans source adaptée, déclarer cette capacité indisponible et soumettre le manque au produit ; aucune simulation de ventes à partir des offres.
- [ ] Réutiliser captures/imports locaux et reventes personnelles avec prix réel documenté ; ne pas assimiler un simple statut « vendu » sans montant à une preuve de prix. Un accès éventuellement payant reste soumis à un choix explicite de budget.
- [ ] Pour Vinted, Leboncoin ou d'autres sources sans accès établi, prévoir captures/imports et liens de recherche manuelle ; ne pas ajouter de recherche serveur automatique sur la seule présence d'un connecteur.
- [x] Consigner dans SOURCES les moyens réellement retenus, les autorisations, les données transmises et les limites ; aucun secret dans les rapports, fixtures ou logs.

**Livrable / acceptation :** matrice de capacités et décision par source, avec références officielles datées. Chaque capacité manquante est visible et son impact sur J3 explicite ; aucune souscription ou acquisition réelle déclenchée par ce tasking documentaire.

**Livraison T15 — 3 novembre 2026 :** matrice versionnée dans [docs/identification/T15_SOURCES_PRIX.md](docs/identification/T15_SOURCES_PRIX.md), section consignée dans [SOURCES.md](SOURCES.md) (§10). Constats établis : le connecteur eBay actuel interroge la page de recherche HTML publique sans authentification (ce n'est pas l'API officielle, aucune clé configurée) ; l'historique des ventes eBay (Marketplace Insights) reste indisponible (API restreinte, fermée aux nouveaux utilisateurs) ; Cardmarket fichiers publics est la seule source automatique disponible et ne couvre que des cotes agrégées non gradées ; aucune source automatique ne couvre les gradées PSA/PCA. Divergence code/documentation corrigée dans SOURCES.md. Décisions §1.2 encore ouvertes, recensées en section 4 de la matrice (D1 à D6) ; aucun comportement dépendant activé, aucune souscription, aucun accès réel déclenché.

### T16 — Déclencher la recherche de marché après identification admissible

**Skills, tests et intégrations :** [fiche T16](docs/identification/PLAN_VALIDATION_LOTS.md#t16).

- [ ] Après enregistrement d'une annonce avec identité admissible, mettre en file une recherche de marché sans clic de recherche supplémentaire ; si une confirmation a été demandée, déclencher après cette confirmation. Une suggestion OCR seule en J1 n'autorise pas ce déclenchement comme identité confirmée.
- [ ] Garantir la reprise si le processus s'arrête entre enregistrement et lancement de recherche : obligation de recherche durable avec l'ajout ou rattrapage déterministe par le worker, puis exécution seulement après commit. Dédupliquer par identité/révision/configuration et tester les arrêts avant/après commit, sans doublon ni recherche perdue ; une obligation transactionnelle non publiée n'est pas une exécution anticipée.
- [ ] Construire les critères depuis l'identité effective et ses attributs admissibles : identifiant/version, nom canonique, extension, numéro complet disponible et langue. Ne pas réutiliser le titre brut comme nom de carte ; tester la transmission du cas §1.3 jusqu'aux sources simulées et aux filtres de comparabilité T17.
- [ ] Préserver les prévisualisations sans écriture ; aucun job durable ni recherche marketplace à chaque frappe, rechargement ou affichage d'un candidat. La recherche externe générale `/search` conserve son déclenchement explicite.
- [ ] Lire d'abord les observations et cotes locales ; interroger ensuite uniquement les capacités autorisées/activées, en exposant les sources non configurées. Une cote fraîche est réutilisée ; pas de téléchargement complet du guide Cardmarket pour chaque carte.
- [ ] Utiliser le worker et les mécanismes de file/verrou existants si adaptés ; définir clé de déduplication par identité/version/langue/finition/gradation, périmètre géographique et configuration de recherche. Rattacher l'application du résultat à la révision de l'annonce, même si le cache est partagé.
- [ ] Borner tentatives, délais, pagination, nombre de candidats et cadence par source ; respecter `Retry-After`, isoler les erreurs et ne garder aucune transaction SQLite pendant le réseau ou l'OCR. Faire valider les valeurs de configuration et la fraîcheur en T15.
- [ ] Transmettre uniquement les critères structurés nécessaires ; aucune photo, identité de vendeur ou description brute à un service de prix. Identifier séparément données d'identité et observations de marché.
- [ ] Montrer les états « en attente », « en cours », « terminé », « partiel », « indisponible » et « erreur », avec date et portée par source ; proposer un rafraîchissement borné.
- [ ] Une correction d'identité, de langue ou de grade invalide l'estimation associée ; rejeter les réponses périmées. Aucune récursion de recherches automatiques quand un comparable est enregistré ; l'import des offres retenues reste une action distincte.

**Acceptation :** enregistrement nominal → une seule demande de recherche → résultats explicites, sans attendre une nouvelle action ; identité incertaine → confirmation demandée avant calcul ; doublons/réingestions sans répétition inutile ; panne réseau sans perte d'annonce ; changement de PSA 9 à PSA 10 sans réemploi financier des anciens résultats.

### T17 — Construire les comparables et séparer les preuves de prix

**Skills, tests et intégrations :** [fiche T17](docs/identification/PLAN_VALIDATION_LOTS.md#t17).

- [ ] Conserver source/identifiant/URL, dates d'observation et de transaction si connues, type de preuve, carte/attributs, montant en centimes, devise et port connu/inconnu. Une date de collecte ne remplace pas une date de vente.
- [ ] Afficher trois groupes : **offres en cours**, **ventes conclues documentées**, **cotes agrégées**. Préciser la nature des références manuelles ; une offre disparue reste une offre observée, pas une transaction.
- [ ] Réidentifier les offres candidates : mots-clés identiques ou illustration proche ne suffisent pas. Exclure lots/scellés, mauvaise impression/version/langue/finition et proxy déclaré des comparables exacts ; inconnu n'est ni égalité ni contradiction prouvée.
- [ ] Appliquer la politique de comparabilité validée en §1.2. Pour les gradées, exiger le même certificateur et la même note ; aucun coefficient inventé pour convertir non gradé, PSA ou PCA. Écarter les différences de label/variante de gradation ayant un effet matériel non résolu.
- [ ] Garder les résultats proches mais incomplets dans un groupe « à vérifier / comparaison partielle », avec motif ; ne pas les injecter silencieusement dans la cote qualifiée.
- [ ] Exposer au parcours T08.2 la liste des attributs bloquants et des sources adaptées disponibles pour la comparaison demandée. Distinguer identité à résoudre, attributs à compléter et absence de données de prix ; une identité confirmée ne suffit pas à rendre une offre comparable ni à produire une estimation.
- [ ] Exclure l'annonce évaluée de sa propre référence de prix ; dédupliquer les republications/observations répétées et signaler les doublons probables entre sources sans gonfler le nombre de preuves.
- [ ] Séparer prix article, port et coût livré. Port inconnu reste inconnu ; pas de mélange de devises ou de frais d'importation supposés tant que la politique géographique n'est pas définie.
- [ ] Montrer les critères, différences, exclusions, effectifs indépendants, dates et fraîcheur. Les cotes issues de moyennes ne sont pas comptées comme autant de transactions individuelles.

**Acceptation :** toute preuve retenue est consultable et expliquée ; aucune confusion offre/vente/cote ; PSA/PCA et notes distinctes jamais fusionnés ; aucune revente sans prix réel, doublon ou auto-comparaison ne fabrique un signal de marché.

### T18 — Estimer la revente et la marge, puis qualifier le parcours complet

**Skills, tests et intégrations :** [fiche T18](docs/identification/PLAN_VALIDATION_LOTS.md#t18).

- [ ] Définir et versionner la méthode d'estimation par type de preuve ; justifier fenêtre de fraîcheur et effectif minimal sur les données disponibles, sans seuil arbitraire présenté comme validé. Ne pas moyenner indistinctement offres, ventes et guide agrégé.
- [ ] Afficher la base de l'estimation : ventes comparables, prix demandés ou cote agrégée ; les différences de statut et de portée restent visibles. Sans preuves admissibles, appliquer uniquement le choix validé en §1.2.
- [ ] Paramétrer le canal de revente et les frais selon le choix produit restant ; afficher prix d'achat, port aller, frais d'achat, prix de revente estimé, frais de vente/port supporté/emballage et autres coûts applicables. Éviter les doubles comptes ; tout coût manquant est signalé, jamais assimilé silencieusement à zéro.
- [ ] Calculer en centimes et points de base avec arrondi `ROUND_HALF_UP` : marge estimée = recettes nettes estimées − coût d'acquisition total. Définir explicitement la base du ROI ; aucun gain réalisé déduit d'une estimation.
- [ ] Indiquer méthode, source, date, quantité et compatibilité des preuves. Une fourchette de scénarios éventuelle n'est pas un intervalle statistique garanti ; aucun pourcentage de confiance fabriqué.
- [ ] Adapter fiche, catalogue, exports, opportunités et retour d'import à la même décision et à la même qualité financière. La rentabilité incertaine ne peut pas produire un verdict d'achat qualifié ; l'annonce reste enregistrable et suivable.
- [ ] Recetter sur fixtures non gradées/PSA/PCA et sources simulées : identité, gradation, recherche, sélection des comparables, frais et affichage. Mesurer séparément justesse d'identification, justesse des comparables, latence et disponibilité ; une source indisponible n'est pas un échec OCR.
- [ ] Valider l'estimation contre des reventes documentées indépendantes si disponibles ; sinon qualifier la méthode et ses limites sans annoncer une précision prédictive non mesurée. Actualiser documentation, migrations/tests, sauvegarde et retour arrière via T12.

**Acceptation :** démonstration reproductible du parcours complet dans les trois segments, sans requête réelle dans les tests ; résultats et abstentions cohérents dans toutes les vues ; aucun calcul avant résolution du doute d'identité ni estimation présentée comme prix de vente garanti. Les critères produit/source non résolus restent explicitement non validés.

### T19 — Adapter les collecteurs marketplace et le traitement OCR

**Skills, tests et intégrations :** [fiche T19](docs/identification/PLAN_VALIDATION_LOTS.md#t19). **Spécification :** [collecte, parcours et OCR](docs/identification/T19_COLLECTE_OCR.md). Les sous-lots sont à réaliser ; aucun collecteur n'est activé ni test réseau lancé par ce complément.

#### T19.1 — Parcourir les annonces et conserver les bonnes images

**Skills, tests et intégrations :** [fiche T19.1](docs/identification/PLAN_VALIDATION_LOTS.md#t191).

- [ ] Vérifier par plateforme le mode réel et modifier ses adaptateurs/normaliseurs : première page, pagination/curseur, DOM/défilement et limites d'accès. Borner pages, annonces, durée, retries ; distinguer fin réelle, réponse partielle, format non compris et blocage.
- [ ] Adapter capture Chrome/service worker et contrat collecteur : texte/provenance, photo principale et galerie optionnelle bornée, vues détaillées et images différées, sans exiger nom canonique/extension connus ; anciens payloads/JSONL compatibles.
- [ ] Préserver l'association source/ID/URL/texte/photos sur DOM virtualisé et pages répétées ; ne pas confondre miniature, photo de l'annonce et image du référentiel. Tester capture après navigation/défilement sans annoncer un scroll actif absent du code.
- [ ] Conserver filtres/prix exacts en centimes/bps, observations d'origine et limites de collecte ; aucune récupération de détail/image non configurée implicitement.

#### T19.2 — Raccorder les veilles à une analyse OCR commune et durable

**Skills, tests et intégrations :** [fiche T19.2](docs/identification/PLAN_VALIDATION_LOTS.md#t192).

- [ ] Après ingestion, garantir une demande d'analyse durable/dédupliquée ou son rattrapage déterministe ; réservation et reprise sans travail perdu, réseau/OCR hors transaction, collecte suivante et autres files non bloquées.
- [ ] Réutiliser T06/T07 et la décision T03/T05 : état d'analyse lié à la vue, aux observations et aux versions, concurrence agrégée app/worker et budgets effectifs. Pas de second moteur de matching par plateforme.
- [ ] Même annonce/photo inchangée ou prix seul modifié : pas de nouvel OCR inutile ; nouvelle preuve pertinente : réexamen. Avant publication vérifier empreinte/révision/existence/lot et préserver confirmations humaines, données originales et `first_seen_at`.
- [ ] Image manquante/inaccessible, OCR indisponible/saturé, délai ou quota : conserver l'annonce, diagnostic et reprise bornée ; traitement éphémère conforme T04 et aucune image/texte brut transmis à TCGdex.

#### T19.3 — Valider la collecte jusqu'à la fiche et aux comparaisons

**Skills, tests et intégrations :** [fiche T19.3](docs/identification/PLAN_VALIDATION_LOTS.md#t193).

- [ ] Tester chaque plateforme sur fixtures : parcours, pages/curseurs répétés, images tardives, tuile réutilisée, autre vue, absence d'image et réponse malformée ; toutes sorties externes interceptées.
- [ ] Tester restart, timeout, annulation, équité des files, limite globale de concurrence, réingestion et résultat périmé ; même annonce via extension/veille à observations égales → même proposition et mêmes limites.
- [ ] Vérifier observations OCR sur la fiche/formulaire de validation, choix humain durable et critères structurés des comparaisons locales/T16 ; ni lot ni identité incertaine valorisés automatiquement.

**Fichiers :** `app/collectors/`, `app/monitoring/`, `app/worker.py` si nécessaire, services OCR/résolution, extension content/background/popup, modèles/stockage et migrations additives si nécessaires. **Acceptation :** cas C01–C06 et T13 concernés passants dans les modes annoncés, tests unitaires/intégration/e2e et preuve photographique selon T01/T10 ; aucun mode indisponible annoncé fonctionnel. Ce lot appartient au job 3 après intégration des jobs 1/2.

## 6. T13 — Matrice de recette obligatoire

**Skills, tests et intégrations :** [fiche T13](docs/identification/PLAN_VALIDATION_LOTS.md#t13).

T13 est le référentiel de vérification des lots précédents, pas un chantier différé après livraison. Les identités attendues doivent provenir des annotations/fixtures, jamais du premier résultat du moteur testé.

| Cas | Attendu |
|---|---|
| Capture §1.3 « carte Pokémon ancienne Tortant obscur », photo lisible « Tortank obscur », `20/82`, texte français | Fixture photo/catalogue annotée indépendamment ; titre conservé, bonne référence parmi les propositions, nom canonique/extension/numéro réutilisables et langue proposée avec preuve ; confirmation puis même identité sur la fiche ; aucun `n` exploitable ni prix sur simple suggestion |
| Ancienne capture `name == title`, candidat compatible ou absent | Repli distingué d'un nom canonique ; proposition applicable sans écraser une correction humaine ; nom non résolu en l'absence de proposition étayée |
| Numéro vide ou fragment `n`, préfixe promo valide et numérotation atypique attestée | Bruit non prérempli comme numéro exploitable ; fragment traçable, numéros légitimes conservés, aucune correction fabriquée |
| Photo francophone sur site étranger, nom commun à plusieurs langues, lecture trop courte ou conflit de langue | Suggestion fondée sur fragments de la carte ou abstention ; ni locale du site/catalogue ni `fra+eng` ne prouvent la langue ; conflit visible et confirmation distincte |
| Bonne réponse OCR reçue, formulaire déjà rempli par le titre ou modifié par l'utilisateur | Repli de capture remplaçable par une proposition ; correction humaine préservée ; aucune ancienne réponse appliquée après changement des preuves |
| Après préremplissage : nom, extension et numéro valides séparément mais incompatibles entre eux ou avec l'ID choisi | Conflit par champ et global, candidats de diagnostic accessibles ; aucune confirmation/valorisation de la combinaison ; même refus côté serveur sans JavaScript |
| Après préremplissage : extension/langue absente ou numéro invalide, autres indices exploitables | Recherche locale partielle possible avec critères et exclusions visibles, aucune valeur inconnue utilisée comme filtre exact ni champ inventé ; limites distinctes pour la confirmation et les comparables |
| Préremplissage depuis un candidat puis réanalyse, ou modification du numéro/extension/langue après choix | Aucun gain artificiel de confiance par recopie ; provenance conservée ; choix/résultats inapplicables invalidés selon révision et nouvelle vérification requise |
| Workflow W01 à W11, correction de champ puis autre photo et enrichissement du catalogue | Ordre et branches §4.1/§4.2 respectés ; correction textuelle sans nouvel OCR, autre photo avec nouvelle analyse, enrichissement suivi d'une recherche locale ; aucun write d'annonce avant W09, aucun job marché avant commit/identité admissible, aucune boucle sur préremplissage/rechargement |
| Collecteurs Vinted/Leboncoin/eBay/Wallapop : pages/curseurs répétés, DOM différé/virtualisé et photos tardives | Parcours borné, conditions d'arrêt établies, chaque texte/photo rattaché au bon ID ; état partiel/erreur distinct d'une vraie fin, galerie/anciens payloads compatibles |
| Veille : ingestion, analyse en file puis autre passage au prix modifié | C01–C06 : annonce conservée avant OCR, analyse dédupliquée, prix seul sans relecture, autres veilles non bloquées et `first_seen_at` inchangé |
| OCR interactif et worker simultanés, crash et réponse d'une ancienne photo/révision | Limite de concurrence agrégée vérifiée ; reprise sans perte/duplication, ancien résultat rejeté et confirmation humaine préservée |
| Même annonce via extension et collecteur, à observations égales | Même proposition/provenance et attributs inconnus, fiche/validation et comparaisons locales utilisant la même identité effective |
| Photo lisible, prix/port mal saisi ou devise absente | OCR, candidats et choix de référence disponibles ; erreur financière affichée séparément, aucun zéro inventé ; correction financière sans nouvel OCR ni perte de sélection |
| Fermeture du popup pendant lecture ou interruption après capture | Capture et corrections récupérables, prévisualisation/progression accessibles ; reprise contrôlée sans doublon ni prétendue conservation d'une photo éphémère perdue |
| Titre vendeur explicitement faux, bonne référence visible dans le diagnostic | Résolution humaine motivée disponible ; titre et conflit conservés dans l'audit, référence revalidée et décision appliquée à l'ajout ; aucune confirmation automatique du conflit |
| Référence choisie en prévisualisation puis ajout, doublon ou échec transactionnel | Même choix effectif sur la fiche ; aucun besoin d'annonce provisoire ; décision humaine existante protégée, rollback sans état faussement confirmé |
| Langue inconnue, carte non résolue, informations financières requises valides | Enregistrement possible sans fausse langue française ni référence arbitraire ; statut inconnu conservé dans fiche/export ; comparaison qualifiée limitée explicitement |
| Arrêt après ajout mais avant lancement de recherche de marché | Après reprise, une seule recherche admissible exécutée ; aucune recherche perdue ni résultat d'une ancienne révision réappliqué |
| Annonce détectée par mots-clés, photo absente/en échec ou analysée sans candidat, puis choix et confirmation | Libellés correspondant aux étapes réellement atteintes : annonce capturée, photo analysée, carte proposée, identité confirmée ; aucune carte annoncée identifiée sur la seule détection d'annonce |
| Mauvaise photo principale ou miniature illisible, autre photo détaillée disponible | Choix de la vue capturée ou téléversement, recadrage dans la prévisualisation et réanalyse accessibles ; photo/région source explicite, résultat précédent invalidé, pas de fusion entre exemplaires |
| Photo inclinée et titre explicitement faux, contrairement à une simple faute de frappe | Photo/référence comparables côte à côte après cadrage ; contradiction conservée, choix explicite demandé, aucune confirmation automatique ni correction silencieuse du titre |
| Plusieurs versions proches, image de référence présente ou manquante | Détails discriminants et photo analysée visibles côte à côte si possible ; agrandissement accessible, comparaison textuelle utilisable sans image, choix non imposé par la seule illustration |
| Numéro illisible, couverture manquante établie, versions multiples et cause indéterminée | Diagnostic distinct avec action adaptée (recadrer/autre photo, enrichir, comparer/choisir ou compléter les preuves) ; aucun catalogue déclaré incomplet sur la seule absence de candidat |
| Identité confirmée, mais attribut nécessaire inconnu ou aucune source de prix adaptée | Identité conservée ; comparaison « à compléter » avec attributs nécessaires listés ou « indisponible » avec raison ; aucune édition/finition/gradation inventée ni estimation forcée |
| « Évoli V vendu avec 3 cartes en plus » | Lot, aucune identité unitaire effective, aucune valorisation comme carte seule |
| « en plus », « en bon état », `VO` seul | Aucune langue anglaise inventée |
| `Langue : EN`, « carte anglaise », langues contradictoires | Contexte explicite reconnu ; contradiction conservée ; pas de substitution silencieuse par une référence française |
| `nearmint`, `near-mint`, `near mint` | Même normalisation d'état déclaré, aucune vérification physique implicite |
| `Dracaufeu ex`, état non fourni | Suffixe préservé, pas d'état Excellent déduit de `ex` |
| Carte unique avec 3 photos, protection ou boîtier | Aucun lot déduit seulement de ces accessoires/vues |
| « carte au choix parmi 3 » | Aucune identité unitaire arbitraire pour l'annonce entière |
| Titre `Pikachu 58/102`, OCR `15` | Fraction textuelle conservée, OCR non substitué ; désaccord visible si pertinent |
| OCR `108/59`, candidat `108/159` | Hypothèse tracée, alternatives/limites, confirmation humaine nécessaire |
| Mauvaise réparation plausible ou bonne référence absente | Aucune acceptation automatique fabriquée ; raison de l'échec visible |
| « Evoli V 0113/15 gempack 2 », « nearmint » | Extraction brute conservée, alias vérifié seulement, couverture réelle visible ; identité exacte non imposée sans preuve |
| Référence dans une autre locale ou deux localisations du même ID | Aucun écrasement ni équivalence d'impression inventée ; recherche adaptée ou abstention |
| Deux impressions avec illustration identique | Candidats multiples tant que le détail discriminant manque |
| Holo/reverse, photo sans preuve de finition | Finition inconnue, aucune cote spécifique implicitement confirmée |
| Proxy/faux visuellement proche | Aucune conclusion d'authenticité |
| Photo inclinée, carte loin du centre, masquage, reflet | Cadrage/OCR bornés, qualité signalée, correction manuelle disponible |
| Photo avec orientation EXIF, carte en perspective et recadrage imbriqué | Orientation appliquée une seule fois ; boîtes OCR reprojetables sur la bonne zone de la photo ; transformations vérifiées |
| Quadrilatère dégénéré, contour de boîtier ou carte partiellement hors champ | Géométrie douteuse rejetée, motif visible et repli manuel/photo entière ; aucune localisation réussie inventée |
| Nom en haut de la photo mais hors de la carte, étiquette PSA/PCA séparée | Positions interprétées dans le repère de chaque objet ; aucun texte de fond/certificat substitué au nom ou au numéro de carte |
| Numéro séparé en `025`, `/`, `165` et fragments provenant d'une autre carte | Reconstruction des fragments voisins du même objet uniquement ; aucune fraction composée entre cartes |
| OCR `O25／165`, préfixe promo valide, numéro secret ou lecture atypique | Original et hypothèses distincts, préfixes préservés, vérification catalogue ; aucune correction globale ni rejet fondé sur le seul ratio 1,6 |
| Première hypothèse sans résultat ou menant à une mauvaise référence, suivante compatible | Hypothèses examinées dans les plafonds, candidats réunis puis départagés ; aucune acceptation de la première correspondance par défaut |
| Plusieurs cartes/régions | Aucune combinaison nom/numéro provenant d'objets distincts |
| Image absente, invalide, trop grande, OCR saturé ou délai dépassé | Message utile, pas de crash ni blocage de l'enregistrement |
| Poids/index/langue OCR non disponibles | Repli local explicite, aucune récupération distante implicite |
| Formulaire modifié pendant une analyse, worker en retard | Résultat périmé non appliqué |
| Confirmation → réingestion identique → réidentification | Décision applicable conservée, `first_seen_at` inchangé |
| Modification de preuve, retrait et corrections concurrentes | Réexamen/conflit explicite ; audit conservé ; ancienne décision non réactivée |
| Sauvegarde/restauration, preuve manquante, purge | Intégrité vérifiée, inéligibilité/réexamen signalé, aucune preuve prétendument disponible |
| Identité connue, langue/état/cote manquants | Annonce conservée ; limites financières claires et mêmes résultats dans exports/opportunités |
| Même annonce via URL, extension, JSONL et collecte | Proposition cohérente à observations égales, provenance conservée, aucun clic d'ajout assimilé à une validation d'identité |
| Carte non gradée, PSA 10, PSA 9 et PCA 10 de même identité | Segments distincts ; aucun mélange de prix ni conversion de note |
| Étiquette lisible mais note/certificat proches du numéro de carte | Champs séparés ; aucun numéro de certificat pris pour l'identité de la carte |
| Titre PSA 10, étiquette PCA 9 ou note illisible | Contradiction/inconnu visible ; confirmation demandée avant valorisation |
| Cote Cardmarket non gradée seule pour une carte PSA/PCA | Cote non utilisée comme prix de revente de l'exemplaire gradé |
| Identité admissible enregistrée, sources configurées | Recherche de marché automatique bornée et état visible, sans clic supplémentaire |
| Réingestion, rechargement et import d'un comparable | Pas de duplication inutile ni boucle de recherches automatiques |
| Correction d'identité/gradation pendant la recherche | Ancienne estimation invalidée, résultat périmé non appliqué |
| Offre active, enchère, annonce retirée et vente documentée | Natures distinctes ; aucun prix de vente réalisé fabriqué |
| Vente marquée conclue mais prix négocié réel inconnu | Pas de montant supposé comme transaction exploitable |
| Annonce évaluée retrouvée, republication ou observations répétées | Auto-comparaison exclue ; effectifs non gonflés |
| Même nom mais autre version/langue/finition ou lot | Exclusion des comparables exacts avec motif, aucun prix injecté silencieusement |
| Accès eBay/ventes absent, panne ou quota épuisé | Couverture manquante/partielle visible, annonce conservée, aucun faux résultat vide global |
| Prix uniquement affichés/cote générale, preuves insuffisantes | Offres/ventes/cote séparées ; repli seulement selon le choix produit validé |
| Port/frais inconnus, devise ou destination incompatibles | Inconnus visibles ; absence de marge qualifiée fondée sur des coûts supposés nuls |

## 7. Vérifications à exécuter lors de l'implémentation

Le [plan de validation par lot](docs/identification/PLAN_VALIDATION_LOTS.md) précise pour **T00 à T19 et leurs sous-lots T06/T08/T19** le skill approprié ou son absence, les intégrations, suites existantes, nouveaux scénarios et critères de validation. Il complète les critères métier de chaque tâche ; les fichiers de tests futurs y sont distingués des fichiers déjà présents. Les écarts et erreurs se suivent dans [tracker.md](tracker.md).

Commandes existantes, à exécuter dans Docker. Les tests utilisent uniquement des fixtures et bases temporaires ; vérifier l'isolation avant exécution. Les futurs tests des nouveaux modules s'ajoutent aux groupes concernés.

```bash
docker compose run --rm app pytest tests/test_identification.py tests/test_identification_reliability.py tests/test_candidate_number_warning.py tests/test_lexical_identification.py
docker compose run --rm app pytest tests/test_ocr_local.py tests/test_ocr_web.py tests/test_listing_preview.py tests/test_validation_history.py
docker compose run --rm app pytest tests/test_tcgdex_cache.py tests/test_tcgdex_sync.py tests/test_identification_research.py
docker compose run --rm app pytest tests/test_identification_reviews.py tests/test_annotation_pilot.py tests/test_migrations.py tests/test_backups.py
docker compose run --rm app pytest tests/test_chrome_extension.py tests/test_extension_e2e.py tests/test_capture_preview.py tests/test_manual_listing.py tests/test_page_fetch.py tests/test_page_extract.py
docker compose run --rm app pytest tests/test_watch_ingestion.py tests/test_pipeline_integration.py tests/test_imports.py tests/test_catalog.py tests/test_profitability.py tests/test_web.py
docker compose run --rm app pytest tests/test_search.py tests/test_cardmarket.py tests/test_cardmarket_guide.py tests/test_cardmarket_daily.py tests/test_sellers_directory_and_purchases.py tests/test_trends.py
docker compose run --rm app pytest
```

Ajouter des tests de comportement pour les nouvelles règles, les contrats de preuves, migrations, concurrence, limites et replis. Ajouter des fixtures photographiques locales avec labels exacts pour les régressions OCR ; les mocks OCR seuls ne démontrent pas un gain de reconnaissance. Les tests d'intégration du moteur réel doivent être bornés et distincts des benchmarks volumineux.

Pour J3, ajouter les tests hermétiques d'orchestration de marché et de comparabilité PSA/PCA ; les suites existantes ne démontrent pas à elles seules l'acquisition de ces nouveaux comportements. Le réseau est simulé jusque dans le worker et les réponses de prix sont figées.

La recette navigateur utilise les données locales prévues et le réseau marketplace simulé. L'acquisition réelle éventuelle reste un script manuel distinct conforme à SOURCES ; le benchmark relit ensuite les artefacts locaux figés. Ne pas lancer `run_30_liens.py` comme s'il s'agissait déjà d'un rejeu hermétique.

## 8. Suivi et transmission au développeur

Pour chaque lot, enregistrer état (`à faire`, `en cours`, `partiel`, `bloqué`, `validé` sur périmètre explicite, `conditionnel` ou `non retenu` pour T11), dépendances, fichiers touchés, tests/rapports, limites et prochaine action. Un blocage d'annotation humaine ou de référence indisponible ne se résout pas avec des labels automatiques.

Appliquer le [plan des skills et validations](docs/identification/PLAN_VALIDATION_LOTS.md) avant de clore un lot. Toute erreur rencontrée ou intégration non validée qui bloque son périmètre doit être créée/dédupliquée dans [tracker.md](tracker.md), avec reproduction, preuve, responsable, tests affectés et revalidation. Le correctif et le résultat des tests mettent à jour le même ID ; une entrée n'est clôturée qu'après vérification. Les autres tâches indépendantes continuent, sans déclarer validé le périmètre encore bloqué. Les entrées initiales et leurs mises à jour distinguent observations statiques, cas à reproduire, intégrations cibles manquantes et limites de capacité/qualification.

**Historique des compléments de cadrage :** les mentions « aucun code livré par cette mise à jour » ci-dessous décrivent chaque intervention datée. Elles ne remplacent pas les acquis livrés ensuite, synthétisés en tête et dans TASKING_PROJET.

**Préparation T06/T07 — 3 novembre 2026 :** procédure technique rédigée dans [docs/identification/T06_T07_PROCEDURE_OCR.md](docs/identification/T06_T07_PROCEDURE_OCR.md). Contrats, algorithmes, étapes, tests et comparaison avant/après y sont proposés ; aucun nouveau code OCR, dépendance, migration ou benchmark de justesse n'est livré par cette rédaction. Prochaine action : étape A (contrats/limites), puis cadrage manuel et TSV, en respectant les dépendances T04/T05 et les annotations nécessaires à la mesure.

**Complément capture/OCR — 8 novembre 2026 :** §1.3, T06.4, T07, T08.1/T08.2, T13 et T16 précisent le résultat attendu depuis la capture fournie. Prochain travail indépendant : T08.1 et reproduction du numéro `n` ; préparer la fixture locale photo/catalogue avec annotation indépendante, puis livrer ensemble moteur T06/T07 et raccordement T08.2. La capture d'écran fournie peut documenter la régression ; l'acquisition de la photo originale pour mesurer l'OCR reste distincte et explicite. Aucun code applicatif ni nouvelle qualification n'est livré par cette mise à jour.

**Précision sur les contrôles — 8 novembre 2026 :** T08.3 et la procédure §8.5 exigent une revalidation après préremplissage/saisie, la cohérence entre champs et référence, des recherches partielles expliquées et un contrôle final serveur. Les champs issus d'un candidat ne peuvent pas servir à s'auto-confirmer. Ces contrôles sont spécifiés, pas encore implémentés par cette modification documentaire.

**Complément de recette utilisateur — 8 novembre 2026 :** cinq exigences rendues obligatoires en T06.1/T08.2/T13 : avancement explicite capture/analyse/proposition/confirmation, choix d'une photo détaillée et recadrage, affichage photo/référence côte à côte, diagnostic avec action adaptée et séparation identité/comparabilité. T17 fournit les attributs manquants et limites de sources. Les variantes de recette incluent titre faux, photo inclinée, mauvaise photo principale, référence absente et versions proches ; acquisition de fixtures et annotations restent à réaliser. Cette mise à jour porte sur les spécifications, sans modification du moteur ni validation de ces recettes.

**Workflow consolidé — 8 novembre 2026 :** §4.1/§4.2 fixent les étapes W01 à W11, les déclencheurs, responsables, sorties et reprises. Recherche de référence avant projection des champs ; recherche de marché après enregistrement admissible. Le code `app/identification/pipeline.py` existant orchestre la résolution d'une annonce persistée : il ne démontre pas à lui seul l'implémentation de ce workflow complet. Consolidation documentaire uniquement ; transitions et recette restent à implémenter/vérifier.

**Revue d'adéquation — 8 novembre 2026 :** écarts et adaptations consignés en §4.3 : identification indépendante des erreurs financières, parcours indépendant du popup, résolution d'un titre faux, conservation atomique du choix, inconnus d'identité explicites, reprise d'enrichissement et recherche de marché durable. W02/W08/W09, T08/T16 et T13 précisés. Verdict limité à la conception documentaire ; aucun test applicatif de ces nouveaux comportements ni recette sur l'annonce réelle n'est déclaré passant.

**Collecteurs marketplace — 8 novembre 2026 :** demande explicite d'adapter les collecteurs qui parcourent Vinted/Leboncoin/eBay/Wallapop. §4.4 et T19 spécifient parcours/images/contrats, traitement OCR durable, concurrence app/worker et recette C01–C06 ; voir [T19_COLLECTE_OCR.md](docs/identification/T19_COLLECTE_OCR.md). Le job 3 doit modifier et intégrer les collecteurs/normaliseurs, la capture Chrome et l'ordonnanceur après les jobs 1/2. Aucun code applicatif modifié par ce complément ; les changements de code en cours d'autres travaux sont préservés. Écarts nouveaux suivis sous TRK-100/TRK-101.

Le développement peut produire les outils et commencer sur les fixtures, mais ne peut déclarer acquises des annotations indépendantes, une expertise humaine ou une qualification statistique manquantes. Réaliser toutes les tâches indépendantes ; laisser explicitement ouverts les critères non démontrés.

**Prochain travail concret au 8 novembre :** préserver T00/T02/T03/T04, le socle T05 et T08.1/T08.3 actuel ; compléter les fixtures/annotations T01, puis développer T06/T07 et leur raccordement T08.2/T09. Ne pas « raccorder T03 » comme s’il manquait. T19.1 et TRK-101 peuvent avancer indépendamment sur fixtures ; T19.2/3 attendent le moteur commun et le parcours intégré.

**Suite au recadrage marché :** préserver le T02 déjà implémenté et vérifier son état courant plutôt que le refaire. Réactualiser T15 déjà documenté et recueillir les choix ouverts de §1.2 ; préparer ensuite les contrats T14/T16/T17. Ne pas attendre un nouveau modèle visuel pour vérifier les sources et ne pas engager une implémentation financière dépendante d'un arbitrage encore absent.

**Dossier final attendu :** code et migrations nécessaires, contrats compatibles, recette end-to-end, rapport de benchmark avec vérité terrain, procédure d'exploitation/restauration, périmètre couvert et registre des limites. Aucun lot n'est déclaré validé sur la seule base d'une démonstration réussie ou du nombre de statuts `identified`.

## 9. Références techniques pour les expériences

Ces sources documentent des méthodes ; elles ne démontrent pas leur performance sur Pokébourse. Figer les versions effectivement retenues au moment des expériences.

- [Tesseract — qualité d'entrée, redressement et segmentation](https://tesseract-ocr.github.io/tessdoc/ImproveQuality.html).
- [Tesseract — sortie TSV, positions et scores des mots](https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html#tsv-output).
- [OpenCV — correspondances locales et homographie](https://docs.opencv.org/4.x/d1/de0/tutorial_py_feature_homography.html).
- [DINOv2 — représentations visuelles](https://arxiv.org/abs/2304.07193).
- [CLIP — apprentissage image/texte](https://proceedings.mlr.press/v139/radford21a.html).
- [Calibration des probabilités — Guo et al.](https://proceedings.mlr.press/v70/guo17a.html).
- [TCGdex — contrat d'une fiche de carte](https://tcgdex.dev/rest/card).

Références d'accès marché consultées lors du recadrage, à revérifier en T15 ; elles ne constituent pas la preuve d'un accès configuré sur cette installation :

- [eBay Browse API — recherche d'offres et authentification](https://developer.ebay.com/develop/api/buy/browse_api).
- [eBay — Marketplace Insights restreint et non ouvert aux nouveaux utilisateurs](https://www.developer.ebay.com/api-docs/buy/static/ref-buy-browse-filters.html).
- [Cardmarket — guide de prix et catalogue téléchargeables, guide actualisé quotidiennement](https://news.cardmarket.com/en/StarWarsUnlimited/were-making-the-price-guide-and-product-catalogue-available-for-download).
