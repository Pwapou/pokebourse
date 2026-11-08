# Recherche lexicale et diagnostic des annonces

**Revue du 8 novembre : baseline lexicale existante**, à mesurer avant toute alternative FTS5/BM25 ou modèle appris. Pour les alias/localisations livrés et la suite OCR, consulter [TASKING_PROJET.md](../TASKING_PROJET.md) et [Identification](../TASKING_IDENTIFICATION_FIABLE.md).

Version `lexical-v1`, 1er novembre 2026. Cette étape améliore la récupération des
candidats à partir du catalogue local et prépare le diagnostic du pilote ML.
Aucun modèle supervisé n’est entraîné ou activé.

## Utilisation

- Réexaminer une annonce depuis sa fiche pour obtenir les candidats du moteur courant.
- Rechercher un nom ou identifiant TCGdex depuis le formulaire de validation. Les résultats exacts gardent leur pagination complète. En l’absence de résultat exact, la recherche propose des noms approchés et les signale comme tels.
- Ouvrir **Annotations → Diagnostic des annonces** (`/identification/diagnostics`). Choisir les non identifiées, les ambiguës ou toutes les non résolues ; le diagnostic analyse les 100 plus récentes par défaut, au maximum 500.
- Télécharger le JSON du diagnostic ou exécuter :

```bash
docker compose run --rm app pokemon-arbitrage diagnose-identification --status all --limit 100 --json
```

Le diagnostic ne crée ni seed, ni snapshot, ni annotation. Il ne synchronise pas
le catalogue et ne modifie aucune identification. Les liens vers les fiches
permettent de réexaminer ou corriger explicitement une annonce.

## Récupération et décision

Le vocabulaire provient des noms effectivement enregistrés dans TCGdex. L’index
inversé de trigrammes recherche les fenêtres proches dans le titre et la
description. Une distance d’édition bornée accepte insertions, suppressions,
substitutions et transpositions voisines. La normalisation conserve les chiffres
significatifs ; elle neutralise casse, accents et ponctuation.

- Les noms de moins de cinq caractères ne sont pas corrigés par proximité.
- Le budget est d’une modification pour les noms courts, deux à partir de neuf caractères.
- Les chiffres intégrés dans un nom ne sont pas modifiés ; EX, GX, V, VMAX et VSTAR ne sont pas corrigés les uns vers les autres.
- Au plus 256 mots, 512 fenêtres distinctes, 64 noms par fenêtre et huit noms proposés sont examinés. Ce récupérateur est borné : il ne garantit pas le rappel de toute faute possible, de tout mot collé ou d’une information très tardive dans un texte long.
- Les numéros de carte sont comparés dans leur intégralité, indépendamment de la recherche sur le nom. Un numéro `4` ne devient pas `14` ou `104`.

Les références sont récupérées par noms et numéros, puis toutes sont classées
avant de retenir les 50 premières. L’ancienne troncature à 200 résultats par
requête n’écarte plus une référence avant le classement. La fiche affiche les
cinq premiers candidats ; la recherche humaine par nom exact ou identifiant
reste disponible au-delà de cette sélection.

Une correction de nom porte un motif explicite, par exemple
`nom approché « dracofeu » → « Dracaufeu » (2 modification(s))`. Son score est
plafonné à 79, sous le seuil historique d’acceptation de 80. Elle reste donc
`ambiguous`, y compris avec un numéro et une extension concordants. Aucun score
de cette baseline n’est présenté comme une probabilité calibrée.

Les lots restent `lot`, sans carte unitaire. Les langues étrangères explicites
restent hors du rapprochement français. Un numéro, une extension ou un total
d’extension contradictoire plafonne le score à 59. Pour une fraction, les totaux
officiel et complet connus de l’extension sont admis ; une valeur inconnue dans
le référentiel n’est pas transformée en contradiction. Les validations humaines
applicables conservent leur priorité dans la résolution commune.

### Numéros isolés et organismes de gradation

