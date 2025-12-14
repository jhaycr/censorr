---
inclusion: always
---

# Project Conventions

This document defines naming conventions, code organization, and project-specific patterns for Censorr.

## Project Structure

### Standard Layout
```
censorr/
├── src/                    # Source code
│   ├── cli/               # CLI entry points
│   ├── lib/               # Core libraries
│   ├── services/          # Business logic services
│   ├── models/            # Data models and types
│   ├── ops/               # Pipeline operations
│   └── utils/             # Utility functions
├── tests/                 # Test suite
│   ├── contract/          # Contract tests
│   ├── integration/       # Integration tests
│   ├── e2e/              # End-to-end tests
│   └── unit/             # Unit tests
├── config/                # Configuration files
│   ├── censorr.json      # Main config
│   └── profanity_list.json
├── docs/                  # Documentation
├── .kiro/                # Kiro specs and steering
│   ├── specs/            # Feature specifications
│   └── steering/         # Development guidelines
└── examples/             # Usage examples
```

## Naming Conventions

### Files and Directories
- **Python modules**: `snake_case.py`
- **Test files**: `test_<module_name>.py`
- **Config files**: `kebab-case.json` or `kebab-case.yaml`
- **Documentation**: `kebab-case.md`

### Code Elements

#### Python
```python
# Classes: PascalCase
class FuzzyMatcher:
    pass

# Functions/methods: snake_case
def extract_subtitles(video_path: Path) -> List[Subtitle]:
    pass

# Constants: UPPER_SNAKE_CASE
MAX_QUEUE_SIZE = 100
DEFAULT_THRESHOLD = 85

# Private members: _leading_underscore
def _internal_helper():
    pass

# Type aliases: PascalCase
SubtitleTrack = Dict[str, Any]
```

#### CLI Commands
```bash
# Commands: kebab-case
censorr process
censorr queue-status

# Flags: kebab-case with double dash
--dry-run
--output-mode
--subtitle-title-exclude

# Short flags: single letter
-v  # verbose
-o  # output
-l  # language
```

### Operations and Artifacts

#### Operation Names
Use noun-verb pattern for clarity:
```python
# Good
subtitle_extract
subtitle_merge
subtitle_mask
audio_extract
audio_mute
video_remux

# Avoid
extract_subtitles  # verb-noun (less clear)
mask               # missing context
```

#### Artifact Types
Use uppercase enum-style names:
```python
class ArtifactType(Enum):
    VIDEO = "video"
    AUDIO = "audio"
    SUBTITLE = "subtitle"
```

## Code Organization Patterns

### Library Structure
Each library should be self-contained:

```python
# src/lib/fuzzy_matcher.py
"""
Fuzzy matching library for profanity detection.

This library provides fuzzy string matching with configurable
thresholds and variant detection strategies.
"""

class FuzzyMatcher:
    """Main matcher class."""
    
    def __init__(self, terms: List[str], threshold: int = 85):
        """Initialize matcher with terms and threshold."""
        pass
    
    def matches(self, text: str) -> bool:
        """Check if text contains any matching terms."""
        pass

# Public API
__all__ = ['FuzzyMatcher']
```

### Service Structure
Services coordinate libraries:

```python
# src/services/subtitle_processor.py
"""
Subtitle processing service.

Coordinates subtitle extraction, merging, and masking operations.
"""

from src.lib.fuzzy_matcher import FuzzyMatcher
from src.lib.subtitle_parser import SubtitleParser

class SubtitleProcessor:
    """Processes subtitles through the pipeline."""
    
    def __init__(self, config: Config):
        self.matcher = FuzzyMatcher(config.profanity_terms)
        self.parser = SubtitleParser()
    
    def process(self, video: Path) -> Subtitle:
        """Extract, merge, and mask subtitles."""
        pass
```

### CLI Structure
CLI is a thin layer over services:

```python
# src/cli/main.py
"""
Censorr CLI entry point.

Provides command-line interface to all Censorr functionality.
"""

import typer
from src.services.subtitle_processor import SubtitleProcessor

app = typer.Typer()

@app.command()
def process(
    video: Path,
    preset: str = typer.Option(None, help="Processing preset"),
    dry_run: bool = typer.Option(False, help="Show plan without executing")
):
    """Process video file with censoring pipeline."""
    processor = SubtitleProcessor.from_preset(preset)
    processor.process(video, dry_run=dry_run)
```

## Configuration Patterns

### Configuration Files
Use hierarchical configuration with clear precedence:

1. CLI arguments (highest priority)
2. Project config: `config/censorr.json`
3. User config: `~/.config/censorr/config.json`
4. Built-in defaults (lowest priority)

### Configuration Schema
```python
# src/models/config.py
from pydantic import BaseModel, Field

class Config(BaseModel):
    """Main configuration model."""
    
    output: Path = Field(default=Path('./output'))
    verbose: bool = Field(default=False)
    language: str = Field(default='en')
    
    class Config:
        # Allow extra fields for forward compatibility
        extra = 'allow'
```

