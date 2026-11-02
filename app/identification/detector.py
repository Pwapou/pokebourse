import re
import unicodedata
from app.identification.models import ExtractedFeatures

_CARD_QUANTITY = r"(?:[1-9]\d*|une?|deux|trois|quatre|cinq|six|sept|huit|neuf|dix)"

_CARD_SELECTION_PATTERN = re.compile(
    r"\bcartes?\s+(?:pok[ée]mon\s+)?(?:au\s+choix|[àa]\s+choisir)\b",
    re.IGNORECASE,
)

_NEGATED_LOT_PATTERN = re.compile(
    r"\b(?:pas\s+(?:un|de)\s+|sans\s+(?:un\s+)?)(?:lot|lots)\b"
    rf"(?:\s+(?:de\s+)?(?:{_CARD_QUANTITY}\s+)?cartes?(?:\s+pok[ée]mon)?|\s+pok[ée]mon)?",
    re.IGNORECASE,
)

_MULTI_CARD_PATTERN = re.compile(
    r"\b(?:[2-9]|[1-9]\d+|deux|trois|quatre|cinq|six|sept|huit|neuf|dix)\s*cartes?\s+pok[ée]mon\b",
    re.IGNORECASE,
)

# « pack » seul peut appartenir au nom d'une extension. Il faut un contexte
# de produit, sans introduire d'alias (notamment pour « Gem Pack 2 »).
_PACK_PATTERN = re.compile(
    r"\bpacks?(?:\s+\d{1,3})?\s+(?:pok[ée]mon|scell[ée]s?|sous\s+blister|"
    r"de\s+(?:\d+\s+)?(?:boosters?|cartes?))\b",
    re.IGNORECASE,
)

_SERIAL_NUMBER_PATTERN = re.compile(
    r"\b(?:num[ée]ro\s+de\s+s[ée]rie|n[°o]\s*(?:de\s+)?s[ée]rie|"
    r"serial(?:\s+(?:number|no))?|num[ée]ro\s+de\s+certificat(?:ion)?)"
    r"\s*[:#=-]?\s*[a-z0-9]+(?:[/-][a-z0-9]+)*\b",
    re.IGNORECASE,
)

_LOT_PATTERNS = [
    re.compile(rf"\b(?:lot|lots)\s+(?:de\s+)?(?:{_CARD_QUANTITY}\s+)?cartes?\b", re.IGNORECASE),
    re.compile(r"\b(?:collection|classeur|vrac|album)\s+(?:de\s+)?cartes?\b", re.IGNORECASE),
    _MULTI_CARD_PATTERN,
    re.compile(r"\b(?:display|booster|coffret|tin|deck|pokebox|tripack)\b", re.IGNORECASE),
    _PACK_PATTERN,
    re.compile(r"\blot\s+pok[ée]mon\b", re.IGNORECASE),
    re.compile(r"\bcartes?\s+diverses\b", re.IGNORECASE),
    re.compile(rf"\bvendu(?:e|s|es)?\s+avec\s+{_CARD_QUANTITY}\s+cartes?\b", re.IGNORECASE),
    re.compile(
        rf"(?:\bavec\s+|\+\s*){_CARD_QUANTITY}\s+cartes?\s+"
        r"(?:en\s+plus|suppl[ée]mentaires?|offertes?)\b",
        re.IGNORECASE,
    ),
]

_FRACTION_NUMBER_PATTERN = re.compile(
    r"\b(?P<num>[A-Za-z0-9]{1,4})\s*/\s*(?P<total>[0-9]{2,3})\b"
)

# Les préfixes sont ceux effectivement utilisés par les identifiants locaux
# TCGdex (dont SM233, SWSH020, XY123 et BW01). SVP est également reconnu pour
# les références Écarlate et Violet, même si l'extension n'est pas synchronisée.
_PROMO_NUMBER_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(?P<num>(?:SWSH|SVP|SM|XY|BW)[0-9O]{1,4})(?![A-Za-z0-9])",
    re.IGNORECASE,
)

