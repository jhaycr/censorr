from pathlib import Path

import pytest

from censorr.media.probe import probe
from tests.fixtures import FixtureUnavailableError, build_pgs_only_fixture

pytestmark = pytest.mark.ffmpeg


def test_probe_movie_fixture(movie_fixture: Path) -> None:
    info = probe(movie_fixture)

    assert info.duration_s == pytest.approx(15.0, abs=0.5)
    assert len(info.video_streams()) == 1
    assert len(info.audio_streams()) == 1
    assert len(info.subtitle_streams()) == 1

    assert info.video_streams()[0].codec_name == "h264"

    audio = info.audio_streams()[0]
    assert audio.codec_name == "aac"

    subtitle = info.subtitle_streams()[0]
    assert subtitle.codec_name == "subrip"
    assert subtitle.language == "eng"
    assert subtitle.title == "English"


def test_probe_episode_fixture(episode_fixture: Path) -> None:
    assert episode_fixture.parent.name == "Season 01"
    assert episode_fixture.parent.parent.name == "Test Show"

    info = probe(episode_fixture)

    assert len(info.video_streams()) == 1
    assert len(info.audio_streams()) == 1
    assert len(info.subtitle_streams()) == 1


def test_probe_multi_subtitle_fixture(multi_subtitle_fixture: Path) -> None:
    info = probe(multi_subtitle_fixture)
    subs = info.subtitle_streams()

    assert len(subs) == 3
    assert subs[0].language == "eng"
    assert subs[0].title == "English"
    assert subs[1].language == "eng"
    assert subs[1].title == "English (SDH)"
    assert subs[1].disposition.get("hearing_impaired") is True
    assert subs[2].language == "spa"
    assert subs[2].title == "Espanol"


def test_probe_multi_audio_fixture(multi_audio_fixture: Path) -> None:
    info = probe(multi_audio_fixture)
    audios = info.audio_streams()

    assert len(audios) == 2
    assert audios[0].codec_name == "aac"
    assert audios[0].title == "English Stereo"
    assert audios[1].codec_name == "ac3"
    assert audios[1].title == "English 5.1"


def test_probe_no_subtitle_fixture(no_subtitle_fixture: Path) -> None:
    info = probe(no_subtitle_fixture)

    assert info.subtitle_streams() == []
    assert len(info.audio_streams()) == 1


def test_probe_language_mismatch_fixture(language_mismatch_fixture: Path) -> None:
    info = probe(language_mismatch_fixture)

    assert info.audio_streams()[0].language == "jpn"
    assert info.subtitle_streams()[0].language == "eng"


def test_pgs_only_fixture_is_documented_unavailable(tmp_path: Path) -> None:
    with pytest.raises(FixtureUnavailableError):
        build_pgs_only_fixture(tmp_path)
