"""Hypothèses de numéro (T07) : lectures spatiales, variantes bornées, recherche catalogue.

Une hypothèse est une variante d'une MÊME lecture (groupe alternatif « ceci ou
cela ») : elle ne devient jamais une assertion simultanée soumise aux conflits.
La lecture brute est toujours conservée ; aucune réparation n'écrase le titre, la
description ou la lecture originale, et aucun préfixe promo valide n'est substitué.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import TYPE_CHECKING, Iterable

from app.identification.models import ExtractedFeatures
from app.identification.normalization import canonical_local_id, normalize_text
from app.identification.ocr_types import (
    HYPOTHESES_VERSION,
    Deadline,
    HypothesisSearch,
    NumberComponents,
    NumberHypothesis,
    OcrConfig,
    OcrLine,
    OcrReading,
    OcrToken,
    RankedCandidate,
)

if TYPE_CHECKING:
    from app.identification.matcher import CardMatcher

_FRACTION_PATTERN = re.compile(r"^\s*([A-Za-z]{0,4})([0-9OIl|]{1,4})\s*([/／∕⁄])\s*([0-9OIl|]{1,4})([A-Za-z]{0,3})\s*$")
_PROMO_PATTERN = re.compile(r"^\s*([A-Za-z]{2,5})([0-9OIl|]{1,4})\s*$")
_WINDOW_PATTERN = re.compile(r"^[A-Za-z0-9/\s／∕⁄|Il]{1,24}$")
_SLASH_CHARS = ("/", "／", "∕", "⁄")
_SLASHES = str.maketrans({"／": "/", "∕": "/", "⁄": "/"})
# Préfixes réellement observés dans le catalogue (jeu initial versionné, à aligner
# sur le vocabulaire du matcher lors de l'intégration). Un préfixe inconnu fait
# partie de la composante numérique : « O25/165 » se lit 0 confondu, pas « O » promo.
_KNOWN_PREFIXES = frozenset({"SM", "SWSH", "XY", "BW", "SVP", "SV", "TG", "CR", "DRM", "HIF", "UNB"})
# Libellés génériques de carte : déclassés sans supprimer un vrai nom du catalogue.
_GENERIC_LABELS = frozenset({
    "pv", "hp", "dresseur", "trainer", "no", "n", "illustration", "attack", "attaque",
    "weakness", "faiblesse", "resistance", "retraite", "retreat", "deck", "obscur",
    "secret", "rare", "holo", "reverse", "promo", "energy", "energie",
})


def parse_number(value: str) -> NumberComponents | None:
    """Reconnaît une fraction (préfixe/numérateur/dénominateur/suffixe) ou un promo.

    Les composantes attendues numériques tolèrent les confusions de lecture
    (O, I, l, |) : la structure est extraite, la correction reste une hypothèse.
    """
    cleaned = value.strip()
    fraction = _FRACTION_PATTERN.match(cleaned)
    if fraction:
        prefix, numerator, _slash, denominator, suffix = fraction.groups()
        if prefix and prefix.upper() not in _KNOWN_PREFIXES:
            # Préfixe inconnu du référentiel : il appartient à la composante lue
            # (confusion O/0 typique), jamais promu préfixe promo.
            merged = prefix + numerator
            if _digits_only(merged):
                numerator = merged
                prefix = ""
            else:
                return None
        return NumberComponents(
            kind="fraction", raw=value, prefix=prefix or None,
            numerator=numerator, denominator=denominator,
            suffix=suffix or None,
        )
    promo = _PROMO_PATTERN.match(cleaned)
    if promo:
        prefix, digits = promo.groups()
        return NumberComponents(kind="promo", raw=value, prefix=prefix, numerator=digits,
                                denominator=None, suffix=None)
    return None


def format_search_value(components: NumberComponents) -> str:
    """Valeur de recherche de l'hypothèse ; le dénominateur imprimé est conservé."""
    if components.kind == "promo":
        return f"{components.prefix}{components.numerator}"
    return (f"{components.prefix or ''}{components.numerator}"
            f"/{components.denominator}{components.suffix or ''}")


