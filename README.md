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

# Run processing jobs
docker exec censorr censorr process /data/media/movies/movie.mkv --output /app/workdir/output

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
**Arguments**: `exec censorr censorr process "{{file_path}}" --operations extract_subtitles,merge_subtitles,mask_subtitles,extract_audio,mute_audio,remux --output /app/workdir/output --language en --create-subtitle-sidecar --force`

Or use webhook integration:
```bash
# Example webhook trigger
curl -X POST http://your-webhook-server/censorr \
  -H "Content-Type: application/json" \
  -d '{"file_path": "/data/media/movies/movie.mkv", "language": "en"}'
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