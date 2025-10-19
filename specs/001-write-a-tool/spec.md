# Feature Specification: Plex/Arr Clean Censor Tool

**Feature Branch**: `001-write-a-tool`  
**Created**: 2025-09-20  
**Status**: Draf- FR-053 (Audio QC override flag): The CLI MUST provide an override (e.g., "--continue-on-audio-qc-fail") that allows the pipeline to proceed despite audio QC failures. When set, the step logs a warning, writes the report, and the pipeline continues; the run's exit status remains success.
- FR-060 (Sidecar tag CLI flag): The CLI MUST accept a `--sidecar-tag` flag allowing users to override the default `censorr` tag used in sidecar subtitle filenames. The specified tag MUST be validated to contain only alphanumeric characters and hyphens (no spaces or special characters). This flag works in conjunction with FR-054 standardized sidecar naming.  
**Input**: User description: "Write a tool that is part of a Plex and arr-stack (Radarr, Sonarr) ecosystem. This tool will censor audio and subtitles for video files (movies, TV episodes) based on subtitle files. This tool will be able to be integrated as either Sonarr/Radarr Custom Script or Webhook. An example use-case is the admin of my Plex server to apply a tag (e.g \"clean\", \"censor\") to a movie in Ombi or Overseer. When the movie is imported into Radarr, the tool will extract the audio track and subtitle file for the specified language, apply a \"bad words\" list, and use mute any censored words from the list based on the subtitle timings. The tool will create a new subtitle track (with bad words masked) and new audio track (with bad words muted), and create separate artifacts (like a local masked subtitle) or attach them to the movie (like a muted audio track). A Plex user should be able to select the new tracks by name (e.g. \"en [CLEAN]\"). Masking can occur as \"full\" (all letters of a bad word are replaced with asterisks), \"partial\" (all but the first letter of a bad word are replaced with asterisks). Bad words use fuzzy matching to capture different spellings (\"Goddam\" versus \"God damn\"), punctuation or variations (e.g. \"Godammnit\"). Muting occurs at the subtitle level, covering the entire timing window where censored words appear."

## Execution Flow (main)
```
1. Parse user description from Input
	→ If empty: ERROR "No feature description provided"
2. Extract key concepts from description
	→ Identify: actors, actions, data, constraints
3. For each unclear aspect:
	→ Mark with [NEEDS CLARIFICATION: specific question]
4. Fill User Scenarios & Testing section
	→ If no clear user flow: ERROR "Cannot determine user scenarios"
5. Generate Functional Requirements
	→ Each requirement must be testable
	→ Mark ambiguous requirements
6. Identify Key Entities (if data involved)
7. Run Review Checklist
	→ If any [NEEDS CLARIFICATION]: WARN "Spec has uncertainties"
	→ If implementation details found: ERROR "Remove tech details"
8. Return: SUCCESS (spec ready for planning)
```

---

## ⚡ Quick Guidelines
- ✅ Focus on WHAT users need and WHY
- ❌ Avoid HOW to implement (no tech stack, APIs, code structure)
- 👥 Written for business stakeholders, not developers

### Section Requirements
- Mandatory sections: Must be completed for every feature
- Optional sections: Include only when relevant to the feature
- When a section doesn't apply, remove it entirely (don't leave as "N/A")

### For AI Generation
When creating this spec from a user prompt:
1. Mark all ambiguities: Use [NEEDS CLARIFICATION: specific question] for any assumption you'd need to make
2. Don't guess: If the prompt doesn't specify something (e.g., "login system" without auth method), mark it
3. Think like a tester: Every vague requirement should fail the "testable and unambiguous" checklist item
4. Common underspecified areas:
	- User types and permissions
	- Data retention/deletion policies  
	- Performance targets and scale
	- Error handling behaviors
	- Integration requirements
	- Security/compliance needs

---

## User Scenarios & Testing (mandatory)

### Primary User Story
As a CLI user, I want to compose a standalone, step-by-step media censoring and cleaning pipeline—extract subtitles from a video (or accept a provided subtitle file), merge multiple subtitles together (such as full vs forced subtitles), process/mask the subtitles based on fuzzy matches against a provided configuration of "bad words", optionally remux the masked subtitles into the video, extract the target audio track, apply mute windows derived from the processed subtitles, and remux the muted audio. I want to mix and match operations, skip or override steps with alternate input. When I provide a video as an input for subtitle extraction, I want the ability to provide selection criteria that select the subtitle track based on matches of track metadata such as language and name.

