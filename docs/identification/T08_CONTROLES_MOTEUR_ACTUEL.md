# T08.1 et contrôles T08.3 — moteur actuel

Livraison du 8 novembre 2026. Le nouveau moteur spatial et la sélection/confirmation transitoire ne sont pas livrés par ce lot. Voir [tracker](../../tracker.md) pour la revalidation et les limites.

## Contrats conservés

- Titre original transporté dans `raw_data.title` puis conservé dans `original_title` ; corrections conservées durablement dans les observations. `edited_title` est un champ de transport, normalisé par l’import JSONL, pas une clé durable garantie de `raw_data`. Les champs `captured_*` du formulaire ne sont pas remplacés par les propositions.
- Nouvelle capture : `name` vide, titre distinct, langue `und`. Export compatible : nom de repli pour respecter les champs JSONL historiques requis, titre brut séparé et `und` explicite. Ancien JSONL sans langue : défaut historique inchangé.
- `prefill_identity_fields()` projette uniquement une référence admissible de tête non ex æquo. Aucun nom arbitraire depuis tout le titre en absence de candidat ; aucune projection unitaire pour un lot ou un conflit. Une saisie différente du repli/proposé n’est pas écrasée.
- `proposed_name/set_name/card_number` gardent la qualité indicative ; `proposal_source_*` sert seulement à l’affichage. Aucune provenance cliente ne confère d’autorité de confirmation. Les préremplissages ne constituent pas des preuves indépendantes de conflit ; les vraies observations OCR et vendeur restent contrôlées.
- `preview_form()` sépare diagnostics financiers et identité. Réanalyse sans OCR/réseau/écriture ; prix et port vides restent inconnus, valeurs invalides conservées. Le serveur recontrôle aussi les soumissions directes.
- Les extensions non reconnues et les numéros de forme invalide ne deviennent pas des filtres exacts. Noms/alias, extension, numéro et langue disposent de diagnostics séparés ; recherche partielle, candidats contradictoires et replis lexicaux existants restent accessibles. Une extension seule produit des candidats bornés, jamais une acceptation nouvelle par abaissement de seuil.
- `und` ne signifie pas langue étrangère et n’est pas une preuve française. Le formulaire, la fiche et le catalogue affichent « Inconnue » ; le CSV garde `und`.

## Diagnostic du parasite n

Deux reproductions avant correction ont été exécutées dans Docker :

1. `extract_features('Non identifiée')` retournait `card_number='n'` : regex `no` sans frontière ni chiffre requis, suivie du dernier `n` de « Non ».
2. Un indice `ocr_numbers=['n']` était accepté par `_features()` comme identifiant alphabétique, puis recopié depuis les features par le préremplissage, sans candidat admissible.

Les préfixes Python/extension exigent désormais des chiffres ; une valeur alphabétique structurée n’est exploitable que si son identifiant est attesté au catalogue local. Les valeurs invalides restent disponibles pour diagnostic. Les numéros promotionnels alphanumériques restent pris en charge. Le titre exact Tortant/description 1995 ne produisait aucun numéro lors du diagnostic. Ces reproductions ne prouvent pas la source précise du `n` sur la photo du chat.

## Consignes au job OCR T06/T07/T08.2

1. Obtenir la photo originale autorisée et le payload correspondant au cas Tortant, séparément de la capture d’écran. Annoter indépendamment nom, numéro `20/82`, référence/extension attendues et langue ; figer le catalogue. Ne pas déduire la vérité terrain du premier candidat.
2. Rejouer chaque frontière : page brute → content script/stockage → payload → texte/TSV OCR → indices reconnus → observations → candidats/diagnostic → champs proposés. Identifier lequel des deux chemins reproduits explique l’incident réel, ou consigner une autre cause dans TRK-002. Ne pas attribuer l’erreur à Tesseract sur simple propagation d’un indice fabriqué.
3. Réutiliser la projection/validation de ce lot ; transmettre des observations `source='ocr'` bornées et leur provenance, jamais une référence « confirmée » cliente. Pour hypothèses alternatives/spatiales et langue, faire évoluer explicitement le contrat actuel (l’OCR n’accepte encore que nom/numéro), avec tests de compatibilité. Ne pas aplatir des alternatives mutuellement exclusives en preuves contradictoires.
4. Proposer le nom canonique et l’extension depuis une référence admissible unique ; conserver le dénominateur effectivement lu, ne pas le reconstruire depuis le catalogue. Un titre faux ou un nom réellement contradictoire reste dans le diagnostic jusqu’à une résolution humaine motivée (TRK-007). Aucun seuil abaissé.
5. Suggérer la langue depuis le texte de l’exemplaire avec abstention ; ne pas remplacer `und` par la locale TCGdex. Préserver les corrections lors des réponses tardives et lier sélection/photo/observations aux empreintes et révisions prévues.
6. Raccorder l’orchestration hors popup (TRK-004), le choix transitoire avant ID et l’ajout/décision atomiques (TRK-005), puis tester doublon, rollback, révision et reprise. Ne pas confondre le bouton d’ajout actuel avec une confirmation humaine d’identité.
7. Rejouer `tests/test_capture_workflow.py`, les suites capture/listing/manual/evidence, OCR, reviews, extension e2e et navigateur, puis `docker compose run --rm app pytest -ra`. Étendre le harnais aux étapes W03/W04/W08 nouvelles ; sa couverture actuelle ne valide pas l’intégralité de W01–W09.
8. Faire la recette photographique réelle et les mesures appariées prévues dans le plan T06/T07/T10. Les tests de transport OCR simulé de ce lot ne mesurent aucun gain de reconnaissance et ne valident pas la recette complète §1.3.

