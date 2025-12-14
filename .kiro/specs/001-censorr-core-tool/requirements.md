# Requirements Document: Censorr Core Tool

## Introduction

Censorr is a media processing tool designed for Plex and *arr-stack (Radarr, Sonarr) ecosystems. It censors audio and subtitles in video files based on configurable profanity lists, creating clean versions suitable for family viewing while preserving the original media quality and structure.

## Glossary

- **System**: The Censorr CLI tool and its processing pipeline
- **Media File**: A video container (MKV, MP4, etc.) containing video, audio, and subtitle streams
- **Artifact**: An immutable file produced or consumed by pipeline operations (VIDEO, AUDIO, SUBTITLE)
- **Operation**: A discrete processing step in the pipeline (extract, mask, mute, remux)
- **Selector**: A filter specification for choosing tracks by language, title, codec, or other metadata
- **Profanity List**: A configuration file containing terms to censor, with optional per-word thresholds
- **Masking**: Replacing profane text in subtitles with asterisks (full or partial)
- **Muting**: Silencing audio during subtitle cue windows containing profane terms
- **Remux**: Repackaging video, audio, and subtitle streams into a new container
- **Sidecar File**: An external subtitle file stored alongside the video
- **Edition Tag**: A Plex-compatible filename marker like `{edition-Censorr}`
- **QC (Quality Check)**: Automated validation that censoring was successful

## Requirements

### Requirement 1: Pipeline Composition

**User Story:** As a CLI user, I want to compose a flexible processing pipeline from discrete operations, so that I can customize the censoring workflow for different media types and use cases.

#### Acceptance Criteria

1. WHEN a user specifies a sequence of operations, THE System SHALL execute them in order, passing artifacts between steps
2. WHEN an operation requires an artifact type that is not available, THE System SHALL fail with a clear error message
3. WHEN a user provides an external artifact (subtitle or audio file), THE System SHALL skip the extraction operation for that artifact type
4. WHEN a user requests a dry-run, THE System SHALL display the planned operations without executing them
5. THE System SHALL support at minimum these operations: subtitle_extract, subtitle_merge, subtitle_mask, audio_extract, audio_mute, audio_qc, subtitle_qc, video_remux

### Requirement 2: Track Selection

**User Story:** As a user, I want to precisely select which audio and subtitle tracks to process based on language, title, and metadata, so that I can target the correct tracks while excluding unwanted variants like SDH or commentary.

#### Acceptance Criteria

1. WHEN a user specifies a language filter, THE System SHALL select only tracks matching that language code
2. WHEN multiple subtitle tracks exist for the same language, THE System SHALL support filtering by title patterns (include/exclude)
3. WHEN a user excludes SDH/HI/CC tracks, THE System SHALL recognize common markers in track titles and exclude those tracks
4. WHEN a user requests forced subtitles, THE System SHALL detect the forced disposition flag and include those tracks
5. WHEN multiple tracks match the selection criteria, THE System SHALL select all matches unless configured for first-only mode

### Requirement 3: Subtitle Processing

**User Story:** As a user, I want to merge multiple subtitle tracks and mask profane content, so that I have a single clean subtitle file suitable for family viewing.

#### Acceptance Criteria

1. WHEN multiple subtitle tracks are selected, THE System SHALL merge them chronologically by start timestamp
2. WHEN merging subtitles, THE System SHALL remove duplicate cues with identical text and overlapping timestamps
3. WHEN masking subtitles, THE System SHALL replace profane terms with asterisks according to the configured policy (full or partial)
4. WHEN a subtitle file has formatting errors, THE System SHALL attempt to normalize and correct them unless in strict mode
5. THE System SHALL support both SRT and WEBVTT subtitle formats

### Requirement 4: Fuzzy Matching and Profanity Detection

**User Story:** As a user, I want the system to detect profanity variations and compound forms without requiring exhaustive enumeration, so that censoring is effective against creative spelling and morphological variants.

#### Acceptance Criteria

1. WHEN a profanity term is configured with aggressive variant detection, THE System SHALL match common morphological variants (e.g., "fuckable" for "fuck")
2. WHEN matching profanity, THE System SHALL use configurable fuzzy thresholds to catch misspellings and spacing variations
3. WHEN a term appears in an allow-listed context, THE System SHALL not censor it
4. WHEN matching profanity, THE System SHALL respect word boundaries to avoid false positives in benign words
5. THE System SHALL support per-word fuzzy threshold overrides in the profanity configuration

### Requirement 5: Audio Muting

**User Story:** As a user, I want to mute audio during subtitle cue windows containing profane terms, so that the audio track is clean while preserving synchronization.

#### Acceptance Criteria