En repli après les fractions (`175/198`) et les préfixes (`#175`, `n°175`), le
détecteur backend et `extractCardNumber()` dans l’extension Chrome extraient un
numéro isolé de deux à trois chiffres (`<= 300`) sous garde-fous stricts :
annonce non classée comme lot, présence préalable d’un nom de carte ou d’une
extension, exclusion des années (`1900`–`2099`), des montants et pourcentages
(`€`, `eur`, `%`), des quantités ou jetons alphanumériques collés (`x3`, `PSA10`)
et des notes rattachées à un certificateur. Tout numéro dépourvu de dénominateur
(`set_card_count` nul) remonte `numéro isolé, sans dénominateur` dans
`uncertain_fields` et plafonne la décision automatique à `ambiguous` (score de
résultat plafonné à 79, jamais d’`identified` automatique équivalent à une
fraction exacte).

La détection de gradation couvre `PSA`, `PCA`, `BGS`, `CGC`, `SGS` et
`COLLECTAURA` (`CollectAura`, `Collect'Aura`, `Collect Aura`), avec note collée
ou séparée (`1` à `10`, demi-points `.5` uniquement, rejet de `9.25`). Cette
information descriptive reste neutre sur le score et la génération de candidats
TCGdex.

## Règles déterministes du détecteur (T02, 2 novembre 2026)

Les cartes réellement ajoutées à la vente (« vendu avec 3 cartes en plus »,
« vendue avec trois cartes supplémentaires », « + 3 cartes offertes ») déclenchent
`lot`, avec motif explicite et sans identité unitaire effective. Une protection,
trois photos, un dénominateur de fraction ou une mention négative (« pas un lot »,
« sans lot ») ne suffisent pas à classer en lot. Une vente de carte « au choix »
reste `ambiguous`, sans choix automatique d'une carte, même si le titre contient
un nom et un numéro exacts.

Le mot français « en » et `VO` seul ne prouvent plus l'anglais ; `langue : EN`,
« carte anglaise » et `English` restent reconnus. Une langue non observée reste
inconnue, y compris avec une référence du catalogue français.

`languages` conserve toutes les langues explicites reconnues (français, anglais,
japonais), dédupliquées et triées. `language` n'est renseigné que si une seule
valeur est observée. Plusieurs langues, même si le nom et le numéro concordent,
produisent `ambiguous`, sans identité unitaire automatique et avec motif de
conflit. Le diagnostic distingue ce cas d'une référence locale absente.
Les codes courts sont reconnus dans des champs (`langue : FR/EN`,
`version : JP`), entre parenthèses/crochets (`[EN]`), ou comme marques
conventionnelles majuscules (`FR`, `JP`, `JA`, `US`). `EN` exige un champ ou
un encadrement ; `en` dans une phrase et `VO` seul restent sans effet.

`nearmint`, `near-mint` et `near mint` (casse et espaces variables) partagent
l'état déclaré `Near Mint`, prioritaire sur `mint`. Le suffixe de carte `ex`
reste significatif mais ne déclare plus l'état `Excellent`. L'abréviation d'état
exige un contexte explicite, par exemple `état : EX` ou `condition EX`.
`condition_raw` conserve l'extrait exact retenu, avec sa casse, ses espaces et
son contexte (`État : EX`), séparément de `condition`. Les textes d'origine
restent conservés. Les équivalences historiques, dont « très bon état » vers
`Near Mint`, restent des normalisations de déclarations, jamais des états
physiquement vérifiés. Une note de gradation seule ne renseigne aucun de ces
deux champs ; aucune normalisation ne vérifie finition ou authenticité.

`pack` exige un contexte de produit (`pack Pokémon`, `pack de 3 boosters`,
`pack 151 scellé`). « Gem Pack 2 » ne suffit pas à classer en lot et ne crée
aucun alias d'extension. Les mentions complètes de noms d'extensions présents
dans le cache sont protégées des règles de lot. Les numéros explicitement
étiquetés comme numéros de série sont exclus des quantités et des numéros de
carte. Les quantités écrites de deux à dix sont reconnues dans les contextes
de vente couverts par les fixtures, avec les mêmes exclusions de négation.

