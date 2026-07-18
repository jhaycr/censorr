import json
from pathlib import Path

import pytest

from censorr.audio.windows import (
    AudioSettings,
    EntrySpanProvider,
    ExternalFileProvider,
    MuteWindow,
    merge_windows,
)
from censorr.detect.matcher import Match
from censorr.subtitles.io import SubtitleEntry

SOURCE = Path("/media/movie.mkv")


def entry(index: int, start_s: float, end_s: float) -> SubtitleEntry:
    return SubtitleEntry(index=index, start_s=start_s, end_s=end_s, text="x", plaintext="x")


def a_match() -> dict[int, list[Match]]:
    return {0: [Match(word="fuck", span=(0, 4), score=100.0)]}


class TestEntrySpanProvider:
    def test_single_word_entry_gets_full_span_plus_both_buffers(self) -> None:
        # The critical R2 case: a short single-word entry must never be
        # trimmed to less than the full entry span + buffer on each side.
        entries = [entry(0, start_s=5.0, end_s=5.4)]
        settings = AudioSettings(buffer_s=0.2)

        windows = EntrySpanProvider().windows(entries, a_match(), SOURCE, settings)

        assert len(windows) == 1
        assert windows[0].start_s == pytest.approx(4.8)
        assert windows[0].end_s == pytest.approx(5.6)

    def test_buffer_never_goes_below_zero(self) -> None:
        entries = [entry(0, start_s=0.1, end_s=1.0)]
        settings = AudioSettings(buffer_s=0.2)

        windows = EntrySpanProvider().windows(entries, a_match(), SOURCE, settings)

        assert windows[0].start_s == 0.0

    def test_entry_without_match_produces_no_window(self) -> None:
        entries = [entry(0, start_s=1.0, end_s=2.0)]
        settings = AudioSettings(buffer_s=0.2)

        windows = EntrySpanProvider().windows(entries, {}, SOURCE, settings)

        assert windows == []

    def test_only_matched_entries_produce_windows(self) -> None:
        entries = [entry(0, 1.0, 2.0), entry(1, 5.0, 6.0)]
        matches = {1: [Match(word="shit", span=(0, 4), score=100.0)]}
        settings = AudioSettings(buffer_s=0.2)

        windows = EntrySpanProvider().windows(entries, matches, SOURCE, settings)

        assert len(windows) == 1
        assert windows[0].start_s == 4.8

    def test_determinism_same_inputs_same_output(self) -> None:
        entries = [entry(0, 1.0, 2.0), entry(1, 5.0, 6.0)]
        matches = {0: [Match(word="fuck", span=(0, 4), score=100.0)],
                   1: [Match(word="shit", span=(0, 4), score=100.0)]}
        settings = AudioSettings(buffer_s=0.2)

        first = EntrySpanProvider().windows(entries, matches, SOURCE, settings)
        second = EntrySpanProvider().windows(entries, matches, SOURCE, settings)

        assert first == second


class TestMergeWindows:
    def test_overlapping_windows_merge(self) -> None:
        windows = [
            MuteWindow(start_s=1.0, end_s=3.0, source="entry_span", reason="matched_entry"),
            MuteWindow(start_s=2.5, end_s=4.0, source="entry_span", reason="matched_entry"),
        ]

        merged = merge_windows(windows)

        assert len(merged) == 1
        assert merged[0].start_s == 1.0
        assert merged[0].end_s == 4.0

    def test_adjacent_touching_windows_merge(self) -> None:
        windows = [
            MuteWindow(start_s=1.0, end_s=2.0, source="entry_span", reason="matched_entry"),
            MuteWindow(start_s=2.0, end_s=3.0, source="entry_span", reason="matched_entry"),
        ]

        merged = merge_windows(windows)

        assert len(merged) == 1
        assert merged[0].start_s == 1.0
        assert merged[0].end_s == 3.0

    def test_disjoint_windows_stay_separate(self) -> None:
        windows = [
            MuteWindow(start_s=1.0, end_s=2.0, source="entry_span", reason="matched_entry"),
            MuteWindow(start_s=5.0, end_s=6.0, source="entry_span", reason="matched_entry"),
        ]

        merged = merge_windows(windows)

        assert len(merged) == 2

    def test_merge_is_order_independent(self) -> None:
        a = MuteWindow(start_s=5.0, end_s=6.0, source="entry_span", reason="matched_entry")
        b = MuteWindow(start_s=1.0, end_s=2.0, source="entry_span", reason="matched_entry")
        c = MuteWindow(start_s=1.9, end_s=5.5, source="entry_span", reason="matched_entry")

        assert merge_windows([a, b, c]) == merge_windows([c, a, b]) == merge_windows([b, c, a])

    def test_empty_list(self) -> None:
        assert merge_windows([]) == []


class TestExternalFileProvider:
    def test_loads_and_merges_windows_from_json(self, tmp_path: Path) -> None:
        windows_file = tmp_path / "windows.json"
        windows_file.write_text(
            json.dumps(
                [
                    {"start_s": 10.0, "end_s": 11.0},
                    {"start_s": 10.5, "end_s": 12.0},
                    {"start_s": 20.0, "end_s": 21.0},
                ]
            )
        )

        provider = ExternalFileProvider(windows_file)
        windows = provider.windows([], {}, SOURCE, AudioSettings())

        assert len(windows) == 2
        assert windows[0].start_s == 10.0
        assert windows[0].end_s == 12.0
        assert windows[1].start_s == 20.0

    def test_merged_with_entry_span_provider_output(self, tmp_path: Path) -> None:
        windows_file = tmp_path / "windows.json"
        windows_file.write_text(json.dumps([{"start_s": 4.9, "end_s": 5.2}]))

        entries = [entry(0, start_s=5.0, end_s=5.4)]
        settings = AudioSettings(buffer_s=0.2)

        entry_windows = EntrySpanProvider().windows(entries, a_match(), SOURCE, settings)
        external_windows = ExternalFileProvider(windows_file).windows([], {}, SOURCE, settings)

        combined = merge_windows(entry_windows + external_windows)

        # entry span (4.8-5.6) overlaps the external window (4.9-5.2) -> one window
        assert len(combined) == 1
        assert combined[0].start_s == pytest.approx(4.8)
        assert combined[0].end_s == pytest.approx(5.6)
