from censorr.detect.matcher import Match
from censorr.subtitles.io import SubtitleDoc, SubtitleEntry
from censorr.subtitles.mask import mask_entries, mask_entry_text


def entry(index: int, text: str, plaintext: str | None = None) -> SubtitleEntry:
    return SubtitleEntry(
        index=index,
        start_s=float(index),
        end_s=float(index) + 1.0,
        text=text,
        plaintext=plaintext or text,
    )


class TestMaskEntryText:
    def test_asterisk_masking_preserves_first_letter(self) -> None:
        text, plaintext = mask_entry_text(
            "You are a fuck", "You are a fuck", [Match(word="fuck", span=(10, 14), score=100.0)]
        )

        assert plaintext == "You are a f***"
        assert text == "You are a f***"

    def test_replacement_word_used_when_provided(self) -> None:
        text, plaintext = mask_entry_text(
            "oh damn it",
            "oh damn it",
            [Match(word="damn", span=(3, 7), score=100.0, replacement="darn")],
        )

        assert plaintext == "oh darn it"

    def test_multiple_matches_applied_right_to_left(self) -> None:
        original = "fuck this shit"
        matches = [
            Match(word="fuck", span=(0, 4), score=100.0),
            Match(word="shit", span=(10, 14), score=100.0),
        ]

        text, plaintext = mask_entry_text(original, original, matches)

        assert plaintext == "f*** this s***"

    def test_unmasked_regions_byte_identical(self) -> None:
        original = "Well, fuck this whole situation honestly"
        matches = [Match(word="fuck", span=(6, 10), score=100.0)]

        _, plaintext = mask_entry_text(original, original, matches)

        assert plaintext[:6] == original[:6]
        assert plaintext[10:] == original[10:]

    def test_ass_override_tags_preserved_around_mask(self) -> None:
        raw = r"{\i1}you are a fuck{\i0}"
        plaintext = "you are a fuck"

        text, masked_plaintext = mask_entry_text(
            raw, plaintext, [Match(word="fuck", span=(10, 14), score=100.0)]
        )

        assert masked_plaintext == "you are a f***"
        assert text == r"{\i1}you are a f***{\i0}"


class TestMaskEntries:
    def test_entries_without_matches_untouched(self) -> None:
        doc = SubtitleDoc(entries=[entry(0, "clean line"), entry(1, "fuck this")])
        matches = {1: [Match(word="fuck", span=(0, 4), score=100.0)]}

        masked_doc, captions_doc = mask_entries(doc, matches)

        assert masked_doc.entries[0].text == "clean line"
        assert masked_doc.entries[0].plaintext == "clean line"

    def test_entry_count_and_timings_unchanged(self) -> None:
        doc = SubtitleDoc(entries=[entry(0, "clean line"), entry(1, "fuck this")])
        matches = {1: [Match(word="fuck", span=(0, 4), score=100.0)]}

        masked_doc, _ = mask_entries(doc, matches)

        assert len(masked_doc.entries) == len(doc.entries)
        for original, masked in zip(doc.entries, masked_doc.entries, strict=True):
            assert original.start_s == masked.start_s
            assert original.end_s == masked.end_s
            assert original.index == masked.index

    def test_captions_doc_contains_only_masked_entries(self) -> None:
        doc = SubtitleDoc(entries=[entry(0, "clean line"), entry(1, "fuck this")])
        matches = {1: [Match(word="fuck", span=(0, 4), score=100.0)]}

        _, captions_doc = mask_entries(doc, matches)

        assert captions_doc is not None
        assert len(captions_doc.entries) == 1
        assert captions_doc.entries[0].plaintext == "f*** this"

    def test_captions_doc_none_when_no_matches_at_all(self) -> None:
        doc = SubtitleDoc(entries=[entry(0, "clean line"), entry(1, "another clean line")])

        _, captions_doc = mask_entries(doc, {})

        assert captions_doc is None