### Acceptance Scenarios
1. Given a newly imported movie with English main subtitles and English audio, when the item carries a "clean" tag and the tool executes post-import, then the system produces: (a) a new English subtitle track with profanities masked according to the selected policy (full/partial) and (b) a new English audio variant with profane words muted over the corresponding subtitle cue durations; both are available as selectable tracks in Plex with a clear naming convention (e.g., "en [CLEAN]").
2. Given a video that has multiple English subtitle tracks (main + forced), when the selection policy targets English and forced-only=false, then the system selects both tracks and, if configured to merge, produces one interleaved English subtitle output sorted by start time with deduplication of identical overlapping text.
3. Given a user supplies an external subtitle file for English via CLI/config, when the pipeline runs, then the system validates compatibility and skips subtitle extraction from the container, using the supplied subtitle instead.
4. Given a user supplies an external audio file via CLI/config, when the pipeline runs, then the system validates compatibility and skips audio extraction from the container, using the supplied audio instead.
5. Given a malformed subtitle file with out-of-order or overlapping timestamps, when the pipeline runs in non-strict mode, then the system attempts to normalize numbering, ordering, and encoding to produce a valid merged output and logs all corrections to an audit log; in strict mode, the pipeline fails fast with a descriptive error.
6. Given a TV episode with multiple audio tracks (e.g., main and commentary), when the audio selector prioritizes "lang=en, role=main", then the system targets the main English audio for muting and passes through others unchanged unless explicitly selected for processing.
7. Given a user only needs cleaned subtitles, when the pipeline runs with subtitle-only target, then it produces a processed/masked subtitle artifact and may stop without remuxing the video.
8. Given a user has externally provided mute windows for audio (without subtitles), when the pipeline runs with audio-only target, then it applies the provided timing windows to mute the selected audio track and may stop without remuxing the video.
9. Given a masked English subtitle still contains residual profane terms per the configured bad-words list (after applying any allow-list), when the QC step runs, then by default the pipeline fails with a descriptive message and writes a QC report to the working directory listing matches and example cues.
10. Given residual profane terms exist, when the user supplies the CLI flag to continue on QC failure, then the pipeline completes subsequent steps (e.g., export sidecar, remux) and emits a warning that links to the QC report; the process exit code indicates success.
11. Given a video container with three English subtitle tracks — (a) a main/full track with a null/empty title or a generic title like "English", (b) a forced track titled "English Forced" (or similar), and (c) a hearing‑impaired track titled with SDH/HI/CC (e.g., "English [SDH]") — when the user targets English and specifies title/metadata filters to include main + forced while excluding SDH/HI, then the system selects only the full and forced English tracks, merges them in chronological order, and excludes the SDH/HI track from the merge.
12. Given that both extracted and muted audio artifacts exist for the same track, when the packaging/remux step runs, then it MUST select the muted audio in preference to the extracted audio; if muted audio is not available, it MUST fall back deterministically to extracted audio and log the decision.
13. Given that multiple subtitle artifacts exist (extracted, merged, masked), when the packaging/remux step runs in the default subtitle mode (masked_only), then only the final post-merge masked subtitle is included; when configured to "all", all provided subtitle artifacts are included; when configured to "none", no subtitles are embedded.
14. Given users prefer to keep subtitles as sidecar files, when the sidecar option is enabled, then the system writes the final masked subtitle next to the remuxed video using Plex-discoverable naming and MAY omit embedding per configuration.
15. Given the audio muting step completed, when the audio quality check runs, then insufficient attenuation in any mute window causes the pipeline to fail by default with a clear report path; when the user supplies the override flag to continue on audio QC failure, the pipeline proceeds and logs a warning.
16. Given a remuxed MOVIE (not an EPISODE) is produced after masking/muting, when the packaging step writes the final container, then the output filename MUST include a Plex Edition tag `{edition-Censorr}` inserted immediately after the canonical "Title (Year)" segment (e.g., `Movie Title (2024) {edition-Censorr}.mkv`) if not already present, and the sidecar masked subtitle MUST follow the standardized naming pattern `<base>.<lang>.<tag>.srt` (e.g., `Movie Title (2024).en.censorr.srt`). If an edition tag already exists (any edition), the system MUST NOT append a second edition tag and MUST log that an edition was detected.

17. Preset config, movies (REMUX_NEW_FILE): Given a default configuration file at `config/censorr.json` defines a preset named `movies`, when I run `censorr process "/data/media/movies/<movie>.mkv" --preset movies` with no other flags, then the tool executes the preset pipeline with operations `extract_subtitles,merge_subtitles,mask_subtitles,extract_audio,mute_audio,audio_quality_check,remux`, writes a sidecar masked subtitle, remuxes a new audio track alongside existing tracks (preserving originals), and writes a separate remuxed file in the same folder named `Movie Title (YYYY) {edition-Censorr}.mkv` (does not overwrite the original). Language selection chooses non‑SDH/non‑CC English subtitles (by name/code or empty title), merges any English "Forced" track, and falls back to SDH/CC only when no non‑Forced English subtitles exist.

18. Preset config, tv: Given the preset named `tv`, when I run `censorr process "/data/media/tv/<show>/<episode>.mkv" --preset tv`, then the same pipeline as movies runs with the same language selection and outputs (sidecar subtitle next to the video; new muted audio track embedded). When output mode is REMUX_NEW_FILE, the destination path is computed by a configurable destination policy (e.g., a tagged subfolder variant or a separate censored library root). Episode outputs MUST NOT get a movie edition tag.

19. Preset fallback and explicit language: Given `--language xx` is provided with a preset, then selection targets that language using the same non‑SDH preference and forced‑merge rules; if no non‑Forced subtitles exist, SDH/CC for that language are used as a fallback; if nothing exists for that language, the run fails fast unless config enables a broader fallback.

20. Backup on remux (in-place only): Given the `--backup` option (or corresponding config) and output mode REMUX_ORIGINAL_VIDEO, when the remux step replaces the original container in place, then a copy of the original file with `.bak` suffix is created in the same directory before replacement. When output mode is REMUX_NEW_FILE, no backup is needed because the original is preserved untouched.

21. New-file destination: subfolder_tag policy: Given episodic media and output mode REMUX_NEW_FILE with destination policy "subfolder_tag", when processing `TV/General/Only Murders in the Building/Season 1/S01E01.mkv`, then the remux is written to `TV/General/Only Murders in the Building [Censorr]/Season 1/S01E01.mkv` (creating the tagged show folder if necessary), and the original remains untouched.

22. New-file destination: separate_root policy: Given episodic media and output mode REMUX_NEW_FILE with destination policy "separate_root" and root name `TV/Censorr`, when processing `TV/General/Only Murders in the Building/Season 1/S01E01.mkv`, then the remux is written to `TV/Censorr/Only Murders in the Building/Season 1/S01E01.mkv` (creating directories as needed), and the original remains untouched.

23. Per-word fuzzy threshold and aggressive variant detection: Given a profanity list that specifies the word "fuck" with a custom per-word fuzzy threshold and an aggressive variant-detection mode, when subtitles contain variants not explicitly listed (e.g., "fuckable", "motherfucker", "fuckin'", hyphenated/compounded forms), then masking MUST detect and mask these variants without requiring each variant to be enumerated. The QC step MUST report zero residual matches for these terms under default conditions, and the report MUST include the effective per-word threshold and variant strategy used.

