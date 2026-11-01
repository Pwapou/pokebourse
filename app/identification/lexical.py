"""Récupération lexicale locale et bornée, indépendante de la décision métier."""

from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
import re

from app.identification.normalization import normalize_text

RETRIEVAL_VERSION = "lexical-v1"
_SUFFIXES = {"v", "vmax", "vstar", "ex", "gx"}


@dataclass(frozen=True)
class NameSuggestion:
    """Une proximité orthographique est une suggestion, jamais une identité validée."""

    name: str
    observed: str
    distance: int
    similarity_bps: int


def bounded_edit_distance(left: str, right: str, budget: int) -> int:
    """Distance avec insertions, suppressions, substitutions et transpositions voisines.

    Seule la bande du budget est calculée. Une distance supérieure au budget
    retourne budget + 1, sans promettre une distance exacte hors de cette bande.
    """
    if left == right:
        return 0
    if abs(len(left) - len(right)) > budget:
        return budget + 1
    previous_previous: dict[int, int] = {}
    previous = {index: index for index in range(min(len(right), budget) + 1)}
    for i, left_character in enumerate(left, 1):
        current = {0: i} if i <= budget else {}
        for j in range(max(1, i - budget), min(len(right), i + budget) + 1):
            cost = int(left_character != right[j - 1])
            value = min(previous.get(j, budget + 1) + 1,
                        current.get(j - 1, budget + 1) + 1,
                        previous.get(j - 1, budget + 1) + cost)
            if i > 1 and j > 1 and left_character == right[j - 2] and left[i - 2] == right[j - 1]:
                value = min(value, previous_previous.get(j - 2, budget + 1) + 1)
            current[j] = min(value, budget + 1)
        previous_previous, previous = previous, current
    return previous.get(len(right), budget + 1)


def _trigrams(value: str) -> set[str]:
    """Indexe les caractères consécutifs sans changer les numéros ou les suffixes."""
    return {value[index:index + 3] for index in range(max(0, len(value) - 2))}


class LexicalNameIndex:
    """Index inversé des noms officiels, partagé entre annonces d'un même catalogue."""

    def __init__(self, names: tuple[str, ...]) -> None:
        self.names: dict[str, list[str]] = defaultdict(list)
        self.postings: dict[str, set[str]] = defaultdict(set)
        for name in names:
            normalized = normalize_text(name)
            self.names[normalized].append(name)
        self.word_lengths = sorted({len(name.split()) for name in self.names if len(name.split()) <= 5})
        for name in self.names:
            if len(name) >= 5:
                for gram in _trigrams(name):
                    self.postings[gram].add(name)

    def search(self, text: str, *, limit: int = 8) -> list[NameSuggestion]:
        """Cherche des fautes proches dans des fenêtres du texte, sans fuzzy sur noms courts.

        Au plus 256 mots, 512 fenêtres distinctes et 64 noms par fenêtre sont
        examinés. Ces limites rendent le coût prévisible ; elles ne garantissent
        pas un rappel exhaustif et ne changent pas les preuves originales.
        """
        words = normalize_text(text).split()[:256]
        queries = set()
        for size in self.word_lengths:
            for start in range(len(words) - size + 1):
                window = " ".join(words[start:start + size])
                if len(window) >= 5 and any(character.isalpha() for character in window):
                    queries.add(window)
        best: dict[str, NameSuggestion] = {}
        for query in sorted(queries, key=lambda value: (len(value), value))[:512]:
            overlaps: dict[str, int] = defaultdict(int)
            for gram in _trigrams(query):
                for name in self.postings.get(gram, ()):
                    if abs(len(name) - len(query)) <= 2:
                        overlaps[name] += 1
            for name in sorted(overlaps, key=lambda value: (-overlaps[value], abs(len(value) - len(query)), value))[:64]:
                if name == query:
                    continue  # Les correspondances exactes restent dans la voie stricte.
                if re.findall(r"\d+", name) != re.findall(r"\d+", query):
                    continue
                query_suffix = query.split()[-1] if query.split()[-1] in _SUFFIXES else None
                name_suffix = name.split()[-1] if name.split()[-1] in _SUFFIXES else None
                if query_suffix != name_suffix:
                    continue
                budget = 2 if max(len(query), len(name)) >= 9 else 1
                distance = bounded_edit_distance(query, name, budget)
                if distance > budget:
                    continue
                similarity = (max(len(query), len(name)) - distance) * 10_000 // max(len(query), len(name))
                for official_name in self.names[name]:
                    suggestion = NameSuggestion(official_name, query, distance, similarity)
                    existing = best.get(official_name)
                    if existing is None or (suggestion.similarity_bps, -distance, query) > (existing.similarity_bps, -existing.distance, existing.observed):
                        best[official_name] = suggestion
        return sorted(best.values(), key=lambda value: (-value.similarity_bps, value.distance, value.name, value.observed))[:max(0, limit)]


@lru_cache(maxsize=2)
def name_index(names: tuple[str, ...]) -> LexicalNameIndex:
    """Réutilise l'index pour un vocabulaire immuable, sans cache de données vendeur."""
    return LexicalNameIndex(names)
