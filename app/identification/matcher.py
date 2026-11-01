import logging
import unicodedata

from app.identification.detector import extract_features
from app.identification.models import (
    CandidateMatch,
    ExtractedFeatures,
    IdentificationResult,
)
from app.tcgdex.cache import TcgdexCache
from app.tcgdex.models import ReferenceCardRecord

logger = logging.getLogger(__name__)


def _norm(text: str | None) -> str:
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(stripped.casefold().split())


class CardMatcher:
    """Moteur d'identification et de réconciliation des annonces avec le catalogue TCGdex."""

    def __init__(self, cache: TcgdexCache) -> None:
        self.cache = cache

    def identify(
        self,
        title: str,
        description: str | None = None,
        *,
        raw_data: dict | None = None,
    ) -> IdentificationResult:
        # S'assurer que le cache a au moins les données de seed
        self.cache.seed_initial_if_empty()

        # Extraire la description si présente dans raw_data
        desc = description
        if not desc and raw_data:
            desc = raw_data.get("description") or raw_data.get("body") or ""

        features = extract_features(title, desc)
        missing_fields: list[str] = []
        uncertain_fields: list[str] = []

        if not features.name:
            missing_fields.append("nom")
        if not features.card_number:
            missing_fields.append("numéro")
        if not features.set_name:
            missing_fields.append("extension")
        if not features.condition:
            uncertain_fields.append("état")

        # Règle 1 : Cas des lots
        if features.is_lot:
            return IdentificationResult(
                status="lot",
                confidence=95,
                reason=features.lot_reason or "Annonce identifiée comme un lot ou produit scellé.",
                features=features,
                matched_card=None,
                candidates=[],
                missing_fields=["carte_unitaire"],
                uncertain_fields=uncertain_fields,
            )

        # Règle 2 : Pas d'informations suffisantes pour chercher
        if not features.name and not features.local_id:
            return IdentificationResult(
                status="unidentified",
                confidence=0,
                reason="Titre et description insuffisants : aucun nom ni numéro de carte explicite.",
                features=features,
                matched_card=None,
                candidates=[],
                missing_fields=missing_fields,
                uncertain_fields=uncertain_fields,
            )

        # Règle 3 : Recherche des candidats dans le catalogue de référence
        candidates = self._find_and_score_candidates(features)

        if not candidates:
            return IdentificationResult(
                status="unidentified",
                confidence=0,
                reason=(
                    f"Aucune carte trouvée dans le catalogue de référence pour "
                    f"« {features.name or ''} » ({features.card_number or 'sans numéro'})."
                ),
                features=features,
                matched_card=None,
                candidates=[],
                missing_fields=missing_fields,
                uncertain_fields=uncertain_fields,
            )

        top_score = candidates[0].confidence
        top_matches = [c for c in candidates if c.confidence == top_score]

        # Règle 4 : Ambiguïté (plusieurs cartes plausibles sans discriminant fort)
        if len(top_matches) > 1 and top_score < 90:
            uncertain_fields.append("extension_ou_variante")
            names_sets = ", ".join(f"« {c.name} » ({c.set_name})" for c in top_matches[:3])
            return IdentificationResult(
                status="ambiguous",
                confidence=50,
                reason=f"Ambiguïté : plusieurs cartes possibles ({names_sets}). Marqué à vérifier.",
                features=features,
                matched_card=None,
                candidates=candidates[:5],
                missing_fields=missing_fields,
                uncertain_fields=uncertain_fields,
            )

        best_match = candidates[0]
        # Seuil d'identification certaine (>= 80)
        if best_match.confidence >= 80:
            record = self.cache.get_card_by_id(best_match.card_id)
            return IdentificationResult(
                status="identified",
                confidence=best_match.confidence,
                reason=best_match.match_reason,
                features=features,
                matched_card=record,
                candidates=candidates[:5],
                missing_fields=missing_fields,
                uncertain_fields=uncertain_fields,
            )

        # Score modéré (ex: nom seul sans numéro ni set) -> ambigu à vérifier
        uncertain_fields.append("confirmation_numéro")
        return IdentificationResult(
            status="ambiguous",
            confidence=best_match.confidence,
            reason=(
                f"Correspondance partielle avec « {best_match.name} » ({best_match.set_name}). "
                f"Numéro ou extension incertains : marqué à vérifier."
            ),
            features=features,
            matched_card=None,
            candidates=candidates[:5],
            missing_fields=missing_fields,
            uncertain_fields=uncertain_fields,
        )

    def _find_and_score_candidates(
        self, features: ExtractedFeatures
    ) -> list[CandidateMatch]:
        raw_candidates: list[ReferenceCardRecord] = []

        # 1. Recherche ciblée avec nom et numéro
        if features.name and features.local_id:
            raw_candidates = self.cache.find_cards(
                name=features.name,
                local_id=features.local_id,
                set_query=features.set_name,
            )
            if not raw_candidates and features.set_name:
                # Réessayer sans restreindre le set
                raw_candidates = self.cache.find_cards(
                    name=features.name,
                    local_id=features.local_id,
                )

        # 2. Si pas trouvé, chercher par numéro seul si set connu
        if not raw_candidates and features.local_id and features.set_name:
            raw_candidates = self.cache.find_cards(
                local_id=features.local_id,
                set_query=features.set_name,
            )

        # 3. Si toujours rien, chercher par nom seul
        if not raw_candidates and features.name:
            raw_candidates = self.cache.find_cards(
                name=features.name,
                set_query=features.set_name,
                limit=20,
            )

        # 4. Évaluation et attribution des scores de confiance
        scored: list[CandidateMatch] = []
        for card in raw_candidates:
            score = 0
            reasons: list[str] = []

            # Nom
            if features.name and _norm(features.name) in _norm(card.name):
                if _norm(features.name) == _norm(card.name):
                    score += 45
                    reasons.append("nom exact")
                else:
                    score += 35
                    reasons.append("nom partiel")

            # Numéro local
            if features.local_id:
                if str(card.local_id).lstrip("0") == str(features.local_id).lstrip("0"):
                    score += 40
                    reasons.append(f"numéro {card.local_id} exact")

            # Extension
            if features.set_name:
                if _norm(features.set_name) in _norm(card.set_name):
                    score += 20
                    reasons.append(f"extension « {card.set_name} »")

            # Variante
            if features.variant:
                if card.rarity and _norm(features.variant) in _norm(card.rarity):
                    score += 10
                    reasons.append(f"rareté/variante « {features.variant} »")

            if score > 0:
                scored.append(
                    CandidateMatch(
                        card_id=card.id,
                        tcgdex_id=card.tcgdex_id,
                        name=card.name,
                        set_name=card.set_name,
                        local_id=card.local_id,
                        confidence=min(score, 100),
                        match_reason=" ; ".join(reasons),
                    )
                )

        scored.sort(key=lambda c: c.confidence, reverse=True)
        return scored