### Edge Cases
 - No subtitles available in the requested language: by default, the pipeline fails fast with a clear error if masking is requested and no compatible subtitles exist. If the target excludes masking and either (a) audio-only muting is requested with externally supplied mute windows or (b) no cleaning is requested, the pipeline proceeds accordingly.
- Multiple tracks match the selector: by default select all; if first-only is specified, select only the highest-priority match.
 - Forced-only requested but only main subs exist: default behavior is to fall back to the best matching main subtitle in the requested language, logging the fallback decision. If --strict-selector is set, the pipeline fails instead.
- Fuzzy matching catches substrings within benign words (false positives): provide a safe-list mechanism and audit logging.
- Subtitles contain mixed encodings or malformed cues: auto-normalize to UTF-8 and correct numbering; in strict mode, abort.
- Long silence windows or dense cue overlaps: ensure remuxing preserves A/V sync and subtitle cue validity.
- Container without embedded subs but external sidecar present: allow selection of sidecar files per policy.
 - Multi-language libraries: default language is 'en' (English) if not specified. Users can override per-run via --language and/or structured selectors.
 - Track naming consistency across players: embedded tracks are titled "<Language Name> [CLEAN]" (e.g., "English [CLEAN]"). Sidecar subtitles default to filename pattern "<Title>.<lang>.clean.srt" (e.g., "Movie.en.clean.srt"). Audio tracks embedded in containers are titled "<Language Name> (Clean Muted)".
 - QC false positives and allow-list interaction: Allow-listed terms MUST not trigger QC failures. QC uses the same normalized matching and word-boundary handling as masking. A configurable sample limit controls how many example excerpts per term are logged in the report.
 - Subtitle titles may be missing, localized, or inconsistent: when title is null/empty, treat as "unknown" and allow inclusion via filters (e.g., include null/empty as "main/full"). When multiple naming variants exist (e.g., "English Forced", "Forced English"), title filtering SHOULD support substring and/or regex matching to cover common patterns.
 - Hearing‑impaired synonyms and markers: SDH/HI/CC variants (e.g., "[SDH]", "(HI)", "Hearing Impaired", "Closed Captions") SHOULD be recognized for exclusion when the user requests to exclude SDH/HI. Recognition MAY rely on configurable lists and simple normalization (case-insensitive, brackets/parentheses stripped).
 - Only SDH/HI track present for requested language: if user requested exclusion of SDH/HI and no non‑SDH tracks exist, selector behavior MUST be explicit: either fail with a clear message (strict) or proceed by selecting the best available SDH/HI track (fallback), according to a user‑visible policy/flag.
- Both muted and extracted audio present for a track: packaging MUST pick muted audio; if none exists, fall back to extracted and record the decision in logs.
- No subtitles selected for embedding while sidecar is enabled: pipeline MUST still emit the masked subtitle sidecar if available and skip embedding.
 - Plex edition naming: For MOVIE outputs only, a single edition tag `{edition-Censorr}` MUST be present exactly once. If another edition (e.g., `{edition-Director's Cut}`) pre-exists in the source filename, the system MUST leave it unchanged and MUST NOT add `{edition-Censorr}` (configurable override MAY allow replacement in future – out of scope now).
 - Sidecar naming normalization: Sidecar subtitle filenames MUST normalize whitespace and punctuation in the base title (collapse consecutive spaces, trim) and use lowercase ISO 639-1 language code. The censorship tag MUST be one of `.censorr` (preferred) or `.clean` (alias) as configured; default is `.censorr`.
 - Duplicate sidecar handling: If a sidecar with the target name already exists and content differs (checksum mismatch), the system MUST append a numeric suffix before the extension (e.g., `.censorr-2.srt`). If content matches, it MUST skip writing a duplicate and log that it was reused.
 - Episode handling: EPISODE outputs MUST NOT receive an edition tag and MUST keep conventional episode naming; their sidecar subtitles MUST adopt the same `<base>.<lang>.<tag>.srt` pattern (e.g., `Show Name - S01E03.en.censorr.srt`).

## Requirements (mandatory)

### Functional Requirements
- FR-001 (Pipeline composition; maps REQ-001): The system MUST support composing a pipeline of extract, process, and package steps where each step consumes and produces well-defined artifacts. Operations MUST be composable as long as input/output artifact types align, and typical flows MUST include video → subtitle → processed subtitle → packaged video and video → audio → muted audio → packaged video.
	Pipelines MAY conclude after producing a processed subtitle artifact or a muted audio artifact without remux, depending on requested targets.
