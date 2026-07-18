from pydantic import BaseModel

from censorr.detect.matcher import Match, Matcher
from censorr.subtitles.io import SubtitleDoc
from censorr.subtitles.mask import mask_entry_text


class MaskedWordAudit(BaseModel):
    entry_index: int
    word: str
    score: float


class SubtitleQCResult(BaseModel):
    residual_matches: list[Match] = []
    unmasked_text_identical: bool
    entry_count_unchanged: bool
    timings_unchanged: bool
    masked_entry_ratio: float
    masked_words: list[MaskedWordAudit] = []
    violations: list[str] = []


def audit(
    original: SubtitleDoc,
    masked: SubtitleDoc,
    matches: dict[int, list[Match]],
    matcher: Matcher,
) -> SubtitleQCResult:
    """R14 symmetric subtitle QC.

    Under-masking: re-scan the masked output for residual profanity.
    Over-masking: every altered word must map to a recorded match (verified
    by re-deriving the expected masked text from the original + matches and
    comparing -- robust to replacement words whose length differs from the
    original, unlike a naive character-position diff); unmasked entries must
    be byte-identical to the original; entry count/timings unchanged.
    """
    residual_matches: list[Match] = []
    for entry in masked.entries:
        residual_matches.extend(matcher.find_matches(entry.plaintext))

    entry_count_unchanged = len(original.entries) == len(masked.entries)
    timings_unchanged = entry_count_unchanged and all(
        o.start_s == m.start_s and o.end_s == m.end_s
        for o, m in zip(original.entries, masked.entries, strict=True)
    )

    violations: list[str] = []
    masked_words: list[MaskedWordAudit] = []
    unmasked_text_identical = True
    masked_entry_count = 0

    original_by_index = {e.index: e for e in original.entries}
    for entry in masked.entries:
        original_entry = original_by_index.get(entry.index)
        entry_matches = matches.get(entry.index, [])
        if original_entry is None:
            continue

        if not entry_matches:
            if entry.plaintext != original_entry.plaintext:
                unmasked_text_identical = False
                violations.append(f"entry {entry.index}: altered with no recorded match")
            continue

        masked_entry_count += 1
        for match in entry_matches:
            masked_words.append(
                MaskedWordAudit(entry_index=entry.index, word=match.word, score=match.score)
            )

        _expected_text, expected_plaintext = mask_entry_text(
            original_entry.text, original_entry.plaintext, entry_matches
        )
        if entry.plaintext != expected_plaintext:
            violations.append(
                f"entry {entry.index}: masked text does not match what the recorded "
                "matches would produce (unauthorized edit)"
            )

    if not entry_count_unchanged:
        violations.append("entry count changed during masking")
    if entry_count_unchanged and not timings_unchanged:
        violations.append("entry timings changed during masking")

    masked_entry_ratio = masked_entry_count / len(original.entries) if original.entries else 0.0

    return SubtitleQCResult(
        residual_matches=residual_matches,
        unmasked_text_identical=unmasked_text_identical,
        entry_count_unchanged=entry_count_unchanged,
        timings_unchanged=timings_unchanged,
        masked_entry_ratio=masked_entry_ratio,
        masked_words=masked_words,
        violations=violations,
    )
