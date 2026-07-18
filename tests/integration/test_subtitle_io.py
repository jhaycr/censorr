import subprocess
from pathlib import Path

import pytest

from censorr.subtitles.io import load, save

pytestmark = pytest.mark.ffmpeg


def _extract_subtitle(source: Path, stream_index: int, out_path: Path) -> Path:
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(source),
            "-map", f"0:{stream_index}",
            "-c:s", "srt",
            str(out_path),
        ],
        check=True,
    )
    return out_path


def test_load_extracted_english_track(multi_subtitle_fixture: Path, tmp_path: Path) -> None:
    srt_path = _extract_subtitle(multi_subtitle_fixture, 2, tmp_path / "en.srt")

    doc = load(srt_path)

    assert len(doc.entries) == 3
    assert doc.entries[0].plaintext == "This is such a fuck up"
    assert doc.entries[0].start_s == pytest.approx(2.0, abs=0.05)
    assert doc.entries[0].end_s == pytest.approx(3.0, abs=0.05)


def test_load_extracted_spanish_track(multi_subtitle_fixture: Path, tmp_path: Path) -> None:
    srt_path = _extract_subtitle(multi_subtitle_fixture, 4, tmp_path / "es.srt")

    doc = load(srt_path)

    assert len(doc.entries) == 2
    assert doc.entries[0].plaintext == "Esto es una prueba"


def test_round_trip_save_and_reload(multi_subtitle_fixture: Path, tmp_path: Path) -> None:
    srt_path = _extract_subtitle(multi_subtitle_fixture, 2, tmp_path / "en.srt")
    doc = load(srt_path)

    resaved = tmp_path / "resaved.srt"
    save(doc, resaved)
    reloaded = load(resaved)

    assert len(reloaded.entries) == len(doc.entries)
    assert [e.plaintext for e in reloaded.entries] == [e.plaintext for e in doc.entries]
