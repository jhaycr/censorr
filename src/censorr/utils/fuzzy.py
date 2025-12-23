import re
import unicodedata
from dataclasses import dataclass
from typing import List, Sequence

from rapidfuzz import fuzz

__all__ = ["FuzzyTerm", "MatchResult", "SimpleFuzzyMatcher"]

_ALLOWED_SUFFIXES = {"", "s", "ed", "er", "ing", "in"}
_AGGRESSIVE_SUFFIXES = _ALLOWED_SUFFIXES | {
    "ly", "ness", "able", "ible", "ful", "less", "ward", "wise",
    "like", "ish", "ment", "tion", "sion",
}
_COMPOUND_PATTERNS = {
    "un", "re", "pre", "mis", "dis", "over", "under", "out", "up", "down",
    "back", "fore", "anti", "pro", "semi", "multi", "non", "sub", "super",
    "inter", "intra", "extra", "ultra", "mega", "mini", "micro", "macro",
}
_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "else",
    "of", "to", "in", "on", "for", "by", "with", "at", "from",
    "as", "is", "it", "its", "be", "are", "was", "were", "am",
    "he", "she", "they", "we", "you", "i", "me", "him", "her",
    "them", "us", "my", "your", "his", "their", "our",
}


@dataclass
class FuzzyTerm:
    word: str
    threshold: float
    aggressive: bool = False


@dataclass
class MatchResult:
    term: FuzzyTerm
    window_text: str
    score: float


class SimpleFuzzyMatcher:
    """Minimal fuzzy matcher for generic term detection using RapidFuzz."""

    def __init__(self, terms: Sequence[FuzzyTerm], default_threshold: float = 85.0):
        self.terms = list(terms)
        self.default_threshold = default_threshold

    def normalize(self, text: str) -> str:
        if not text:
            return ""
        text = text.lower()
        text = unicodedata.normalize("NFKD", text)
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        text = re.sub(r"[-_']", " ", text)
        text = re.sub(r"[^\w\s]", " ", text)
        text = re.sub(r"\d+", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _score_single_word(self, query: str, target: str, aggressive: bool) -> float:
        if query == target:
            return 100.0

        suffixes = _AGGRESSIVE_SUFFIXES if aggressive else _ALLOWED_SUFFIXES
        for suffix in suffixes:
            if suffix and (query == target + suffix or target == query + suffix):
                return 100.0

        if aggressive and len(target) >= 3:
            if target in query:
                return 100.0
            for pattern in _COMPOUND_PATTERNS:
                if query == pattern + target or query == target + pattern:
                    return 100.0

        score = float(fuzz.ratio(query, target))
        if (
            len(query) >= 3
            and len(target) >= 3
            and query[0] != target[0]
            and target not in query
            and query not in target
        ):
            score = max(0.0, score - 25.0)

        return score

    def _score_window(self, window_text: str, target: str, aggressive: bool) -> float:
        target_words = target.split()
        window_words = window_text.split()

        if not target_words or not window_words:
            return 0.0

        if len(target_words) == 1 and len(window_words) == 1:
            return self._score_single_word(window_text, target, aggressive)

        return float(fuzz.ratio(window_text, target))

    def find_matches(self, text: str) -> List[MatchResult]:
        if not self.terms:
            return []

        normalized = self.normalize(text)
        words = normalized.split()
        matches: List[MatchResult] = []

        for term in self.terms:
            target = self.normalize(term.word)
            if not target:
                continue

            target_word_count = len(target.split())
            threshold = term.threshold if term.threshold is not None else self.default_threshold

            for i in range(len(words) - target_word_count + 1):
                window_words = words[i : i + target_word_count]
                window_text = " ".join(window_words)

                if window_text in _STOPWORDS:
                    continue

                score = self._score_window(window_text, target, term.aggressive)
                if score >= threshold:
                    matches.append(
                        MatchResult(term=term, window_text=window_text, score=score)
                    )

        return matches
