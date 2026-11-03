# T03 — Observations et décision commune

Livraison du 3 novembre 2026. Le développement s'appuie sur T02 et des fixtures
locales ; il ne dépend pas de l'achèvement des annotations T00/T01 et ne les
déclare pas acquises. Aucun benchmark de précision n'est annoncé.

## Contrat compatible

Les anciens fichiers JSONL restent valides. Le champ optionnel
`identity_evidence` accepte au plus 64 observations, également prises en charge
dans le `raw_data` d'un collecteur. Deux listes différentes fournies à la fois
dans le champ et le brut sont refusées.

```json
{
  "external_id": "capture-1",
  "name": "Pikachu",
  "set_name": "Non identifiée",
  "card_number": "58/102",
  "price_cents": 1200,
  "raw_data": {"title": "Carte photographiée"},
  "identity_evidence": [
    {"field": "name", "value": "Pikachu", "source": "prefill"},
    {"field": "card_number", "value": "58/102", "source": "ocr"}
  ]
}
```

Les sources sont `title`, `description`, `structured`, `manual`, `prefill`,
`ocr`. La provenance reste une déclaration ; aucun de ces libellés n'est une
validation humaine. Les sources `confirmed`, les champs `verified` ou autres
champs de confiance ne sont pas acceptés dans ce contrat. Seules les actions
humaines existantes, avec empreinte/révision contrôlées, publient une confirmation.

Chaque observation expose sa valeur brute, sa normalisation Unicode/casse/espaces,
sa source, sa qualité déclarée ou indicative, sa version d'extracteur et sa version
de normalisation. Un extrait, une référence d'image et une région sont optionnels.
Une région exige quatre entiers ordonnés, entre 0 et 1 000 000. Une référence
d'image est une métadonnée : elle ne prouve pas la présence des octets et ne
déclenche aucun téléchargement.

Les valeurs sont bornées à 20 000 caractères, les extraits à 10 000. Les indices
OCR sont limités aux noms (200 caractères) et numéros (50 caractères), six de
chaque dans les adaptateurs de prévisualisation ; aucun titre/description OCR ne
peut remplacer les textes de l'annonce. Le résultat détaillé n'est pas un stockage
du texte brut complet de Tesseract. La normalisation propre aux numéros reste
celle du matcher ; la normalisation descriptive d'une observation n'est pas une
réparation de numéro.

## Recherche et acceptation

`CardMatcher.identify()` construit le bundle commun. `identify_evidence()` et
`decision.propose()` réutilisent les mêmes règles dans tous les parcours.
La proposition opère en mémoire ; le matcher de prévisualisation désactive le
seed et la réparation d'index et n'effectue aucune écriture. L'application du
résultat reste dans `resolve_and_apply()`/`apply_resolution()` et les transactions
d'import ou de décision humaine existantes.

- Les champs structurés effectivement fournis sont exploités ; les valeurs
  inconnues/absentes n'acquièrent pas de valeur à partir des défauts historiques
  de stockage ou de la locale du catalogue.
- Les textes, saisies et extractions sont évalués indépendamment des indices
  OCR/préremplis. Une acceptation exige des preuves suffisantes dans les premiers.
- Un OCR peut compléter les candidats, mais ne crée pas une nouvelle acceptation
  automatique. Une suggestion suffisante reste `ambiguous`, sans carte effective,
  avec score de résultat plafonné à 79. Un texte indépendamment suffisant garde
  sa décision si l'OCR concorde.
- Une contradiction significative sur nom/suffixe, numéro, extension, total ou
  langue interdit la nouvelle acceptation automatique. Le numéro textuel reste
  inchangé et les observations concurrentes restent consultables.
- `candidates` contient les suggestions admissibles. `diagnostic_candidates`
  conserve les références contradictoires et leurs raisons, dans une rubrique
  distincte sans bouton d'acceptation automatique. La recherche humaine explicite
  reste disponible pour résoudre le désaccord.
- `reason_code` distingue notamment `insufficient_evidence`, `contradiction`,
  `multiple_candidates`, `lot`, `local_reference_missing`, `out_of_scope`,
  `service_unavailable`, `indicative_evidence`, `object_uncertain`, `exact_match`.
  `decision_source` distingue proposition automatique et décision humaine.

Les formulaires gardent la valeur proposée dans des champs cachés dédiés. Une
réanalyse ou un clic « Confirmer et ajouter l'annonce » ne change donc pas la
provenance du préremplissage. Les rubriques « Indices et provenance » et
« Références contradictoires — diagnostic uniquement » sont communes à la
prévisualisation et à la fiche. L'import conserve les libellés/fractions des
anciens imports structurés lorsqu'aucun numéro n'est présent dans le texte,
pour préserver les clés de cotes existantes. Le moteur financier n'est pas modifié.

## Persistance, versions et réexamen

