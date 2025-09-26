# Implementation Plan: Plex/Arr Clean Censor Tool

**Branch**: `001-write-a-tool` | **Date**: 2025-09-20 | **Spec**: ./spec.md
**Input**: Feature specification from `/specs/001-write-a-tool/spec.md`

## Summary
Primary requirement: Provide a CLI-first, composable pipeline that can extract/accept subtitles and audio, mask profanities in subtitles via fuzzy matching, mute aligned audio windows, and optionally remux into a playable output. Support Radarr/Sonarr triggers by tag, clear naming, sidecar export, and dry-run/explain for predictability. Deliverables MUST be container-deployable (Docker/Podman) with a minimal, non-root image and documented Compose/Podman examples per Constitution XII.

Technical approach (high level): Implement a Python 3 CLI with a small core (Artifacts, Operations, Registry, Planner, Executor). Use adapters to call FFmpeg for extract/mute/remux and Python subtitle parsing utilities for SRT/WEBVTT. Use RapidFuzz for fuzzy matching. Maintain deterministic workdir, manifest-based caching, and structured execution/audit logs.

## Technical Context
- Language/Version: Python 3.11+
- Primary Dependencies: RapidFuzz, FFmpeg (external binary), a subtitle parsing library (e.g., pysubs2 or custom minimal parser), click/typer for CLI, pydantic for data validation (selectors/artifacts), PyYAML for config.
- Storage: Local filesystem workdir; deterministic layout; manifest.json per operation.
- Testing: pytest + tmp_path fixtures; golden samples for subtitles/audio; integration tests performing dry-run and small media fragments.
- Target Platform: Linux server; Docker/Podman friendly. FFmpeg must be available on PATH.
- Containerization: Provide a Dockerfile (Podman compatible) producing a minimal, non-root image with ENTRYPOINT to the CLI; publish Compose/Podman run examples; log to stdout/stderr.
- Project Type: Single project (CLI tool + library) → default structure.
- Performance Goals: Handle feature-length media with linear passes; keep memory bounded by streaming where possible; parallelize independent ops.
- Constraints: Avoid full re-encode unless requested; preserve codecs by default; ensure idempotency and deterministic filenames. Container images must use pinned bases and support amd64/arm64 when feasible.
- Scale/Scope: Single-node CLI; batch processing through Arr triggers.
 - Selector Enhancements: Subtitle selection includes support for title/metadata filtering (case-insensitive substring and optional regex) and exclusion of SDH/HI/CC. Minimal adapter updates expose track "forced" disposition and title straight from ffprobe; CLI exposes new selector inputs with sane defaults.

## Constitution Check
- KISS: Minimal core (Artifacts, Ops, Planner, Executor) with adapters; avoid frameworks beyond CLI/validation.
- SRP: Each Operation does one thing (extract-subtitles, merge-subs, mask-subs, extract-audio, mute-audio, remux, export-sidecar, qc-subs).
- Composition: Ops wired via artifact types; no inheritance chains.
- Explicit Contracts: Documented shapes for Artifact/Selector/Operation contracts in `/contracts` and `data-model.md`.
- Plugin-First: Operation registry allows plugin registration at startup.
- YAGNI: No HTTP server; CLI-only; manifest caching is simple file-based.
- Test-First & Docs: Contract and acceptance tests before implementation; quickstart guides usage.
- Observability: Execution and audit logs per op under workdir; container logs on stdout/stderr; optional healthcheck guidance for long-running modes.
- Idempotency/Dry-Run: Planner/executor support dry-run and manifest checks.

Container Deployability (XII): Plan includes Dockerfile (non-root, pinned base), ENTRYPOINT, stdout/stderr logging, and Compose/Podman examples. Multi-arch documented. No violations anticipated; any complexity will be documented in Complexity Tracking.

## Project Structure

### Documentation (this feature)
```
specs/001-write-a-tool/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
└── tasks.md (generated later)
```

### Source Code (repository root)
```
src/
├── cli/
├── models/
├── ops/
├── planner/
├── adapters/
└── utils/

tests/
├── unit/
├── contract/
└── integration/
```

Structure Decision: Option 1 (single project).

## Profanity List Input (JSON dictionaries)

- The `mask_subtitles` operation accepts a `--profanity-list-file` CLI option pointing to a JSON file.
- File format: an array of JSON objects, each with at least a `word` key. Example:

  [
    { "word": "damn" },
    { "word": "hell", "tier": 2, "category": "mild" },
    { "word": "foobar", "replacement": "f****r" }
  ]

- Rationale: Using dictionaries enables forward-compatible expansion (tiers, categories, replacements) without breaking input.
- Current behavior: we read the `word` field into the allow list; additional fields are ignored for now.

## Masking Refinements and Tuning (appendix)

