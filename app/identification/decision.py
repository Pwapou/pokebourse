"""Proposition pure commune : récupération, contradictions et acceptation séparées."""

from __future__ import annotations

import re
from dataclasses import fields, replace
from typing import TYPE_CHECKING

from app.identification.detector import extract_features
from app.identification.evidence import ListingEvidence, Observation
from app.identification.models import ExtractedFeatures, IdentificationResult
from app.identification.normalization import canonical_local_id, normalize_text

if TYPE_CHECKING:
    from app.identification.matcher import CardMatcher


def _features(matcher: CardMatcher, observation: Observation) -> ExtractedFeatures:
    """Extrait chaque observation sans convertir sa provenance en confirmation."""
    value = observation.value
    field = observation.field
    if field == "language":
        code = value.lower().strip()
        parsed = extract_features(f"langue : {value}")
        languages = parsed.languages or (code,)
        return ExtractedFeatures(language=languages[0] if len(languages) == 1 else None, languages=languages)
    if field == "card_number":
        match = re.fullmatch(r"\s*([A-Za-z0-9]{1,5})(?:\s*/\s*(\d{1,3}))?\s*", value)
        if match:
            return ExtractedFeatures(card_number=value.strip(), local_id=match[1], set_card_count=match[2])
    if field == "set_name":
        if normalize_text(value) in {"non identifiee", "inconnue", "inconnu"}:
            return ExtractedFeatures()
        extracted = extract_features(value, catalog_sets=matcher._sets)
        return ExtractedFeatures(set_name=extracted.set_name or value)
    if field in {"variant", "edition", "grading_company", "grade"}:
        if field == "edition":
            return ExtractedFeatures()
        return ExtractedFeatures(**{field: value})
    text = f"condition : {value}" if field == "condition" else value
    extracted = extract_features("" if field == "description" else text, text if field == "description" else None,
                                 catalog_names=matcher._names, catalog_sets=matcher._sets)
    if field == "condition":
        return ExtractedFeatures(condition=extracted.condition, condition_raw=value)
    return extracted


def _merge(primary: ExtractedFeatures, additional: list[ExtractedFeatures]) -> ExtractedFeatures:
    """Complète uniquement les absences ; les contradictions sont traitées à part."""
    values = {field.name: getattr(primary, field.name) for field in fields(primary)}
    for features in additional:
        for key in values:
            if not values[key] and getattr(features, key):
                values[key] = getattr(features, key)
    languages = tuple(sorted({language for features in [primary, *additional] for language in features.languages}))
    values.update(languages=languages, language=languages[0] if len(languages) == 1 else None)
    return ExtractedFeatures(**values)


def _names_agree(left: str, right: str) -> bool:
    """Une absence de suffixe est incomplète ; deux suffixes différents se contredisent."""
    left, right = normalize_text(left), normalize_text(right)
    suffixes = {"v", "vmax", "vstar", "ex", "gx"}
    if left.split()[-1] in suffixes and right.split()[-1] in suffixes:
        return left == right
    return left == right or left.startswith(right + " ") or right.startswith(left + " ")


def _conflicts(features: list[ExtractedFeatures]) -> tuple[str, ...]:
    """Détecte les désaccords d'identité explicites sans réparer les nombres."""
    conflicts = set()
    for key in ("name", "local_id", "set_name", "language", "set_card_count"):
        values = [getattr(item, key) for item in features if getattr(item, key)]
        for index, left in enumerate(values):
            for right in values[index + 1:]:
                agrees = (_names_agree(left, right) if key == "name" else
                          canonical_local_id(left) == canonical_local_id(right) if key in {"local_id", "set_card_count"} else
                          normalize_text(left) == normalize_text(right))
                if not agrees:
                    conflicts.add("number" if key == "local_id" else key)
    return tuple(sorted(conflicts))