- FR-002 (Artifact abstraction; maps REQ-002): Interactions between steps MUST occur via immutable Artifact types (VIDEO, AUDIO, SUBTITLE). Each Artifact MUST carry metadata such as format, codec, language, and flags. The pipeline MUST validate artifact compatibility before execution.
- FR-003 (Input substitution; maps REQ-003): Users MUST be able to provide external subtitle and/or audio files to bypass extraction (e.g., via flags or config). The system MUST validate compatibility (language, timing format, container compatibility) before proceeding.
- FR-004 (Operation discovery; maps REQ-004): Help output MUST list available operations with a brief description of expected input and produced output artifacts.
- FR-005 (Subtitle selection; maps REQ-025): Users MUST be able to specify subtitle selection criteria (e.g., language and forced flag). If multiple tracks match, the system selects all unless configured to select only the first.
- FR-006 (Subtitle merging & interleaving; maps REQ-026, REQ-028): When multiple subtitle tracks are selected and merging is enabled, the system MUST combine them into a single subtitle artifact, interleaving cues by start timestamp, preserving overlaps, and removing duplicates where text is identical.
- FR-007 (Subtitle format preservation; maps REQ-029): Merged or processed subtitles MUST output as a valid file in the chosen format (SRT or WEBVTT). SRT outputs MUST renumber sequentially starting at 1; WEBVTT outputs MUST contain valid cue formatting and ordered timestamps. A configuration option MUST allow choosing the output subtitle format.
- FR-008 (Subtitle error handling; maps REQ-030): The system MUST attempt to recover from common subtitle issues (missing/duplicate sequence numbers, overlapping/out-of-order timestamps, mixed encodings) by normalizing and correcting where possible. A strict mode MUST cause the pipeline to fail fast on malformed inputs with descriptive errors.
- FR-009 (Subtitle error logging; maps REQ-031): All corrections and unrecoverable errors MUST be captured in an audit log with before/after details. Users MUST be able to direct this log to stdout or a file.
- FR-010 (Subtitle selector specification; maps REQ-032): Users MUST be able to express structured subtitle selectors via CLI flags or JSON configuration, including language, forced flag, and preference ranking. Multiple selectors MAY be combined. When multiple tracks match a selector, all are chosen unless configured to select only the first. Selectors are applied in priority order provided by the user.
- FR-011 (Audio selector specification; maps REQ-033): Users MUST be able to express audio selectors via CLI flags or JSON configuration, including language, codec, role, and priority. Multiple selectors MAY be combined and applied in priority order.
- FR-012 (Unified track selector model; maps REQ-034): A common selector model MUST be used across track types, distinguishing VIDEO, AUDIO, and SUBTITLE via a type field and validating allowable fields per type. Structured selectors MUST be validated against a published schema located at `selector.schema.json` in the repository root; the CLI validates `--selectors-json` inputs against this schema.
- FR-013 (Audio extraction; maps REQ-040): Given a VIDEO, the system MUST support extraction of audio tracks, preserving codec or re-encoding when requested by configuration.
- FR-014 (Audio muting; maps REQ-041): Given AUDIO and SUBTITLE artifacts, the system MUST mute audio segments that align with selected subtitle timings containing censored terms. The muted output remains otherwise unchanged.
- FR-015 (Packaging/remux; maps REQ-050): The system MUST allow packaging/remuxing VIDEO with one or more AUDIO and SUBTITLE artifacts into a single playable output, preserving codecs unless re-encoding is requested.
- FR-016 (Arr integration trigger): The system MUST support invocation by Radarr/Sonarr on Import/Download events. Triggering defaults to media items tagged with any of ["clean", "censor"] on the movie/series in Radarr/Sonarr. For Custom Script, standard environment fields are consumed (e.g., event type, path, media type). For Webhook, JSON payload must include title, path, and tags. Tags in Radarr/Sonarr determine trigger; Ombi/Overseerr propagate via those platforms' tag workflows.
- FR-017 (Masking policy): The system MUST support both "full" masking (all letters replaced) and "partial" masking (all but first letter replaced) for censored words in subtitle text, selectable by configuration and/or request. Default is "partial" globally; per-language overrides are supported via config (e.g., overrides.en=partial, overrides.es=full).
- FR-018 (Fuzzy matching): The system MUST recognize variations of profane terms including spacing, punctuation, and common misspellings to reduce misses while minimizing false positives. Defaults: case-insensitive matching; text normalization (whitespace/punctuation); token-based fuzzy threshold 85/100; word-boundary regex to avoid substring false positives; bad-word dictionary loaded from user config (YAML/JSON); an allow-list (safe-list) takes precedence to prevent masking/muting of whitelisted terms. A global default fuzzy threshold MUST be configurable.

- FR-075 (Per-word profanity configuration): The profanity list MUST support both simple string entries and structured objects for per-word overrides. Structured entries MUST allow specifying at least: the base term (word), an optional `fuzzy_threshold` override for that term, and a `variant_strategy` with values `default` or `aggressive`. When unspecified, terms inherit the global default threshold and the `default` variant strategy. Backward compatibility: lists of strings remain valid and use global defaults.

- FR-076 (Aggressive variant detection for family terms): When a term’s `variant_strategy=aggressive`, the system MUST match common morphological and compounding variants not explicitly listed (e.g., for "fuck": "fuckable", "fucking", "motherfucker", "motherfuckers", "fuckin'", hyphenated/concatenated forms), while still respecting word-boundary semantics to avoid benign substrings. The system MUST minimize false positives via normalization and allow-list precedence, and MUST surface any collisions in the QC report for review.

- FR-077 (Per-word observability): QC and masking audit logs/reports MUST include, for each matched profane term, the effective fuzzy threshold and variant strategy used (global vs per-word override) to aid in tuning.

- FR-078 (Selector/QC consistency): The post-mask subtitle QC MUST use the same per-word thresholds and variant strategies as masking so that residual detections are meaningful. Overrides (e.g., allow-list) MUST apply consistently across masking and QC.
- FR-019 (Track naming): Cleaned artifacts MUST present clear and consistent track names in players. Embedded subtitle title: "<Language Name> [CLEAN]" (e.g., "English [CLEAN]"). Embedded audio title: "<Language Name> (Clean Muted)". Sidecar subtitle filename default: "<Title>.<lang>.clean.srt" (e.g., "Movie.en.clean.srt").
	- NOTE (Selector philosophy): Avoid adding one-off CLI exclusion flags (e.g., `--exclude-sdh`). Such exclusions MUST be expressed in structured selector configuration (JSON/YAML) via explicit exclusion lists or lower-priority fallback selectors.