_PREFIX_NUMBER_PATTERN = re.compile(
    r"(?:#|n°|no\.?|num[ée]ro)\s*(?P<num>[A-Za-z0-9]{1,4})\b",
    re.IGNORECASE,
)

_SIMPLE_NUMBER_PATTERN = re.compile(r"(?<![\d.])(?P<num>\d{2,3})(?![\d.])")

_CURRENCY_BEFORE_PATTERN = re.compile(r"(?:€|\b(?:eur|euros?))\s*$", re.IGNORECASE)
_CURRENCY_OR_PERCENT_AFTER_PATTERN = re.compile(
    r"^\s*(?:€|%|(?:eur|euros?)\b)", re.IGNORECASE
)
_SLASH_BEFORE_PATTERN = re.compile(r"/\s*$")
_SLASH_AFTER_PATTERN = re.compile(r"^\s*/")

_GENERIC_HEAD_WORDS: frozenset[str] = frozenset(
    {
        "album",
        "annonce",
        "article",
        "booster",
        "carte",
        "cartes",
        "classeur",
        "coffret",
        "collection",
        "deck",
        "display",
        "edition",
        "figurine",
        "item",
        "lot",
        "lots",
        "objet",
        "pack",
        "pokebox",
        "pokemon",
        "promo",
        "ref",
        "reference",
        "serie",
        "set",
        "tin",
        "tripack",
        "vrac",
    }
)

_KNOWN_SETS = {
    "set de base": "Set de Base",
    "base set": "Set de Base",
    "151": "151",
    "tenebres embrasees": "Ténèbres Embrasées",
    "ténèbres embrasées": "Ténèbres Embrasées",
    "evolutions": "Évolutions",
    "évolutions": "Évolutions",
    "flammes obsidiennes": "Flammes Obsidiennes",
    "evolution celeste": "Évolution Céleste",
    "évolution céleste": "Évolution Céleste",
    "zenith supreme": "Zénith Suprême",
    "zénith suprême": "Zénith Suprême",
    "origine perdue": "Origine Perdue",
    "tempete argentee": "Tempête Argentée",
    "tempête argentée": "Tempête Argentée",
    "stars etincelantes": "Stars Étincelantes",
    "stars étincelantes": "Stars Étincelantes",
    "voltage eclatant": "Voltage Éclatant",
    "voltage éclatant": "Voltage Éclatant",
    "forces temporelles": "Forces Temporelles",
    "mascarade crepusculaire": "Mascarade Crépusculaire",
    "couronne stellaire": "Couronne Stellaire",
    "etincelles deferlantes": "Étincelles Déferlantes",
    "étincelles déferlantes": "Étincelles Déferlantes",
}

_KNOWN_GRADING_COMPANIES: tuple[str, ...] = (
    "PSA",
    "PCA",
    "BGS",
    "CGC",
    "SGS",
    "COLLECTAURA",
)

_GRADING_COMPANY_PATTERNS: dict[str, str] = {
    "COLLECTAURA": r"collect[\s'’`]*aura",
}


def _company_regex_fragment(company: str) -> str:
    """Construit l'expression régulière tolérante associée à un certificateur connu."""
    return _GRADING_COMPANY_PATTERNS.get(company, re.escape(company.lower()))


def _canonical_grading_company(raw_company: str) -> str:
    """Normalise le nom du certificateur détecté vers sa forme canonique majuscule."""
    return re.sub(r"\s+", "", _normalize_text(raw_company)).upper()


_GRADING_COMPANY_ALTERNATION = "|".join(
    _company_regex_fragment(company) for company in _KNOWN_GRADING_COMPANIES
)

_GRADING_PATTERN = re.compile(
    rf"\b(?P<company>{_GRADING_COMPANY_ALTERNATION})\s*(?P<grade>10|[1-9](?:\.5)?)\b(?![.,]\d)",
    re.IGNORECASE,
)

_GRADING_COMPANY_BEFORE_PATTERN = re.compile(
    rf"\b(?:{_GRADING_COMPANY_ALTERNATION})\s*$",
    re.IGNORECASE,
)

