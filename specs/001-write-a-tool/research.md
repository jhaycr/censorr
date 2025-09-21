# Research Notes: Plex/Arr Clean Censor Tool

Date: 2025-09-20
Spec: ./spec.md

## FFmpeg Strategies

Decision: Prefer stream copy where possible; re-encode only when necessary.
- Audio extraction:
  - Copy: `-map 0:a:m:language:eng -c:a copy` to extract without quality loss.
  - Re-encode: Allow user to select codec (e.g., AAC/AC3) if filters applied.
- Muting audio via filter_complex:
  - Option A (recommended): `volume=enable='between(t,START,END)':volume=0` chained for multiple windows or `aselect`/`atrim` with `alimiter` to stitch silences; ensure sync.
  - Option B: Generate silence chunks and concat; more complex, less streaming-friendly.
- Subtitle extraction/conversion:
  - Use `-map 0:s:m:language:eng` with `-c:s srt`/`webvtt` for conversion. For sidecars, `-f srt` to file.

Alternatives considered: SoX for finer audio ops; rejected to keep single-tool dependency.

## RapidFuzz Matching

Decision: Use token_set_ratio (or token_sort_ratio) with normalization; threshold 85.
- Normalize text: lowercase, strip punctuation, collapse whitespace.
- Word-boundary regex to avoid substring false positives.
- Allow-list precedence: never censor whitelisted terms.
- Aliases in dictionary: capture common misspellings and hyphenation.

Alternatives: python-Levenshtein based fuzzywuzzy (deprecated/slow); regex-only (too brittle).

## Subtitle Parsing/Normalization

Decision: Use pysubs2 for SRT/WEBVTT parsing and writing; augment with custom normalization when strict mode is off.
- Fix duplicate/missing sequence numbers.
- Order cues by start time; merge overlaps if identical text.
- Convert encodings to UTF-8.

Alternative: Custom minimal parser; deferred unless pysubs2 proves insufficient.

## Arr Integration

Decision: Support both Custom Script and Webhook; trigger on Import/Download with tags [clean, censor].
- Custom Script: rely on env vars for paths, media info, and tags.
- Webhook: expect JSON payload with title, path, tags; map to CLI invocation.

## Workdir & Caching

Decision: Deterministic layout: `${workdir}/{op-name}/{hash}/...` with manifest.json recording inputs + outputs.
- Idempotency: Skip when manifest matches and outputs exist; allow `--force OP` to rerun.

## Observability

Decision: Structured JSON logs per operation; summary execution log capturing plan graph, timings, and outputs.

## Open Questions (to close during design)
- Exact CLI surface for selectors vs JSON schema path defaults.
- Maximum number of mute windows before preferring an alternate FFmpeg strategy (performance tuning).