def propose(matcher: CardMatcher, evidence: ListingEvidence, *, allow_lot_override: bool = False) -> IdentificationResult:
    """Produit le même résultat à observations égales, sans aucune écriture."""
    observations = [(item, _features(matcher, item)) for item in evidence.observations]
    trusted = [features for item, features in observations if item.source not in {"ocr", "prefill"}]
    indicative = [features for item, features in observations if item.source in {"ocr", "prefill"}]
    trusted_title = evidence.title if any(item.field == "title" and item.value == evidence.title
                                         and item.source not in {"ocr", "prefill"} for item, _ in observations) else ""
    trusted_description = evidence.description if any(item.field == "description" and item.value == evidence.description
                                                       and item.source not in {"ocr", "prefill"} for item, _ in observations) else None
    # Préserver les règles T02 sur le couple titre/description (une formulation
    # peut traverser leur frontière), sans perdre les observations séparées.
    textual = extract_features(trusted_title, trusted_description, catalog_names=matcher._names, catalog_sets=matcher._sets)
    base = _merge(textual, trusted)
    combined = _merge(base, indicative)
    # La recherche peut réunir les textes, mais toutes les observations gardent
    # leur origine et aucune de celles issues de l'OCR n'entre dans « trusted ».
    retrieval_text = " ".join(item.value for item, _ in observations)
    primary = matcher._identify_features(base, retrieval_text, allow_lot_override=allow_lot_override)
    result = primary if primary.status in {"identified", "lot"} else matcher._identify_features(combined, retrieval_text, allow_lot_override=allow_lot_override)
    conflicts = _conflicts([features for _, features in observations])
    diagnostics = {candidate.tcgdex_id: candidate for candidate in result.candidates if candidate.contradictions}
    admissible = [candidate for candidate in result.candidates if not candidate.contradictions]
    if conflicts and result.status != "lot":
        # Les références liées aux observations concurrentes restent consultables
        # dans le diagnostic, jamais parmi les suggestions admissibles.
        for features in [base, combined, *(features for _, features in observations)]:
            for candidate in matcher._find_and_score_candidates(features):
                diagnostics.setdefault(candidate.tcgdex_id, replace(candidate,
                    contradictions=tuple(sorted(set(candidate.contradictions) | set(conflicts))),
                    match_reason=candidate.match_reason + f" ; preuves contradictoires ({', '.join(conflicts)})"))
        reason = (f"Mentions de langues multiples ou contradictoires : {', '.join(combined.languages)}. Langue de la carte à préciser."
                  if conflicts == ("language",) else f"Les observations contredisent la carte proposée ({', '.join(conflicts)}) : vérification humaine requise.")
        result = replace(result, status="ambiguous", matched_card=None, confidence=min(result.confidence or 0, 79), reason=reason)
        admissible = []
        reason_code = "contradiction"
    elif result.status == "lot":
        reason_code = "lot"
    elif result.status == "identified" and primary.status == "identified":
        reason_code = "exact_match"
    elif len(combined.languages) > 1:
        reason_code = "contradiction"
    elif combined.selection_reason:
        reason_code = "object_uncertain"
    elif combined.language and combined.language != "fr":
        reason_code = "out_of_scope"
    elif result.status == "identified" and primary.status != "identified":
        result = replace(result, status="ambiguous", matched_card=None, confidence=min(result.confidence or 0, 79),
                         reason="Indices OCR ou préremplis : confirmation humaine requise avant de retenir une identité.")
        reason_code = "indicative_evidence"
    elif result.status == "identified":
        reason_code = "exact_match"
    elif diagnostics and not admissible:
        reason_code = "contradiction"
    elif len(admissible) > 1 and admissible[0].confidence == admissible[1].confidence:
        reason_code = "multiple_candidates"
    elif any(candidate.name_match_kind == "fuzzy" for candidate in admissible):
        reason_code = "fuzzy_name"
    elif admissible:
        reason_code = "insufficient_evidence"
    else:
        reason_code = "local_reference_missing" if combined.name or combined.local_id else "insufficient_evidence"
    if evidence.ocr_unavailable and result.status == "unidentified" and reason_code in {"insufficient_evidence", "local_reference_missing"}:
        reason_code = "service_unavailable"
        result = replace(result, reason="Analyse OCR indisponible ; preuves locales insuffisantes pour identifier la carte.")
    return replace(result, candidates=admissible[:50], diagnostic_candidates=sorted(diagnostics.values(), key=lambda item: (-item.confidence, item.tcgdex_id))[:50],
                   features=combined if result.status != "identified" else base,
                   observations=evidence.observations, evidence_conflicts=conflicts, reason_code=reason_code,
                   uncertain_fields=list(dict.fromkeys(result.uncertain_fields + (["contradiction_des_preuves"] if conflicts else []))))