L'extension aligne ses garde-fous de lot et de vente au choix pour le repli sur
un numéro isolé. Elle conserve les numéros explicitement observés (fraction ou
préfixe), sauf si ces nombres sont étiquetés comme numéros de série. Les règles
de pack, de quantité et de série sont également alignées. L'extension ne possède
pas le catalogue local et ne décide ni de l'identité, ni des langues, ni de
l'état. Le backend reste l'autorité. Ces correctifs terminent les règles T02
sur leurs fixtures ; ils ne démontrent aucun gain global sans benchmark annoté
et ne valident pas les autres volets de la recette T13.

## Lecture du diagnostic

Depuis T03, les motifs sont également exposés par `reason_code`. Les suggestions
admissibles (`candidates`) sont séparées des références contradictoires
(`diagnostic_candidates`), avec les désaccords conservés. Les observations et
leurs origines restent distinctes après fusion ; un complément OCR/prérempli ne
suffit pas à accepter automatiquement une identité. Les textes indépendamment
suffisants gardent leur traitement, sauf contradiction significative. Voir le
[contrat T03](identification/T03_EVIDENCE.md) pour les versions et les garanties
de réingestion, de snapshot et de confirmation humaine.

Les catégories décrivent les observations du moteur : original indisponible,
lot, langues contradictoires, langue hors périmètre, indices insuffisants, aucun candidat local,
contradiction, nom approché, ambiguïté, correspondance partielle ou correspondance
exacte désormais disponible. **L’absence de candidat local ne prouve pas une absence
dans TCGdex** : catalogue incomplet, extraction insuffisante et texte non
discriminant restent des hypothèses à examiner.

L’inventaire présente les cartes en cache par extension, les effectifs de
référence connus et les langues enregistrées. Il n’affirme pas une couverture
globale du catalogue. Le diagnostic lit les originaux et les descriptions
observées, jamais les noms déjà corrigés comme substituts d’entrées originales.
Un original historique non fiable est signalé. Les exports excluent les champs
vendeur et le JSON brut ; les contacts explicites sont masqués dans les textes
affichés et les motifs.

Les effectifs portent uniquement sur les annonces récentes analysées. Ils ne
mesurent ni la précision, ni le rappel candidats@50, ni le gain réel sur un jeu
humain figé. Les métadonnées structurées présentes mais non exploitées par
l’extraction textuelle sont signalées dans le JSON pour faciliter l’investigation.

## Versions et premiers contrôles

Les vagues d’annotation créées avec cette baseline enregistrent `lexical-v1` et
la limite de 50 candidats dans leur protocole. Les vagues antérieures restent
figées et sont exportées comme `rules-v1`, avec leur limite historique de 10.
Les comparaisons sur le pilote doivent tenir compte de cette version.

Contrôle de la base locale en lecture seule au 1er novembre 2026 : 15 cartes,
6 extensions, 21 annonces non résolues examinées ; 18 sans candidat local,
une correspondance partielle et deux originaux non fiables. Ce constat souligne
le besoin d’inventorier et compléter le catalogue ; il ne constitue pas une
évaluation de précision.

Un essai CPU dans Docker sur un catalogue **synthétique** de 40 015 références,
dont 1 000 noms artificiels, a mesuré environ 199 ms d’initialisation et 18 ms
au p95 sur 25 requêtes après initialisation. Ces mesures ponctuelles ne qualifient
pas la latence en production. Le JSON du diagnostic expose les durées de recherche
en microsecondes, hors initialisation de l’index.

La suite est de compléter le catalogue sur les cas utiles, qualifier les erreurs
avec les annotations humaines, puis comparer les récupérateurs et futurs rankers
sur des entrées et candidats figés. Les noms approchés ne deviennent pas des
pseudo-labels automatiques.
