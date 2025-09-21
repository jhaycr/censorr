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
censorr --video "/path/movie.mkv" \
  --target subtitle --language en \
  --masking partial --export-sidecar \
  --dry-run --explain

# Audio-only with external mute windows
censorr --audio "/path/movie.en.dts" \
  --mute-windows windows.json \
  --target audio --dry-run --explain
```

## Troubleshooting
- FFmpeg not found: ensure `ffmpeg` command is available.
- Selector schema errors: validate your JSON against `selector.schema.json`.
- Malformed subtitles: use `--strict` to fail fast, or default normalization will attempt to recover.

## Next steps
- See `spec.md` for full requirements
- See `plan.md` and `research.md` for design context
- When ready, generate tasks and start implementation