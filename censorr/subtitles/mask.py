from censorr.detect.matcher import Match
from censorr.subtitles.io import SubtitleDoc, SubtitleEntry

# Matches an ASS/SSA override tag block, e.g. "{\i1}".
_TAG_START = "{"
_TAG_END = "}"


def _plaintext_to_raw_index_map(raw: str) -> list[int]:
    """Map each plaintext character (post override-tag-stripping) to its
    starting index in `raw`. `\\N`/`\\n`/`\\h` escapes collapse to one
    plaintext char each, mirroring pysubs2's plaintext derivation.
    """
    indices: list[int] = []
    i = 0
    n = len(raw)
    while i < n:
        if raw[i] == _TAG_START:
            end = raw.find(_TAG_END, i)
            if end == -1:
                break
            i = end + 1
            continue
        if raw[i] == "\\" and i + 1 < n and raw[i + 1] in ("N", "n", "h"):
            indices.append(i)
            i += 2
            continue
        indices.append(i)
        i += 1
    return indices


def _raw_span_for_plaintext_span(raw: str, span: tuple[int, int]) -> tuple[int, int]:
    index_map = _plaintext_to_raw_index_map(raw)
    start_i, end_i = span
    raw_start = index_map[start_i]
    last_char_raw = index_map[end_i - 1]
    raw_end = last_char_raw + 2 if raw[last_char_raw] == "\\" else last_char_raw + 1
    return raw_start, raw_end


def _mask_word(original: str, replacement: str | None) -> str:
    if replacement is not None:
        return replacement
    if not original:
        return original
    return original[0] + "*" * (len(original) - 1)


def mask_entry_text(text: str, plaintext: str, matches: list[Match]) -> tuple[str, str]:
    """Apply `matches` (spans into `plaintext`) to both `text` (styling
    preserved) and `plaintext`. Returns (masked_text, masked_plaintext).
    """
    masked_text = text
    masked_plaintext = plaintext
    for match in sorted(matches, key=lambda m: m.span[0], reverse=True):
        start, end = match.span
        original_word = plaintext[start:end]
        mask = _mask_word(original_word, match.replacement)

        raw_start, raw_end = _raw_span_for_plaintext_span(masked_text, match.span)
        masked_text = masked_text[:raw_start] + mask + masked_text[raw_end:]
        masked_plaintext = masked_plaintext[:start] + mask + masked_plaintext[end:]

    return masked_text, masked_plaintext


def mask_entries(
    doc: SubtitleDoc, matches: dict[int, list[Match]]
) -> tuple[SubtitleDoc, SubtitleDoc | None]:
    """Mask profane spans across `doc`. Returns (masked_doc, captions_doc);
    captions_doc holds only the masked entries and is None when empty (R3).
    """
    masked_entries: list[SubtitleEntry] = []
    caption_entries: list[SubtitleEntry] = []

    for entry in doc.entries:
        entry_matches = matches.get(entry.index, [])
        if not entry_matches:
            masked_entries.append(entry)
            continue

        masked_text, masked_plaintext = mask_entry_text(entry.text, entry.plaintext, entry_matches)
        masked_entry = entry.model_copy(update={"text": masked_text, "plaintext": masked_plaintext})
        masked_entries.append(masked_entry)
        caption_entries.append(masked_entry)

    masked_doc = doc.model_copy(update={"entries": masked_entries})
    captions_doc = doc.model_copy(update={"entries": caption_entries}) if caption_entries else None
    return masked_doc, captions_doc