_LANGUAGE_PATTERNS = [
    (re.compile(r"\b(?:vf|fran[çc]aise?|french)\b", re.IGNORECASE), "fr"),
    (re.compile(r"\b(?:anglaise?|english)\b", re.IGNORECASE), "en"),
    (re.compile(r"\b(?:jap|japonaise?|japanese)\b", re.IGNORECASE), "ja"),
]

_LANGUAGE_CODES = {"fr": "fr", "en": "en", "us": "en", "jp": "ja", "ja": "ja"}
_LANGUAGE_CODE_LIST = r"(?:fr|en|us|jp|ja)(?:\s*[/,+&]\s*(?:fr|en|us|jp|ja))*"
_LANGUAGE_FIELD_PATTERN = re.compile(
    rf"\b(?:langue|language|version)\s*[:=]\s*(?P<codes>{_LANGUAGE_CODE_LIST})\b",
    re.IGNORECASE,
)
_BRACKETED_LANGUAGE_PATTERN = re.compile(r"[\[(](fr|en|us|jp|ja)[\])]", re.IGNORECASE)
# Marques de langue conventionnelles en majuscules ; « en » reste une
# préposition, et même « EN » exige un champ explicite ou des parenthèses.
_LANGUAGE_MARKER_PATTERN = re.compile(r"\b(?:FR|US|JP|JA)\b")

_VARIANT_PATTERNS = [
    (re.compile(r"\b(?:holo|holographique)\b", re.IGNORECASE), "Holo"),
    (re.compile(r"\breverse\b", re.IGNORECASE), "Reverse"),
    (re.compile(r"\b(?:vmax)\b", re.IGNORECASE), "VMAX"),
    (re.compile(r"\b(?:vstar)\b", re.IGNORECASE), "VSTAR"),
    (re.compile(r"\b(?:ex)\b", re.IGNORECASE), "ex"),
    (re.compile(r"\b(?:gx)\b", re.IGNORECASE), "GX"),
    (re.compile(r"\b(?:secrete|secrète|secret)\b", re.IGNORECASE), "Secrète"),
    (re.compile(r"\b(?:alternative|alt art)\b", re.IGNORECASE), "Alternative"),
    (re.compile(r"\bpromo\b", re.IGNORECASE), "Promo"),
    (re.compile(r"\bfull art\b", re.IGNORECASE), "Full Art"),
    (re.compile(r"\b(?:1ere|1ère|premiere|première)\s*[ée]dition\b", re.IGNORECASE), "1ère Édition"),
]

_CONDITION_PATTERNS = [
    # Le Near Mint déclaré reste prioritaire sur le mot « mint » qu'il contient.
    (re.compile(r"\b(?:near\s*-?\s*mint|nm|tres bon etat|très bon état)\b", re.IGNORECASE), "Near Mint"),
    (re.compile(r"\b(?:gem mint|mint|neuf)\b", re.IGNORECASE), "Neuf"),
    (re.compile(r"\b(?:excellent|bon etat|bon état)\b|\b(?:[ée]tat|condition)\s*[:=-]?\s*ex\b", re.IGNORECASE), "Excellent"),
    (re.compile(r"\b(?:played|etat moyen|état moyen|abime|abîmé)\b", re.IGNORECASE), "Played"),
]