La migration additive `0022_identification_observations.sql` ajoute les observations
et la version de pipeline aux preuves/snapshots existants, avec des valeurs par
défaut historiques. Elle ne réécrit ni ne supprime aucune ancienne preuve,
annotation ou décision. Les snapshots et exports de labels conservent ces
métadonnées, avec masquage des contacts dans les copies d'annotation/export.

Le pilote et les exports textuels gardent leur périmètre : les attributs qui
ne proviennent que d'OCR/préremplissage ne sont pas présentés comme des preuves
textuelles. Leurs observations restent dans l'audit. Les nouvelles vagues
enregistrent la version du pipeline sans modifier les vagues déjà figées.

- Pipeline courant : `evidence-rules-v1` ; normalisation descriptive :
  `observations-v1`. La version de récupération lexicale reste distincte.
- L'empreinte historique `identity-v2` conserve sa sérialisation pour les
  annonces sans nouveau contrat explicite. Une évolution du pipeline seule ne
  retire pas une confirmation applicable aux mêmes preuves.
- Lorsqu'une liste explicite d'observations est utilisée, ses valeurs, origines
  et métadonnées entrent dans l'empreinte. Leur modification demande un réexamen
  de la confirmation, sans effacer son historique.
- Une capture partielle n'efface pas les preuves précédentes. Prix, port et
  dates ne modifient pas l'empreinte. Une valeur explicitement retirée reste
  distinguée d'une absence de champ. Les changements explicites de preuves
  suspendent une confirmation ancienne et conservent l'audit.
- La disponibilité d'un service OCR n'est pas une preuve d'identité et n'entre
  pas dans l'empreinte ; elle peut expliquer une abstention, sans masquer un
  périmètre de langue explicitement non couvert.
- Le réexamen explicite et les reprises du worker utilisent la version courante.
  Aucune réécriture massive des confirmations ou des snapshots n'est lancée à la
  livraison. Une nouvelle détection de lot reste bloquante.

La migration est validée sur bases temporaires. Elle s'applique selon le cycle
de migration existant lors du prochain démarrage de l'application ; cette
livraison ne redémarre pas l'instance réelle ni ses services.

## Validation et limites

Point de départ : 728 tests Docker passants. Validation T03 : 386 tests ciblés,
puis suite complète : 749 passants, avec le même avertissement de dépréciation
FastAPI/Starlette/httpx. Aucun appel distant réel. Les bases utilisateur ne sont
pas utilisées.

Les tests vérifient notamment l'égalité statut/motif/candidats à observations
égales entre proposition, prévisualisation, JSONL, collecte et réidentification ;
la prévisualisation sans écriture ; les faux rôles humains ; les contradictions
OCR ; la confirmation distincte ; la réingestion partielle/prix seul ; les
confirmations historiques et l'audit ; les migrations et les cotes existantes.

La recette Chromium réelle couvre capture simulée → réanalyse → enregistrement
sur serveur local, avec interception de toutes les destinations distantes. Les
pages, les contrôles et la console JavaScript sont vérifiés ; captures aux
formats 1440×1000 et 390×844 inspectées. Le plugin Browser n'étant pas disponible,
Playwright fourni par le projet est utilisé dans Docker.

T00/T01 restent responsables de l'inventaire/annotation et du benchmark figé.
La conservation durable et vérifiable des images relève de T04. Ce contrat
conserve des observations, pas une certification de leur véracité, de l'état,
de la finition ou de l'authenticité. Les règles d'extraction gardent les limites
lexicales de T02 ; cette livraison ne valide ni la recette T13 entière ni J1/J2/J3.

## Fichiers de la livraison

- Contrat/proposition : `app/identification/evidence.py`, `decision.py`,
  `models.py`, `matcher.py`.
- Résolution, audit et pilote : `app/identification/resolution.py`, `reviews.py`,
  `diagnostics.py`, `dataset.py`, `annotation_pilot.py` ; migration
  `app/storage/migrations/0022_identification_observations.sql`.
- Adaptateurs : `app/catalog.py`, `app/collectors/models.py`,
  `app/listing_preview.py`, `app/capture_preview.py`, `app/manual_listing.py`.
  L'ingestion et le worker réutilisent leur résolution commune existante.
- Vues : `app/templates/_identification_evidence.html`, `capture_preview.html`,
  `manual_listing.html`, `catalog_detail.html`.
- Régressions : `tests/test_identification_evidence.py`,
  `test_identification_evidence_browser.py`, `test_listing_preview.py`,
  `test_lexical_identification.py`, `test_migrations.py`,
  `test_identification_reviews.py`, `test_annotation_pilot.py`.
- Documentation : ce guide, `TASKING_IDENTIFICATION_FIABLE.md`, `README.md`,
  `SUIVI.md`, `docs/IDENTIFICATION_LEXICALE.md`, `extension/README.md`.
