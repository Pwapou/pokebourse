"""Récupération et décision automatique locale, sans accès réseau."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from app.identification.evidence import ListingEvidence, build_evidence
from app.identification.lexical import RETRIEVAL_VERSION, NameSuggestion, name_index
from app.identification.models import CandidateMatch, ExtractedFeatures, IdentificationResult
from app.identification.normalization import canonical_local_id, normalize_text

if TYPE_CHECKING:
    from app.tcgdex.cache import TcgdexCache


_PROMO_SERIES = {
    "SM": "soleil et lune",
    "SWSH": "epee et bouclier",
    "XY": "xy",
    "BW": "noir et blanc",
    "SVP": "ecarlate et violet",
}


class CardMatcher:
    """Propose des candidats lexicaux et garde les corrections de nom à vérifier."""

    strategy_version = RETRIEVAL_VERSION

    def __init__(self, cache: TcgdexCache, *, seed_if_empty: bool = True, repair_index: bool = True) -> None:
        self.cache = cache
        self.seed_if_empty = seed_if_empty
        self.repair_index = repair_index
        if seed_if_empty:
            self.cache.seed_initial_if_empty()
        self._refresh_index()

    def _database_state(self) -> tuple[int, int]:
        """Détecte les écritures locales et celles d'une autre connexion."""
        return self.cache.connection.total_changes, self.cache.connection.execute("PRAGMA data_version").fetchone()[0]

    def _refresh_index(self) -> None:
        """Indexe les noms et numéros complets avant toute limite sur les candidats."""
        rows = self.cache.connection.execute(
            "SELECT id, name, set_name, local_id, normalized_name, normalized_set_name, canonical_local_id "
            "FROM pokemon_reference_cards"
        ).fetchall()
        self._name_ids: dict[str, set[int]] = defaultdict(set)
        self._number_ids: dict[str, set[int]] = defaultdict(set)
        for row in rows:
            values = (normalize_text(row["name"]), normalize_text(row["set_name"]), canonical_local_id(row["local_id"]))
            self._name_ids[values[0]].add(row["id"])
            self._number_ids[values[2]].add(row["id"])
            if self.repair_index and values != (row["normalized_name"], row["normalized_set_name"], row["canonical_local_id"]):
                self.cache.connection.execute(
                    "UPDATE pokemon_reference_cards SET normalized_name=?, normalized_set_name=?, canonical_local_id=? WHERE id=?",
                    (*values, row["id"]),
                )
        self._names = sorted({row["name"] for row in rows}, key=lambda value: (-len(value), value))
        self._sets = sorted({row["set_name"] for row in rows}, key=lambda value: (-len(value), value))
        self._set_counts = {row["id"]: {count for count in (row["card_count_official"], row["card_count_total"]) if count is not None}
                            for row in self.cache.connection.execute("SELECT id, card_count_official, card_count_total FROM pokemon_reference_sets")}
        self._lexical = name_index(tuple(self._names))
        self._state = self._database_state()

    def identify(self, title: str, description: str | None = None, *, raw_data: dict | None = None, allow_lot_override: bool = False) -> IdentificationResult:
        """Sépare recherche et acceptation ; un nom approché ne suffit pas à accepter."""
        raw_data = raw_data or {}
        desc = description if description is not None else raw_data.get("description", raw_data.get("body"))
        return self.identify_evidence(build_evidence(title, desc if isinstance(desc, str) else None, attributes=raw_data), allow_lot_override=allow_lot_override)

    def identify_evidence(self, evidence: ListingEvidence, *, allow_lot_override: bool = False) -> IdentificationResult:
        """Décide depuis les observations communes ; aucun accès réseau n'est effectué."""
        if self.seed_if_empty:
            self.cache.seed_initial_if_empty()
        if self._state != self._database_state():
            self._refresh_index()
        from app.identification.decision import propose
        return propose(self, evidence, allow_lot_override=allow_lot_override)

    def _identify_features(self, features: ExtractedFeatures, retrieval_text: str, *, allow_lot_override: bool = False) -> IdentificationResult:
        """Classe puis accepte les indices déjà extraits, aux seuils historiques."""
        missing = [label for value, label in ((features.name, "nom"), (features.card_number, "numéro"), (features.set_name, "extension")) if not value]
        uncertain = [] if features.condition else ["état"]
        if features.is_lot and not allow_lot_override:
            return IdentificationResult("lot", 95, features.lot_reason or "Annonce identifiée comme un lot.", features, missing_fields=["carte_unitaire"], uncertain_fields=uncertain)
        if features.selection_reason:
            return IdentificationResult("ambiguous", 0, features.selection_reason, features, missing_fields=missing, uncertain_fields=uncertain + ["objet_vendu"])
        if len(features.languages) > 1:
            reason = f"Mentions de langues multiples ou contradictoires : {', '.join(features.languages)}. Langue de la carte à préciser."
            return IdentificationResult("ambiguous", 0, reason, features, missing_fields=missing, uncertain_fields=uncertain + ["langue"])
        # Une référence promotionnelle alphanumérique est complète en elle-même
        # (SM233, SWSH020…) : elle n'a pas besoin d'un dénominateur. Un simple
        # nombre isolé reste soumis à confirmation humaine.
        is_promo_number = bool(features.local_id and not features.local_id.isdigit())
        isolated_number = bool(features.local_id and features.set_card_count is None and not is_promo_number)
        if isolated_number:
            uncertain.append("numéro isolé, sans dénominateur")
        if features.language and features.language != "fr":
            return IdentificationResult("unidentified", 0, "Langue étrangère explicite : le référentiel français n'est pas substitué silencieusement.", features, missing_fields=missing, uncertain_fields=uncertain + ["langue"])
        candidates = self._find_and_score_candidates(features)
        # Le repli n'ajoute que des suggestions : les décisions exactes existantes restent prioritaires.
        if not candidates or candidates[0].confidence < 80:
            suggestions = self._lexical.search(retrieval_text)
            candidates = self._find_and_score_candidates(features, suggestions)
        if not candidates:
            reason = ("Preuves insuffisantes : aucun nom ni numéro explicite." if not features.name and not features.local_id
                      else f"Aucune référence locale trouvée pour « {features.name or ''} » ({features.card_number or 'sans numéro'}).")
            return IdentificationResult("unidentified", 0, reason, features, missing_fields=missing, uncertain_fields=uncertain)
        top = candidates[0].confidence
        ties = [candidate for candidate in candidates if candidate.confidence == top]
        if len(ties) > 1:
            labels = ", ".join(f"« {candidate.name} » ({candidate.set_name})" for candidate in ties[:3])
            tie_cap = 79 if isolated_number else 89
            return IdentificationResult("ambiguous", min(top, tie_cap), f"Ambiguïté : plusieurs cartes possibles ({labels}).", features, candidates=candidates[:50], missing_fields=missing, uncertain_fields=uncertain + ["extension_ou_variante"])
        best = candidates[0]
        if best.confidence >= 80 and best.name_match_kind != "fuzzy" and not best.contradictions and not isolated_number:
            return IdentificationResult("identified", best.confidence, best.match_reason, features, self.cache.get_card_by_id(best.card_id), candidates[:50], missing, uncertain)
        if best.name_match_kind == "fuzzy":
            reason = f"Nom approché : {best.match_reason}. Confirmation humaine requise."
            uncertain += ["orthographe_du_nom"]
        elif isolated_number and best.confidence >= 80 and not best.contradictions:
            reason = f"Numéro isolé sans dénominateur avec « {best.name} » ({best.set_name}) : {best.match_reason}. Vérification requise."
        else:
            reason = f"Correspondance partielle avec « {best.name} » ({best.set_name}) : {best.match_reason}. Vérification requise."
        confidence = min(best.confidence, 79) if isolated_number else best.confidence
        return IdentificationResult("ambiguous", confidence, reason, features, candidates=candidates[:50], missing_fields=missing, uncertain_fields=uncertain + ["confirmation_numéro"])

    def retrieve_candidates(self, features: ExtractedFeatures) -> list[CandidateMatch]:
        """Récupération publique et bornée pour les hypothèses OCR (T07).

        Réutilise le classement commun sans repli lexical ni écriture ; la décision
        d'acceptation reste à la décision commune et aucune identité effective n'est
        publiée par une branche OCR.
        """
        return self._find_and_score_candidates(features)

    def _find_and_score_candidates(self, features: ExtractedFeatures, suggestions: list[NameSuggestion] | None = None) -> list[CandidateMatch]:
        """Classe les preuves sans éliminer un numéro exact à cause d'un nom mal lu."""
        wanted = normalize_text(features.name)
        ids: set[int] = set()
        if wanted:
            for name, card_ids in self._name_ids.items():
                if wanted == name or wanted in name or name in wanted:
                    ids.update(card_ids)
        if features.set_name and not wanted and not features.local_id:
            ids.update(row["id"] for row in self.cache.connection.execute(
                "SELECT id FROM pokemon_reference_cards WHERE normalized_set_name=? LIMIT 200",
                (normalize_text(features.set_name),)))
        if features.local_id:
            ids.update(self._number_ids.get(canonical_local_id(features.local_id), ()))
        fuzzy = {normalize_text(suggestion.name): suggestion for suggestion in suggestions or []}
        for name in fuzzy:
            ids.update(self._name_ids.get(name, ()))
        scored: list[CandidateMatch] = []
        for card in self.cache.get_cards_by_ids(list(ids)):
            score = 0
            reasons: list[str] = []
            contradictions: list[str] = []
            actual = normalize_text(card.name)
            kind = "absent"
            if wanted and wanted == actual:
                score += 45
                kind = "exact"
                reasons.append("nom exact")
            elif wanted and (wanted in actual or actual in wanted):
                score += 30
                kind = "partial"
                reasons.append("nom partiel")
            elif actual in fuzzy:
                suggestion = fuzzy[actual]
                # Un suffixe de nom explicite n'est jamais corrigé vers une autre variante.
                suffix = wanted.split()[-1] if wanted else None
                if suffix in {"v", "vmax", "vstar", "ex", "gx"} and actual.split()[-1] != suffix:
                    continue
                score += max(10, 35 - suggestion.distance * 5)
                kind = "fuzzy"
                reasons.append(f"nom approché « {suggestion.observed} » → « {card.name} » ({suggestion.distance} modification(s))")
            elif wanted:
                # Le numéro reste une preuve autonome : un nom OCR faux est une
                # contradiction explicite, pas une raison de perdre le candidat.
                contradictions.append("name")
                reasons.append(f"nom contradictoire (« {features.name} » lu)")
            if features.local_id:
                if canonical_local_id(card.local_id) == canonical_local_id(features.local_id):
                    score += 40
                    reasons.append(f"numéro {card.local_id} exact")
                else:
                    contradictions.append("number")
                    reasons.append("numéro contradictoire")
            if features.set_card_count and self._set_counts.get(card.set_id) and int(features.set_card_count) not in self._set_counts[card.set_id]:
                contradictions.append("set_card_count")
                reasons.append("total de l'extension contradictoire")
            if features.set_name:
                expected_set, actual_set = normalize_text(features.set_name), normalize_text(card.set_name)
                promo_series = next(
                    (series for prefix, series in _PROMO_SERIES.items()
                     if card.local_id.upper().startswith(prefix) and expected_set == series),
                    None,
                )
                if expected_set == actual_set or expected_set in actual_set:
                    score += 20
                    reasons.append(f"extension « {card.set_name} »")
                elif promo_series:
                    score += 20
                    reasons.append(f"série cohérente avec « {card.set_name} »")
                else:
                    contradictions.append("set")
                    reasons.append("extension contradictoire")
            if features.variant and card.rarity and normalize_text(features.variant) in normalize_text(card.rarity):
                score += 5
                reasons.append(f"variante « {features.variant} »")
            if kind == "fuzzy":
                score = min(score, 79)
            if contradictions:
                score = min(score, 59)
            if score > 0:
                final_score = min(score, 100)
                level = "élevé" if final_score >= 80 else "moyen" if final_score >= 60 else "faible"
                scored.append(CandidateMatch(
                    card.id, card.tcgdex_id, card.name, card.set_name, card.local_id,
                    final_score, " ; ".join(reasons), kind, tuple(contradictions),
                    tuple(reasons), level,
                ))
        scored.sort(key=lambda candidate: (-candidate.confidence, candidate.name, candidate.set_name, candidate.tcgdex_id))
        return scored
