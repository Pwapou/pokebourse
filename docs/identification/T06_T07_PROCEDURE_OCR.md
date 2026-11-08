# Procédure T06/T07 — Cadrage, OCR spatial et hypothèses de numéro

**État réconcilié au 8 novembre :** les composants internes du moteur spatial sont désormais consolidés depuis `ocr-parallele` et `ocr-p2` ; le raccordement HTTP/T03/T08.2, la concurrence app/worker et la qualification photographique restent à réaliser. Voir [l’intégration retenue](T06_T07_INTEGRATION_JOB3.md). T08.1 et les contrôles du moteur actuel sont préservés : réutiliser [leur contrat et le relais](T08_CONTROLES_MOTEUR_ACTUEL.md), sans refaire ces correctifs. Ordre global : [TASKING_PROJET.md](../../TASKING_PROJET.md).

Date : **3 novembre 2026**. Statut : **spécification à implémenter**, sans changement du moteur livré ni résultat de précision acquis. Ce document précise les lots [T06/T07 du tasking](../../TASKING_IDENTIFICATION_FIABLE.md#t06--repérerredresser-la-carte-et-conserver-la-position-des-textes). Les valeurs de réglage ci-dessous constituent un point de départ expérimental versionné, pas des seuils de fiabilité démontrés.

Complément du **8 novembre 2026** : inclure la suggestion de langue étayée par la photo et la projection des références vers les champs de capture, selon [le cas de recette §1.3](../../TASKING_IDENTIFICATION_FIABLE.md#13-résultat-attendu-sur-une-capture-au-titre-imprécis) et T08.1/T08.2. Le correctif titre/nom peut être livré avant le moteur spatial ; le parcours OCR n'est terminé qu'après raccordement à l'interface. Aucun code nouveau n'est livré par ce complément.

## 1. Résultat attendu et point de départ

Parcours cible : **photo → orientation EXIF → sélection de la carte → redressement → textes positionnés et indices de langue → lectures/hypothèses de numéro → candidats TCGdex → champs canoniques proposés → confirmation de référence/attributs → enregistrement cohérent**. Une étape infructueuse laisse une voie manuelle disponible. Une carte reconnue dans une photo de lot n'autorise jamais une identité unitaire pour l'annonce. La comparaison directe d'images reste T11 ; l'acquisition d'offres/prix reste T16/T17.

Le [workflow d'exécution W01 à W11](../../TASKING_IDENTIFICATION_FIABLE.md#41-workflow-dexécution-de-la-capture-aux-comparaisons) fixe l'ordre global, les déclencheurs et les effets de bord ; ses [règles de reprise](../../TASKING_IDENTIFICATION_FIABLE.md#42-reprises-branches-derreur-et-absence-de-boucles) précisent les retours. Cette procédure détaille surtout W03 à W07. La recherche locale de référence précède le préremplissage canonique ; une correction de champ relance la recherche locale avec les lectures encore valides, un changement de photo/cadrage relance l'OCR. Aucune boucle d'auto-confirmation ni recherche marketplace dans la prévisualisation ; les estimations indicatives locales gardent les restrictions T09.

La [revue d'adéquation du workflow](../../TASKING_IDENTIFICATION_FIABLE.md#43-revue-dadéquation-au-besoin--8-novembre-2026) précise les écarts restant à implémenter : erreurs financières non bloquantes pour l'identification, reprise sans popup, résolution humaine d'un titre faux et conservation du choix jusqu'à l'ajout. Les prescriptions de §8 ci-dessous doivent respecter ces branches, sans promouvoir l'OCR en confirmation automatique.

L'entrée [collecteurs et workers T19](T19_COLLECTE_OCR.md) doit réutiliser ces composants pour les annonces des veilles : ingestion préalable puis travail OCR en file, publication contrôlée par empreinte/révision, pas de calcul long dans l'ingestion. La limite de concurrence se vérifie sur app et worker ensemble. Le job OCR parallèle livre les modules indépendants ; le job 3 adapte réellement collecte/extension/ordonnanceur et valide les deux entrées.

Le code courant fournit déjà :

- `app/identification/ocr.py` : validation JPEG/PNG/WebP, 8 Mo, 12 millions de pixels, orientation EXIF, Tesseract local `fra+eng`, deux analyses simultanées, suggestions sans écriture. Le délai de 20 secondes s'applique actuellement à **chaque appel** Tesseract.
- `_targeted_images()` : bandes haute de 20 % et basse de 15 % de **la photo entière**, contraste et agrandissement en secours. Les positions du texte sont perdues dans la sortie texte actuelle.
- `CardMatcher.identify_evidence()` et `decision.propose()` : règles communes et garde-fous T03 ; `seed_if_empty=False`, `repair_index=False` nécessaires pour les lectures sans écriture.
- `ObservationInput` : `image_ref` et `region` optionnels, mais pas de transformation projective ni de groupe d'hypothèses. Le contrat refuse les champs inconnus.
- `decision._conflicts()` : deux numéros OCR différents sont aujourd'hui des observations concurrentes. **Ne pas envoyer toutes les corrections possibles dans `ocr_numbers` : cela créerait de fausses contradictions.**
- `manual_listing.py`, `capture_preview.py` et les formulaires : transport historique de listes de noms/numéros, au plus six de chaque ; `ocr.js` affiche des suggestions et utilise la confirmation existante avec empreinte/révision.

Aucun pHash, modèle distant, ML Kit ni nouveau moteur OCR n'est nécessaire à cette procédure. Les objets géométriques utilisent des nombres réels ; les prix/taux restent exclusivement en centimes et points de base.

## 2. Découpage de développement et fichiers

Les noms suivants sont proposés pour l'implémentation, ils ne désignent pas des modules déjà présents. Garder les fonctions pures séparées de HTTP/SQLite et les nouvelles fonctions typées/documentées.

| Étape | Fichiers à créer ou adapter | Livraison vérifiable |
|---|---|---|
| A — Contrats et limites | `app/identification/ocr_types.py`, `ocr.py`, tests locaux | Types/versions, budget global, anciens appels compatibles |
| B — Cadrage manuel | `ocr_geometry.py`, `ocr.js`, templates OCR concernés | Rectangle, rotation explicite et coordonnées fiables après EXIF |
| C — Texte positionné | `ocr_text.py`, `ocr.py` | Parsing TSV, lignes/fragments et reprojection |
| D — Redressement automatique | `ocr_geometry.py`, dépendance expérimentale si nécessaire | Détection de quadrilatères, homographie, refus/repli |
| E — Hypothèses et recherche | `ocr_numbers.py`, `matcher.py`, `decision.py`, `evidence.py` | Alternatives groupées, union des candidats, mêmes règles de décision |
| F — Transport et recette | `manual_listing.py`, `capture_preview.py`, formulaires, extension, pilote T04 | Nom/extension/numéro proposés, langue étayée à confirmer, choix de référence utilisable avant ajout, recette §1.3 et benchmark apparié |

Interfaces internes proposées (types définis en §3) : `prepare_image(content: bytes) -> PreparedImage`, `select_regions(image: PreparedImage, selection: CropSelection | None, config: OcrConfig) -> tuple[CardRegion, ...]`, `rectify_region(image: PreparedImage, region: CardRegion) -> RectifiedCard`, `parse_tsv(payload: str, context: OcrPassContext) -> tuple[OcrToken, ...]`, puis `generate_number_hypotheses(...)` et récupération commune. Passer configuration/échéance explicitement aux traitements ; les fonctions géométriques et de parsing ne dépendent ni d'une requête HTTP ni d'une connexion SQLite.

Implémenter B/C avant D : le cadrage humain fournit une référence pour séparer les échecs de localisation des échecs de lecture. Ne pas marquer T06/T07 terminés après les seules étapes A/B.

En parallèle, réaliser T08.1 avec le matcher actuel : `name: title` est un repli de capture, pas une identité canonique. La nouvelle projection peut remplacer ce repli tout en conservant le titre capturé et sa provenance ; elle ne remplace jamais silencieusement une correction humaine. Livrer C/E avec F pour démontrer que les lectures améliorées deviennent utilisables dans le formulaire et sur la fiche.

### Dépendances et mode expérimental

Pillow suffit à la première livraison : orientation, rectangle, rotations de 90°, régions et mise à l'échelle. Pour D, retenir **OpenCV headless** comme backend expérimental de contours/homographie (`opencv-python-headless` et sa dépendance NumPy), sans modèle appris. Il n'est actuellement pas déclaré dans `pyproject.toml`.

Lors de l'implémentation de D, isoler cette dépendance dans un extra d'expérimentation, vérifier sa compatibilité Python 3.12/Linux et figer les versions testées dans le manifeste de benchmark. Documenter coût mémoire/taille d'image Docker et gain avant intégration au profil de production. Import paresseux : sans cet extra, cadrage manuel et OCR restent utilisables. Aucun `pip install` ni téléchargement au moment d'analyser une photo. Le changement de dépendance n'est pas effectué par cette spécification.

## 3. Contrats internes et contrat HTTP

Définir des dataclasses immuables pour l'interne et une validation Pydantic stricte aux frontières. Les noms/versionnements ci-dessous sont des cibles ; les modèles actuels ne les acceptent pas encore.

| Type | Champs minimaux et sens |
|---|---|
| `PreparedImage` | `image_ref` (empreinte des pixels orientés et dimensions, méthode versionnée), image RGB éphémère, largeur/hauteur, rotation EXIF appliquée |
| `CardRegion` | `region_id`, `object_id`, `kind` (`card`, `label`, `unknown`), quatre coins dans la photo orientée, méthode (`manual`, `auto`, `full_image`), motifs/qualité géométrique |
| `RectifiedCard` | image redressée, dimensions, `photo_to_card` et inverse `card_to_photo` (matrices 3 × 3), rotation supplémentaire explicite |
| `OcrToken` | identifiant de passe/fragment, texte brut, boîte dans la passe, boîte normalisée, quadrilatère reprojeté dans la photo, groupe page/bloc/paragraphe/ligne, score technique optionnel |
| `OcrReading` | `reading_id`, `object_id`, fragments sources, texte brut assemblé, rôle supposé (`name`, `number`, `language`, `unknown`), opérations géométriques, version |
| `NumberHypothesis` | identifiant, `reading_id`/groupe alternatif, valeur proposée, préfixe/numérateur/dénominateur/suffixe optionnels, opérations, rang, origine(s), état de recherche catalogue |
| `LanguageHypothesis` | langue candidate ou abstention, fragments discriminants du même objet, méthode/version, motif et éventuel conflit ; aucune confirmation implicite |
| `OcrAnalysis` | versions schéma/pipeline/paramètres, régions, seules lectures utiles, hypothèses, diagnostics, durées et troncatures ; aucune autorité humaine |

Les coordonnées géométriques doivent être finies et bornées ; rejeter `NaN`, infinis, matrices singulières, listes excessives et références de fragments absentes. Les IDs d'objet sont locaux à l'analyse, pas une conclusion sur les objets vendus.

### Extension compatible de `/ocr/suggestions`

Conserver `status`, `recognized`, `candidates`, `message` et les valeurs actuelles de statut. Ajouter des champs optionnels `analysis_version`, `geometry`, `ocr_evidence`, `language_hypotheses`, `diagnostics`, `timings`. Un résultat partiel porte un diagnostic, sans inventer un nouveau statut obligatoire pour les anciens clients.

- `recognized.names` et `recognized.numbers` restent des lectures originales utiles, au plus six de chaque. **Ne jamais y projeter une réparation comme si elle avait été lue.** Des lectures originales différentes restent concurrentes.
- `ocr_evidence` est une enveloppe versionnée et bornée de lectures/hypothèses ; elle contient seulement les fragments nécessaires au nom/numéro et à l'indice de langue. Ne retourner ni TSV complet ni textes de fond, contacts ou métadonnées EXIF.
- `language_hypotheses` est optionnel, limité aux langues effectivement évaluées, au plus trois propositions et six fragments utiles par proposition dans les plafonds globaux. Il expose une suggestion, pas la langue confirmée. Étendre explicitement le champ OCR `language`, aujourd'hui refusé par `validate_observations()`, avec code validé, fragments justificatifs et provenance indicative ; adapter décision et formulaires ensemble. Les langues alternatives restent groupées et ne deviennent pas des déclarations simultanées dans `decision._conflicts()` ; un désaccord réel avec une langue déclarée reste visible. Aucun score Tesseract n'est une probabilité de langue.
- Exposer « lu », « hypothèse » et opérations dans l'UI, pas seulement une liste de numéros corrigés. Les scores restent techniques.
- Pour les anciens clients sans enveloppe, garder le comportement T03 ; l'absence de géométrie reste une provenance inconnue, jamais une boîte fabriquée.
- Pour les nouveaux clients, adapter explicitement les schémas/formulaires/adaptateurs avant transport. Ne pas glisser des champs spatiaux dans `ObservationInput`, qui les refuse actuellement, sans faire évoluer son contrat.

Entrées de cadrage proposées : `crop` rectangle ou `quad` de quatre coins, rotation choisie parmi 0/90/180/270, dimensions du repère orienté et version du contrat ; rectangle et quadrilatère sont exclusifs. Le serveur valide contre les dimensions réellement décodées et reconstruit les transformations : aucune matrice fournie par le navigateur n'est une preuve fiable.

## 4. Orientation et recadrage manuel

**Avancement du 8 novembre 2026 :** la fiche annonce propose un rectangle manuel sur prévisualisation éphémère orientée, saisie numérique et rotations de 90°, transmis à l'OCR existant. La prévisualisation de capture, le choix des photos, le parcours spatial complet et les mesures restent à réaliser (TRK-017) ; le chemin existant sans sélection reste la baseline.

1. Réutiliser les contrôles de `_prepare_image()`, appliquer `ImageOps.exif_transpose()` **une fois** et produire un RGB sans métadonnées. Calculer une référence stable des pixels/dimensions préparés ; pour T04, conserver séparément l'empreinte des octets exacts archivés. Une empreinte seule ne prouve pas leur conservation.
2. Présenter au navigateur une prévisualisation locale dans le même repère orienté. Préférer les pixels préparés par le serveur pour éviter les différences d'orientation implicite des navigateurs. Transport éphémère borné, sans URL publique, fichier temporaire durable ni cache persistant.
3. Prévoir un rectangle déplaçable/redimensionnable, champs numériques et rotations accessibles au clavier. Le recadrage manuel reste utilisable sans OpenCV. L'édition de quatre coins peut être ajoutée avec D pour corriger une perspective.
4. Convertir les coordonnées de l'affichage vers l'image en tenant compte de `object-fit: contain`, des marges de centrage et du zoom CSS : `x_photo = (x_affichage - marge_x) / échelle`, idem pour `y`. Les coordonnées du pointeur et du rectangle doivent employer le même repère CSS ; ne pas multiplier une seconde fois par `devicePixelRatio`.
5. Valider côté serveur : valeurs finies, dimensions concordantes, rectangle inclus et non vide, quatre points distincts/convexes/non croisés si quadrilatère. Refuser une demande invalide avec 400 ; garder photo et saisie dans l'UI.
6. Un rectangle produit une translation de coordonnées, puis éventuellement une rotation. Un quadrilatère utilise l'homographie de §5. Le défaut « photo entière » porte `kind=unknown` et `method=full_image`, sans prétendre qu'une carte a été détectée.

Dans le nouveau chemin spatial, un repère `full_image`/`unknown` ne prouve pas que tous ses textes appartiennent au même objet. Autoriser des recherches séparées sur ses lectures, mais pas une association nom/numéro distant sans sélection ou localisation suffisamment étayée. Si l'attribution reste douteuse, demander le cadrage ; le chemin historique reste uniquement la baseline ou le retour explicite à l'ancienne stratégie.

La réception d'un nouveau fichier invalide sélection, résultat et requête précédente. Associer chaque analyse à un ID de requête/référence d'image ; ignorer les réponses anciennes et utiliser `AbortController` côté client. L'annulation HTTP seule ne garantit pas l'arrêt du processus serveur : voir §9.

## 5. Localisation automatique et redressement projectif

### 5.1 Détecter plusieurs quadrilatères plausibles

Sur une **copie réduite** dont le grand côté est au plus 1 600 pixels :

1. Convertir en niveaux de gris, flou gaussien 5 × 5, puis `Canny(50, 150)` ; tester en comparaison une seconde voie par seuillage adaptatif pour les bords peu contrastés. Ces réglages sont initiaux et font partie du manifeste.
2. `findContours(RETR_LIST, CHAIN_APPROX_SIMPLE)` ; garder au plus les 100 plus grands contours au-dessus du plancher d'aire. Pour chacun, calculer le périmètre et `approxPolyDP` avec epsilon de 2 % puis 4 % du périmètre, dans le budget.
3. Conserver les polygones convexes de quatre sommets distincts. Réordonner cycliquement autour du centroïde ; vérifier les produits vectoriels, l'aire et les intersections. Ne pas utiliser seulement les sommes/différences de coordonnées, ambiguës pour certaines rotations. Le point de départ définit une convention stable ; il ne prouve pas le haut sémantique de la carte.
4. Filtres initiaux de faisabilité : aire au moins 1 % de la photo réduite, chaque côté au moins 30 pixels, pas de sommet hors image. Après projection vers la source, viser une largeur utile d'au moins 150 pixels ; en dessous, indiquer une qualité insuffisante plutôt qu'agrandir indéfiniment.
5. Classer par soutien des bords, absence de dégénérescence et cohérence des côtés ; le ratio portrait proche d'une carte standard (environ 0,71) est un **indice souple**, pas une preuve ni une condition universelle. Ne pas privilégier systématiquement le plus grand contour : il peut s'agir du boîtier ou de la feuille support.
6. Dédupliquer les quadrilatères quasi identiques par IoU polygonale (valeur initiale 0,9), mais préserver les contours imbriqués carte/boîtier. Présenter au plus quatre régions plausibles. En cas de plusieurs objets ou de carte/boîtier indécidable, demander une sélection ; le parcours sans UI de sélection garde une proposition incertaine et le repli manuel.

Une localisation automatique n'identifie pas à elle seule le contenu d'un contour. Ne pas alimenter un champ `grading_company`, `grade`, `is_lot` ou une identité à partir de la seule géométrie. Aucune recherche de prix à cette étape.

### 5.2 Calculer et appliquer l'homographie

Reporter les coins dans la photo orientée avec les facteurs de réduction exacts en x/y. Pour un quadrilatère source ordonné `p0, p1, p2, p3`, définir un rectangle destination de largeur égale au maximum des deux côtés opposés correspondants, et de hauteur égale au maximum des deux autres. Ne pas forcer le ratio standard : une perspective n'est pas corrigée par un simple étirement arbitraire.

Utiliser `getPerspectiveTransform(source, destination)`, puis `warpPerspective`. Notation :

```text
[u', v', w']ᵀ = H_photo_to_card × [x_photo, y_photo, 1]ᵀ
u_card = u' / w' ; v_card = v' / w'
H_card_to_photo = inverse(H_photo_to_card)
```

Vérifier l'inversibilité, les dénominateurs non nuls et la reprojection des quatre coins. Une taille destination arrondie doit être celle enregistrée dans les matrices. Plafonds initiaux : grand côté de carte 2 000 pixels, chaque raster dérivé au plus 12 millions de pixels ; réduire les dimensions proportionnellement avant allocation. Traiter/libérer les variantes successivement.

L'ordre des coins et le ratio ne déterminent pas si le texte est à l'endroit. Demander la rotation manuelle en cas de doute ; pour l'automatique, comparer d'abord les deux orientations portrait opposées, puis les orientations restantes uniquement dans le plafond de passes. Ne pas présenter un manque de budget comme une orientation validée. Une rotation retenue compose une nouvelle matrice avec H.

### 5.3 Reprojeter les boîtes OCR

Chaque passe OCR possède une matrice `H_card_to_pass` intégrant recadrage, rotation et agrandissement. Pour chacun des quatre coins d'une boîte :

```text
p_photo ∝ inverse(H_photo_to_card) × inverse(H_card_to_pass) × p_pass
```

Conserver le quadrilatère projeté et, pour l'ancien champ `region`, son rectangle englobant arrondi vers l'extérieur puis borné à la photo. Le rectangle englobant est une approximation explicitement étiquetée. Normaliser x par la largeur du repère concerné et y par sa hauteur ; ne jamais mélanger coordonnées normalisées et pixels.

## 6. Lire le texte et reconstruire les fragments

### 6.1 Appel Tesseract et parsing

Remplacer progressivement la lecture texte par une fonction interne proposée `run_tesseract_tsv(image, *, psm, deadline) -> OcrPass`, en gardant un adaptateur pour les anciens tests/consommateurs. Commande cible, construite en liste sans shell :

```text
tesseract stdin stdout -l fra+eng --psm 11 tsv
```

Employer `csv.DictReader(..., delimiter="\t")`. Pour les lignes de niveau mot (`level=5`), conserver page/bloc/paragraphe/ligne/mot, `left`, `top`, `width`, `height`, `conf`, `text`. Rejeter une boîte invalide ; un score négatif/absent devient `None`. Les boîtes doivent correspondre au raster de cette passe. Reconstituer les lignes par identifiants complets, puis ordre horizontal et enveloppe des boîtes ; ne pas joindre deux blocs distants sur le seul numéro de ligne.

### 6.2 Régions et séquence de passes

Configuration initiale versionnée :

| Région | Repère de la carte orientée | Lecture initiale |
|---|---|---|
| Carte entière | 0–100 % | PSM 11, lecture originale |
| Nom | haut 0–35 %, pleine largeur | PSM 6 ; conserver suffixes significatifs et noms courts |
| Numéro | bas 70–100 %, pleine largeur | PSM 11 ; PSM 7 seulement sur une ligne isolée |

Exécuter d'abord la carte entière, puis uniquement les régions nécessaires pour compléter/lever une ambiguïté. Une lecture nom+numéro ne suffit pas à arrêter si plusieurs hypothèses restent plausibles. Réserver au plus six appels Tesseract **au total**, orientations et secours inclus ; ne pas faire le produit de toutes les rotations, échelles, zones et variantes.

Conserver l'original ; contraste/agrandissement servent de variantes de secours (facteur au plus 3, plafonds raster respectés). Ne pas imposer une liste de chiffres seule à toute la bande numéro : préfixes et suffixes sont légitimes. La priorité haut/bas est un critère de rang, pas une exclusion : une mise en page atypique doit bénéficier de la lecture globale ou du cadrage manuel.

### 6.3 Fragments et noms

Un numéro peut être un token unique ou plusieurs tokens. Dans une même région/objet/passe, tester des fenêtres de deux à cinq tokens proches : ordre horizontal, chevauchement vertical initial d'au moins 50 % de la plus petite hauteur, intervalle horizontal au plus deux hauteurs médianes. Pour deux lignes, autoriser seulement un slash en fin/début et un écart vertical au plus une hauteur médiane. Versionner ces réglages et garder les fragments sources.

Ne pas relier des régions ou objets distincts. Les passes différentes du même objet peuvent compléter nom/numéro mais restent corrélées. Extraire les noms avec le vocabulaire/normalisation existants ; déclasser les libellés génériques (`PV`, `HP`, `Dresseur`, etc.) sans supprimer un nom réel du catalogue. Ne pas rejeter tous les noms de moins de quatre lettres : `Mew` est un cas à tester.

### 6.4 Indices de langue de l'exemplaire

Réutiliser les fragments de texte de la carte, hors étiquette et fond, pour tester une méthode locale versionnée fondée sur des expressions discriminantes. La sélection de langues `fra+eng` dans Tesseract ne détecte pas la langue de l'exemplaire. Le nom seul et la localisation TCGdex ne la prouvent pas non plus. Texte trop court, ambigu ou contradictoire : abstention ; aucun modèle ni appel externe implicite.

Conserver seulement les fragments nécessaires à l'explication et appliquer les plafonds de §3/§9. Une suggestion française peut aider à explorer les références françaises, mais ne supprime pas les autres candidats ni ne certifie la version. Garder la proposition séparée de la langue déclarée/confirmée et exposer les désaccords. Tester sur labels indépendants français/anglais, noms communs, bruit et conflits, puis documenter les langues effectivement qualifiées.

## 7. Produire et classer plusieurs hypothèses de numéro

Fonction proposée : `generate_number_hypotheses(readings, catalog_vocabulary, config)`. Elle ne modifie ni titre/description ni lecture originale.

1. **Lecture littérale** : conserver texte et fragments ; normaliser séparateurs Unicode `／`, `∕`, `⁄` dans une représentation de recherche distincte. Espaces et zéros initiaux ne disparaissent pas de la valeur brute.
2. **Analyse structurée** : reconnaître fractions et identifiants promotionnels à partir des formats réellement présents dans le catalogue et des patterns existants ; conserver préfixe et suffixe. Ne pas introduire une grammaire limitée aux seuls numéros entièrement numériques.
3. **Variantes** : proposer `O → 0` ou `I/l/| → 1` uniquement dans une composante attendue numérique. Ne pas remplacer le préfixe d'un promo valide. Une insertion comme `108/59 → 108/159` exige une extension compatible du catalogue ; explorer au plus une édition de caractère par hypothèse initiale, jamais toutes les combinaisons possibles.
4. **Bornes** : au plus 24 lectures spatiales de numéro, quatre variantes par lecture **original compris**, puis 12 valeurs de recherche distinctes par image. Préserver les originaux ; si les originaux seuls dépassent le plafond, exposer une troncature/ambiguïté et demander une sélection au lieu de prétendre avoir tout examiné.
5. **Déduplication** : clé séparée numérateur canonique/dénominateur canonique/préfixe/suffixe ; ne pas appliquer `canonical_local_id()` à la fraction entière (cela fusionnerait les composantes). Conserver toutes les provenances et versions ; plusieurs essais concordants ne sont pas autant de preuves indépendantes.
6. **Ordre déterministe** : littéral avant réparé, position/cohérence spatiale, score technique disponible, coût de réparation, puis valeur canonique/ID comme départage stable. Une unicité dans le catalogue local ne transforme pas une correction en lecture certaine. La compatibilité catalogue est un résultat séparé.
7. **Vérification** : interroger numérateur complet et extension compatible avec le dénominateur imprimé (`card_count_official`/`card_count_total` selon les règles existantes). Préserver numéros secrets et sous-séries ; aucun rejet générique fondé sur `numéro ≤ 1,6 × total`. Catalogue incomplet ou format non pris en charge donne une limite explicite, pas une correction forcée.

Exemples de comportement :

| Lecture | Sortie attendue |
|---|---|
| `025 ／ 165` | Original et clé de recherche `025/165`, opération de séparateur tracée |
| `O25/165` | Original + hypothèse `025/165` si composante numérique compatible ; aucune substitution sur le nom |
| `SWSH020` | Préfixe intact, clé de comparaison selon normalisation partagée |
| `108/59` | Original conservé ; `108/159` éventuel avec motif/extension compatible, confirmation nécessaire |
| Deux numéros plausibles sur deux cartes | Deux objets distincts ; aucun nom de l'un apparié au numéro de l'autre |
| Bonne référence absente | Hypothèses conservées comme non résolues, pas d'identité inventée |

## 8. Recherche des candidats et articulation avec T03

### 8.1 Alternatives et contradictions : deux niveaux distincts

Ajouter un contrat optionnel versionné `ocr_evidence` aux attributs et un champ interne dédié dans `ListingEvidence` (valeur vide par défaut pour garder les appels existants). Les détails géométriques et les groupes d'alternatives vivent dans cette enveloppe, pas dans une liste plate d'assertions. Les lectures héritées sans enveloppe gardent leur sémantique actuelle.

- Toutes les variantes d'une **même lecture** partagent un groupe alternatif : elles signifient « ceci ou cela ». Elles ne deviennent pas deux assertions simultanées soumises telles quelles à `_conflicts()`.
- Deux lectures originales incompatibles restent visibles, notamment entre objets ou avec le texte vendeur. Des doublons issus des passes d'une même région ne créent pas artificiellement de preuves indépendantes.
- Une correction qui coïncide avec le titre ne supprime pas la lecture originale discordante. Conserver ce désaccord dans le diagnostic et la demande de vérification.
- Une nouvelle enveloppe cliente n'est pas plus fiable que `source="ocr"` : valider contenu/bornes, recalculer normalisations et critères ; aucun champ `verified` ni statut de confirmation fourni par le client.

Adapter `build_evidence`, `form_evidence`, les modèles JSONL concernés et les adaptateurs **ensemble**, avec tests de compatibilité. Les positions/transforms durables n'entrent dans les snapshots qu'avec le mode de conservation T04 et son contrat explicite. Une confirmation utilisant une preuve visuelle non conservée garde la limite prévue par T04 ; aucun label visuel reproductible n'est créé.

### 8.2 Récupération et union

1. Construire **un seul** `CardMatcher` pour l'analyse (seed/réparation désactivés). Extraire une méthode publique de récupération/classement depuis la logique existante si nécessaire ; ne pas appeler les méthodes privées depuis HTTP ni recopier les règles.
2. Pour chaque hypothèse retenue, récupérer par numéro complet, puis départager par au plus trois noms issus **du même objet** et les autres observations. Plafonner à 36 combinaisons nom/numéro ; une hypothèse sans nom reste cherchable. Les recherches nom seul réutilisent le repli lexical existant.
3. Examiner toutes les hypothèses dans ces bornes avant de tronquer la sortie. Union par ID de carte, conserver hypothèses justificatives et contradictions ; maximum 20 suggestions et diagnostic borné. Ne pas s'arrêter au premier numéro qui renvoie une carte.
4. Garder un classement déterministe fondé sur les critères actuels, la qualité de lecture et le coût de correction explicités. Ne pas additionner des scores OCR, géométriques et de matcher pour fabriquer une probabilité.
5. Faire appliquer les règles finales par la décision commune, avec prise en charge des groupes d'alternatives. Aucune branche OCR ne publie sa propre identité effective. OCR seul : suggestions/ambiguïté et confirmation humaine J1 ; lot : aucune carte unitaire ; contradiction : diagnostic et vérification.

### 8.3 Transport entre écrans et versions

Conserver une enveloppe minimale bornée via `manual_listing.py`, `capture_preview.py` et les formulaires ; la revalider à chaque entrée. Ne pas transmettre seulement le premier numéro corrigé via `ocr_numbers`, ni recréer la correction comme saisie `manual`. Lorsqu'un ancien client ne transporte pas les nouvelles métadonnées, signaler cette perte ; ne pas prétendre conserver une provenance complète.

Versionner extracteur/configuration géométrique, parsing et hypothèses. Ajouter les champs optionnels sans modifier les empreintes historiques quand ils sont absents. Une preuve nouvelle/modifiée exige les règles de réexamen T03 ; aucun remplacement automatique d'une confirmation humaine. Si la persistance impose un changement relationnel, inspecter le dernier numéro réel puis créer une migration additive selon AGENTS ; ne pas réserver un numéro depuis ce document.

### 8.4 Projeter les références dans le formulaire de capture

Réutiliser les candidats et la décision commune pour proposer identifiant/localisation, nom canonique, extension et numéro disponible, sans branche de confirmation spécifique à l'OCR. L'absence d'extension dans le titre n'empêche pas la recherche nom/numéro ; une extension provenant du catalogue reste une propriété de candidat, pas une mention observée. Ne pas confondre dénominateur imprimé et effectif total générique.

Filtrer avant préremplissage les valeurs sans structure reconnue ni attestation de catalogue, dont le fragment `n` du cas §1.3. Conserver ce fragment au diagnostic ; ne pas supprimer les préfixes/numéros alphanumériques légitimes. Un numéro valide ne prouve pas une identité et une référence unique dans un cache partiel reste insuffisante.

Dans T08.2, permettre le choix/confirmation de la référence dans la prévisualisation, la confirmation distincte de la langue proposée et l'enregistrement final avec la même identité. Revalider côté serveur preuves, révision et référence ; aucun write pendant la prévisualisation. Ne pas exiger de recopier les champs du candidat ni de confirmer une annonce incorrecte pour accéder au choix de référence. Une proposition sans candidat admissible garde les champs non résolus et la saisie manuelle accessible.

Le choix préparé avant ajout reste transitoire : `save_review()` exige actuellement un `item_id`. Adapter l'orchestration finale pour revalider les preuves et créer/résoudre l'annonce puis appliquer sa décision dans une unité atomique ; ne pas traiter la simple réimportation des champs comme conservation d'une confirmation. Conserver les limites T04 lorsqu'une décision s'appuie sur une photo éphémère non archivée, sans créer de preuve durable ni de label visuel reproductible fictif.

### 8.5 Revalider après préremplissage et avant utilisation

Appliquer T08.3 après préremplissage/saisie, avant recherche locale, puis avant confirmation et dans la transaction finale d'enregistrement. Réutiliser normalisation, recherche et décision communes ; le serveur ne fait confiance ni aux badges ni à un ID ou statut de validation transmis par le client. Conserver valeurs brutes, provenance et diagnostic par champ.

| Champ | Contrôle et conséquence pour la recherche |
|---|---|
| Nom | Distinguer titre recopié, nom canonique, alias et approximation ; préserver suffixes. Nom non résolu : repli lexical borné, sans preuve exacte fabriquée. |
| Extension | Résoudre les noms/alias du référentiel ; inconnue : recherche nom/numéro possible. Une extension proposée depuis un candidat n'est pas une observation indépendante. |
| Numéro | Vérifier structure complète et compatibilité avec les références, préfixes/suffixes et dénominateur attesté. Bruit comme `n` sans attestation : diagnostic et exclusion des filtres exacts, pas de suppression de la valeur brute. |
| Langue | Valider le code et distinguer inconnue, déclarée, proposée et confirmée. Une suggestion peut orienter l'exploration, sans exclusion définitive des autres locales ; locale du candidat et langue de l'exemplaire restent distinctes. |
| Ensemble des champs / ID | Vérifier la compatibilité avec la même référence/version et les observations ; champs valides isolément mais contradictoires : diagnostic et candidats accessibles, confirmation/valorisation bloquées pour cette combinaison. |

Afficher les critères réellement utilisés/écartés et leurs raisons ; ne pas imposer tous les champs remplis pour chercher une carte. Un filtre invalide ou inconnu peut être écarté de la récupération locale, mais une contradiction avec une preuve explicite reste attachée aux candidats et à la décision. Aucune répétition illimitée de requêtes pour forcer un résultat.

Séparer erreurs d'identité et erreurs financières : le parsing du prix/port ne doit pas interrompre OCR/recherche TCGdex, et une correction financière ne modifie pas les preuves d'identité. Un conflit explicite continue de bloquer l'acceptation automatique ; une résolution humaine motivée peut retenir une référence du diagnostic en qualifiant l'observation vendeur erronée, sans modifier son texte brut ni prétendre que les preuves concordaient. Revalider ce choix et les attributs propres à l'exemplaire ; aucune résolution d'un conflit ne prouve l'état/la finition/la langue.

Ne pas transformer la projection d'un candidat en preuves supplémentaires le confirmant : une réanalyse après préremplissage conserve son caractère indicatif. Une modification significative applique les règles d'empreinte/révision T03 pour invalider choix et résultats inapplicables. Vérifier après sauvegarde que fiche et critères T16 réutilisent l'identité effective revalidée. Tester aussi les soumissions directes sans JavaScript, les champs individuellement valides mais incompatibles et la recherche partielle avec champ absent/invalide.

### 8.6 Rendre la vérification utilisable dans le parcours de capture

Les exigences T08.2/T13 suivantes font partie de la livraison commune :

- **Avancement fidèle :** distinguer « annonce capturée », « photo analysée », « carte proposée », « identité confirmée » ; ne franchir une étape qu'après résultat effectif. Garder séparés progression/échec et statuts métier d'identification.
- **Continuité et effort utilisateur :** après envoi, ouvrir rapidement la prévisualisation/progression et enchaîner analyse/recherche/préremplissage sans recopie ni clic de recherche supplémentaire. Définir un propriétaire d'exécution et de retour de résultat indépendant du maintien du popup ouvert ; capture et corrections récupérables, images éphémères non prétendues archivées. Les confirmations J1 restent explicites ; enregistrer une identité/langue inconnue n'impose pas une fausse référence ou un défaut français.
- **Photo exploitable :** privilégier la vue détaillée déjà accessible dans la capture, permettre le choix d'une autre vue ou un téléversement local et le recadrage avant réanalyse. Conserver `image_url` historique et prévoir un contrat optionnel borné pour les vues supplémentaires ; ne pas inventer d'URL haute résolution. Analyser une photo choisie à la fois, dans les budgets existants. Rattacher résultats et sélection à `image_ref`/requête/région ; changer de vue invalide les résultats devenus inapplicables, sans fusion d'objets différents.
- **Vérification côte à côte :** montrer photo/région analysée et image de référence avec agrandissement accessible et détails discriminants. Signaler les images manquantes et conserver le choix textuel ; illustration proche ne confirme ni version, ni finition, ni authenticité. Cette aide humaine ne dépend pas de T11.
- **Diagnostic avec action :** proposer recadrage/autre photo pour lecture insuffisante, enrichissement T05 pour couverture manquante établie, comparaison/choix pour versions proches, correction pour conflit et saisie/réessai pour moteur indisponible. Sans cause établie, indiquer les preuves insuffisantes ; aucun diagnostic d'absence de catalogue déduit du seul résultat vide.
- **Identité et comparabilité séparées :** réutiliser T09/T17 pour afficher les attributs nécessaires manquants (langue, édition, finition, état, gradation selon le périmètre retenu) et l'indisponibilité des sources adaptées. Une identité confirmée peut rester non valorisable ; n'inventer aucun attribut pour rendre les prix comparables.

## 9. Budgets, isolation et erreurs

Configuration initiale à figer dans les rapports : deux analyses simultanées, 8 Mo/12 millions de pixels en entrée, six appels OCR, 24 lectures/12 hypothèses de recherche, 36 combinaisons, 20 suggestions. Ajouter des plafonds de sortie TSV de 2 Mio par passe et 4 096 mots par analyse ; signaler/refuser la troncature avant de chercher une identité.

Utiliser une échéance monotone globale **de 20 secondes** à partir du début du traitement, hors téléversement ; cette procédure choisit un budget englobant décodage, géométrie, OCR et recherche, plus strict que le seul cumul des appels OCR demandé par T06. Chaque sous-opération reçoit le temps restant ; aucun nouvel essai à l'échéance.

Pour une borne effective et une annulation réelle, exécuter le traitement image/OCR dans un processus contrôlé ; le superviseur garde le sémaphore, interrompt/récolte le worker et son Tesseract à l'échéance, à l'annulation ou à la sortie excessive. Lire les pipes de manière bornée plutôt que conserver une sortie illimitée avant troncature. Ne pas supposer qu'un `Future.cancel()` arrête un thread ou qu'une déconnexion arrête Tesseract. Réutiliser `OMP_THREAD_LIMIT=1` et borner aussi les threads OpenCV.

Ne pas partager une connexion SQLite entre processus. Dans le chemin cible, le worker image retourne les lectures ; la recherche locale utilise ensuite une connexion de lecture courte dans le temps restant. Les appels actuels `analyze_image(connection, content)` gardent un adaptateur compatible ; aucun `BEGIN` ne reste ouvert pendant OCR/géométrie. T04/persistance et décisions humaines conservent leurs transactions dédiées.

La recherche doit elle aussi respecter l'échéance : vérifier le temps entre hypothèses, dans les boucles de classement et pendant l'indexation ; installer temporairement un `set_progress_handler` SQLite pour interrompre les requêtes longues, puis le retirer dans `finally`. Plafonner l'attente d'un verrou au temps restant. Ces contrôles s'ajoutent aux bornes de combinaisons ; ne pas annoncer un délai global garanti sur la seule base du `timeout` du sous-processus Tesseract.

Politique d'erreurs :

| Situation | Réponse et suite |
|---|---|
| Fichier/cadrage invalide | HTTP 400, motif utile et formulaire conservé |
| Deux analyses déjà actives, moteur absent, aucun résultat exploitable avant délai | HTTP 503 selon contrat existant, réessai/saisie manuelle |
| Localisation douteuse ou backend automatique absent | Diagnostic de repli, recadrage manuel/photo entière possible |
| Délai pendant un essai de secours avec lectures déjà valides | Résultat partiel de suggestions si sérialisation dans le budget ; diagnostic explicite, aucune identité confirmée |
| TSV excessif/invalide, budget épuisé avant lecture exploitable | Analyse indisponible, pas de match sur une sortie tronquée silencieusement |
| Plusieurs cartes ou résultat périmé | Sélection/correction demandée ; aucun assemblage entre objets ni application d'une ancienne réponse |

Ne journaliser ni photo ni TSV/texte brut ; limiter les logs aux versions, temps, compteurs et codes d'échec. La conservation de preuves de benchmark reste explicite via T04.

## 10. Tests et comparaison avant activation

Appliquer les fiches [T06](PLAN_VALIDATION_LOTS.md#t06), [T07](PLAN_VALIDATION_LOTS.md#t07) et [T08](PLAN_VALIDATION_LOTS.md#t08) du plan de validation : skill UI seulement pour les interactions/rendus concernés, pytest et mesures photographiques locales pour le moteur. Tout échec ou obstacle d'intégration rejoint [tracker.md](../../tracker.md), y compris test obligatoire sauté ou gain non démontré. Ne pas confondre commande prévue, test exécuté et comportement validé.

Les tests sont hermétiques, dans Docker, sur bases temporaires. Tester des comportements et erreurs plausibles ; les mocks seuls ne mesurent pas une amélioration de reconnaissance.

| Groupe | Vérifications nécessaires |
|---|---|
| Géométrie | EXIF 1/3/6/8 ; coordonnées CSS avec marges ; rotations ; homographie de quadrilatère connu ; reprojection ≤ 1 pixel hors arrondi ; points croisés/colinéaires/hors image refusés ; plafonds raster |
| Localisation | Carte décentrée/inclinée, boîtier et contour intérieur, objets multiples, absence de carte ; échec/refus/repli distincts ; aucune déduction de lot depuis le seul nombre de photos |
| TSV/spatial | Score absent/négatif, boîtes invalides, lignes homonymes de blocs distincts, fragment `/` séparé ; absence de liaison entre objets ; positions après crop/scale/rotation |
| Noms/numéros | `Mew`, suffixe `ex`, préfixes promos, Unicode, zéros initiaux, secrets, insertion négative ; aucune correction destructrice du préfixe ou du titre |
| Alternatives | Premier numéro erroné puis bon ; deux variantes d'un groupe sans fausse contradiction ; désaccord original/titre visible même si réparation concordante ; cache partiel et candidat absent |
| Décision/transport | Ancien JSONL inchangé, formulaire nouveau/ancien, provenance conservée, limites validées côté serveur, lot sans suggestion unitaire, OCR seul sans identité effective, décision humaine applicable préservée |
| Capture utilisable | Cas §1.3 avec fixture photo/catalogue annotée ; titre conservé, nom canonique et extension proposés, `20/82` sans `n` parasite, choix de référence avant ajout, même identité sur la fiche ; anciens `name == title` et corrections humaines testés |
| Vérification utilisateur | Statuts d'avancement fidèles, mauvaise photo principale puis sélection/recadrage, photo inclinée avec titre faux, versions proches et image de référence manquante ; affichage côte à côte ou repli textuel, diagnostic avec action, identité distincte de l'admissibilité des prix |
| Orchestration W01–W11 | Recherche de référence avant projection canonique ; correction textuelle réutilisant les indices OCR valides ; changement de photo relançant la lecture ; pas de boucle de préremplissage, pas d'écriture d'annonce avant ajout final ni job de marché avant commit admissible |
| Adéquation au besoin | Prix invalide sans blocage d'identification, popup fermé pendant OCR, résolution motivée d'un titre faux, sélection conservée atomiquement à l'ajout, langue inconnue sans défaut français et reprise d'enrichissement sans perte du formulaire |
| Contrôles après préremplissage | Champs incompatibles malgré leur validité individuelle, ID divergent, critères partiels visibles, soumission sans JavaScript et changement après sélection ; aucune auto-confirmation par recopie des propriétés du candidat |
| Langue | Fragments français/anglais, nom commun à plusieurs langues, texte trop court, site/catalogue d'une autre locale et conflits ; proposition expliquée ou abstention, aucune confirmation par simple préremplissage |
| Limites | Six passes toutes rotations comprises ; sortie pipe excessive ; délai global/annulation et processus récoltés ; sémaphore libéré après erreur ; aucun write/seed/réparation d'index ni appel distant |
| Confidentialité | Aucun contact/texte OCR complet dans réponse/logs/stockage courant ; conservation seulement dans le mode T04 |

Créer selon le découpage retenu `tests/test_ocr_geometry.py`, `test_ocr_spatial.py`, `test_ocr_hypotheses.py` ; compléter les suites existantes d'intégration. Un petit ensemble de photos locales autorisées/annotées teste Tesseract réel ; le benchmark plus volumineux reste séparé de pytest.

Commandes prévues **après implémentation** des nouveaux fichiers :

```bash
docker compose run --rm app pytest tests/test_ocr_local.py tests/test_ocr_web.py tests/test_ocr_geometry.py tests/test_ocr_spatial.py tests/test_ocr_hypotheses.py
docker compose run --rm app pytest tests/test_identification_evidence.py tests/test_identification_reliability.py tests/test_manual_listing.py tests/test_capture_preview.py tests/test_identification_reviews.py
docker compose run --rm app pytest tests/test_migrations.py
docker compose run --rm app pytest
```

### Benchmark apparié et critères de livraison

Réutiliser `validation/ocr/marketplaces/replay_local.py` pour le rejeu et `scripts/evaluate_identification.py` pour les métriques compatibles, sans téléchargement. La campagne existante comporte 30 annonces, 15 photos et aucune annotation humaine à cette date : la compléter selon T01/T04 avant une conclusion de justesse. Ne pas déduire les labels des suggestions.

Comparer à catalogue/labels figés : **baseline actuelle → cadrage manuel + TSV → automatique + TSV → hypothèses multiples**. Pour la géométrie, un cadrage/coins humains annotés fournissent une référence distincte de l'identité. Ajouter des métriques OCR dédiées sans changer le sens des métriques d'identification existantes.

Publier pour chaque variante : couverture de localisation et refus, lecture exacte nom/numéro, présence du bon numéro dans les hypothèses, rappel top-3 de la bonne référence, nouvelles erreurs de suggestion, précision/couverture des décisions admissibles, faux rattachements de lots, latence p50/p95 et mémoire sur machine décrite. Compter images absentes, plafonds, cas non pris en charge et catalogue incomplet séparément. Conserver groupes de doublons/partitions T01/T10 ; aucun réglage sur le test indépendant.

Conditions minimales : cas de recette passants, pas de nouvelle acceptation automatique OCR ni régression des garde-fous, temps et mémoire bornés, gain/limites documentés sur cas annotés. Un résultat négatif conserve manuel/baseline et documente la raison ; une hausse des statuts `identified` ne vaut pas amélioration. L'activation automatique exige un gain démontré ; les critères d'acceptation automatique restent ceux de T10.

La livraison commune T06/T07/T08.2 exige aussi la recette de capture §1.3, de l'analyse jusqu'à la fiche enregistrée, avec réseau marketplace simulé et aucune écriture avant confirmation finale. Les captures d'écran reçues documentent l'erreur ; préparer une fixture autorisée avec annotation indépendante et distinguer leur rejeu de celui de la photo originale. Mesurer séparément qualité de lecture, rappel des références, suggestion de langue et exactitude des champs affichés/enregistrés ; une API OCR correcte seule ne valide pas le parcours. La propagation aux comparaisons de marché est testée en T16/T17 avec les critères structurés de l'identité effective, pas le titre vendeur.

Inclure les variantes T13/§8.6 dans cette recette : titre faux, photo inclinée, mauvaise photo principale, référence absente et versions proches. Vérifier pour chacune l'étape effectivement atteinte, la photo analysée, les champs/provenances, l'action de résolution et les limites de comparabilité. Les fixtures photo locales autorisées et annotées vérifient la lecture réelle ; les mocks restent utiles pour erreurs/transport mais ne démontrent pas le gain OCR.

Livrer avec chaque étape : fichiers et versions, tests exécutés, rapport avant/après disponible ou limite d'annotation, réglages, mode de retour au chemin historique. Garder la stratégie `legacy`/`spatial` explicite et versionnée dans la configuration ; ne pas faire passer silencieusement le chemin historique pour la nouvelle méthode. Toute nouvelle option exposée doit être documentée dans README au moment de son implémentation.

## 11. Références et portée

Références primaires consultées le 3 novembre 2026, à confronter aux versions effectivement installées :

- [Tesseract — sortie TSV et modes de segmentation](https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html) : format des mots/boîtes/scores et commande ; la reconstruction spatiale proposée ici est propre à Pokébourse.
- [OpenCV — contours et approximation polygonale](https://docs.opencv.org/4.13.0/dd/d49/tutorial_py_contour_features.html) : primitives de §5.1 ; les seuils proposés ne sont pas des performances garanties par cette documentation.
- [OpenCV — transformations géométriques](https://docs.opencv.org/4.13.0/da/d6e/tutorial_py_geometric_transformations.html) : homographie/warping ; la sélection de carte et ses refus restent à développer et mesurer.
- [Pillow — orientation EXIF](https://pillow.readthedocs.io/en/stable/reference/ImageOps.html#PIL.ImageOps.exif_transpose) : appliquer l'orientation avant les coordonnées de cadrage ; le projet impose actuellement Pillow `<13` et doit vérifier la version réellement testée.

Le rapport fourni sur Pokécardex est une source d'idées, pas une dépendance d'implémentation ni une preuve de qualité : l'OCR n'y est pas relié de façon démontrée au scan courant. Aucun code décompilé, modèle ou magasin de hash de cette application n'est nécessaire. Les constantes de cette procédure sont des propositions Pokébourse à versionner/évaluer, pas des paramètres repris comme acquis.
