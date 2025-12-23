# Censorr

Censorr is a command-line tool that automatically detects and masks profanity in video files. It processes video files through a multi-stage pipeline: extracting and masking subtitles, extracting and muting audio, running quality control checks, and finally remuxing the modified audio and subtitles back into the video container.

## Features

- **Subtitle Processing**: Extracts subtitles from video files, identifies profanity using configurable term lists and fuzzy matching, and masks offensive words with asterisks.
- **Audio Muting**: Extracts audio tracks, identifies profanity timings from subtitles, and mutes the corresponding audio segments using FFmpeg filters.
- **Language Selection**: Process only specific languages or exclude certain subtitle types (e.g., SDH/HoH subtitles).
- **Quality Control**: Validates that audio muting doesn't introduce clipping or normalization artifacts by checking audio levels.
- **Flexible Remuxing**: Remux processed audio and subtitles back into the original video with options for append or replace modes, plus configurable naming conventions for movie/TV show outputs.
- **Automatic Cleanup**: Optionally remove intermediate files after successful processing.
- **Fuzzy Matching**: Detect profanity variations through fuzzy string matching with configurable thresholds.

## Installation

Install from source:

```bash
pip install -e .
```

This installs the `censorr` command-line tool and its dependencies.

## Configuration

Censorr uses two configuration files:

### Profanity List (`profanity_list.json`)

A JSON array of profanity terms to detect and mask in subtitles. Each entry can be a simple string or an object with advanced options.

#### Simple Format

```json
[
  "damn",
  "hell",
  "crap"
]
```

#### Advanced Format

```json
[
  {
    "word": "damn",
    "fuzzy_threshold": 75,
    "variant_strategy": "aggressive"
  },
  {
    "word": "hell",
    "fuzzy_threshold": 95,
    "variant_strategy": "conservative"
  }
]
```

#### Options

Each profanity entry can have the following properties:

- `word` (required): The term to detect and mask.
- `fuzzy_threshold` (optional): Fuzzy matching threshold for this specific word (0-100). Controls how similar a word must be to trigger a match. Lower values detect more variations but increase false positives. Default: inherited from `--threshold` CLI option (default 85).
  - `95+`: Very strict; only near-exact matches
  - `85-94`: Balanced; catches common misspellings
  - `75-84`: Lenient; detects more variations and typos
  - `<75`: Very lenient; may catch unintended matches
- `variant_strategy` (optional): How aggressively to search for variations of the word. Options:
  - `conservative`: Only match the word exactly and very close variations (1-2 character differences)
  - `aggressive`: Match the word, common variations, and loose phonetic matches
  - Default: `conservative`

**Example**: A word with `fuzzy_threshold: 75` and `variant_strategy: "aggressive"` will catch many spelling variations and word forms of that term.

**Default location**: `config/profanity_list.json`

### Application Config (`app_config.json`)

A JSON object with application-level settings:

```json
{
  "audio_qc_threshold_db": -20.0
}
```

- `audio_qc_threshold_db`: The minimum audio level (in dB) that should be present after muting. If audio levels fall below this threshold, the audio is too quiet and may have been over-muted. Default: -20.0 dB

**Default location**: `config/app_config.json`

## Usage

The main command is `censorr run`, which processes a video file through the complete pipeline:

```bash
censorr run <input_file> [OPTIONS]
```

### Options

#### Required Arguments
- `INPUT_FILE_PATH`: Path to the video file to process (e.g., `video.mkv`)

#### Input/Output Options
- `--output, -o`: Output directory for intermediate and final files. Default: current directory
- `--remux-output-base`: Output path for the final remuxed video (without extension). By default, the remuxed video is saved to the output directory with a generated filename.