1. WHEN a subtitle cue contains a censored term, THE System SHALL mute the audio for the entire duration of that cue
2. WHEN multiple mute windows overlap, THE System SHALL merge them into continuous silence regions
3. WHEN muting audio, THE System SHALL preserve the original codec, channel layout, and sample rate
4. WHEN a user provides external mute windows, THE System SHALL accept them without requiring subtitle processing
5. THE System SHALL support muting multiple audio tracks independently

### Requirement 6: Quality Assurance

**User Story:** As a user, I want automated quality checks to verify that censoring was successful, so that I can be confident no profanity slipped through.

#### Acceptance Criteria

1. WHEN subtitle masking completes, THE System SHALL automatically scan for residual profane terms
2. WHEN residual profanity is detected, THE System SHALL fail by default and generate a detailed QC report
3. WHEN audio muting completes, THE System SHALL verify that mute windows have sufficient attenuation
4. WHEN a user provides the continue-on-qc-fail flag, THE System SHALL log warnings but continue the pipeline
5. THE System SHALL write QC reports to the working directory with term counts, sample excerpts, and cue references

### Requirement 7: Output Packaging

**User Story:** As a user, I want to package censored audio and subtitles back into the video container with clear track naming, so that Plex users can easily select the clean versions.

#### Acceptance Criteria

1. WHEN remuxing, THE System SHALL embed censored audio as an additional track alongside the original
2. WHEN remuxing, THE System SHALL title embedded tracks with clear labels (e.g., "English [CLEAN]", "English (Clean Muted)")
3. WHEN creating sidecar subtitles, THE System SHALL use Plex-compatible naming (e.g., "Movie.en.censorr.srt")
4. WHEN processing a movie, THE System SHALL add a Plex edition tag `{edition-Censorr}` to the filename
5. WHEN processing a TV episode, THE System SHALL not add an edition tag

### Requirement 8: Configuration and Presets

**User Story:** As a user, I want to use presets for common workflows (movies, TV shows), so that I don't have to specify all options for every run.

#### Acceptance Criteria

1. WHEN a user specifies a preset, THE System SHALL load the configured pipeline, flags, and selector rules
2. THE System SHALL provide built-in presets for "movies" and "tv" with sensible defaults
3. WHEN CLI arguments conflict with preset values, THE System SHALL prioritize CLI arguments
4. THE System SHALL support configuration files at project and user levels with clear precedence rules
5. THE System SHALL default to excluding SDH/HI/CC subtitles unless explicitly included

### Requirement 9: Output Modes and Destinations

**User Story:** As a user, I want to choose between in-place replacement and creating new files, so that I can preserve originals or organize censored media separately.

#### Acceptance Criteria

1. WHEN output mode is REMUX_ORIGINAL_VIDEO, THE System SHALL replace the original file in place
2. WHEN output mode is REMUX_NEW_FILE, THE System SHALL create a new file and preserve the original
3. WHEN replacing in place with backup enabled, THE System SHALL create a .bak copy before replacement
4. WHEN using REMUX_NEW_FILE for TV shows, THE System SHALL support destination policies (subfolder_tag, separate_root)
5. WHEN a destination file already exists with identical content, THE System SHALL reuse it without rewriting

### Requirement 10: Observability and Debugging

**User Story:** As a user, I want detailed logs and progress indicators for long-running operations, so that I can monitor progress and troubleshoot issues.

#### Acceptance Criteria

1. WHEN executing long-running FFmpeg operations, THE System SHALL emit periodic heartbeat messages with timestamps
2. WHEN operations complete, THE System SHALL log execution time, input/output paths, and success status
3. WHEN errors occur, THE System SHALL capture stdout/stderr from external tools and reference log paths
4. THE System SHALL write a structured execution log with per-operation entries to the working directory
5. THE System SHALL support a verbose mode that provides additional diagnostic information

### Requirement 11: Idempotency and Determinism

**User Story:** As a user, I want to safely re-run the pipeline on the same inputs, so that I can recover from failures or verify results without creating duplicates.

#### Acceptance Criteria

1. WHEN re-running with unchanged inputs, THE System SHALL produce identical outputs
2. WHEN a sidecar file exists with identical content, THE System SHALL not rewrite it
3. WHEN an edition tag already exists in a filename, THE System SHALL not add a duplicate
4. THE System SHALL use deterministic naming for intermediate and final artifacts
5. THE System SHALL maintain a manifest recording input/output checksums for debugging

### Requirement 12: Container Deployment

**User Story:** As a user, I want to run Censorr in a Docker container, so that I can deploy it consistently across different environments without dependency issues.

#### Acceptance Criteria

1. THE System SHALL provide a Dockerfile that builds a minimal, non-root container image
2. THE System SHALL include FFmpeg in the container image
3. THE System SHALL support volume mounts for media input and output directories
4. THE System SHALL support environment variables mapping to CLI flags
5. THE System SHALL log to stdout/stderr for container-native observability
