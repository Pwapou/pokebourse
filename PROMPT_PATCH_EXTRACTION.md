# Prompt de développement — Renforcement de l'extraction des preuves d'identification

Document de tasking pour agent de code. Date : 2 novembre 2026.
Références obligatoires avant tout travail : `AGENTS.md` (règles d'or), `docs/IDENTIFICATION_LEXICALE.md`, `TASKING_RECHERCHE_CARTES.md`.

## 1. Contexte et problème

L'identification d'une annonce repose d'abord sur `app/identification/detector.py`, qui extrait les preuves (nom, numéro, extension, gradation, langue, variante, état) depuis le titre et la description capturés par les collecteurs et l'extension Chrome.

Limites constatées sur un cas réel — titre marketplace « Mentali EX 175 CollectAura 9.5 » :

1. **Le numéro isolé n'est jamais extrait.** `_FRACTION_NUMBER_PATTERN` exige une fraction (`175/198`) et `_PREFIX_NUMBER_PATTERN` un préfixe (`#175`, `n°175`). Un numéro seul, très fréquent dans les titres Vinted/Leboncoin, est ignoré.
2. **CollectAura n'est pas reconnu comme certificateur.** `_GRADING_PATTERNS` ne connaît que `PSA|PCA|BGS|CGC|SGS`.
3. **L'extension Chrome partage la même limite** : `extractCardNumber()` dans `extension/content/content.js` (lignes 38–42) ne capture que les fractions. Une annonce capturée via l'addon avec un numéro isolé n'alimente donc pas `card_number` dans le JSONL.

Objectif : améliorer le taux d'extraction des preuves depuis les données capturées (scraper + extension) **sans baisser l'exigence de preuve** — un cas ambigu doit rester `ambiguous`, un indice faible doit être signalé comme incertain, jamais présenté comme une certitude.

## 2. Périmètre

### Dans le périmètre

- `app/identification/detector.py` : extraction du numéro isolé, liste extensible de certificateurs, cas de parsing additionnels.
- `app/identification/matcher.py` : remontée de l'incertitude « numéro isolé » et neutralité de la gradation sur la confiance.
- `extension/content/content.js` : alignement de `extractCardNumber()` sur les mêmes règles (garde-fous inclus).
- `tests/test_identification.py` et `tests/test_chrome_extension.py` : matrice de cas de parsing et de rejet.
- `docs/IDENTIFICATION_LEXICALE.md` : courte note sur les nouvelles formes reconnues.

### Hors périmètre (ne pas faire)

- Cotation des cartes gradées dans `app/profitability.py` (sujet séparé).
- Nouveaux champs JSONL ou modification du schéma `CatalogItem` / migrations SQLite.
- Toute dépendance ML ou nouvelle librairie.
- Modification des seuils de scoring du matcher au-delà de ce qui est spécifié en 4.3.

## 3. Spécification fonctionnelle

### 3.1 Numéro isolé (priorité 1)

Ajouter un repli contrôlé à l'étape 2 de `extract_features()`, après `_FRACTION_NUMBER_PATTERN` et `_PREFIX_NUMBER_PATTERN` :

```python
_SIMPLE_NUMBER_PATTERN = re.compile(r"(?<![\d.])(?P<num>\d{2,3})(?![\d.])")
```

Garde-fous — le numéro isolé n'est retenu que si **toutes** ces conditions sont vraies :

| Garde-fou | Justification | Exemple rejeté |
|---|---|---|
| `is_lot` est faux | Règle d'or 4 : un numéro seul dans un lot ne désigne pas une carte | « Lot de 50 cartes, Dracaufeu 4 » |
| Pas une année : `1900 <= valeur <= 2099` rejeté | Années fréquentes dans les titres | « Carte Pokémon 2023 » |
| `valeur <= 300` | Au-delà de la taille max plausible d'une extension | « Réf 9999 » |
| Non adjacent à `€`, `eur`, `%` | Prix ou pourcentage | « Mentali 150 € » |
| Non adjacent à un certificateur connu suivi d'un grade | C'est un grade, pas un numéro de carte | « Mentali PSA 9 » |
| Au moins 2 chiffres | Un chiffre isolé est indiscernable d'un grade/quantité | « Mentali ex 9 » |
| Un nom de carte **ou** une extension est déjà détecté | Évite les faux positifs sur titres génériques | « Cartes 125 disponibles » |

Le lookbehind/lookahead `(?<![\d.])…(?![\d.])` exclut les décimaux : dans « CollectAura 9.5 », le « 9 » n'est jamais candidat. `card_number` reçoit le numéro seul, `local_id` également, `set_card_count` reste `None` (c'est ce `None` qui distingue un numéro isolé d'une fraction dans le matcher).

### 3.2 Certificateurs de gradation (priorité 2)

Remplacer `_GRADING_PATTERNS` par une construction à partir d'une constante extensible :

```python
_KNOWN_GRADING_COMPANIES: tuple[str, ...] = ("PSA", "PCA", "BGS", "CGC", "SGS", "COLLECTAURA")
```

- Le pattern accepte « CollectAura », « Collect'Aura » et « Collect Aura » (apostrophe normalisée via `_normalize_text`, espace optionnel).
- Le grade collé est accepté : `PSA10`, `psa10`, `PCA9.5` — espace optionnel entre société et grade.
- Le grade reste `10|[1-9](?:\.5)?` : `9.5` est valide, `9.25` ne l'est pas.
- Ne pas ajouter d'autres certificateurs sans exemple réel observé : un faux positif de certification est plus dommageable qu'une non-détection, car la certification influence la cote.

### 3.3 Cas de parsing additionnels à couvrir

Vérifier par des tests que les formes suivantes sont traitées correctement (certaines passent déjà — les tests doivent les figer, pas forcément modifier le code) :

| Titre | Attendu |
|---|---|
| `Mentali EX 175 CollectAura 9.5` | `local_id="175"`, variant `ex`, `grading_company="COLLECTAURA"`, `grade="9.5"` |
| `mentali ex 175 collectaura 9.5` | Idem (casse/minuscules insensibles) |
| `Mentali ex PSA10` | `grading_company="PSA"`, `grade="10"`, aucun `local_id` |
| `Mentali CGC 9.5` | `grading_company="CGC"`, `grade="9.5"` |
| `Mentali ex 175/198 Forces Temporelles` | Fraction prioritaire : `card_number="175/198"` |
| `Mentali ex #175` | Préfixe : `local_id="175"` |
| `Mentali ex n°175` | Préfixe : `local_id="175"` |
| `Dracaufeu 4/102 set de base` | Fraction + extension |
| `Carte pokemon Mentali ex 175 sous sleeve` | Numéro isolé accepté (nom présent) |

### 3.4 Cas de rejet à vérifier (checking)

| Titre | Attendu |
|---|---|
| `Lot de 50 cartes Pokémon dont Mentali 4` | `is_lot=True`, aucun `local_id` |
| `Mentali ex 9.5` | Pas de `local_id` (décimal) ; pas de gradation sans société |
| `Mentali ex 9` | Pas de `local_id` (1 chiffre isolé) |
| `Carte Pokémon édition 2023` | Pas de `local_id` (année) |
| `Mentali 150€` | Pas de `local_id` (prix) |
| `Vends x3 Mentali ex` | Pas de `local_id` (quantité) |
| `Mentali PSA 9` | `grade="9"`, aucun `local_id` |

### 3.5 Extension Chrome

`extractCardNumber()` dans `extension/content/content.js` :

- Ajouter la capture du numéro isolé avec les mêmes garde-fous qu'en 3.1 (années, prix, grades collés à un certificateur).
- Le format JSONL produit ne change pas : `card_number` reste une chaîne optionnelle ; « 175/198 » et « 175 » sont tous deux valides côté `app/catalog.py`.
- Mettre à jour `tests/test_chrome_extension.py` en conséquence.

### 3.6 Matcher — remontée d'incertitude

Dans `app/identification/matcher.py` :

1. Quand `features.local_id` est présent avec `features.set_card_count is None` (numéro isolé), ajouter le motif « numéro isolé, sans dénominateur » à `uncertain_fields` du résultat, et s'assurer qu'un tel match ne peut pas produire un `identified` automatique de niveau équivalent à une fraction exacte (au mieux `ambiguous` si d'autres indices concordent, sinon le scoring actuel s'applique tel quel).
2. La détection d'une gradation (`grading_company`/`grade` non nuls) doit être **neutre** sur le score de rattachement TCGdex : le référentiel ne contient pas les cartes gradées. Elle ne doit ni renforcer la confiance, ni créer de candidat. Si le code actuel l'ignore déjà, le figer par un test.

**Ne jamais baisser les seuils d'exigence** : tout cas qui était `ambiguous` avant le patch doit le rester, sauf si un indice factuel nouveau le justifie.

## 4. Investigation préalable (étape 0)

Avant d'écrire le patch, vérifier et rapporter en quelques lignes :

1. Comment le pipeline d'ingestion (`app/identification/pipeline.py`, `app/collectors/service.py`, `app/catalog.py`) alimente le détecteur : le `card_number` structuré fourni par l'extension dans le JSONL est-il utilisé comme preuve quand le titre seul n'en contient pas ? Si non, le signaler dans le rapport sans l'implémenter (hors périmètre, décision à prendre).
2. Le comportement actuel du matcher sur chaque cas des matrices 3.3 et 3.4, pour distinguer les régressions potentielles des améliorations.
3. La compatibilité de `canonical_local_id()` (`app/identification/normalization.py`) avec un numéro isolé.

## 5. Contraintes du projet (rappel AGENTS.md)

- Tests 100 % hermétiques : aucun appel réseau réel, mocks ou `seed_data` uniquement.
- Toutes les exécutions dans Docker : `docker compose run --rm app pytest`.
- Aucune nouvelle dépendance dans `pyproject.toml`.
- Typage strict Python 3.12 (`str | None`), docstrings sur les nouvelles fonctions.
- Aucune ressource distante (CDN, fonts, JS externe).
- Ne pas modifier les migrations existantes ; aucune migration nécessaire ici (pas de changement de schéma).
- Ne jamais lancer `docker compose down -v`.

## 6. Critères d'acceptation

- [ ] `docker compose run --rm app pytest` complet au vert, zéro régression.
- [ ] Tous les cas des matrices 3.3 et 3.4 couverts par des tests nommés explicitement.
- [ ] `extractCardNumber()` de l'extension alignée + tests extension à jour.
- [ ] Cas réel « Mentali EX 175 CollectAura 9.5 » traité : preuves extraites, statut honnête (`ambiguous` ou mieux si les indices concordent, jamais un `identified` forcé).
- [ ] Rapport d'étape 0 (point 4) joint à la livraison.
- [ ] `docs/IDENTIFICATION_LEXICALE.md` mis à jour avec les nouvelles formes reconnues.

## 7. Effort estimé

1 à 2 jours de développement, tests inclus.
