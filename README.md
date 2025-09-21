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

### Prerequisites
- Python 3.11+
- FFmpeg installed and available on PATH

### Installation
```bash
# Clone and install
git clone <repository-url>
cd Censorr2
pip install -e .

# Or install dev dependencies
pip install -e .[dev]
```

### Basic Usage
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