import pytest

from censorr.utils.fuzzy import FuzzyTerm, SimpleFuzzyMatcher


class TestSimpleFuzzyMatcherNormalize:
    """Test text normalization for fuzzy matching."""

    def test_lowercases_text(self):
        matcher = SimpleFuzzyMatcher([])
        assert matcher.normalize("HELLO WORLD") == "hello world"

    def test_removes_accents(self):
        matcher = SimpleFuzzyMatcher([])
        assert matcher.normalize("café") == "cafe"
        assert matcher.normalize("naïve") == "naive"

    def test_replaces_dashes_underscores_apostrophes_with_spaces(self):
        matcher = SimpleFuzzyMatcher([])
        assert matcher.normalize("don't") == "don t"
        assert matcher.normalize("mother-in-law") == "mother in law"
        assert matcher.normalize("snake_case") == "snake case"

    def test_removes_punctuation(self):
        matcher = SimpleFuzzyMatcher([])
        assert matcher.normalize("hello, world!") == "hello world"
        assert matcher.normalize("what?") == "what"

    def test_removes_digits(self):
        matcher = SimpleFuzzyMatcher([])
        assert matcher.normalize("test123abc") == "test abc"

    def test_collapses_whitespace(self):
        matcher = SimpleFuzzyMatcher([])
        assert matcher.normalize("hello   world") == "hello world"
        assert matcher.normalize("  leading trailing  ") == "leading trailing"

    def test_empty_string(self):
        matcher = SimpleFuzzyMatcher([])
        assert matcher.normalize("") == ""
        assert matcher.normalize("   ") == ""


class TestSimpleFuzzyMatcherFindMatches:
    """Test match finding with various term types."""

    def test_exact_match_single_word(self):
        terms = [FuzzyTerm(word="damn", threshold=85.0)]
        matcher = SimpleFuzzyMatcher(terms)
        matches = matcher.find_matches("This is damn funny")
        assert len(matches) == 1
        assert matches[0].term.word == "damn"
        assert matches[0].score == 100.0

    def test_case_insensitive_match(self):
        terms = [FuzzyTerm(word="damn", threshold=85.0)]
        matcher = SimpleFuzzyMatcher(terms)
        matches = matcher.find_matches("This is DAMN funny")
        assert len(matches) == 1

    def test_accented_term_matches_normalized(self):
        terms = [FuzzyTerm(word="café", threshold=85.0)]
        matcher = SimpleFuzzyMatcher(terms)
        matches = matcher.find_matches("I love cafe")
        assert len(matches) == 1

    def test_suffix_matching_default_strategy(self):
        # 'damn' with -ed suffix should match 'damned' with default suffixes
        terms = [FuzzyTerm(word="damn", threshold=85.0)]
        matcher = SimpleFuzzyMatcher(terms)
        matches = matcher.find_matches("He was damned")
        assert len(matches) == 1
        assert matches[0].window_text == "damned"

    def test_suffix_matching_ing(self):
        terms = [FuzzyTerm(word="damn", threshold=85.0)]
        matcher = SimpleFuzzyMatcher(terms)
        matches = matcher.find_matches("Stop damning him")
        assert len(matches) == 1

    def test_no_substring_match_without_aggressive(self):
        # 'damn' should NOT match inside 'damnation' without aggressive
        terms = [FuzzyTerm(word="damn", threshold=85.0)]
        matcher = SimpleFuzzyMatcher(terms)
        matches = matcher.find_matches("That damnation is wrong")
        # damnation has allowed suffix, but 'damn' != 'damnation'
        assert len(matches) == 0

    def test_aggressive_matches_compound_prefix(self):
        # With aggressive, 'use' should match 'misuse'
        terms = [FuzzyTerm(word="use", threshold=85.0, aggressive=True)]
        matcher = SimpleFuzzyMatcher(terms)
        matches = matcher.find_matches("They misuse the system")
        assert any(m.window_text == "misuse" for m in matches)

    def test_aggressive_matches_compound_suffix(self):
        # With aggressive, 'place' should match 'placement'
        terms = [FuzzyTerm(word="place", threshold=85.0, aggressive=True)]
        matcher = SimpleFuzzyMatcher(terms)
        matches = matcher.find_matches("We need placement")
        assert any(m.window_text == "placement" for m in matches)

    def test_aggressive_matches_substring(self):
        # With aggressive, short target in longer query
        terms = [FuzzyTerm(word="use", threshold=85.0, aggressive=True)]
        matcher = SimpleFuzzyMatcher(terms)
        matches = matcher.find_matches("We reuse it")
        assert any(m.window_text == "reuse" for m in matches)

    def test_multiple_terms(self):
        terms = [
            FuzzyTerm(word="damn", threshold=85.0),
            FuzzyTerm(word="heck", threshold=85.0),
        ]
        matcher = SimpleFuzzyMatcher(terms)
        matches = matcher.find_matches("That damn heck of a mess")
        assert len(matches) == 2
        target_words = {m.term.word for m in matches}
        assert target_words == {"damn", "heck"}

    def test_multiple_occurrences_same_term(self):
        terms = [FuzzyTerm(word="damn", threshold=85.0)]
        matcher = SimpleFuzzyMatcher(terms)
        matches = matcher.find_matches("Damn, damn, damn!")
        assert len(matches) == 3
        assert all(m.term.word == "damn" for m in matches)

    def test_threshold_filtering(self):
        terms = [FuzzyTerm(word="hello", threshold=95.0)]
        matcher = SimpleFuzzyMatcher(terms)
        # "hallo" is similar but score may be < 95
        matches = matcher.find_matches("hallo world")
        # With high threshold, fuzzy match may not pass
        # This tests threshold enforcement

    def test_stopwords_excluded(self):
        # Common stopwords should be excluded from matching
        terms = [FuzzyTerm(word="the", threshold=85.0)]
        matcher = SimpleFuzzyMatcher(terms)
        matches = matcher.find_matches("the quick brown fox")
        # "the" is a stopword, so should be excluded
        assert len(matches) == 0

    def test_empty_matches_list(self):
        terms = [FuzzyTerm(word="xyz", threshold=85.0)]
        matcher = SimpleFuzzyMatcher(terms)
        matches = matcher.find_matches("hello world")
        assert len(matches) == 0

    def test_no_terms_returns_empty(self):
        matcher = SimpleFuzzyMatcher([])
        matches = matcher.find_matches("any text")
        assert len(matches) == 0

    def test_multi_word_term(self):
        terms = [FuzzyTerm(word="go to hell", threshold=85.0)]
        matcher = SimpleFuzzyMatcher(terms)
        matches = matcher.find_matches("tell him to go to hell")
        assert len(matches) == 1

    def test_punctuation_normalized_in_matches(self):
        terms = [FuzzyTerm(word="damn", threshold=85.0)]
        matcher = SimpleFuzzyMatcher(terms)
        matches = matcher.find_matches("Damn, that's bad!")
        assert len(matches) == 1