## Résultats de validation de cette livraison

- Suites ciblées du plan (15 fichiers, commande complète dans le tracker) : **188 passants**, zéro skip ; vraie extension sous Chromium/Xvfb incluse.
- Rejeu navigateur/harnais après le dernier ajustement de libellé : **11 passants** ; captures desktop 1440×1000 et mobile 390×844 inspectées, aucun débordement ni erreur console applicative.
- `docker compose run --rm app pytest -ra` : **829 passants**, zéro skip, code 0 ; un avertissement existant de dépréciation Starlette/httpx.
- `git diff --check` : code 0. Aucun seuil d’acceptation abaissé, aucune migration ni nouvelle dépendance, aucun effacement de données utilisateur.

TRK-001/TRK-003/TRK-006 (captures) et les régressions d’intégration TRK-012/TRK-013 sont revalidés dans ce périmètre. TRK-002 sur la photo originale et les intégrations T08.2/T09 restent ouverts : voir les consignes ci-dessus.


## Complément du job 1 — reprise du 8 novembre 2026

Acquis précédents conservés. Changements de cette reprise :

- `CAPTURE_LISTINGS` accepte l'absence de nom et d'extension si le titre brut est présent ; un nom historique seul reste accepté. Aucun attribut d'identité inventé au stockage Chrome. Prix entiers positifs ou inconnus, URL, déduplication et provenance restent contrôlés.
- Devise absente : erreur financière affichée auprès du champ, sans bloquer l'identification partielle.
- Soumission finale URL sans JavaScript : les erreurs de prix/port conservent candidats, diagnostics et corrections. Aucun OCR ni réseau supplémentaire ; aucune écriture en cas d'erreur. Priorité du diagnostic de doublon préservée.
- Le chemin URL conserve désormais `captured_title` comme titre original lors de l'ajout ; la correction reste une observation manuelle. L'importeur JSONL conserve son contrat de normalisation existant.

Les cases T08.1 sont acquises ; T08.3 est validable pour les contrôles du moteur actuel. Les cases impliquant choix transitoire, résolution motivée et invalidation d'une sélection restent ouvertes pour l'intégration T08.2/T09 du job 3 (TRK-005/TRK-007). Aucun nouveau module OCR n'a été développé ici.

### Reprise job 3

1. Réutiliser `preview_form`, `identity_checks`, `prefill_identity_fields` et le contrat d'observations existant ; conserver les erreurs financières séparées, les champs corrigés et `und`.
2. Raccorder les nouveaux modules du job 2 sans leur substituer une nouvelle extraction locale ; tester les réponses tardives, changements de photo/preuves et invalidation de sélection.
3. Implémenter orchestration indépendante du popup, sélection transitoire puis décision atomique motivée (TRK-004/005/007). Ne pas déclarer qu'un ajout résout les contradictions.
4. Rejouer la photo originale pour l'origine exacte de `n` (TRK-002), puis la recette photographique et la qualification OCR (TRK-009). Les corrections déterministes du parasite restent validées séparément.
5. Pour les collecteurs, suivre T19/TRK-100/101 et garder confirmations humaines et `first_seen_at`. Avant toute migration, relire le dernier numéro réel : `0026` lors de cette reprise.
6. Rejouer les suites ciblées du plan et `docker compose -p pokebourse-fields-p1 run --rm app pytest -ra`. Résultats de cette reprise et incidents détaillés dans `tracker.md`.


### Revalidation de la reprise

- Commande ciblée détaillée dans le tracker : **311 passants**, zéro skip, code 0.
- `docker compose -p pokebourse-fields-p1 run --rm app pytest -ra` : **834 passants**, zéro skip, code 0, en 40,95 s ; un avertissement existant Starlette/httpx.
- POST directs sans JavaScript, vraie extension MV3, interactions capture et URL, clavier, console erreurs/avertissements et rendu 1440×1000/390×844 revalidés. Captures inspectées dans `/tmp/pokebourse-fields-p1-qa/`, hors dépôt.
- TRK-014/015/016 validés après reproduction puis revalidation. Pas de migration ni de nouvelle dépendance. Les autres limites de reprise demeurent explicites ci-dessus.
