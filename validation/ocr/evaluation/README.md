# Évaluation hors ligne de l’identification

Ce dossier documente un comparateur autonome pour les rapports de prédiction enregistrés. L’outil relit des JSON et des annotations humaines : il ne lance ni OCR, ni matcher, ni collecte, ni synchronisation, n’ouvre pas la base opérationnelle et ne télécharge rien.

Ce lot fournit l’outil de mesure, **pas la vérité terrain des 30 annonces ni une qualification statistique**. Les exemples fournis sont entièrement synthétiques.

## Entrées

Le rapport courant `validation/ocr/marketplaces/runs/<campagne>/resultats.json` est accepté avec ses variantes :

- `title_only` : titre seul ;
- `ocr_only` : OCR seul ;
- `combined` : texte et OCR combinés.

Chaque annonce doit porter **exactement un** identifiant stable : `listing_id` ou `url`. Pour les 30 annonces existantes, utiliser l’URL exacte comme `listing_id` dans les labels. La position, le champ `index` et le titre ne sont jamais utilisés pour rapprocher une annotation d’une prédiction. Les doublons, identifiants multiples, annotations orphelines et annotations incohérentes sont refusés.

Une variante `null` reste indisponible : elle n’est ni une abstention ni une prédiction correcte. Pour `ocr_only`, le rapport distingue aussi les photos explicitement non analysées (`ocr: null` ou `image_status`). `title_identification` est accepté comme ancien alias de `title_only`.

Les champs optionnels `catalog_version`, `data_version`, `pipeline_version` et `decision_origin` peuvent être placés à la racine du rapport ou dans `metadata`. `decision_origin` peut aussi être défini sur chaque variante. Valeurs : `automatic`, `human`, `mixed`, `unknown`. Les décisions humaines ou mixtes ne sont pas comptées comme automatiques. Les rapports historiques sans origine restent évaluables à titre descriptif, mais une limite signale que leur caractère automatique n’est pas prouvé.

## Contrat d’annotations `identification-labels-v1`

Créer un fichier indépendant, par exemple `validation/ocr/evaluation/labels.json`, en partant de la structure de `labels.example.json`. Ne pas le générer depuis les prédictions.

```json
{
  "schema_version": "identification-labels-v1",
  "catalog_version": "catalogue-fige-identifie-par-l-annotateur",
  "annotations": [
    {
      "listing_id": "URL-ou-identifiant-stable",
      "status": "annotated",
      "product_type": "single_card",
      "identity_determinable": true,
      "expected_tcgdex_id": "identifiant-verifie-ou-null",
      "catalog_presence": "present",
      "external_identity": null
    }
  ]
}
```

Champs :

| Champ | Valeurs et règles |
|---|---|
| `listing_id` | Obligatoire ; copie exacte de `listing_id` ou `url` du rapport. |
| `status` | `unannotated`, `annotated` ou `needs_arbitration`. Une annotation absente ou `unannotated` ne vaut jamais confirmation. `needs_arbitration` est exclue des métriques. |
| `product_type` | `single_card`, `lot`, `sealed`, `choice` (choix parmi plusieurs) ou `unknown`. |
| `identity_determinable` | Booléen obligatoire pour une ligne `annotated`. Indique si une identité exacte peut être déterminée humainement. |
| `expected_tcgdex_id` | ID TCGdex vérifié, ou `null` s’il n’a pas été vérifié. Obligatoire pour entrer dans le dénominateur d’exactitude, mais non fabriqué pour rendre un cas évaluable. |
| `catalog_presence` | `present`, `absent` ou `unknown` dans le catalogue figé utilisé. À distinguer de l’absence parmi les trois candidats. |
| `external_identity` | Description facultative d’une identité externe documentée lorsque la référence manque au catalogue ; ne remplace pas un ID TCGdex vérifié. |

Pour les types non unitaires, `identity_determinable` doit être `false` et `expected_tcgdex_id` doit être `null`. Une identité attendue est interdite avec `identity_determinable: false`. Un lot ou un scellé ne reçoit jamais une identité unitaire de complaisance.

## Utilisation

Depuis la racine du dépôt :

```bash
python -m scripts.evaluate_identification --help
```

Évaluer un rapport (le fichier `labels.json` doit être constitué humainement au préalable) :

```bash
python -m scripts.evaluate_identification \
  --report validation/ocr/marketplaces/runs/2026-11-02-30-liens/resultats.json \
  --labels validation/ocr/evaluation/labels.json \
  --output validation/ocr/evaluation/evaluation-avant.json
```