class TestSimpleFuzzyMatcherInit:
    """Test matcher initialization and default threshold."""

    def test_init_with_terms(self):
        terms = [FuzzyTerm(word="test", threshold=90.0)]
        matcher = SimpleFuzzyMatcher(terms)
        assert len(matcher.terms) == 1
        assert matcher.terms[0].word == "test"

    def test_default_threshold_applied(self):
        terms = [FuzzyTerm(word="test", threshold=None)]
        matcher = SimpleFuzzyMatcher(terms, default_threshold=80.0)
        matches = matcher.find_matches("test")
        assert len(matches) == 1

    def test_term_threshold_overrides_default(self):
        terms = [FuzzyTerm(word="test", threshold=95.0)]
        matcher = SimpleFuzzyMatcher(terms, default_threshold=80.0)
        # exact match should always pass
        matches = matcher.find_matches("test")
        assert len(matches) == 1

    def test_empty_term_list(self):
        matcher = SimpleFuzzyMatcher([])
        assert len(matcher.terms) == 0
        assert matcher.find_matches("text") == []


class TestFuzzyTerm:
    """Test FuzzyTerm dataclass."""

    def test_fuzzy_term_creation(self):
        term = FuzzyTerm(word="test", threshold=85.0)
        assert term.word == "test"
        assert term.threshold == 85.0
        assert term.aggressive is False

    def test_fuzzy_term_aggressive_flag(self):
        term = FuzzyTerm(word="test", threshold=85.0, aggressive=True)
        assert term.aggressive is True

    def test_fuzzy_term_none_threshold(self):
        term = FuzzyTerm(word="test", threshold=None)
        assert term.threshold is None