Remux packaging behavior (audio prioritization, subtitle modes, and sidecar)
- FR-049 (Remux audio prioritization): The packaging/remux step MUST prefer muted audio artifacts over extracted audio for the same track. If a muted variant is unavailable, it MUST fall back to the extracted variant in a documented priority order (muted > extracted) and log the choice.
- FR-050 (Remux subtitle inclusion modes): The system MUST support a subtitle inclusion mode with options: masked_only (default) to include only the final post-merge masked subtitle; all to include all provided subtitle artifacts; none to exclude subtitles entirely. The chosen mode MUST be surfaced via CLI/config and reflected in logs.
- FR-051 (Subtitle sidecar on remux): When enabled, the packaging/remux step MUST write the final masked subtitle as a sidecar adjacent to the remuxed video using Plex-discoverable naming, regardless of whether subtitles are embedded. This refines FR‑044 by specifying behavior during packaging.
 - FR-054 (Standardized sidecar naming): The system MUST generate sidecar subtitle filenames following Plex-friendly convention: `<base>.<lang>.<tag>.srt` where `<base>` equals the video base filename (without any existing edition tag), `<lang>` is lowercase ISO 639-1 language code, and `<tag>` defaults to `censorr` (configurable alias `clean`). Additional ordering rules: language ALWAYS precedes the censorship tag; forced or SDH variants (if ever exported) would appear as `<base>.<lang>.forced.<tag>.srt` or `<base>.<lang>.sdh.<tag>.srt` (future extension – not required to implement forced/SDH export now). Filenames MUST avoid duplicate dots (collapse) and MUST normalize whitespace in `<base>` (collapse spaces, trim). If a file of the same name exists with identical checksum, reuse; if different, append numeric incremental suffix before `.srt`.
 - FR-055 (Plex Edition tag for movie remux outputs): For MOVIE remux outputs only, the resulting media filename MUST include a single edition tag `{edition-Censorr}` placed after the canonical `Title (Year)` segment and before any quality or other tokens. If the source filename already contains any edition tag (pattern `{edition-*}`), the system MUST leave it unchanged and log that an edition was already present. The process MUST be idempotent (re-running will not add additional edition tags). EPISODE outputs MUST NOT receive this tag.
 - FR-056 (Audio codec parity): Remuxed outputs MUST preserve original selected audio track codec, channel layout, and sample rate when embedding either extracted or muted audio, unless an explicit re-encode directive is provided. Post-remux validation MUST confirm parity (via probe) and log discrepancies as warnings (or fail in strict mode).
 - FR-056a (Preset-driven audio parameter parity): When a preset enables "audio_transcode_to_original", the remux step MUST re-encode the processed audio to match the original selected audio stream’s parameters by default: codec, channel layout, sample rate, and bitrate. CLI flags MAY override any of these (e.g., --audio-target-codec, --audio-channels, --audio-bitrate). The system MUST probe and capture original audio parameters up front and carry them through to remux.
 - FR-057 (Ephemeral intermediate cleanup): Intermediate artifacts (extracted audio, merged-but-unmasked subtitles, temporary muted audio) MUST be deleted after successful downstream consumption unless a persistence flag is set (`--persist-intermediate`). On failure, intermediates MUST be retained.
 - FR-058 (Final destination relocation): After successful pipeline completion (QC passes or overrides), the final remuxed video and any associated sidecars MUST be moved from the working directory to an optional configured final destination. Move SHOULD use atomic rename when possible; otherwise copy+verify+remove. Failures MUST leave originals intact.
 - FR-059 (Selector config precedence): Structured selector configuration (JSON/YAML) MUST take precedence over ad-hoc CLI selection tweaks. Convenience exclusion flags SHOULD NOT be introduced; users express ordering and exclusion explicitly in selectors.

Presets and Config-driven Defaults
- FR-065 (Config file and presets): The CLI MUST support a configuration file at `config/censorr.json` (with existing precedence rules) that can define named presets (e.g., `movies`, `tv`). A preset specifies a pipeline (list of operations), default flags, selector configuration, and output policies. CLI `--preset <name>` loads and applies that preset.
- FR-066 (Preset pipelines): The built-in recommended presets `movies` and `tv` MUST execute the pipeline: `extract_subtitles,merge_subtitles,mask_subtitles,extract_audio,mute_audio,audio_quality_check,remux` and enable `--create-subtitle-sidecar` and `--profanity-list-file config/profanity_list.json` by default. Presets MUST embed the muted audio as an additional track (preserving existing tracks) and write the sidecar masked subtitle.
- FR-067 (Language selection rules): For the target language (default `en` unless overridden), subtitle selection MUST prefer non‑SDH/non‑CC tracks identified by title/name/description or language code; include and merge any Forced track of the same language; if no non‑Forced subtitles exist, fall back to SDH/CC; document detection patterns (configurable list).
- FR-068 (Default invocation): With a valid preset, users SHOULD be able to run only: `censorr process <video> --preset <movies|tv>` and achieve the default pipeline and outputs. CLI arguments MUST override preset/config values when both are provided.
- FR-069 (In-place remux and backup option): When output mode is REMUX_ORIGINAL_VIDEO, the remux step replaces the original video in place after successful pipeline completion (consistent with FR‑058 final move when unset). When `--backup` is provided (or enabled in config), a copy `<filename>.bak` MUST be created next to the original before replacement. Replacement MUST be atomic where possible; on failure, the original MUST remain intact.
- FR-071 (Output mode configuration): The system MUST support a configurable output mode with two values: `REMUX_ORIGINAL_VIDEO` (overwrite original in place per FR‑069) and `REMUX_NEW_FILE` (write a new remux path; original is preserved). The output mode MUST be settable via config and overridable via CLI, and may be specified per preset.
- FR-072 (Movies new-file behavior): When output mode is `REMUX_NEW_FILE` for MOVIE media, the remux MUST be written to the same directory as the source with the filename pattern `Movie Title (YYYY) {edition-Censorr}.mkv` (FR‑055). This operation MUST be non-destructive; the original file remains.
- FR-073 (New-file destination policies and templating): When output mode is `REMUX_NEW_FILE`, the destination path MUST be computed by a configurable destination policy. The system MUST support at least two policies: `subfolder_tag` (append a configurable tag, e.g., `[Censorr]`, to a collection/series folder name) and `separate_root` (write under a configurable censored library root, e.g., `TV/Censorr`). The policy MUST be configurable globally and per preset, and MUST be reusable across titles via a template with tokens (e.g., `{library_root}/{collection}{tag}/{season}/{episode}` for episodic media). The system MUST create missing directories.
- FR-074 (New-file idempotency and conflicts): When output mode is `REMUX_NEW_FILE` and a target file already exists, the system MUST: (a) reuse if content matches (checksum), or (b) resolve per policy: overwrite, fail, or write with numeric suffix (configurable). The choice MUST be logged and tests MUST cover all policies.

