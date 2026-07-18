from censorr.detect.matcher import Match, Matcher
from censorr.detect.wordlist import Word, WordList
from censorr.subtitles.io import SubtitleDoc, SubtitleEntry
from censorr.subtitles.mask import mask_entries
from censorr.subtitles.qc import audit


def entry(index: int, text: str) -> SubtitleEntry:
    return SubtitleEntry(
        index=index, start_s=float(index), end_s=float(index) + 1.0, text=text, plaintext=text
    )


def make_matcher(*words: str) -> Matcher:
    return Matcher(WordList(words=[Word(word=w) for w in words]), similarity_threshold=85.0)


class TestHappyPath:
    def test_correctly_masked_output_passes_all_checks(self) -> None:
        original = SubtitleDoc(entries=[entry(0, "clean line"), entry(1, "fuck this")])
        matches = {1: [Match(word="fuck", span=(0, 4), score=100.0)]}
        masked_doc, _ = mask_entries(original, matches)
        matcher = make_matcher("fuck")

        result = audit(original, masked_doc, matches, matcher)

        assert result.residual_matches == []
        assert result.unmasked_text_identical is True
        assert result.entry_count_unchanged is True
        assert result.timings_unchanged is True
        assert result.violations == []
        assert result.masked_entry_ratio == 0.5
        assert len(result.masked_words) == 1
        assert result.masked_words[0].word == "fuck"


class TestUnderMasking:
    def test_residual_match_detected_if_masking_was_skipped(self) -> None:
        original = SubtitleDoc(entries=[entry(0, "fuck this")])
        matches = {0: [Match(word="fuck", span=(0, 4), score=100.0)]}
        # Simulate a masking bug: masked_doc left untouched (still profane).
        unmasked_output = original.model_copy(deep=True)
        matcher = make_matcher("fuck")

        result = audit(original, unmasked_output, matches, matcher)

        assert len(result.residual_matches) == 1
        assert result.residual_matches[0].word == "fuck"


class TestOverMasking:
    def test_unauthorized_edit_outside_matches_flagged(self) -> None:
        original = SubtitleDoc(entries=[entry(0, "clean line")])
        masked_doc = SubtitleDoc(entries=[entry(0, "CORRUPTED line")])
        matcher = make_matcher("fuck")

        result = audit(original, masked_doc, {}, matcher)

        assert result.unmasked_text_identical is False
        assert any("no recorded match" in v for v in result.violations)

    def test_masked_text_diverging_from_expected_masking_flagged(self) -> None:
        original = SubtitleDoc(entries=[entry(0, "fuck this")])
        matches = {0: [Match(word="fuck", span=(0, 4), score=100.0)]}
        # Correct masking would produce "f*** this"; simulate a bug that masks wrong.
        bad_masked = SubtitleDoc(entries=[entry(0, "**** this")])
        matcher = make_matcher("fuck")

        result = audit(original, bad_masked, matches, matcher)

        assert any("does not match" in v for v in result.violations)

    def test_replacement_word_of_different_length_does_not_false_positive(self) -> None:
        original = SubtitleDoc(entries=[entry(0, "oh shit really")])
        matches = {0: [Match(word="shit", span=(3, 7), score=100.0, replacement="poop")]}
        masked_doc, _ = mask_entries(original, matches)
        matcher = make_matcher("shit")

        result = audit(original, masked_doc, matches, matcher)

        assert result.violations == []


class TestEntryCountAndTimings:
    def test_entry_count_changed_flagged(self) -> None:
        original = SubtitleDoc(entries=[entry(0, "a"), entry(1, "b")])
        masked_doc = SubtitleDoc(entries=[entry(0, "a")])
        matcher = make_matcher("fuck")

        result = audit(original, masked_doc, {}, matcher)

        assert result.entry_count_unchanged is False
        assert any("entry count changed" in v for v in result.violations)

    def test_timing_changed_flagged(self) -> None:
        original = SubtitleDoc(entries=[entry(0, "a")])
        shifted = SubtitleEntry(index=0, start_s=5.0, end_s=6.0, text="a", plaintext="a")
        masked_doc = SubtitleDoc(entries=[shifted])
        matcher = make_matcher("fuck")

        result = audit(original, masked_doc, {}, matcher)

        assert result.timings_unchanged is False
        assert any("timings changed" in v for v in result.violations)


class TestMaskedEntryRatio:
    def test_ratio_computed_over_all_entries(self) -> None:
        original = SubtitleDoc(
            entries=[entry(0, "fuck"), entry(1, "clean"), entry(2, "clean"), entry(3, "clean")]
        )
        matches = {0: [Match(word="fuck", span=(0, 4), score=100.0)]}
        masked_doc, _ = mask_entries(original, matches)
        matcher = make_matcher("fuck")

        result = audit(original, masked_doc, matches, matcher)

        assert result.masked_entry_ratio == 0.25

    def test_zero_entries_gives_zero_ratio(self) -> None:
        original = SubtitleDoc(entries=[])
        matcher = make_matcher("fuck")

        result = audit(original, original, {}, matcher)

        assert result.masked_entry_ratio == 0.0
