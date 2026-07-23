import re
import unicodedata
from typing import NamedTuple

from pydantic import BaseModel
from rapidfuzz import fuzz

from censorr.detect.wordlist import WordList

# Runs of Unicode letters. Punctuation, digits, underscores, hyphens and
# apostrophes are all token separators (matches v1 semantics: "fuckin'" ->
# "fuckin", "well-being" -> "well" + "being").
_TOKEN_RE = re.compile(r"[^\W\d_]+", re.UNICODE)

# Character elongation: runs of 3+ identical letters collapse to one so
# drawn-out spellings ("fuuuck", "shiiit") match. English words essentially
# never contain 3+ identical consecutive letters, so ordinary doubles ("pass",
# "cool") are untouched -- only runs of length >= 3 are affected.
_ELONGATION_RE = re.compile(r"(.)\1{2,}")

_ALLOWED_SUFFIXES = {"", "s", "ed", "er", "ing", "in"}
_AGGRESSIVE_SUFFIXES = {
    "", "s", "ed", "er", "ing", "in", "ly", "ness", "able", "ible",
    "ful", "less", "ward", "wise", "like", "ish", "ment", "tion", "sion",
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


class Match(BaseModel):
    word: str
    span: tuple[int, int]
    score: float
    replacement: str | None = None


class _Token(NamedTuple):
    normalized: str
    start: int
    end: int


def _normalize_word(word: str) -> str:
    word = word.lower()
    word = unicodedata.normalize("NFKD", word)
    word = "".join(ch for ch in word if not unicodedata.combining(ch))
    return _ELONGATION_RE.sub(r"\1", word)


def _tokenize(text: str) -> list[_Token]:
    return [
        _Token(normalized=_normalize_word(m.group(0)), start=m.start(), end=m.end())
        for m in _TOKEN_RE.finditer(text)
    ]


class Matcher:
    """Fuzzy profanity matcher (rapidfuzz), ported from v1's window-based
    FuzzyMatcher semantics: per-word thresholds with a length-based minimum,
    morphology-aware single-word scoring with an aggressive variant mode,
    and multi-word phrase matching via a straight fuzzy ratio.
    """

    def __init__(self, wordlist: WordList, *, similarity_threshold: float = 85.0) -> None:
        if not 0 <= similarity_threshold <= 100:
            raise ValueError("similarity_threshold must be between 0 and 100")
        self._words = wordlist.words
        self._allowlist = {_normalize_word(w) for w in wordlist.allowlist}
        self._thresholds: dict[str, float] = {}
        self._aggressive: set[str] = set()
        for word in self._words:
            key = _normalize_word(word.word)
            self._thresholds[key] = word.effective_threshold(similarity_threshold)
            if word.aggressive:
                self._aggressive.add(key)

    def find_matches(self, text: str) -> list[Match]:
        tokens = _tokenize(text)
        matches: list[Match] = []
        for word in self._words:
            target_tokens = [_normalize_word(t) for t in word.word.split()]
            n = len(target_tokens)
            if n == 0 or n > len(tokens):
                continue
            normalized_target = " ".join(target_tokens)
            threshold = self._thresholds[_normalize_word(word.word)]
            for i in range(len(tokens) - n + 1):
                window = tokens[i : i + n]
                window_text = " ".join(t.normalized for t in window)
                if window_text in _STOPWORDS or window_text in self._allowlist:
                    continue
                score = self._score(window_text, normalized_target, n)
                if score >= threshold:
                    matches.append(
                        Match(
                            word=word.word,
                            span=(window[0].start, window[-1].end),
                            score=score,
                            replacement=word.replacement,
                        )
                    )
        matches.sort(key=lambda m: m.span[0])
        return matches

    def _score(self, query: str, target: str, target_word_count: int) -> float:
        if min(len(query), len(target)) <= 3:
            return 100.0 if query == target else 0.0
        if target_word_count == 1:
            return self._morphology_score(query, target)
        return float(fuzz.ratio(query, target))

    def _morphology_score(self, query: str, target: str) -> float:
        if query == target:
            return 100.0

        aggressive = target in self._aggressive
        suffixes = _AGGRESSIVE_SUFFIXES if aggressive else _ALLOWED_SUFFIXES
        for suffix in suffixes:
            if suffix and (query == target + suffix or target == query + suffix):
                return 100.0

        if aggressive:
            for pattern in _COMPOUND_PATTERNS:
                if query == pattern + target or query == target + pattern:
                    return 100.0
            if len(target) >= 3 and target in query:
                return 100.0

        return float(fuzz.ratio(query, target))