## Error Handling Patterns

### Exception Hierarchy
```python
# src/lib/exceptions.py
class CensorrError(Exception):
    """Base exception for all Censorr errors."""
    pass

class ValidationError(CensorrError):
    """Configuration or input validation failed."""
    pass

class ProcessingError(CensorrError):
    """Error during media processing."""
    pass

class FFmpegError(ProcessingError):
    """FFmpeg operation failed."""
    
    def __init__(self, message: str, exit_code: int):
        super().__init__(message)
        self.exit_code = exit_code
```

### Error Messages
Provide actionable error messages:

```python
# Good
raise ValidationError(
    "Preset 'movies' not found in config. "
    "Available presets: tv, movies-strict. "
    "Check config/censorr.json or use --list-presets."
)

# Bad
raise ValidationError("Invalid preset")
```

## Logging Patterns

### Structured Logging
```python
import structlog

logger = structlog.get_logger()

# Log with context
logger.info(
    "subtitle_extraction_complete",
    video_path=str(video_path),
    track_count=len(tracks),
    language=language,
    duration_ms=elapsed_ms
)

# Log errors with details
logger.error(
    "ffmpeg_failed",
    command=cmd,
    exit_code=result.returncode,
    stderr=result.stderr[:500]  # Truncate long output
)
```

### Log Levels
- **DEBUG**: Detailed diagnostic information
- **INFO**: Normal operation events (extraction complete, job queued)
- **WARNING**: Unexpected but handled situations (fallback used, QC warning)
- **ERROR**: Operation failures that prevent completion

## Documentation Patterns

### Module Docstrings
```python
"""
Module name and purpose.

Longer description of what this module does and how it fits
into the larger system.

Example:
    >>> from src.lib.fuzzy_matcher import FuzzyMatcher
    >>> matcher = FuzzyMatcher(['damn', 'hell'])
    >>> matcher.matches('This is damn good')
    True
"""
```

### Function Docstrings
```python
def extract_subtitles(
    video: Path,
    language: str,
    output_dir: Path
) -> List[Subtitle]:
    """
    Extract subtitle tracks from video file.
    
    Args:
        video: Path to input video file
        language: ISO 639-1 language code (e.g., 'en')
        output_dir: Directory for extracted subtitle files
    
    Returns:
        List of extracted Subtitle objects
    
    Raises:
        ValidationError: If video file doesn't exist
        FFmpegError: If extraction fails
    
    Example:
        >>> subtitles = extract_subtitles(
        ...     Path('movie.mkv'),
        ...     language='en',
        ...     output_dir=Path('./output')
        ... )
        >>> len(subtitles)
        2
    """
    pass
```

## Type Hints

### Use Type Hints Consistently
```python
from typing import List, Dict, Optional, Union
from pathlib import Path

def process_video(
    video_path: Path,
    preset: Optional[str] = None,
    dry_run: bool = False
) -> Dict[str, Any]:
    """Process video with type-safe interface."""
    pass

# Use type aliases for complex types
SubtitleTrack = Dict[str, Union[str, int, bool]]
ProcessingResult = Dict[str, Any]
```

## Testing Patterns

### Fixture Organization
```python
# tests/conftest.py
import pytest
from pathlib import Path

@pytest.fixture
def sample_video(tmp_path: Path) -> Path:
    """Provide sample video file for testing."""
    video = tmp_path / 'sample.mkv'
    # Create or copy sample video
    return video

@pytest.fixture
def profanity_config(tmp_path: Path) -> Path:
    """Provide test profanity configuration."""
    config = tmp_path / 'profanity.json'
    config.write_text('["damn", "hell"]')
    return config
```

### Test Naming
```python
# Pattern: test_<what>_<condition>_<expected>
def test_fuzzy_matcher_detects_spelling_variations():
    pass

def test_webhook_rejects_missing_preset_tag():
    pass

def test_remux_preserves_audio_when_codec_matches():
    pass
```

## Git Commit Patterns

### Commit Message Format
```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `test`: Test additions/changes
- `refactor`: Code refactoring
- `chore`: Maintenance tasks

**Examples:**
```
feat(webhook): add tag-based filtering

Implement allowlist filtering for webhook events. Only events
containing at least one allowlisted tag are processed.

Implements: T005, T006
Refs: #123
```

```
test(subtitle): add integration tests for merge operation

Add tests verifying subtitle merging with real FFmpeg:
- Multiple tracks merged chronologically
- Duplicate cues removed
- Overlapping timestamps preserved

Implements: T012
```

## Version Control Patterns

### Branch Naming
```
feature/<issue>-<description>    # New features
fix/<issue>-<description>        # Bug fixes
refactor/<description>           # Code refactoring
docs/<description>               # Documentation
```

### Task References
Always reference completed tasks in commits:
```
Implements: T029, T030
Refs: T025 (partial)
Closes: #45
```

---

**Version:** 0.5.0 | **Last Updated:** 2025-11-02