Validation and Tests
- FR-070 (End-to-end preset tests): The project MUST include end-to-end tests demonstrating the preset pipelines (`movies` and `tv`) on small fixtures, verifying: language selection behavior (non‑SDH preference, forced merge, SDH fallback), sidecar creation and naming, muted audio track embedding, and in-place replacement with optional backup.

Filename Processing & Output Management Audit Requirements
- FR-061 (Edition tagging audit): The system MUST log edition tag decisions including: movie vs episode detection logic, presence of existing edition tags, edition tag application (or skip), final output filename. Logs MUST use structured format with operation context.
- FR-062 (Sidecar collision audit): The system MUST log sidecar collision handling including: target sidecar path, existence check results, content comparison (identical/different), collision resolution strategy (reuse/numeric suffix), final sidecar path used.
- FR-063 (Filename normalization audit): The system MUST log filename processing steps including: input filename, whitespace normalization, edition tag extraction/removal for base name, language code formatting, final computed sidecar name, path validation results.
 
Runtime Observability Enhancements
- FR-064 (FFmpeg heartbeat & timestamped progress): For any FFmpeg invocation classified as potentially long-running (heuristics: presence of filter graphs `-af`/`-vf`, codec transforms `-acodec`/`-vcodec`, complex mapping `-map`, mute window application, or explicit context flag), the system MUST emit periodic heartbeat log lines until process completion. Each heartbeat line MUST include (a) ISO-8601 UTC timestamp, (b) elapsed wall-clock time since command start (human friendly, e.g. `elapsed=32s`), (c) succinct operation context (e.g., `context="muting audio track 1 (eng)"`), and (d) a stable marker token (e.g., `HEARTBEAT`) to facilitate log scraping. Default heartbeat intervals:
	- Mute audio (<=50 windows): 8s
	- Mute audio (>50 windows): 5s (adaptive shorter interval for higher complexity)
	- Remux operations: 6s
	- Audio extraction: 8s
	- Subtitle extraction: 12s
	The first heartbeat MUST appear no later than the configured interval after FFmpeg start; heartbeats MUST cease immediately upon process termination (success or failure). Heartbeats MUST coexist with legacy verbose phrases expected by tests (e.g., "Applying mute windows"), MUST NOT interleave partial lines, and MUST be written to both stdout (user visibility) and the structured execution log (FR-034). A configuration flag or environment variable (e.g., `CENSORR_NO_HEARTBEAT=1`) MAY disable heartbeats (principle of test determinism) but defaults to enabled. This requirement strengthens Observability (NFR-009) without altering functional outputs.

Audio quality verification for muted outputs
- FR-052 (Audio quality check): After the muting operation, the system MUST run an audio quality check that verifies attenuation across all mute windows (e.g., energy reduction below a configurable threshold). It MUST write a machine‑readable report to the working directory and summarize results to the execution log. By default, insufficient attenuation in any window causes the pipeline to fail with a clear message and a link to the report.
- FR-053 (Audio QC override flag): The CLI MUST provide an override (e.g., "--continue-on-audio-qc-fail") that allows the pipeline to proceed despite audio QC failures. When set, the step logs a warning, writes the report, and the pipeline continues; the run’s exit status remains success.

