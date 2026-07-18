"""Matcher spec ported from v1's tests/unit/test_fuzzy_matcher.py and
test_per_word_fuzzy.py (see ~/Code/Censorr2). Semantics only -- v2 uses
Word/WordList instead of ProfanityTerm, and find_matches() returns spans
into the original text instead of v1's whitespace-token MatchResult list.
"""

import pytest

from censorr.detect.matcher import Matcher
from censorr.detect.wordlist import Word, WordList


def make_matcher(
    words: list[Word], *, allowlist: list[str] | None = None, threshold: float = 85.0
) -> Matcher:
    return Matcher(WordList(words=words, allowlist=allowlist or []), similarity_threshold=threshold)


def matched_words(matcher: Matcher, text: str) -> set[str]:
    return {m.word for m in matcher.find_matches(text)}


def contains_profanity(matcher: Matcher, text: str) -> bool:
    return len(matcher.find_matches(text)) > 0


class TestInvalidThreshold:
    def test_negative_threshold_rejected(self) -> None:
        with pytest.raises(ValueError, match="between 0 and 100"):
            Matcher(WordList(), similarity_threshold=-1)

    def test_over_100_threshold_rejected(self) -> None:
        with pytest.raises(ValueError, match="between 0 and 100"):
            Matcher(WordList(), similarity_threshold=101)


class TestEmptyWordlist:
    def test_empty_wordlist_finds_nothing(self) -> None:
        matcher = make_matcher([])

        assert matcher.find_matches("anything at all") == []


class TestBasicMatching:
    def test_exact_word_matches(self) -> None:
        matcher = make_matcher([Word(word="damn")], threshold=75.0)

        matches = matcher.find_matches("This is damn good")

        assert len(matches) == 1
        assert matches[0].word == "damn"
        assert matches[0].score == 100.0
        text = "This is damn good"
        assert text[matches[0].span[0] : matches[0].span[1]] == "damn"

    def test_no_match_on_unrelated_text(self) -> None:
        matcher = make_matcher([Word(word="hello")], threshold=80.0)

        assert matcher.find_matches("completely different") == []

    def test_multiple_matches_in_text(self) -> None:
        matcher = make_matcher(
            [Word(word="damn"), Word(word="hell"), Word(word="shit", threshold=75.0)],
            threshold=75.0,
        )

        text = "This damn thing is going to hell, shit happens"
        found = matched_words(matcher, text)

        assert found == {"damn", "hell", "shit"}

    def test_stopwords_never_match(self) -> None:
        # A pathological single-letter target shouldn't ever fire on stopwords
        matcher = make_matcher([Word(word="a", threshold=0.0)], threshold=0.0)

        assert matcher.find_matches("a an the") == []


class TestLengthBasedMinimumThreshold:
    """A <=4 char word is never matchable below 95%, even with a lower global default."""

    def test_short_word_false_positive_rejected(self) -> None:
        matcher = make_matcher([Word(word="shit", threshold=95, aggressive=True)], threshold=85.0)

        assert not contains_profanity(matcher, "shirt")  # ~89% < 95%
        assert not contains_profanity(matcher, "sit")  # too short a target, exact-only
        assert not contains_profanity(matcher, "shift")  # ~89% < 95%

    def test_short_word_exact_and_morphology_matches(self) -> None:
        matcher = make_matcher([Word(word="shit", threshold=95, aggressive=True)], threshold=85.0)

        assert contains_profanity(matcher, "shit")
        assert contains_profanity(matcher, "shits")
        assert contains_profanity(matcher, "shitting")
        assert contains_profanity(matcher, "shitty")  # aggressive suffix


class TestPerWordThreshold:
    def test_lenient_and_strict_thresholds_respected(self) -> None:
        matcher = make_matcher(
            [Word(word="lenient", threshold=50), Word(word="strict", threshold=95)],
            threshold=85.0,
        )

        lenient_matches = matcher.find_matches("lienient behavior")  # typo, close match
        strict_matches = matcher.find_matches("strikt behavior")  # typo, close match

        assert len(lenient_matches) > 0
        assert len(strict_matches) == 0


class TestAggressiveVariantDetection:
    def test_aggressive_catches_morphological_and_compound_forms(self) -> None:
        matcher = make_matcher([Word(word="fuck", aggressive=True)], threshold=85.0)

        for query, expected_word in [
            ("unfuck", "fuck"),
            ("fuckup", "fuck"),
            ("refuck", "fuck"),
            ("fuckward", "fuck"),
            ("fuckable", "fuck"),
            ("unfuckingbelievable", "fuck"),
        ]:
            found = matched_words(matcher, query)
            assert expected_word in found, f"expected {query!r} to match {expected_word!r}"

    def test_default_mode_does_not_catch_compound_forms(self) -> None:
        matcher = make_matcher([Word(word="shit")], threshold=85.0)

        # Without aggressive mode, "shitable" isn't a real morphological
        # variant of "shit" and shouldn't be forced to a 100 score.
        assert matcher._morphology_score("shitable", "shit") < 100.0