Comparer deux rapports, le premier étant l’« avant » :

```bash
python -m scripts.evaluate_identification \
  --report validation/ocr/evaluation/rapport-avant.json \
  --compare-with validation/ocr/evaluation/rapport-apres.json \
  --labels validation/ocr/evaluation/labels.json \
  --output validation/ocr/evaluation/comparaison.json
```

La commande affiche un résumé lisible. `--output` est facultatif et refuse systématiquement d’écraser un fichier existant. Les rapports et labels d’entrée ne sont jamais réécrits.

## Définitions des métriques

Toutes les proportions exportent `numerator`, `denominator` et `value`. Si le dénominateur est nul, `value` vaut `null` : l’interface n’invente ni 0 % ni 100 %.

| Métrique | Numérateur / dénominateur |
|---|---|
| `automatic_coverage` | Décisions acceptées d’origine automatique ou inconnue sur les cartes unitaires évaluables / toutes les cartes unitaires annotées, déterminables et dotées d’un ID attendu. |
| `automatic_precision` | Identités acceptées exactes / décisions acceptées sur ces mêmes cas évaluables. |
| `correct_overall` | Identités acceptées exactes / tous les cas évaluables, y compris abstentions et variantes absentes. |
| `top3_recall` | Bon ID dans les trois premiers candidats / cartes déterminables avec ID attendu et `catalog_presence: present`. Une référence absente du catalogue n’entre pas dans ce dénominateur. |
| `lot_or_sealed_false_acceptance` | Lots ou scellés acceptés comme carte unitaire / lots et scellés annotés. |
| `out_of_catalog_false_acceptance` | Acceptations automatiques sur références explicitement absentes du catalogue / cartes annotées explicitement absentes. |
| `lot_precision` | Vrais lots classés `lot` / toutes les prédictions `lot` sur annotations renseignées. |
| `lot_recall` | Vrais lots classés `lot` / tous les vrais lots annotés. |

`lot_confusion_matrix` croise les cinq types humains avec `single_card`, `lot`, `abstained`, `missing` et `human_or_mixed`. `top3_reference_absent_from_candidates` compte les références présentes dans le catalogue mais absentes du top-3 ; il reste distinct de `catalog_absent`.

Les effectifs `total`, `annotated`, `unannotated`, `excluded`, les disponibilités de variantes, les photos non analysées, les origines et les décisions non évaluables accompagnent les métriques.

## Comparaison appariée

La comparaison publie l’intersection des identifiants, les annonces absentes de chaque version et les variantes manquantes. Les deltas sont calculés uniquement sur les annonces ayant la même variante disponible dans les deux rapports.

Sont distingués :

- erreur acceptée avant puis identité exacte après (`errors_corrected`) ;
- nouvelle erreur acceptée (`new_errors`), dont le sous-cas exact → faux (`correct_to_incorrect`) ;
- exact → abstention et faux → abstention ;
- décisions devenues `ambiguous` ou `unidentified` ;
- changements d’identité et changements de statut.

Une hausse du nombre de statuts `identified` n’est pas présentée comme une amélioration de justesse. Toute version de catalogue, données ou pipeline absente ou différente ajoute une limite de comparabilité.

## Point de départ T00/T01 figé

Le dossier contient désormais :

- `STATUS_T00_T01.md` : verdict détaillé, inventaire, tests et travail restant ;
- `manifest.json` : versions, partitions et empreintes SHA-256 des artefacts ;
- `labels.json` : les 30 URL avec le statut `unannotated`, sans vérité préremplie ;
- `evaluation-initiale.json` : rapport à 0 annotation, avec métriques de justesse indisponibles ;
- `catalogue-inventory.json` : inventaire du catalogue sur sauvegarde cohérente.

**T00 est terminé comme inventaire, avec des échecs de tests courants consignés. T01 n’est pas terminé : les annotations humaines, le rejeu local figé et le rapport de justesse manquent encore.**

## Travail humain encore requis

Les 30 annonces doivent encore recevoir des annotations indépendantes, avec recherche au-delà des candidats automatiques et arbitrage des désaccords. Les photos exactes, le catalogue figé et les versions de pipeline doivent être documentés. Les volumes de double lecture, le test indépendant et les intervalles d’incertitude prévus par T01/T10 ne sont pas réalisés par cet outil.
