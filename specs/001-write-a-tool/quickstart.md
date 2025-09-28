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

# Select English full + forced tracks while excluding SDH
censorr process "/path/movie.mkv" \
  --language en --exclude-sdh \
  --subtitle-title-include "forced" \
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