#### Language Filtering
- `--include-lang`: Process only subtitles in these languages (ISO 639-3 codes, comma-separated). Example: `en,es`
- `--exclude-lang`: Skip subtitles in these languages. Example: `pt,br`
- `--include-title`: Process only subtitles with titles matching these patterns (regex, comma-separated).
- `--exclude-title`: Skip subtitles with titles matching these patterns (regex, comma-separated).
- `--include-any`: Process subtitles matching any of the criteria (special mode).
- `--exclude-any`: Skip subtitles matching any of these criteria. Example: `SDH` to exclude Deaf/Hard of Hearing subtitles.

#### Profanity Detection
- `--config, -c`: Path to profanity list JSON file. Default: `config/profanity_list.json`
- `--threshold`: Fuzzy match threshold (0-100). Words matching within this percentage are flagged. Default: 85

#### Audio Processing
- `--qc-threshold-db`: Audio quality control threshold in dB. Overrides `app_config.json` setting.

#### Remuxing
- `--remux-mode`: How to handle existing audio tracks in the output. Options:
  - `append`: Keep original audio tracks and add the processed track (default)
  - `replace`: Remove all original audio tracks and use only the processed audio
- `--remux-naming-mode`: Naming convention for the output file. Options:
  - `movie`: Format as `Title (YYYY).ext`
  - `tv`: Format as `Title - SxxExx - Episode Name.ext` (requires season/episode info)
  - Default: based on heuristics

#### Other Options
- `--app-config`: Path to application config JSON file. Default: `config/app_config.json`
- `--cleanup`: Remove intermediate files after successful processing. Default: enabled
- `--no-cleanup`: Keep all intermediate files (useful for debugging)

### Examples

Process a video file end-to-end (full pipeline), including only English subtitles:

```bash
censorr run "movie.mkv" --include-lang en --output ./output
```

Process a video, excluding SDH subtitles and using replace mode for audio:

```bash
censorr run "movie.mkv" --exclude-any SDH --remux-mode replace --output ./output
```

Process with a custom profanity list and stricter fuzzy matching:

```bash
censorr run "episode.mkv" \
  --config ./custom_profanity.json \
  --threshold 90 \
  --include-lang en \
  --output ./output
```

Process without cleanup to keep all intermediate files:

```bash
censorr run "movie.mkv" --no-cleanup --output ./output
```

## Pipeline Overview

The `run` command executes the following stages sequentially:

1. **Subtitle Extraction & Merge**: Extracts all subtitle streams from the video file and merges them into a single subtitle file for processing.

2. **Subtitle Masking**: Scans the merged subtitle file for profanity using the configured term list. Profanity is replaced with asterisks (e.g., `hell` becomes `****`). Fuzzy matching detects variations.

3. **Audio Extraction**: Extracts audio tracks in the selected language(s) from the video file.

4. **Audio Muting**: Identifies the exact timing of profanity in audio based on subtitle timings and mutes those segments using FFmpeg audio filters.

5. **Audio Quality Control**: Validates that the muted audio doesn't contain clipping or excessive quiet sections by analyzing audio levels against the configured threshold.

6. **Video Remuxing**: Remuxes the masked subtitles and muted audio back into the original video file, using the specified remux mode (append or replace) and naming convention.

7. **Cleanup** (optional): Removes all intermediate files created during processing.


## Future Milestones

### Worker Queue System

A background worker service that processes a queue of video files, enabling batch processing and integration with media management systems.

### Webhook Integration

HTTP webhook support to automatically add videos to the processing queue based on notifications from Sonarr or Radarr, enabling fully automated profanity filtering when new media is added to your library.

## Requirements

- Python 3.8+
- FFmpeg with audio/video codec support
- FFprobe (included with FFmpeg)
- pysubs2 for subtitle handling
- RapidFuzz for fuzzy string matching
- Typer for CLI framework

## Development

Run tests:

```bash
pytest tests/
```

Run tests with coverage reporting:

```bash
pytest tests/ --cov=src/censorr --cov-report=html
```

## AI Assistance Disclosure

This project uses AI tools (including GitHub Copilot) to assist with code generation, documentation, and development tasks. All AI-generated code is reviewed, tested, and validated before being committed to ensure quality and correctness.

## License

See LICENSE file for details.