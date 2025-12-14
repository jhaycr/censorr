# Censorr: Plex/Arr Clean Media Tool

A CLI tool for censoring audio and subtitles in media files, designed to integrate with Plex and Arr (Radarr/Sonarr) ecosystems.

## Features

- **Composable Pipeline**: Extract, process, and package media components
- **Fuzzy Matching**: Intelligent profanity detection with customizable word lists
- **Multiple Formats**: Support for SRT/WEBVTT subtitles and various audio codecs
- **Arr Integration**: Custom Script and Webhook support for Radarr/Sonarr
- **Dry-Run Mode**: Preview operations before execution
- **Audit Logging**: Comprehensive operation tracking and error handling

## Quick Start

### Docker Compose (Recommended)

The easiest way to run Censorr as a long-running service:

```bash
# Clone the repository
git clone <repository-url>
cd Censorr2

# Start the service (builds locally from Dockerfile)
docker compose up -d

# Run processing jobs (use container paths: /data/media/movies or /data/media/tv)
docker exec censorr-cli censorr process "/data/media/movies/Movie Name (2024)/Movie.mkv" --preset movies --output /app/workdir/output

# Stop the service
docker compose down
```

#### Environment Configuration

Censorr runs with sensible defaults. Optionally copy `env.template` to `.env` to customize:

```bash
cp env.template .env
# Edit .env as needed
```

| Variable | Default | Description |
|----------|---------|-------------|
| `MEDIA_PATH_TV` | `/mnt/media/tv` | Host path for TV shows |
| `MEDIA_PATH_MOVIES` | `/mnt/media/movies` | Host path for movies |
| `WORKDIR_PATH` | `/srv/censorr/work` | Host path for work/output |
| `CONFIG_PATH` | `/srv/censorr/config` | Host path for config |
| `TZ` | `UTC` | Container timezone |
| `UID` | `1000` | User ID for file permissions |
| `GID` | `1000` | Group ID for file permissions |
| `CENSORR_VERBOSE` | `false` | Enable verbose logging |

#### Radarr/Sonarr Integration

Add a Custom Script in your Arr application:

**Path**: `/usr/local/bin/docker`  
**Arguments**: `exec censorr-cli censorr process "{{file_path}}" --preset movies --output /app/workdir/output --force`

**Note**: Radarr/Sonarr will pass the host path in `{{file_path}}`. Make sure your Arr application's root folders match the paths you've mounted in docker-compose (e.g., `/mnt/media/movies` on host maps to `/data/media/movies` in container).

Or use webhook integration:
```bash
# Example webhook trigger
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "source": "radarr",
    "eventType": "Download",
    "tags": {"censorr_profile": "movies", "censorr_preset": "movies"},
    "mediaPaths": ["/data/media/movies/Movie Name (2024)/Movie.mkv"]
  }'
```

### Native Installation

For development or non-containerized deployments:

#### Prerequisites
- Python 3.11+
- FFmpeg installed and available on PATH

#### Installation
```bash
# Clone and install
git clone <repository-url>
cd Censorr2
pip install -e .

# Or install dev dependencies
pip install -e .[dev]
```

#### Basic Usage
```bash
# Extract and clean subtitles only
censorr --video movie.mkv --target subtitle --language en --dry-run

# Full pipeline: clean subtitles and mute audio
censorr --video movie.mkv --target video --language en --masking partial

# Audio-only with external mute windows
censorr --audio movie.en.dts --mute-windows windows.json --target audio
```

#### Track Pruning

By default, the final remux will include only censored/clean tracks (muted audio and masked subtitles). To include all processed tracks:

```bash
# Disable pruning to keep all audio and subtitle tracks
censorr process movie.mkv --preset movies --no-prune-non-clean-tracks

# Or configure in config/censorr.json preset flags:
# "prune_non_clean_tracks": false
```

When pruning is enabled (default):
- **Audio**: Only the first muted audio track is retained
- **Subtitles**: Only the first masked subtitle is retained
- **Movies**: Output is tagged with `{edition-Censorr}` for Plex
- **Episodes**: No edition tag applied

This produces clean-only remuxes ideal for family viewing while preserving original files.

## Development

See `specs/001-write-a-tool/` for detailed requirements, implementation plan, and development tasks.

### Running Tests
```bash
pytest
```

### Code Quality
```bash
black src tests
ruff check src tests
mypy src
```

## License

MIT License - see LICENSE file for details.