"""Synthetic lavfi media fixtures for integration tests.

No binary media is checked into git; everything here is synthesized by
ffmpeg at test time (see .sop/planning/research/test-fixtures.md in the
Censorr2 repo for the generation approach). Fixtures are built once per
pytest session into a session-scoped tmp dir.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

# Words drawn from censorr/wordlists/default.json, so mute-window and
# masking assertions in later steps can target exact known timestamps.
PROFANITY_ENTRIES: list[tuple[float, float, str]] = [
    (2.0, 3.0, "This is such a fuck up"),
    (6.0, 7.5, "What the shit is that"),
    (10.0, 11.0, "This entry is perfectly clean"),
]

CLEAN_ENTRIES: list[tuple[float, float, str]] = [
    (2.0, 3.0, "This is a perfectly ordinary line"),
    (6.0, 7.5, "Nothing profane happens here either"),
]

SPANISH_ENTRIES: list[tuple[float, float, str]] = [
    (2.0, 3.0, "Esto es una prueba"),
    (6.0, 7.5, "Otra linea limpia"),
]


class FixtureUnavailableError(RuntimeError):
    """Raised when a fixture recipe cannot be synthesized with ffmpeg CLI alone."""


def _run_ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def _srt_timestamp(seconds: float) -> str:
    hours, rem = divmod(seconds, 3600)
    minutes, rem = divmod(rem, 60)
    secs, frac = divmod(rem, 1)
    millis = round(frac * 1000)
    return f"{int(hours):02d}:{int(minutes):02d}:{int(secs):02d},{millis:03d}"


def write_dialogue_srt(
    path: Path, entries: list[tuple[float, float, str]] = PROFANITY_ENTRIES
) -> Path:
    lines = []
    for i, (start, end, text) in enumerate(entries, start=1):
        lines.append(str(i))
        lines.append(f"{_srt_timestamp(start)} --> {_srt_timestamp(end)}")
        lines.append(text)
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def build_movie_fixture(
    root: Path,
    duration: float = 15.0,
    entries: list[tuple[float, float, str]] = PROFANITY_ENTRIES,
) -> Path:
    """`Test Movie (2024).mkv`: 1 video, 1 aac audio, 1 embedded English SRT.

    Pass `entries=CLEAN_ENTRIES` for a zero-match fixture (R16 clean mode).
    """
    movie_dir = root / "Test Movie (2024)"
    movie_dir.mkdir(parents=True, exist_ok=True)
    srt = write_dialogue_srt(movie_dir / "dialogue.srt", entries=entries)
    out = movie_dir / "Test Movie (2024).mkv"
    _run_ffmpeg(
        "-f", "lavfi", "-i", f"testsrc2=duration={duration}:size=320x180:rate=10",
        "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={duration}",
        "-i", str(srt),
        "-map", "0:v", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "35",
        "-map", "1:a", "-c:a", "aac", "-b:a", "64k",
        "-map", "2:0", "-c:s", "srt",
        "-metadata:s:s:0", "language=eng", "-metadata:s:s:0", "title=English",
        str(out),
    )
    return out


def build_episode_fixture(root: Path, duration: float = 15.0) -> Path:
    """`Test Show - s01e01.mkv` under `Test Show/Season 01/`."""
    season_dir = root / "Test Show" / "Season 01"
    season_dir.mkdir(parents=True, exist_ok=True)
    srt = write_dialogue_srt(root / "episode_dialogue.srt")
    out = season_dir / "Test Show - s01e01.mkv"
    _run_ffmpeg(
        "-f", "lavfi", "-i", f"testsrc2=duration={duration}:size=320x180:rate=10",
        "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={duration}",
        "-i", str(srt),
        "-map", "0:v", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "35",
        "-map", "1:a", "-c:a", "aac", "-b:a", "64k",
        "-map", "2:0", "-c:s", "srt",
        "-metadata:s:s:0", "language=eng",
        str(out),
    )
    return out


def build_multi_subtitle_fixture(root: Path, duration: float = 15.0) -> Path:
    """1 audio + 3 subtitle tracks: en, en (SDH-titled), es."""
    fixture_dir = root / "multi_subtitle"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    srt_en = write_dialogue_srt(fixture_dir / "en.srt")
    srt_sdh = write_dialogue_srt(fixture_dir / "en_sdh.srt")
    srt_es = write_dialogue_srt(fixture_dir / "es.srt", entries=SPANISH_ENTRIES)
    out = fixture_dir / "Multi Subtitle Test.mkv"
    _run_ffmpeg(
        "-f", "lavfi", "-i", f"testsrc2=duration={duration}:size=320x180:rate=10",
        "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={duration}",
        "-i", str(srt_en), "-i", str(srt_sdh), "-i", str(srt_es),
        "-map", "0:v", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "35",
        "-map", "1:a", "-c:a", "aac", "-b:a", "64k",
        "-map", "2:0", "-map", "3:0", "-map", "4:0", "-c:s", "srt",
        "-metadata:s:s:0", "language=eng", "-metadata:s:s:0", "title=English",
        "-metadata:s:s:1", "language=eng", "-metadata:s:s:1", "title=English (SDH)",
        "-disposition:s:1", "hearing_impaired",
        "-metadata:s:s:2", "language=spa", "-metadata:s:s:2", "title=Espanol",
        str(out),
    )
    return out


def build_multi_audio_fixture(root: Path, duration: float = 15.0) -> Path:
    """1 video + aac stereo audio + ac3 5.1 audio + 1 English SRT."""
    fixture_dir = root / "multi_audio"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    srt = write_dialogue_srt(fixture_dir / "dialogue.srt")
    out = fixture_dir / "Multi Audio Test.mkv"
    _run_ffmpeg(
        "-f", "lavfi", "-i", f"testsrc2=duration={duration}:size=320x180:rate=10",
        "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={duration}",
        "-i", str(srt),
        "-filter_complex",
        "[1:a]pan=stereo|FL=c0|FR=c0[a2ch];"
        "[1:a]pan=5.1|FL=c0|FR=c0|FC=c0|LFE=c0|BL=c0|BR=c0[a51]",
        "-map", "0:v", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "35",
        "-map", "[a2ch]", "-c:a:0", "aac", "-b:a:0", "64k",
        "-map", "[a51]", "-c:a:1", "ac3", "-b:a:1", "192k",
        "-map", "2:0", "-c:s", "srt",
        "-metadata:s:a:0", "language=eng", "-metadata:s:a:0", "title=English Stereo",
        "-metadata:s:a:1", "language=eng", "-metadata:s:a:1", "title=English 5.1",
        "-metadata:s:s:0", "language=eng",
        str(out),
    )
    return out


def build_eac3_51_fixture(root: Path, duration: float = 15.0) -> Path:
    """1 video + eac3 5.1 audio + 1 embedded English SRT (R13 codec preservation)."""
    fixture_dir = root / "eac3_51"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    srt = write_dialogue_srt(fixture_dir / "dialogue.srt")
    out = fixture_dir / "EAC3 51 Test.mkv"
    _run_ffmpeg(
        "-f", "lavfi", "-i", f"testsrc2=duration={duration}:size=320x180:rate=10",
        "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={duration}",
        "-i", str(srt),
        "-filter_complex", "[1:a]pan=5.1|FL=c0|FR=c0|FC=c0|LFE=c0|BL=c0|BR=c0[a51]",
        "-map", "0:v", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "35",
        "-map", "[a51]", "-c:a", "eac3", "-b:a", "448k",
        "-map", "2:0", "-c:s", "srt",
        "-metadata:s:a:0", "language=eng",
        "-metadata:s:s:0", "language=eng",
        str(out),
    )
    return out


def build_no_subtitle_fixture(root: Path, duration: float = 10.0) -> Path:
    """1 video + 1 audio, no subtitle tracks at all."""
    fixture_dir = root / "no_subtitle"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    out = fixture_dir / "No Subtitle Test.mkv"
    _run_ffmpeg(
        "-f", "lavfi", "-i", f"testsrc2=duration={duration}:size=320x180:rate=10",
        "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={duration}",
        "-map", "0:v", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "35",
        "-map", "1:a", "-c:a", "aac", "-b:a", "64k",
        "-metadata:s:a:0", "language=eng",
        str(out),
    )
    return out


def build_language_mismatch_fixture(root: Path, duration: float = 15.0) -> Path:
    """Japanese audio + English subtitles (R16 subtitles-only mode trigger)."""
    fixture_dir = root / "language_mismatch"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    srt = write_dialogue_srt(fixture_dir / "dialogue.srt")
    out = fixture_dir / "Language Mismatch Test.mkv"
    _run_ffmpeg(
        "-f", "lavfi", "-i", f"testsrc2=duration={duration}:size=320x180:rate=10",
        "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={duration}",
        "-i", str(srt),
        "-map", "0:v", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "35",
        "-map", "1:a", "-c:a", "aac", "-b:a", "64k",
        "-map", "2:0", "-c:s", "srt",
        "-metadata:s:a:0", "language=jpn",
        "-metadata:s:s:0", "language=eng",
        str(out),
    )
    return out


def build_pgs_only_fixture(root: Path) -> Path:
    """Bitmap-only subtitle fixture (PGS/VOBSUB), per design R12.

    Not buildable with ffmpeg CLI alone: its subtitle encoders only convert
    text-to-text or bitmap-to-bitmap ("Subtitle encoding currently only
    possible from text to text or bitmap to bitmap") -- there is no CLI-only
    path to rasterize a synthetic SRT into dvd_subtitle/hdmv_pgs_subtitle
    without an external rendering pipeline. Per the implementation plan's
    documented escape hatch (Step 3), bitmap-exclusion is covered by Step 5's
    unit tests over synthetic MediaInfo objects instead of an ffmpeg-built
    fixture; this function documents why no integration fixture exists yet.
    """
    raise FixtureUnavailableError(build_pgs_only_fixture.__doc__ or "")


@pytest.fixture(scope="session")
def fixture_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("censorr_fixtures")


@pytest.fixture(scope="session")
def movie_fixture(fixture_root: Path) -> Path:
    return build_movie_fixture(fixture_root)


@pytest.fixture(scope="session")
def clean_movie_fixture(fixture_root: Path) -> Path:
    clean_root = fixture_root / "clean"
    clean_root.mkdir(exist_ok=True)
    return build_movie_fixture(clean_root, entries=CLEAN_ENTRIES)


@pytest.fixture(scope="session")
def qc_pass_fixture(fixture_root: Path) -> Path:
    """Same 2 profane windows as movie_fixture but a much longer runtime,
    so the mute ratio stays within the default 5% QC budget -- movie_fixture
    itself (15s, ~22% mute ratio) legitimately fails that budget and is used
    for over-mute-budget QC failure tests instead.
    """
    qc_root = fixture_root / "qc_pass"
    qc_root.mkdir(exist_ok=True)
    return build_movie_fixture(qc_root, duration=90.0)


@pytest.fixture(scope="session")
def episode_fixture(fixture_root: Path) -> Path:
    return build_episode_fixture(fixture_root)


@pytest.fixture(scope="session")
def multi_subtitle_fixture(fixture_root: Path) -> Path:
    return build_multi_subtitle_fixture(fixture_root)


@pytest.fixture(scope="session")
def multi_audio_fixture(fixture_root: Path) -> Path:
    return build_multi_audio_fixture(fixture_root)


@pytest.fixture(scope="session")
def eac3_51_fixture(fixture_root: Path) -> Path:
    return build_eac3_51_fixture(fixture_root)


@pytest.fixture(scope="session")
def no_subtitle_fixture(fixture_root: Path) -> Path:
    return build_no_subtitle_fixture(fixture_root)


@pytest.fixture(scope="session")
def language_mismatch_fixture(fixture_root: Path) -> Path:
    return build_language_mismatch_fixture(fixture_root)
