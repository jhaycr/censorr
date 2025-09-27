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

## Troubleshooting
- FFmpeg not found: ensure `ffmpeg` command is available.
- Selector schema errors: validate your JSON against `selector.schema.json`.
- Malformed subtitles: use `--strict` to fail fast, or default normalization will attempt to recover.

## Next steps
- See `spec.md` for full requirements
- See `plan.md` and `research.md` for design context
- When ready, generate tasks and start implementation