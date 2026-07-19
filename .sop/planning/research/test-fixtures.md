# Research: Synthetic Test Media Fixtures

Gathered 2026-07-15. How v2's integration tests exercise real FFmpeg without committing binary fixtures (constitution §7: keep binary fixtures tiny; prefer generating on the fly).

## Generation technique (lavfi virtual sources)

FFmpeg's `lavfi` input format synthesizes streams — no source files needed:

```bash
# tiny_movie.mkv: 20 s, 320×180 test pattern, 440 Hz tone, embedded English SRT
ffmpeg -y \
  -f lavfi -i "testsrc2=duration=20:size=320x180:rate=10" \
  -f lavfi -i "sine=frequency=440:sample_rate=48000:duration=20" \
  -i dialogue.srt \
  -map 0:v -c:v libx264 -preset ultrafast -crf 35 \
  -map 1:a -c:a aac -b:a 64k \
  -map 2:0 -c:s srt -metadata:s:s:0 language=eng \
  tiny_movie.mkv
```
Result: a few hundred KB, generated in ~1 s. `dialogue.srt` is a checked-in *text* file whose entries contain known profanity words from the test word list at known timestamps — making mute-window and masking assertions exact.

## Fixture recipes needed by the test suite

| Fixture | Purpose |
|---|---|
| Basic movie-named file (`Test Movie (2024).mkv`) with 1 audio + 1 sub | happy path, movie naming/edition tag |
| Episode-named file (`Test Show - s01e01.mkv`) in `Show/Season 01/` tree | episode naming, clean-root mirroring |
| Multi-subtitle file (en, en SDH-titled, es) | selection filters (language, title excludes) |
| Multi-audio file (aac stereo + ac3 5.1) | track selection, codec-preservation policy |
| No-subtitle file | subtitle-source chain fallback / clear error |
| 5.1 eac3 file | surround re-encode policy |
| Forced-flag subtitle track | forced handling |

Implementation: a `tests/fixtures.py` module with functions building each recipe into `tmp_path` (or a session-scoped cache dir keyed by recipe hash so each fixture builds once per test session). Verifying muting in tests: decode the output's audio in a flagged window vs. an unflagged window (`ffmpeg -ss/-t ... -f wav`) and compare RMS — the same measurement the audio QC stage uses, so tests double as QC validation.

**CI note**: tests require real `ffmpeg` on PATH (GitHub Actions: `apt-get install ffmpeg` or a container job). Unit tests (naming, matching, config, fingerprints) need no FFmpeg and stay sub-second; integration tests are marked (`@pytest.mark.ffmpeg`) and skippable when the binary is absent.

Sources: [Creating test signal files with FFmpeg](https://mark.himsley.org/FFmpeg/creating_test_signal_files.html), [FFmpeg filters documentation — testsrc2/sine](https://ffmpeg.org/ffmpeg-filters.html)