- Hyphenated-subtoken masking: Masking now targets only the profane sub-part within hyphenated or apostrophized tokens (e.g., "Criss-fuckin'-Angel" → only "fuckin'" is masked, preserving surrounding text and punctuation). Implementation splits on `-` and `'` and masks per subtoken.
- Fuzzy matching enhancement: Similarity score uses the maximum of full ratio and partial ratio to improve recall for suffixes/compounds (e.g., `fuck` vs `fucking`/`fuckup`).
- Threshold tuning: New CLI flag `--fuzzy-threshold` (0–100) overrides the default similarity threshold used in subtitle masking; wired through `OperationFlags.fuzzy_threshold`.
- QC improvements: Residual scan generates variants (base, minus common suffixes like `ing`/`in`) to better catch missed forms like "6-foot-fucking-6", "Criss-fuckin'-Angel", and "shit-stirrer".

### New Tasks (appended)
- [ ] Add CLI option `--fuzzy-threshold` and plumb through to masking (Done)
- [ ] Update fuzzy matcher to use `max(ratio, partial_ratio)` for improved recall (Done)
- [ ] Refine masking to only replace profane sub-part inside hyphenated/apostrophized tokens (Done)
- [ ] Enhance QC to check base + stem variants to catch hyphenated/contracted forms (Done)

## Naming Strategy Addendum (FR-054, FR-055)
Rationale: Ensure Plex auto-discovers cleaned subtitles and distinguishes remuxed movie variant without polluting episode naming.

Sidecar subtitles
- Pattern: `<base>.<lang>.<tag>.srt`
  - `<base>`: Derived from video filename minus any `{edition-*}` tag; preserve `Title (Year)` or episode pattern.
  - Normalize: collapse multiple spaces, trim, preserve punctuation already Plex-compatible.
  - `<lang>`: lowercase ISO 639-1.
  - `<tag>`: `censorr` (default) or `clean` (alias via CLI/config).
- Collision handling: If path exists and checksum differs, append incremental numeric suffix before extension.
- Reuse: If identical checksum, skip write (log reuse).

Edition tag (movies only)
- Insert `{edition-Censorr}` after the canonical `Title (Year)` segment if no existing `{edition-*}` present.
- Detection: regex for `{edition-[^}]+}`; idempotent and skip when any edition exists.
- Episodes: Identified by `S\d{2}E\d{2}` pattern or explicit media type flag; never modified with edition tag.
- Logging: differentiate added vs skipped; surface decision in structured log.

Open Questions (deferred): Replacement of pre-existing edition tags or stacking multiple tags (out of scope now); forced/SDH sidecar variants (future extension).

## Phase 0: Outline & Research
Create `research.md` to resolve:
- FFmpeg strategies:
  - Audio extraction without re-encode (copy) vs with re-encode when needed.
  - Applying mute windows: filter_complex volume enable between timestamps vs generate silenced segments and splice.
  - Subtitle extraction and format conversions (SRT/WEBVTT).
- Fuzzy matching with RapidFuzz:
  - Token-based vs partial ratios; thresholds; normalization.
  - Word-boundary handling and allow-list precedence.
- Subtitle parsing/normalization:
  - Library choice (pysubs2) vs minimal custom parser; handling malformed cues and encoding normalization.
  - Merging strategies and deduplication semantics.
- Arr integrations:
  - Custom Script env vars and Webhook payload fields; tag detection; safest defaults.

Output: research.md with Decisions, Rationale, Alternatives for each topic.

## Phase 1: Design & Contracts
- Data Model (`data-model.md`): Define Artifact, Selector, Operation, MuteWindow, AuditLogEntry, ManifestEntry with fields and validation.
- Contracts (`/contracts`):
  - artifacts.md: Artifact types, metadata, validation rules.
  - selectors.md: Unified selector model, reference to `selector.schema.json`, examples. Add subtitle-specific fields: `title_include[]`, `title_exclude[]`, `title_regex[]`, and `exclude_sdh` convenience toggle. Document precedence: excludes win.
  - operation.md: Operation interface (inputs, outputs, run contract), error modes.
- Quickstart (`quickstart.md`): Environment setup, installing deps, small sample run (dry-run), interpreting logs, troubleshooting.
- Agent file: If agent updater exists, note to run it post-creation (manual in this repo).

Re-check Constitution Gates; update if any complexity was added.

## Phase 2: Task Planning Approach (informational)
- Generate tasks from contracts + data model + quickstart.
- TDD order; mark independent test files as parallelizable.

## Complexity Tracking
(n/a at plan time)

## Progress Tracking
- [ ] Phase 0: Research complete (/plan)
- [ ] Phase 1: Design complete (/plan)
- [ ] Phase 2: Task planning complete (/tasks)
- [ ] Phase 3: Tasks generated (/tasks)
- [ ] Phase 4: Implementation complete
- [ ] Phase 5: Validation passed

- [ ] Initial Constitution Check: PASS
- [ ] Post-Design Constitution Check: PASS
- [ ] All NEEDS CLARIFICATION resolved
- [ ] Complexity deviations documented
