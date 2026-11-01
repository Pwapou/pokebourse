import re
import unicodedata
from app.identification.models import ExtractedFeatures

_LOT_PATTERNS = [
    re.compile(r"\b(?:lot|lots)\s+(?:de\s+)?(?:\d+\s+)?cartes?\b", re.IGNORECASE),
    re.compile(r"\b(?:collection|classeur|vrac|album)\s+(?:de\s+)?cartes?\b", re.IGNORECASE),
    re.compile(r"\b\d+\s*cartes?\s+pok[ée]mon\b", re.IGNORECASE),
    re.compile(r"\b(?:display|booster|coffret|tin|deck|pack|pokebox|tripack)\b", re.IGNORECASE),
    re.compile(r"\blot\s+pok[ée]mon\b", re.IGNORECASE),
    re.compile(r"\bcartes?\s+diverses\b", re.IGNORECASE),
]

_FRACTION_NUMBER_PATTERN = re.compile(
    r"\b(?P<num>[A-Za-z0-9]{1,4})\s*/\s*(?P<total>[0-9]{2,3})\b"
)

_PREFIX_NUMBER_PATTERN = re.compile(
    r"(?:#|n°|no\.?|num[ée]ro)\s*(?P<num>[A-Za-z0-9]{1,4})\b",
    re.IGNORECASE,
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

_GRADING_PATTERNS = [
    re.compile(r"\b(?P<company>PSA|PCA|BGS|CGC|SGS)\s*(?P<grade>10|[1-9](?:\.5)?)\b", re.IGNORECASE),
]

_LANGUAGE_PATTERNS = [
    (re.compile(r"\b(?:vf|francais|français|french|fr)\b", re.IGNORECASE), "fr"),
    (re.compile(r"\b(?:vo|anglais|english|en|us)\b", re.IGNORECASE), "en"),
    (re.compile(r"\b(?:jap|japonais|japanese|jp)\b", re.IGNORECASE), "ja"),
]

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
    (re.compile(r"\b(?:near mint|nm|tres bon etat|très bon état)\b", re.IGNORECASE), "Near Mint"),
    (re.compile(r"\b(?:gem mint|mint|neuf)\b", re.IGNORECASE), "Neuf"),
    (re.compile(r"\b(?:excellent|ex|bon etat|bon état)\b", re.IGNORECASE), "Excellent"),
    (re.compile(r"\b(?:played|etat moyen|état moyen|abime|abîmé)\b", re.IGNORECASE), "Played"),
]


def _normalize_text(text: str) -> str:
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(stripped.casefold().split())


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

    # 1. Détection de lot
    is_lot = False
    lot_reason = None
    for pattern in _LOT_PATTERNS:
        match = pattern.search(full_text)
        if match:
            is_lot = True
            lot_reason = f"Mention explicite de lot ou produit scellé : « {match.group(0)} »"
            break

    # 2. Numéro de carte (fraction en priorité, sinon numéro simple)
    card_number = None
    local_id = None
    set_card_count = None

    frac_match = _FRACTION_NUMBER_PATTERN.search(full_text)
    if frac_match:
        local_id = frac_match.group("num")
        set_card_count = frac_match.group("total")
        card_number = f"{local_id}/{set_card_count}"
    else:
        prefix_match = _PREFIX_NUMBER_PATTERN.search(full_text)
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
            if key in norm_text:
                set_name = official_name
                break

    # 4. Gradation
    grading_company = None
    grade = None
    for pattern in _GRADING_PATTERNS:
        match = pattern.search(full_text)
        if match:
            grading_company = match.group("company").upper()
            grade = match.group("grade")
            break

    # 5. Langue
    language = None
    for pattern, lang_code in _LANGUAGE_PATTERNS:
        if pattern.search(full_text):
            language = lang_code
            break

    # 6. Variante
    variant = None
    for pattern, var_name in _VARIANT_PATTERNS:
        if pattern.search(full_text):
            variant = var_name
            break

    # 7. État
    condition = None
    for pattern, cond_name in _CONDITION_PATTERNS:
        if pattern.search(full_text):
            condition = cond_name
            break

    # 8. Extraction du nom de carte potentiel
    extracted_name = _extract_card_name(title, full_text, norm_text, catalog_names)

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
        if candidate and len(candidate) >= 3 and not candidate.isdigit():
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

    # Sinon si le titre nettoyé commence par un mot pertinent
    words = cleaned_start.split()
    if words and len(words[0]) >= 3 and words[0].isalpha():
        first_few = " ".join(words[:2]) if len(words) > 1 and words[1].lower() in {"v", "vmax", "ex", "vstar", "gx"} else words[0]
        return first_few

    return None