@pytest.mark.parametrize(
    ("target_word", "false_positives"),
    [
        (
            "shit",
            [
                "shirt", "shirts", "shirted", "shirting",
                "sit", "sits", "sitting", "sat",
                "shift", "shifts", "shifted", "shifting",
                "shot", "shots", "shooting",
                "shut", "shuts", "shutting",
                "shy", "shyly", "shyness",
                "ship", "ships", "shipped", "shipping",
                "shop", "shops", "shopped", "shopping",
                "show", "shows", "showed", "showing",
                "short", "shorter", "shortest", "shortly",
            ],
        ),
        (
            "fuck",
            [
                "duck", "ducks", "ducking",
                "tuck", "tucks", "tucked", "tucking",
                "luck", "lucky", "luckily", "unlucky",
                "suck", "sucks", "sucked", "sucking",
                "buck", "bucks", "bucking",
                "muck", "mucks", "mucked", "mucking",
                "stuck", "sticking",
                "truck", "trucks", "trucking",
                "pluck", "plucks", "plucked", "plucking",
            ],
        ),
        (
            "dick",
            [
                "deck", "decks", "decked", "decking",
                "sick", "sicker", "sickest", "sickly",
                "pick", "picks", "picked", "picking",
                "kick", "kicks", "kicked", "kicking",
                "tick", "ticks", "ticked", "ticking",
                "thick", "thicker", "thickest",
                "quick", "quicker", "quickest", "quickly",
                "click", "clicks", "clicked", "clicking",
                "stick", "sticks", "sticked", "sticking",
                "brick", "bricks",
            ],
        ),
        (
            "cunt",
            [
                "cant", "cannot",
                "hunt", "hunts", "hunted", "hunting",
                "punt", "punts", "punted", "punting",
                "bunt", "bunts", "bunted", "bunting",
                "runt", "runts",
                "blunt", "blunts", "blunted", "blunting",
                "grunt", "grunts", "grunted", "grunting",
                "count", "counts", "counted", "counting",
                "mount", "mounts", "mounted", "mounting",
                "front", "fronts", "fronted", "fronting",
            ],
        ),
        (
            "bitch",
            [
                "batch", "batches", "batched", "batching",
                "catch", "catches", "caught", "catching",
                "patch", "patches", "patched", "patching",
                "match", "matches", "matched", "matching",
                "watch", "watches", "watched", "watching",
                "hatch", "hatches", "hatched", "hatching",
                "latch", "latches", "latched", "latching",
                "witch", "witches",
                "switch", "switches", "switched", "switching",
                "pitch", "pitches", "pitched", "pitching",
            ],
        ),
    ],
)
def test_false_positives_rejected(target_word: str, false_positives: list[str]) -> None:
    matcher = make_matcher([Word(word=target_word, aggressive=True)], threshold=85.0)

    for word in false_positives:
        assert not contains_profanity(matcher, word), f"{word!r} should NOT match {target_word!r}"


@pytest.mark.parametrize(
    ("target_word", "legitimate_variants"),
    [
        ("shit", ["shit", "shits", "shitting", "shitted", "shitty", "shittier", "shittiest",
                  "bullshit", "horseshit", "apeshit", "shithead", "shithole", "shitshow"]),
        ("fuck", ["fuck", "fucks", "fucking", "fucked", "fucker", "fuckers",
                  "fuckable", "fuckery", "fucktard", "motherfucker", "clusterfuck",
                  "unfuckingbelievable"]),
        ("dick", ["dick", "dicks", "dickhead", "dickheads", "dickwad", "dickish", "dickery"]),
        ("bitch", ["bitch", "bitches", "bitchy", "bitching", "bitchiest", "bitchass"]),
    ],
)
def test_legitimate_variants_caught(target_word: str, legitimate_variants: list[str]) -> None:
    matcher = make_matcher([Word(word=target_word, aggressive=True)], threshold=85.0)

    for word in legitimate_variants:
        assert contains_profanity(matcher, word), f"{word!r} should match {target_word!r}"


def test_cunt_exact_match_only_caught() -> None:
    matcher = make_matcher([Word(word="cunt")], threshold=85.0)

    assert contains_profanity(matcher, "cunt")


class TestAllowlistSuppression:
    """R1: the allowlist suppresses false positives regardless of fuzzy score."""

    def test_allowlisted_word_never_matches(self) -> None:
        # "flarn"/"flarm" are 5+ chars (no length-based 95% floor applies) and
        # a deliberately low threshold so "flarm" would otherwise score high
        # enough against "flarn" to match (80% fuzzy ratio).
        without_allowlist = make_matcher([Word(word="flarn", threshold=40)], threshold=40.0)
        assert contains_profanity(without_allowlist, "flarm")

        with_allowlist = make_matcher(
            [Word(word="flarn", threshold=40)], allowlist=["flarm"], threshold=40.0
        )
        assert not contains_profanity(with_allowlist, "flarm")

    def test_allowlist_does_not_suppress_other_words(self) -> None:
        matcher = make_matcher(
            [Word(word="flarn", threshold=40)], allowlist=["flarm"], threshold=40.0
        )

        assert contains_profanity(matcher, "flarn")


class TestMultiWordPhrases:
    def test_multi_word_target_matches_phrase(self) -> None:
        matcher = make_matcher([Word(word="god damn")], threshold=85.0)

        matches = matcher.find_matches("oh god damn it")

        assert len(matches) == 1
        assert matches[0].word == "god damn"

    def test_multi_word_target_not_matched_by_single_word(self) -> None:
        matcher = make_matcher([Word(word="god damn")], threshold=85.0)

        assert matcher.find_matches("god is good") == []


class TestReplacement:
    def test_replacement_carried_through_to_match(self) -> None:
        word = Word(word="darn", replacement="d*rn", threshold=75.0)
        matcher = make_matcher([word], threshold=75.0)

        matches = matcher.find_matches("darn it")

        assert matches[0].replacement == "d*rn"