Additional Functional Requirements (planning, execution, CLI, and extensibility)
- FR-020 (Operation contract): The system MUST represent each pipeline step as an Operation with a declared name, declared input artifact types, declared output artifact types, and a standard run() contract that accepts inputs, a working directory, and execution flags (dry-run, verbose) and returns produced artifacts.
- FR-021 (Typed artifacts): Data passed between operations MUST be modeled as typed Artifacts carrying type, path, and metadata, enabling validation and compatibility checks.
- FR-022 (Operation registry): The system MUST maintain a registry of available Operations and which artifact types they produce to support discovery and planning.
- FR-023 (Planner): Given requested targets and any user-provided artifacts, the system MUST compute an ordered plan of operations that can produce the targets, omitting producers for already-provided artifacts and failing clearly if no producer exists.
- FR-024 (Producer selection policy): When multiple operations can produce the same artifact type, planning MUST choose a producer according to a configurable priority policy (defaulting to registration order) and allow users to override.
- FR-025 (Executor/orchestrator): The system MUST execute the planned operations in order, passing produced artifacts downstream and writing outputs into a working directory, honoring dry-run (no side effects) and verbose modes, and raising informative errors if required inputs are missing.
- FR-026 (CLI entry points): The CLI MUST accept flags to specify provided inputs and targets (e.g., --video, --subtitles, --target, --workdir, --dry-run, --verbose, --sidecar-tag) and invoke the planner and executor accordingly, returning a success exit code on completion.
- FR-027 (Preemption/fallback): When user-supplied artifacts exist for required types, planning MUST treat them as satisfied and not schedule any producer for those types; integration tests MUST demonstrate that e.g., supplying subtitles causes extraction to be omitted.
- FR-028 (Adapters for external tools): Operations that invoke external tools MUST do so via dedicated adapters that encapsulate argument building, escaping, timeouts, and error parsing to keep operations testable.
- FR-029 (Operation strategies): Where multiple algorithms exist for the same operation, users MUST be able to select a strategy via configuration or CLI, and operations MUST adapt behavior accordingly.
- FR-030 (Deterministic workdir layout): All intermediate and final outputs MUST be written under a configurable working directory using deterministic names derived from inputs and operation purpose.
- FR-031 (Manifest and caching): The system SHOULD maintain a manifest in the working directory capturing input/output checksums per operation and MAY use it for debugging visibility (inputs/outputs, parameters, checksums). Use of the manifest for automatic skipping is optional.
- FR-032 (Idempotency): Re-running the pipeline with unchanged inputs MUST be safe and produce identical outputs; automatic skip of unchanged steps is OPTIONAL (debug manifest retained even if skipping is disabled by default).
- FR-033 (Error handling for external tools): On non-zero exits from external tools, the system MUST capture stdout/stderr in per-operation logs within the working directory, fail with a clear message, and preserve any existing artifacts.
- FR-034 (Observable execution log): The system MUST emit a structured execution log in the working directory with per-operation entries (start/end times, exit codes, stdout/stderr references, produced artifact paths).
- FR-035 (Dry-run and explain): The CLI MUST support a dry-run that prints the planned operations without creating files, and an explain mode that describes why each operation was selected during planning.
- FR-036 (Skip/force step controls): The CLI MUST accept controls to skip a planned operation or force re-execution of specific operations even when cached.
- FR-037 (Parallelism): Where the dependency graph permits, the system SHOULD execute independent operations concurrently, with a user-configurable parallelism level, and results MUST match serial execution.
- FR-038 (Plugin discovery): At startup, the system SHOULD load additional operations from a configured plugins source and register them into the operation registry.
- FR-039 (Unit testability): Each Operation MUST be unit-testable in isolation with temporary working directories and mocked adapters.
- FR-040 (CLI listing and documentation): The CLI MUST provide operation discovery (e.g., --list-ops) and helpful usage (--help) documentation including flags and brief operation descriptions.
- FR-041 (Validation of provided artifacts): When users supply external artifacts, the system MUST validate existence and basic compatibility (format/parseability) and fail with helpful errors if invalid.
- FR-042 (Acceptance tests and fixtures): The project SHOULD include small sample fixtures and end-to-end acceptance tests that exercise common planning and execution flows, including manifest generation (even if skip optimization disabled).
- FR-043 (Extensibility): Adding a new operation MUST be possible by implementing the Operation contract and registering it, without modifying planner or executor code.

- FR-044 (Local subtitle export): Users MUST be able to export processed/masked subtitles as a sidecar file adjacent to the media using Plex-discoverable naming conventions; embedding into the container remains optional and configurable.
- FR-045 (Subtitle quality check): After masking completes, the system MUST automatically perform a quality-check pass that scans the processed subtitle using case-insensitive regex based on the same configured bad-words patterns (after applying any allow-list/safe-list). The QC MUST:
	- Report residual matches with counts, example excerpts (up to N samples per term), and cue indices/timestamps for auditing.
	- Write a machine-readable QC report under the working directory and summarize to the execution log.
	- Fail the pipeline by default if any residual matches are detected, with a clear failure message pointing to the QC report.
	- Respect allow-listed terms so they do not contribute to residual failures.
	- Be deterministic and run regardless of whether subsequent steps (e.g., remux) are requested.
	(See FR-047 for an override flag to continue the pipeline on QC failures.)
- FR-046 (External mute windows): Users MUST be able to provide external mute windows (e.g., JSON/CSV of [start,end] times) to drive audio-only muting when no subtitle artifact is present; the muting operation MUST accept either subtitle-derived or externally supplied timing windows.
- FR-047 (QC override flag): The CLI MUST provide a flag to continue the pipeline despite QC failures (residual matches). When this flag is set, QC results are treated as a soft failure: the pipeline proceeds, exit status remains success, and a warning is logged with a pointer to the QC report. The flag MUST be clearly documented (e.g., "--continue-on-qc-fail"). If both configuration and CLI specify behavior, the CLI MUST take precedence for that run.

Note: FR‑047 applies to subtitle QC. FR‑053 provides a parallel override for audio QC.

- FR-048 (Subtitle title & metadata filtering): Users MUST be able to filter subtitle tracks by title patterns and metadata in addition to language and forced flag, to precisely select English "full" + English "forced" tracks while excluding hearing‑impaired (SDH/HI/CC) tracks from merges.
	- Title filtering MUST support simple substring contains (any-of list) and an optional regex mode; matching is case-insensitive and applies after basic normalization (trim, collapse whitespace, strip surrounding brackets/parentheses).
	- Exclusion filters MUST allow specifying SDH/HI/CC markers via a convenience toggle (e.g., exclude SDH) and/or explicit patterns; exclusion takes precedence over inclusion when both match.
	- Forced disposition MUST be available from track metadata (e.g., container disposition flags) and addressable via selector criteria; combining criteria MUST support: include non‑forced "main/full" (null/empty or generic title) AND include forced; exclude hearing‑impaired.
	- When multiple tracks match inclusion and are not excluded, the system MUST select all (or the highest‑priority only when configured) and merge them chronologically per FR‑006.
	- Behavior MUST be documented with examples, and acceptance tests MUST demonstrate selecting English full + English forced while excluding SDH/HI.