def _normalize_text(text: str) -> str:
    """Normalise accents, apostrophes, casse et espaces pour la détection."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    stripped = re.sub(r"['’`]", " ", stripped)
    return " ".join(stripped.casefold().split())


def _overlaps_span(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    """Indique si un indice appartient déjà à une observation protégée."""
    return any(start < span_end and end > span_start for span_start, span_end in spans)


def _catalog_set_spans(text: str, catalog_sets: list[str] | None) -> list[tuple[int, int]]:
    """Protège les noms d'extensions fournis par le cache, sans inventer d'alias."""
    spans = []
    for name in catalog_sets or []:
        # Un nom purement numérique ne masque pas une quantité réellement vendue.
        if not any(char.isalpha() for char in name):
            continue
        pattern = r"\b" + r"\s+".join(re.escape(word) for word in name.split()) + r"\b"
        spans.extend(match.span() for match in re.finditer(pattern, text, re.IGNORECASE))
    return spans


def _extract_languages(text: str) -> tuple[str, ...]:
    """Conserve toutes les langues explicitement mentionnées, sans ordre de priorité."""
    languages = {code for pattern, code in _LANGUAGE_PATTERNS if pattern.search(text)}
    for match in _LANGUAGE_FIELD_PATTERN.finditer(text):
        languages.update(_LANGUAGE_CODES[code] for code in re.findall(r"[a-z]+", match["codes"].lower()))
    for match in _BRACKETED_LANGUAGE_PATTERN.finditer(text):
        languages.add(_LANGUAGE_CODES[match[1].lower()])
    for match in _LANGUAGE_MARKER_PATTERN.finditer(text):
        languages.add(_LANGUAGE_CODES[match[0].lower()])
    return tuple(sorted(languages))


def _extract_simple_number(
    full_text: str,
    *,
    is_lot: bool,
    extracted_name: str | None,
    set_name: str | None,
    grading_spans: list[tuple[int, int]],
    excluded_spans: list[tuple[int, int]],
) -> str | None:
    """Extrait un numéro de carte isolé (2 à 3 chiffres) sous garde-fous stricts."""
    if is_lot or (not extracted_name and not set_name):
        return None

    for match in _SIMPLE_NUMBER_PATTERN.finditer(full_text):
        raw_num = match.group("num")
        start, end = match.span("num")
        if _overlaps_span(start, end, excluded_spans):
            continue
        value = int(raw_num)

        # Bornes plausibles d'une extension et exclusion explicite des années
        if value == 0 or (1900 <= value <= 2099) or value > 300:
            continue

        # Exclusion des jetons alphanumériques collés (ex: PSA10, x10, 24h) et décimaux à virgule
        if start > 0 and full_text[start - 1].isalpha():
            continue
        if end < len(full_text) and full_text[end].isalpha():
            continue
        if start >= 2 and full_text[start - 1] == "," and full_text[start - 2].isdigit():
            continue
        if end + 1 < len(full_text) and full_text[end] == "," and full_text[end + 1].isdigit():
            continue

        before = full_text[:start]
        after = full_text[end:]

        # Exclusion des expressions fractionnaires non retenues (ex: 11/2023)
        if _SLASH_BEFORE_PATTERN.search(before) or _SLASH_AFTER_PATTERN.match(after):
            continue

        # Exclusion des prix et pourcentages (€, eur, euros, %)
        if _CURRENCY_BEFORE_PATTERN.search(before) or _CURRENCY_OR_PERCENT_AFTER_PATTERN.match(after):
            continue

        # Exclusion des grades rattachés ou adjacents à un certificateur connu
        if any(start < g_end and end > g_start for g_start, g_end in grading_spans):
            continue
        if _GRADING_COMPANY_BEFORE_PATTERN.search(before):
            continue

        # Une extension numérique seule (« Carte Pokémon 151 ») ne crée pas de numéro isolé
        if extracted_name is None and set_name == raw_num:
            occurrences = len(_SIMPLE_NUMBER_PATTERN.findall(full_text))
            if occurrences < 2:
                continue

        return raw_num

    return None


def extract_features(
    title: str,
    description: str | None = None,
    *,
    catalog_names: list[str] | None = None,
    catalog_sets: list[str] | None = None,
) -> ExtractedFeatures:
    """Analyse les preuves, avec un vocabulaire dérivé du référentiel local."""
    full_text = f"{title or ''} {description or ''}".strip()
    norm_text = _normalize_text(full_text)

    # 1. Objet vendu : un choix de carte ne désigne pas une identité unique.
    selection_match = _CARD_SELECTION_PATTERN.search(full_text)
    selection_reason = (
        f"Vente de carte au choix : « {selection_match.group(0)} ». Objet vendu à préciser."
        if selection_match else None
    )
    is_lot = False
    lot_reason = None
    negated_lots = [match.span() for match in _NEGATED_LOT_PATTERN.finditer(full_text)]
    serial_spans = [match.span() for match in _SERIAL_NUMBER_PATTERN.finditer(full_text)]
    set_spans = _catalog_set_spans(full_text, catalog_sets)
    product_exclusions = negated_lots + serial_spans + set_spans
    for pattern in _LOT_PATTERNS:
        if selection_reason and pattern is _MULTI_CARD_PATTERN:
            continue
        for match in pattern.finditer(full_text):
            start = match.start()
            if _overlaps_span(start, match.end(), product_exclusions):
                continue
            # Un dénominateur de fraction n'est pas une quantité : dans
            # « Dracaufeu 4/102 Carte Pokémon », le « 102 » appartient au
            # numéro de carte et ne doit pas déclencher la détection de lot.
            if re.search(r"/\s*$", full_text[:start]):
                continue
            is_lot = True
            lot_reason = f"Mention explicite de lot ou produit scellé : « {match.group(0)} »"
            break
        if is_lot:
            break

    # 2. Numéro explicite : fraction, promotion alphanumérique, puis préfixe # / n°.
    # Le préfixe alphabétique évite de confondre prix, dates et quantités avec
    # une référence promotionnelle. Les lots ne produisent jamais d'indice unitaire.
    card_number = None
    local_id = None
    set_card_count = None

    frac_match = next((match for match in _FRACTION_NUMBER_PATTERN.finditer(full_text)
                       if not _overlaps_span(*match.span(), serial_spans)), None)
    promo_match = None if is_lot else next((match for match in _PROMO_NUMBER_PATTERN.finditer(full_text)
                                           if not _overlaps_span(*match.span(), serial_spans)), None)
    if frac_match:
        local_id = frac_match.group("num")
        set_card_count = frac_match.group("total")
        card_number = f"{local_id}/{set_card_count}"
    elif promo_match:
        # Après un préfixe promotionnel connu, Tesseract confond parfois O et 0.
        local_id = promo_match.group("num").upper().replace("O", "0")
        card_number = local_id
    else:
        prefix_match = next((match for match in _PREFIX_NUMBER_PATTERN.finditer(full_text)
                             if not _overlaps_span(*match.span(), serial_spans)), None)
        if prefix_match:
            local_id = prefix_match.group("num")
            card_number = local_id

    # 3. Extension : vocabulaire du catalogue prioritaire, alias historiques en repli.
    set_name = None
    for official_name in catalog_sets or []:
        if re.search(rf"\b{re.escape(_normalize_text(official_name))}\b", norm_text):
            set_name = official_name
            break
    if set_name is None:
        for key, official_name in _KNOWN_SETS.items():
            if re.search(rf"\b{re.escape(_normalize_text(key))}\b", norm_text):
                set_name = official_name
                break

    # 4. Gradation
    grading_company = None
    grade = None
    grading_matches = list(_GRADING_PATTERN.finditer(full_text))
    if grading_matches:
        first_grading = grading_matches[0]
        grading_company = _canonical_grading_company(first_grading.group("company"))
        grade = first_grading.group("grade")
    grading_spans = [m.span() for m in grading_matches]

    # 5. Langue
    languages = _extract_languages(full_text)
    language = languages[0] if len(languages) == 1 else None

    # 6. Variante
    variant = None
    for pattern, var_name in _VARIANT_PATTERNS:
        if pattern.search(full_text):
            variant = var_name
            break

    # 7. État
    condition = None
    condition_raw = None
    for pattern, cond_name in _CONDITION_PATTERNS:
        if match := pattern.search(full_text):
            condition = cond_name
            condition_raw = match.group(0)
            break

    # 8. Extraction du nom de carte potentiel
    extracted_name = _extract_card_name(title, full_text, norm_text, catalog_names)

    # 2b. Repli contrôlé sur un numéro isolé (si aucune fraction ni aucun préfixe n'a abouti)
    if card_number is None:
        simple_num = _extract_simple_number(
            full_text,
            is_lot=is_lot,
            extracted_name=extracted_name,
            set_name=set_name,
            grading_spans=grading_spans,
            excluded_spans=serial_spans + set_spans,
        )
        if simple_num is not None:
            local_id = simple_num
            card_number = simple_num

    return ExtractedFeatures(
        name=extracted_name,
        card_number=card_number,
        local_id=local_id,
        set_card_count=set_card_count,
        set_name=set_name,
        language=language,
        variant=variant,
        condition=condition,
        grading_company=grading_company,
        grade=grade,
        is_lot=is_lot,
        lot_reason=lot_reason,
        selection_reason=selection_reason,
        languages=languages,
        condition_raw=condition_raw,
    )


def _extract_card_name(
    title: str, full_text: str, norm_text: str, catalog_names: list[str] | None = None
) -> str | None:
    """Tente d'isoler le nom potentiel de la carte sans inventer."""
    for official_name in catalog_names or []:
        if re.search(rf"\b{re.escape(_normalize_text(official_name))}\b", norm_text):
            return official_name
    clean_title = re.sub(r"^\s*(?:carte\s+)?pok[ée]mon\s+", "", title, flags=re.IGNORECASE).strip()

    # Si tiret séparateur (ex: "Dracaufeu - Set de base" ou "Pikachu - Évolutions")
    if "-" in clean_title:
        candidate = clean_title.split("-")[0].strip()
        # Retirer numéros et variantes du début
        candidate = re.sub(r"\b\d{1,3}/\d{1,3}\b", "", candidate).strip()
        if (
            candidate
            and len(candidate) >= 3
            and not candidate.isdigit()
            and _normalize_text(candidate.split()[0]) not in _GENERIC_HEAD_WORDS
        ):
            return candidate

    # Vérifier les noms de Pokémon très connus directement
    famous_pokemon = [
        "Dracaufeu", "Pikachu", "Tortank", "Florizarre", "Mewtwo", "Mew",
        "Evoli", "Évoli", "Noctali", "Mentali", "Voltali", "Pyroli", "Aquali",
        "Nymphali", "Phyllali", "Givrali", "Rayquaza", "Lugia", "Ho-Oh",
        "Gengar", "Ectoplasma", "Dracolosse", "Galvagon", "Lucario", "Roucarnage",
        "Salameche", "Salamèche", "Reptincel", "Carapuce", "Carabaffe",
        "Bulbizarre", "Herbizarre", "Groudon", "Kyogre", "Tyranocif", "Léviator",
        "Alakazam", "Ronflex", "Gardevoir", "Carchacrok", "Dialga", "Palkia",
        "Giratina", "Arceus", "Darkrai", "Mimiqui", "Miraidon", "Koraidon",
        "Sulfura", "Electhor", "Artikodin", "Suicune", "Entei", "Raikou",
        "Deoxys", "Celebi", "Jirachi", "Latios", "Latias", "Zacian", "Zamazenta",
    ]
    for pk in famous_pokemon:
        norm_pk = _normalize_text(pk)
        if re.search(rf"\b{re.escape(norm_pk)}\b", norm_text):
            # Conserver suffixe ex/VMAX/V/GX si présent juste après
            match_suffix = re.search(
                rf"\b{re.escape(norm_pk)}\s+(vmax|vstar|ex|v|gx)\b", norm_text
            )
            if match_suffix:
                return f"{pk} {match_suffix.group(1).upper()}"
            return pk

    # Nettoyage des qualificatifs parasites fréquents en tête d'annonce
    cleaned_start = re.sub(
        r"^(?:superbe|magnifique|rare|tr[èe]s\s+rare|ancienne?|authentique|officielle?|ultra\s+rare|vintage|originale?|vends?|vente|belle|véritable|veritable)\s+",
        "",
        clean_title,
        flags=re.IGNORECASE,
    ).strip()

    # Sinon si le titre nettoyé commence par un mot pertinent (hors mots génériques d'annonce)
    words = cleaned_start.split()
    if (
        words
        and len(words[0]) >= 3
        and words[0].isalpha()
        and _normalize_text(words[0]) not in _GENERIC_HEAD_WORDS
    ):
        first_few = " ".join(words[:2]) if len(words) > 1 and words[1].lower() in {"v", "vmax", "ex", "vstar", "gx"} else words[0]
        return first_few

    return None
