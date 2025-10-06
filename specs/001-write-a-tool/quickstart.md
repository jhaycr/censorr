# Quickstart: Plex/Arr Clean Censor Tool

This guide shows how to set up the environment and run the CLI in dry-run to see the planned pipeline.

## Prerequisites
- Linux with Python 3.11+
- FFmpeg installed and available on PATH

## Install Python dependencies (recommended venv)
```
python -m venv .venv
source .venv/bin/activate
pip install rapidfuzz pysubs2 pydantic typer PyYAML
```

## Example inputs
- Video: /media/Movie (2020)/Movie (2020).mkv
- External bad-words config: badwords.yaml
- Selectors JSON: selectors.json (validated against selector.schema.json)

## Dry-run planning examples
- Subtitle-only clean (export sidecar):
  - Provide video and target SUBTITLE; merge full+forced, mask, export sidecar.
- Audio-only mute with external windows:
  - Provide audio and external windows; mute and stop (no remux).

## CLI examples (conceptual)
```
# Subtitle-only
censorr process "/path/movie.mkv" \
  --output /work/output --language en \
  --create-subtitle-sidecar \
  --dry-run

# Audio-only with external mute windows
censorr process "/path/movie.mkv" \
  --mute-windows windows.json \
  --operations extract_audio,mute_audio \
  --dry-run

# Select English full + forced while excluding SDH using structured selectors
# (preferred over ad-hoc CLI toggles)
censorr process "/path/movie.mkv" \
  --language en \
  --selectors-json selectors.en.full_plus_forced.json \
  --operations extract_subtitles,merge_subtitles,mask_subtitles \
  --dry-run

# Using regex to select specific subtitle tracks
censorr process "/path/movie.mkv" \
  --language en \
  --subtitle-title-regex "English.*(Forced|Full)" \
  --dry-run
```

## Naming Outputs (FR-054 / FR-055)
- Movie remux output (if edition absent): `Movie Title (2024) {edition-Censorr}.mkv`
- Sidecar masked subtitle (movie): `Movie Title (2024).en.censorr.srt`
- Sidecar masked subtitle (episode): `Show Name - S01E03.en.censorr.srt` (no edition tag)
- Alternate tag alias example (if configured to use clean): `Movie Title (2024).en.clean.srt`

Idempotency: Re-running will not duplicate `{edition-Censorr}` nor rewrite identical sidecar files.

## Quality Check (QC) Behavior

After subtitle masking, the tool automatically runs a quality check to detect any residual profanity that wasn't properly masked:

### Default Behavior (Strict Mode)
```bash
# QC failure will abort the pipeline by default
censorr process "/path/movie.mkv" \
  --language en \
  --operations mask_subtitles \
  --dry-run
# If residual matches found: ERROR and pipeline stops
```

### Override to Continue on QC Failure
```bash
# Continue pipeline despite QC failures
censorr process "/path/movie.mkv" \
  --language en \
  --continue-on-qc-fail \
  --operations mask_subtitles
# QC failures logged but pipeline continues
```

### QC Report Format
When QC detects residual matches, a detailed report is generated at `{workdir}/qc_report.json`:

```json
{
  "terms": [
    {
      "term": "damn",
      "count": 2,
      "samples": [
        {
          "cue_index": 15,
          "start": 123.45,
          "end": 126.78,
          "excerpt": "This is still damn good after masking...",
          "matched_token": "damn",
          "matched_term": "damn"
        }
      ]
    }
  ],
  "totals": {
    "residual_matches": 2,
    "unique_terms": 1,
    "sampled_cues": 1
  },
  "metadata": {
    "timestamp": "2025-01-27T10:30:00Z",
    "input_file": "/path/to/masked_subtitles.srt",
    "matcher_threshold": 85.0
  }
}
```

### Allow-List Handling
The QC process respects the same allow-list as the masking operation:
- Terms in allow-list contexts (e.g., "Hell's Kitchen") are not flagged as residual matches
- QC report includes `allowlist_filtered` count when applicable

## Container Usage

Censorr can be run in a container (Docker/Podman) for isolated execution:

## Configuration System

Censorr supports configuration files to set defaults for common options. The configuration hierarchy is:

1. Custom config file (via `--config` option)
2. Project-local config: `config/censorr.json`
3. User-global config: `~/.config/censorr/config.json`
4. Built-in defaults

### Default Configuration

By default, Censorr automatically excludes SDH/hearing-impaired subtitles using the following patterns:
- `["sdh", "hi", "cc"]`

This means you no longer need to specify `--subtitle-title-exclude "sdh,hi,cc"` for basic SDH filtering.

### Example Configuration File

Create `config/censorr.json` in your project:

```json
{
  "output": "./output",
  "verbose": true,
  "subtitle_title_exclude": ["sdh", "hi", "cc", "commentary"],
  "language": "en",
  "subtitle_mode": "masked_only",
  "sidecar_tag": "clean",
  "jobs": 4,
  "presets": {
    "movies": {
      "operations": [
        "extract_subtitles",
        "merge_subtitles",
        "mask_subtitles",
        "extract_audio",
        "mute_audio",
        "audio_quality_check",
        "remux"
      ],
      "flags": {
        "create_subtitle_sidecar": true,
        "profanity_list_file": "config/profanity_list.json"
      },
      "language_selector": { "prefer_non_sdh": true },
  "output": { "in_place": false, "embed_muted_audio": true, "output_mode": "REMUX_NEW_FILE" },
      "backup_default": false
    },
    "tv": {
      "operations": [
        "extract_subtitles",
        "merge_subtitles",
        "mask_subtitles",
        "extract_audio",
        "mute_audio",
        "audio_quality_check",
        "remux"
      ],
      "flags": {
        "create_subtitle_sidecar": true,
        "profanity_list_file": "config/profanity_list.json"
      },
      "language_selector": { "prefer_non_sdh": true },
      "output": { "in_place": false, "embed_muted_audio": true, "output_mode": "REMUX_NEW_FILE" },
      "destination_policy": {
        "policy": "subfolder_tag",
        "tag": "[Censorr]"
      },
      "backup_default": false
    }
  }
}
```

### Configuration Options

All CLI options can be set in the config file:
- `output`: Default output directory
- `verbose`: Enable verbose output by default
- `subtitle_title_exclude`: Default subtitle exclusion patterns
- `language`: Default language filter
- `jobs`: Default number of parallel jobs
- `subtitle_mode`: How to handle subtitles in remux (`all`, `masked_only`, `none`)
- `sidecar_tag`: Tag for sidecar filenames (`censorr` or `clean`)

CLI arguments always override config file values.

### Using Configuration

```bash
# Uses config defaults (including SDH exclusion)
censorr process movie.mkv --language en

# Override config with CLI args
censorr process movie.mkv --config ./custom-config.json --verbose

# CLI args override config values
censorr process movie.mkv --subtitle-title-exclude "different,patterns"
```

### Preset Examples

```bash
# Minimal default pipeline for movies preset
censorr process "/data/media/movies/Movie (2024).mkv" --preset movies

# TV preset, explicit language override (CLI overrides preset/config)
censorr process "/data/media/tv/Show/S01E03.mkv" --preset tv --language es

# In-place remux with backup of original
censorr process "/data/media/movies/Movie (2024).mkv" --preset movies --backup

# New-file to separate censored root
censorr process "/data/media/tv/Show/S01E03.mkv" --preset tv --output-mode REMUX_NEW_FILE \
  --dest-policy separate_root --dest-separate-root "/data/media/TV/Censorr"
```

### Basic Container Examples

#### Docker
```bash
# Build the image
docker build -t censorr .

# Dry-run example
docker run --rm \
  -v /path/to/media:/media:ro \
  -v $(pwd)/output:/app/workdir \
  censorr \
  process /media/movie.mkv \
  --output /app/workdir \
  --language en \
  --dry-run

# Full processing with sidecar
docker run --rm \
  -v /path/to/media:/media:ro \
  -v $(pwd)/output:/app/workdir \
  censorr \
  process /media/movie.mkv \
  --output /app/workdir \
  --language en \
  --create-subtitle-sidecar \
  --continue-on-qc-fail
```

#### Podman
```bash
# Build the image
podman build -t censorr .

# Run with SELinux labels (recommended on RHEL/Fedora)
podman run --rm \
  --security-opt label=disable \
  -v /path/to/media:/media:ro,Z \
  -v $(pwd)/output:/app/workdir:Z \
  censorr \
  process /media/movie.mkv \
  --output /app/workdir \
  --language en \
  --dry-run
```

### Volume Mounts

- **`/media`**: Mount your media directory (read-only recommended)
- **`/app/workdir`**: Mount output directory for processed files
- **`/app/config`**: Mount configuration directory (optional)

### Environment Variables

Map CLI flags to environment variables:
- `CENSORR_VERBOSE=true` → `--verbose`
- `CENSORR_DRY_RUN=true` → `--dry-run`
- `CENSORR_NO_HEARTBEAT=1` → Disable heartbeat logging

### Docker Compose

See `examples/compose.yaml` for complete Docker Compose configuration with multiple service examples.

### Container Troubleshooting

- **Permission Issues**: Ensure mounted directories are writable by UID/GID 10001
- **SELinux (RHEL/Fedora)**: Use `:Z` volume labels or `--security-opt label=disable`
- **FFmpeg Missing**: The container includes FFmpeg; if issues persist, check base image
- **Memory Limits**: Large media files may require increased container memory limits

## Troubleshooting
- FFmpeg not found: ensure `ffmpeg` command is available.
- Selector schema errors: validate your JSON against `selector.schema.json`.
- Malformed subtitles: use `--strict` to fail fast, or default normalization will attempt to recover.

## Next steps
- See `spec.md` for full requirements
- See `plan.md` and `research.md` for design context
- When ready, generate tasks and start implementation