def _digits_only(component: str) -> bool:
    return bool(re.fullmatch(r"[0-9OIl|]+", component))


def _letter_to_digit(component: str) -> str:
    """Confusions typiques de lecture, composante numérique uniquement."""
    return component.translate(str.maketrans({"O": "0", "I": "1", "l": "1", "|": "1"}))


def _variant_operations(components: NumberComponents) -> list[tuple[tuple[str, ...], NumberComponents]]:
    """Variantes bornées d'une même lecture : originale, puis au plus 3 réparations.

    Priorité déterministe : séparateur Unicode, confusion lettre/chiffre, insertion
    d'un caractère unique. Une seule insertion est explorée (jamais toutes les
    combinaisons) et le préfixe d'un promo valide n'est jamais substitué.
    """
    variants: list[tuple[tuple[str, ...], NumberComponents]] = [(("original",), components)]
    seen = {format_search_value(components)}

    def push(operations: tuple[str, ...], candidate: NumberComponents) -> None:
        value = format_search_value(candidate)
        if value not in seen:
            seen.add(value)
            variants.append((operations, candidate))

    normalized_raw = components.raw.translate(_SLASHES)
    if normalized_raw != components.raw:
        reparsed = parse_number(normalized_raw)
        if reparsed is not None:
            push(("separator_normalized",), reparsed)

    numeric_parts = [components.numerator] + ([components.denominator] if components.denominator else [])
    if all(_digits_only(part) for part in numeric_parts):
        corrected = NumberComponents(
            kind=components.kind, raw=components.raw, prefix=components.prefix,
            numerator=_letter_to_digit(components.numerator),
            denominator=_letter_to_digit(components.denominator) if components.denominator else None,
            suffix=components.suffix,
        )
        if format_search_value(corrected) != format_search_value(components):
            push(("letter_to_digit",), corrected)

    if components.denominator:
        inserted = NumberComponents(
            kind=components.kind, raw=components.raw, prefix=components.prefix,
            numerator=components.numerator, denominator="1" + components.denominator,
            suffix=components.suffix,
        )
    else:
        inserted = NumberComponents(
            kind="promo", raw=components.raw, prefix=components.prefix,
            numerator="1" + components.numerator, denominator=None, suffix=None,
        )
    push(("insert_leading_1",), inserted)
    return variants


def generate_number_hypotheses(readings: Iterable[OcrReading],
                               config: OcrConfig | None = None) -> tuple[tuple[NumberHypothesis, ...], bool]:
    """Produit les hypothèses groupées, dédupliquées et classées déterministement.

    Retourne les hypothèses (plafond global de valeurs de recherche) et un drapeau
    de troncature : dépasser le plafond est exposé, jamais masqué. Les lectures sans
    structure reconnue ne produisent aucune hypothèse (leur brute reste au diagnostic).
    """
    config = config or OcrConfig()
    numbered = [reading for reading in readings if reading.role == "number"][: config.max_number_readings]
    produced: list[tuple[int, float, NumberHypothesis]] = []
    for sequence, reading in enumerate(numbered):
        components = parse_number(reading.raw_text)
        if components is None:
            continue
        confidence = reading.confidence if reading.confidence is not None else -1.0
        for variant_index, (operations, variant) in enumerate(
                _variant_operations(components)[: config.max_variants_per_reading]):
            produced.append((sequence, confidence, NumberHypothesis(
                hypothesis_id=f"{reading.reading_id}-h{variant_index}",
                alternative_group_id=reading.reading_id,
                reading_id=reading.reading_id,
                value=format_search_value(variant),
                components=variant,
                operations=operations,
                origins=(reading.reading_id, *reading.token_refs[:3]),
            )))
    # Rang déterministe : littéral avant réparé, lecture spatiale, score technique,
    # coût de réparation, valeur comme départage stable.
    produced.sort(key=lambda item: (
        item[2].operations != ("original",), item[0], -item[1],
        len(item[2].operations), item[2].value,
    ))
    # Déduplication par clé séparée numérateur/dénominateur canoniques + préfixe/suffixe,
    # en conservant toutes les provenances (essais concordants ≠ preuves indépendantes).
    # Le meilleur rang (premier dans l'ordre déterministe) représente la clé ; les
    # lectures ultérieures identiques n'ajoutent que leurs provenances.
    by_key: dict[tuple[str, str, str, str], NumberHypothesis] = {}
    for _sequence, _confidence, hypothesis in produced:
        components = hypothesis.components
        key = (
            canonical_local_id(f"{components.prefix or ''}{components.numerator}"),
            canonical_local_id(components.denominator or ""),
            (components.prefix or "").upper(),
            (components.suffix or "").upper(),
        )
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = hypothesis
        else:
            by_key[key] = replace(
                existing,
                origins=tuple(dict.fromkeys((*existing.origins, *hypothesis.origins))),
            )
    ranked = list(by_key.values())
    truncated = len(ranked) > config.max_search_values
    ranked = ranked[: config.max_search_values]
    ranked = [replace(hypothesis, rank=index) for index, hypothesis in enumerate(ranked, start=1)]
    return tuple(ranked), truncated