Traceability for additional requirements
- FR-020 ↔ Operation contract (addendum REQ-001)
- FR-021 ↔ Typed artifacts (addendum REQ-002)
- FR-022 ↔ Operation registry (addendum REQ-003)
- FR-023 ↔ Planner (addendum REQ-004)
- FR-024 ↔ Planner producer selection (addendum REQ-005)
- FR-025 ↔ Executor/orchestrator (addendum REQ-006)
- FR-026 ↔ CLI entry points (addendum REQ-007)
- FR-027 ↔ Preemption/fallback (addendum REQ-008)
- FR-028 ↔ Adapters for external tools (addendum REQ-009)
- FR-029 ↔ Strategy support for ops (addendum REQ-010)
- FR-030 ↔ Deterministic workdir layout (addendum REQ-011)
- FR-031 ↔ Manifest and caching (addendum REQ-012)
- FR-032 ↔ Idempotency (addendum REQ-013)
- FR-033 ↔ Error handling/unwanted behavior (addendum REQ-014)
- FR-034 ↔ Observable execution log (addendum REQ-015)
- FR-035 ↔ Dry-run and explain mode (addendum REQ-016)
- FR-036 ↔ Skip/force step controls (addendum REQ-017)
- FR-037 ↔ Parallelism (addendum REQ-018)
- FR-038 ↔ Plugin discovery (addendum REQ-019)
- FR-039 ↔ Unit testability (addendum REQ-020)
- FR-040 ↔ CLI listing and documentation (addendum REQ-021)
- FR-041 ↔ Validation of provided artifacts (addendum REQ-022)
- FR-042 ↔ Acceptance tests / fixtures (addendum REQ-023)
- FR-043 ↔ Extensibility (addendum REQ-024)

### Key Entities (include if feature involves data)
- Artifact (VIDEO, AUDIO, SUBTITLE): Conceptual units produced/consumed by pipeline steps; immutable once created; include metadata such as language, codec/format, channel/layout (for audio), forced flag (for subtitles), and user-visible naming attributes.
- Selector: Structured filter and prioritization model with common fields (type, language, role, codec, forced, prefer, firstOnly, priority) with type-specific validation and ordering semantics. Subtitle selectors are extended to include title-based include/exclude patterns (substring/regex) and a convenience flag to exclude hearing‑impaired (SDH/HI/CC) tracks.
- Pipeline Step (Operation): A unit that declares required input artifact types and produced output artifact types; validated at composition time; examples include extract, process (mask/mute), and package/remux.
- Audit Log Entry: Records of corrections, normalization steps, errors, and decisions (e.g., selector results), including before/after context and timestamps.

- Profanity Term (config entity): Represents an entry in the profanity list; either a simple string or an object with fields: `word: string`, optional `fuzzy_threshold: number`, optional `variant_strategy: "default"|"aggressive"`. Global defaults apply when fields are omitted. This entity is configuration-only and drives matcher behavior without prescribing implementation details.

---

## Non-Functional Requirements

- NFR-001 (KISS & Simplicity): Designs MUST remain as simple as possible to meet current needs. Additional layers/patterns require documented rationale in the plan/spec.
- NFR-002 (Single Responsibility): Operations and modules MUST have one clear purpose. Complex behavior MUST be composed from small units.
- NFR-003 (Composition over Inheritance): Prefer composition and explicit wiring over inheritance hierarchies.
- NFR-004 (Explicit Contracts): Public contracts (artifacts, selectors, ops) MUST be explicitly documented; the public surface area is minimal and stable.
- NFR-005 (Plugin-First Extensibility): New behaviors SHOULD be added via a registry-backed plugin API without modifying core planner/executor logic.
- NFR-006 (YAGNI & Documented Complexity): Avoid speculative features. Any added abstraction MUST be justified and recorded in "Complexity Tracking" within the plan.
- NFR-007 (Test-First & Doc-Driven): Features MUST land with tests and updated docs (spec/quickstart/contracts). No implementation without failing tests first in the workflow.
- NFR-008 (Container-Native Compatibility): Tooling SHOULD run cleanly in common homelab contexts (Linux, Docker/Podman). CLI MUST be primary; any HTTP/automation layer MUST call the same contracts.
- NFR-009 (Observability & Auditability): Structured logs and audit trails MUST be produced for operations and corrections; logs are written under workdir with stable fields.
- NFR-010 (Idempotency & Dry-Run): Pipeline MUST be safe to re-run (outputs reproducible) and support a dry-run showing planned operations. Manifest supports debugging; skip optimization optional.
- NFR-011 (Deterministic Outputs): Workdir layout and filenames MUST be deterministic based on inputs/op purpose.
- NFR-012 (Documentation Deliverables): Each feature MUST update quickstart and operation help text; selector schema reference MUST be included when selectors are exposed.

---

## Review & Acceptance Checklist
Content Quality
- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

Requirement Completeness
- [ ] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous  
- [x] Success criteria are measurable
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

Constitution Gates
- [ ] KISS: Is there a simpler equivalent design documented?
- [ ] SRP: Do operations have one clear purpose each?
- [ ] Composition: Are behaviors composed rather than inherited?
- [ ] Explicit Contracts: Are public inputs/outputs documented and minimal?
- [ ] Plugin-First: Can extensions be added without core changes?
- [ ] YAGNI: Any added abstraction justified in plan’s Complexity Tracking?
- [ ] Test-First & Docs: Tests precede implementation and docs updated?
- [ ] Observability: Structured logs/audit coverage present?
- [ ] Idempotency/Dry-Run: Repeatable with dry-run showing planned actions?

Dependencies & Assumptions (non-exhaustive)
- Integration events will supply enough metadata to identify media, language, and tags. [Assumption]
- Player environments (Plex) will display multiple audio/subtitle tracks and selected naming formats consistently. [Assumption]
- Source media contains at least one of: embedded subtitles, external sidecar subtitles, or externally provided subtitles; otherwise masking is not applicable. [Assumption]

---

## Execution Status
Updated during spec creation

- [x] User description parsed
- [x] Key concepts extracted
- [x] Ambiguities marked
- [x] User scenarios defined
- [x] Requirements generated
- [x] Entities identified
- [ ] Review checklist passed

---