def _photo_box(tokens: Iterable[OcrToken]) -> tuple[float, float, float, float] | None:
    """Rectangle englobant des fragments projetés dans la photo orientée."""
    quads = [token.photo_quad for token in tokens if token.photo_quad]
    if not quads:
        return None
    xs = [point[0] for quad in quads for point in quad]
    ys = [point[1] for quad in quads for point in quad]
    return (min(xs), min(ys), max(xs), max(ys))


def extract_number_readings(tokens: tuple[OcrToken, ...], lines: tuple[OcrLine, ...], *,
                            object_id: str, pass_role: str,
                            config: OcrConfig | None = None) -> tuple[OcrReading, ...]:
    """Assemble des lectures de numéro depuis des fenêtres de 1 à 5 fragments proches.

    Fenêtres d'une même ligne : ordre horizontal, intervalle au plus deux hauteurs
    médianes. Deux lignes sont reliées uniquement pour un slash en fin/début avec un
    écart vertical d'au plus une hauteur médiane. Jamais entre régions ou objets
    distincts : les tokens fournis appartiennent tous à la passe d'un même objet.
    """
    config = config or OcrConfig()
    by_index = {token.token_index: token for token in tokens}
    readings: list[OcrReading] = []
    heights = sorted(token.box[3] for token in tokens if token.box[3] > 0)
    median_height = heights[len(heights) // 2] if heights else 10

    def push(raw: str, token_refs: list[tuple[str, int]], operations: tuple[str, ...],
             confidence: float | None, photo_box: tuple[float, float, float, float] | None,
             role: str = "number") -> None:
        if len(readings) >= config.max_number_readings:
            return
        readings.append(OcrReading(
            reading_id=f"{'num' if role == 'number' else 'rej'}-{object_id}-{len(readings)}",
            object_id=object_id,
            role="number" if role == "number" else "unknown",  # type: ignore[arg-type]
            raw_text=raw, token_refs=tuple(token_refs),
            pass_roles=(pass_role,), operations=operations, confidence=confidence,
            photo_box=photo_box,
        ))

    for line in lines:
        members = [by_index[index] for index in line.token_indexes if index in by_index]
        for start in range(len(members)):
            for size in range(1, 6):
                end = start + size
                if end > len(members):
                    break
                window = members[start:end]
                if len(window) > 1:
                    gaps = [window[index + 1].box[0] - (window[index].box[0] + window[index].box[2])
                            for index in range(len(window) - 1)]
                    if max(gaps) > 2 * median_height:
                        break  # fenêtre trop étendue : les suivantes le seront aussi
                has_slash = any(token.text in _SLASH_CHARS for token in window)
                joined = "".join(token.text for token in window) if has_slash else " ".join(
                    token.text for token in window)
                if not _WINDOW_PATTERN.match(joined) or not any(char.isdigit() for char in joined):
                    continue
                if parse_number(joined) is None:
                    continue
                window_conf = [token.confidence for token in window if token.confidence is not None]
                confidence = max(window_conf) if window_conf else None
                push(joined, [(line.pass_id, token.token_index) for token in window],
                     (), confidence, _photo_box(window))
    # Paires de lignes reliées par un slash isolé (fraction coupée sur deux lignes).
    ordered = sorted(lines, key=lambda line: (line.box[1], line.box[0]))
    for upper_index, upper in enumerate(ordered):
        for lower in ordered[upper_index + 1:]:
            vertical_gap = lower.box[1] - (upper.box[1] + upper.box[3])
            if vertical_gap > median_height:
                continue
            if vertical_gap < -median_height:
                break
            if upper.text.rstrip().endswith(_SLASH_CHARS) or lower.text.lstrip().startswith(_SLASH_CHARS):
                joined = f"{upper.text.rstrip()} {lower.text.lstrip()}"
                if parse_number(joined) is not None and joined not in {reading.raw_text for reading in readings}:
                    upper_members = [by_index[index] for index in upper.token_indexes if index in by_index]
                    lower_members = [by_index[index] for index in lower.token_indexes if index in by_index]
                    refs = [(upper.pass_id, ref) for ref in upper.token_indexes]
                    refs += [(lower.pass_id, ref) for ref in lower.token_indexes]
                    push(joined, refs, ("two_line_join",), None, _photo_box(upper_members + lower_members))
    # Fragments non couverts par une lecture acceptée et sans structure reconnue :
    # conservés au diagnostic (ex. « n »), jamais des numéros exploitables. Le bruit
    # alpha est limité aux fragments très courts pour ne pas stocker le texte de fond.
    covered = {ref for reading in readings for ref in reading.token_refs}
    rejected: dict[str, None] = {}
    for token in tokens:
        if (token.pass_id, token.token_index) in covered:
            continue
        text = token.text.strip()
        if not _WINDOW_PATTERN.match(text) or parse_number(text) is not None:
            continue
        number_like = any(char.isdigit() for char in text) or (text.isalpha() and len(text) <= 2)
        if number_like and text not in rejected and len(rejected) < 8:
            rejected[text] = None
    for raw in rejected:
        push(raw, [], ("rejected_no_structure",), None, None, role="unknown")
    return tuple(readings)


def extract_name_readings(lines: Iterable[OcrLine], *, object_id: str, pass_role: str,
                          catalog_names: tuple[str, ...] | None = None,
                          tokens: tuple[OcrToken, ...] = (),
                          limit: int = 6) -> tuple[OcrReading, ...]:
    """Extrait des lectures de nom : libellés génériques déclassés, noms courts conservés.

    Les tokens chiffrés ou barrés sont retirés de la ligne (le numéro a son propre
    rôle). Avec un vocabulaire, seuls les noms du catalogue sont proposés ; sans
    vocabulaire, un nom hors catalogue exige au moins quatre lettres et aucun
    libellé générique en tête. « Mew » reste possible dès qu'un catalogue le porte.
    """
    catalog = {normalize_text(name) for name in catalog_names or ()}
    by_index = {token.token_index: token for token in tokens}
    readings: list[OcrReading] = []
    for line in lines:
        words = [word for word in line.text.split()
                 if not any(char.isdigit() for char in word) and not any(char in word for char in _SLASH_CHARS)]
        candidate = " ".join(words).strip()
        normalized = normalize_text(candidate)
        if not normalized or len(readings) >= limit:
            continue
        split = normalized.split()
        if not split:
            continue
        if catalog:
            if normalized not in catalog:
                continue
        elif len(normalized) < 4 or split[0] in _GENERIC_LABELS:
            continue
        members = [by_index[index] for index in line.token_indexes if index in by_index]
        readings.append(OcrReading(
            reading_id=f"name-{object_id}-{len(readings)}", object_id=object_id,
            role="name", raw_text=candidate[:80],
            token_refs=tuple((line.pass_id, ref) for ref in line.token_indexes[:5]),
            pass_roles=(pass_role,), confidence=None,
            photo_box=_photo_box(members),
        ))
    return tuple(readings)


def hypothesis_features(hypothesis: NumberHypothesis, name: str | None) -> ExtractedFeatures:
    """Construit les indices structurés réutilisant le scorer commun (T03/T05)."""
    components = hypothesis.components
    return ExtractedFeatures(
        name=name,
        card_number=hypothesis.value,
        local_id=f"{components.prefix or ''}{components.numerator}",
        set_card_count=components.denominator,
    )


def search_hypotheses(matcher: CardMatcher, hypotheses: tuple[NumberHypothesis, ...],
                      names_by_reading: dict[str, tuple[str, ...]],
                      config: OcrConfig | None = None,
                      deadline: Deadline | None = None) -> HypothesisSearch:
    """Vérifie les hypothèses dans le catalogue local : toutes examinées, union dédupliquée.

    Chaque hypothèse est interrogée (numérateur complet + dénominateur attesté) puis
    départagée par au plus trois noms du MÊME objet ; une hypothèse sans nom reste
    cherchable. La recherche ne s'arrête pas au premier numéro qui renvoie une carte,
    respecte l'échéance globale et ne produit jamais d'identité effective : la
    décision finale revient à la décision commune (J1 : suggestions + confirmation).
    """
    config = config or OcrConfig()
    combos = 0
    examined = 0
    truncated = False
    by_card: dict[int, tuple[object, list[str], bool]] = {}
    for hypothesis in hypotheses:
        if deadline is not None:
            deadline.check()
        if hypothesis.search_state == "not_searchable":
            continue
        examined += 1
        names = names_by_reading.get(hypothesis.reading_id, ())[:3]
        feature_sets = [hypothesis_features(hypothesis, name) for name in names] or [
            hypothesis_features(hypothesis, None)
        ]
        for features in feature_sets:
            combos += 1
            if combos > config.max_name_number_combos:
                truncated = True
                break
            for candidate in matcher.retrieve_candidates(features):
                literal = hypothesis.operations == ("original",)
                existing = by_card.get(candidate.card_id)
                if existing is None:
                    by_card[candidate.card_id] = (candidate, [hypothesis.hypothesis_id], literal)
                else:
                    best, supporters, was_literal = existing
                    supporters.append(hypothesis.hypothesis_id)
                    by_card[candidate.card_id] = (best, supporters, was_literal or literal)
        if truncated:
            break
    hypothesis_by_id = {hypothesis.hypothesis_id: hypothesis for hypothesis in hypotheses}
    group_values: dict[str, set[str]] = {}
    for hypothesis in hypotheses:
        group_values.setdefault(hypothesis.alternative_group_id, set()).add(hypothesis.value)
    ranked: list[RankedCandidate] = []
    for _card_id, (candidate, supporters, literal) in by_card.items():
        alternatives = sorted({
            value
            for supporter in supporters
            for value in group_values.get(hypothesis_by_id[supporter].alternative_group_id, set())
            if value != hypothesis_by_id[supporter].value
        })[:3]
        ranked.append(RankedCandidate(
            card_id=candidate.card_id, tcgdex_id=candidate.tcgdex_id, name=candidate.name,
            set_name=candidate.set_name, local_id=candidate.local_id,
            confidence=candidate.confidence, name_match_kind=candidate.name_match_kind,
            contradictions=candidate.contradictions,
            hypothesis_ids=tuple(sorted(supporters)), literal_support=literal,
            alternatives=tuple(alternatives),
        ))
    ranked.sort(key=lambda item: (-item.confidence, not item.literal_support, item.name, item.tcgdex_id))
    if len(ranked) > config.max_suggestions:
        truncated = True
        ranked = ranked[: config.max_suggestions]
    diagnostics = ["search_truncated: bornes de combinaisons ou de suggestions atteintes."] if truncated else []
    return HypothesisSearch(
        suggestions=tuple(ranked), diagnostics=tuple(diagnostics),
        combos_used=min(combos, config.max_name_number_combos), values_examined=examined,
        truncated=truncated,
    )


HYPOTHESES_MODULE_VERSION = HYPOTHESES_VERSION
