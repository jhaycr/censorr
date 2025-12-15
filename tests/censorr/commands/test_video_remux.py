import json
import subprocess
from pathlib import Path

import pytest

from censorr.commands.video_remux import VideoRemux


class FakeFFprobe:
    """Fake ffprobe for stream counting."""

    def __init__(self, cmd, capture_output=True, text=True, **kwargs):
        self.cmd = cmd
        self.returncode = 0

    def communicate(self):
        return ("", "")


class FakeFFprobeWithStreams(FakeFFprobe):
    """Fake ffprobe that returns stream counts."""

    def __init__(self, audio_count=2, subtitle_count=1, **kwargs):
        super().__init__(None, **kwargs)
        self.audio_count = audio_count
        self.subtitle_count = subtitle_count

    @property
    def stdout(self):
        audio_streams = [
            {"codec_type": "audio", "index": i} for i in range(self.audio_count)
        ]
        subtitle_streams = [
            {"codec_type": "subtitle", "index": self.audio_count + i}
            for i in range(self.subtitle_count)
        ]
        data = {"streams": [{"codec_type": "video", "index": 0}] + audio_streams + subtitle_streams}
        return json.dumps(data)


class FakeFFmpeg:
    """Fake ffmpeg that creates output file and tracks command."""

    calls = []

    def __init__(self, cmd, capture_output=True, text=True, **kwargs):
        self.cmd = cmd
        FakeFFmpeg.calls.append(cmd)
        self.returncode = 0
        # Create output file (last arg in our ffmpeg command)
        out_path = Path(cmd[-1])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")


class FakeFFmpegFailure(FakeFFmpeg):
    """Fake ffmpeg that fails."""

    def __init__(self, cmd, capture_output=True, text=True, **kwargs):
        super().__init__(cmd, capture_output=capture_output, text=text, **kwargs)
        self.returncode = 1


def make_fake_run(audio_count=2, subtitle_count=1):
    """Factory for ffprobe/ffmpeg fake."""

    def fake_run(cmd, capture_output=True, text=True, **kwargs):
        if cmd[0] == "ffprobe":
            fake = FakeFFprobeWithStreams(audio_count, subtitle_count)
            return subprocess.CompletedProcess(
                cmd, 0, stdout=fake.stdout, stderr=""
            )
        if cmd[0] == "ffmpeg":
            ffmpeg = FakeFFmpeg(cmd, capture_output, text, **kwargs)
            return subprocess.CompletedProcess(cmd, ffmpeg.returncode, stdout="", stderr="")
        raise AssertionError(f"Unexpected command: {cmd}")

    return fake_run


def test_movie_naming_inserts_censorr_token(tmp_path, monkeypatch):
    input_file = tmp_path / "Movie Title {imdb-123} - [NF][1080p].mkv"
    input_file.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")

    subtitle_file = tmp_path / "subtitles.srt"
    subtitle_file.write_text("1\n00:00:01,000 --> 00:00:02,000\ntest\n")

    audio_file = tmp_path / "audio.wav"
    audio_file.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")

    output_dir = tmp_path / "out"
    monkeypatch.setattr(subprocess, "run", make_fake_run())

    op = VideoRemux()
    result = op.do(
        input_video_path=str(input_file),
        masked_subtitle_path=str(subtitle_file),
        muted_audio_path=str(audio_file),
        naming_mode="movie",
        output_base=str(output_dir),
    )

    result_path = Path(result)
    assert "{edition-Censorr}" in result_path.name
    assert result_path.name.startswith("Movie Title {edition-Censorr}")
    assert "[1080p].mkv" in result_path.name


def test_tv_naming_adds_censorr_to_show_folder(tmp_path, monkeypatch):
    show_dir = tmp_path / "Shows" / "Breaking Bad"
    season_dir = show_dir / "Season 1"
    input_file = season_dir / "s01e01.mkv"
    input_file.parent.mkdir(parents=True, exist_ok=True)
    input_file.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")

    subtitle_file = tmp_path / "subtitles.srt"
    subtitle_file.write_text("1\n00:00:01,000 --> 00:00:02,000\ntest\n")

    audio_file = tmp_path / "audio.wav"
    audio_file.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")

    output_base = tmp_path / "out"
    monkeypatch.setattr(subprocess, "run", make_fake_run())

    op = VideoRemux()
    result = op.do(
        input_video_path=str(input_file),
        masked_subtitle_path=str(subtitle_file),
        muted_audio_path=str(audio_file),
        naming_mode="tv",
        output_base=str(output_base),
    )

    result_path = Path(result)
    assert "Breaking Bad [Censorr]" in result_path.parts
    assert "Season 1" in result_path.parts
    assert result_path.name == "s01e01.mkv"


def test_replace_mode_maps_only_new_audio(tmp_path, monkeypatch):
    input_file = tmp_path / "video.mkv"
    input_file.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")

    subtitle_file = tmp_path / "subtitles.srt"
    subtitle_file.write_text("1\n00:00:01,000 --> 00:00:02,000\ntest\n")

    audio_file = tmp_path / "audio.wav"
    audio_file.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")

    output_dir = tmp_path / "out"
    FakeFFmpeg.calls = []
    monkeypatch.setattr(subprocess, "run", make_fake_run())

    op = VideoRemux()
    op.do(
        input_video_path=str(input_file),
        masked_subtitle_path=str(subtitle_file),
        muted_audio_path=str(audio_file),
        remux_mode="replace",
        output_base=str(output_dir),
    )

    cmd = FakeFFmpeg.calls[-1]
    # Should NOT map 0:a (original audio)
    assert "0:a" not in cmd
    # Should map video, data, text, chapters, and new audio
    assert "-map" in cmd
    assert "0:v?" in cmd
    assert "0:d?" in cmd
    assert "0:t?" in cmd
    assert "1:a?" in cmd


def test_append_mode_keeps_original_audio(tmp_path, monkeypatch):
    input_file = tmp_path / "video.mkv"
    input_file.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")

    subtitle_file = tmp_path / "subtitles.srt"
    subtitle_file.write_text("1\n00:00:01,000 --> 00:00:02,000\ntest\n")

    audio_file = tmp_path / "audio.wav"
    audio_file.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")

    output_dir = tmp_path / "out"
    FakeFFmpeg.calls = []
    monkeypatch.setattr(subprocess, "run", make_fake_run(audio_count=2))

    op = VideoRemux()
    op.do(
        input_video_path=str(input_file),
        masked_subtitle_path=str(subtitle_file),
        muted_audio_path=str(audio_file),
        remux_mode="append",
        output_base=str(output_dir),
    )

    cmd = FakeFFmpeg.calls[-1]
    # Should map everything from original plus new audio
    assert "-map" in cmd and "0" in cmd
    assert "1:a?" in cmd


def test_creates_subtitle_sidecar_with_language(tmp_path, monkeypatch):
    input_file = tmp_path / "video.mkv"
    input_file.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")

    subtitle_file = tmp_path / "subtitles.srt"
    subtitle_text = "1\n00:00:01,000 --> 00:00:02,000\nHello world\n"
    subtitle_file.write_text(subtitle_text)

    audio_file = tmp_path / "audio.wav"
    audio_file.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")

    output_dir = tmp_path / "out"
    monkeypatch.setattr(subprocess, "run", make_fake_run())

    op = VideoRemux()
    result = op.do(
        input_video_path=str(input_file),
        masked_subtitle_path=str(subtitle_file),
        muted_audio_path=str(audio_file),
        sidecar_language="spa",
        output_base=str(output_dir),
    )

    result_path = Path(result)
    sidecar = result_path.with_name(f"{result_path.stem}.spa.censorr.srt")
    assert sidecar.exists()
    assert sidecar.read_text() == subtitle_text


def test_audio_title_metadata_set(tmp_path, monkeypatch):
    input_file = tmp_path / "video.mkv"
    input_file.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")

    subtitle_file = tmp_path / "subtitles.srt"
    subtitle_file.write_text("1\n00:00:01,000 --> 00:00:02,000\ntest\n")

    audio_file = tmp_path / "audio.wav"
    audio_file.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")

    output_dir = tmp_path / "out"
    FakeFFmpeg.calls = []
    monkeypatch.setattr(subprocess, "run", make_fake_run())

    op = VideoRemux()
    op.do(
        input_video_path=str(input_file),
        masked_subtitle_path=str(subtitle_file),
        muted_audio_path=str(audio_file),
        remux_mode="replace",
        output_base=str(output_dir),
    )

    cmd = FakeFFmpeg.calls[-1]
    # Metadata title should be set (replace mode has new audio at index 0)
    assert "-metadata:s:a:0" in cmd
    title_idx = cmd.index("-metadata:s:a:0") + 1
    assert cmd[title_idx] == "title=Censorr"


def test_raises_when_input_not_found(tmp_path, monkeypatch):
    subtitle_file = tmp_path / "subtitles.srt"
    subtitle_file.write_text("1\n00:00:01,000 --> 00:00:02,000\ntest\n")

    audio_file = tmp_path / "audio.wav"
    audio_file.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")

    op = VideoRemux()
    with pytest.raises(FileNotFoundError):
        op.do(
            input_video_path="/nonexistent/video.mkv",
            masked_subtitle_path=str(subtitle_file),
            muted_audio_path=str(audio_file),
        )


def test_raises_when_subtitle_not_found(tmp_path, monkeypatch):
    input_file = tmp_path / "video.mkv"
    input_file.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")

    audio_file = tmp_path / "audio.wav"
    audio_file.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")

    op = VideoRemux()
    with pytest.raises(FileNotFoundError):
        op.do(
            input_video_path=str(input_file),
            masked_subtitle_path="/nonexistent/subs.srt",
            muted_audio_path=str(audio_file),
        )


def test_raises_when_audio_not_found(tmp_path, monkeypatch):
    input_file = tmp_path / "video.mkv"
    input_file.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")

    subtitle_file = tmp_path / "subtitles.srt"
    subtitle_file.write_text("1\n00:00:01,000 --> 00:00:02,000\ntest\n")

    op = VideoRemux()
    with pytest.raises(FileNotFoundError):
        op.do(
            input_video_path=str(input_file),
            masked_subtitle_path=str(subtitle_file),
            muted_audio_path="/nonexistent/audio.wav",
        )


def test_raises_when_ffmpeg_fails(tmp_path, monkeypatch):
    input_file = tmp_path / "video.mkv"
    input_file.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")

    subtitle_file = tmp_path / "subtitles.srt"
    subtitle_file.write_text("1\n00:00:01,000 --> 00:00:02,000\ntest\n")

    audio_file = tmp_path / "audio.wav"
    audio_file.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")

    output_dir = tmp_path / "out"

    def fake_run_fail(cmd, **kwargs):
        if cmd[0] == "ffprobe":
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"streams": []}), stderr="")
        if cmd[0] == "ffmpeg":
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="boom")
        raise AssertionError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(subprocess, "run", fake_run_fail)

    op = VideoRemux()
    with pytest.raises(RuntimeError):
        op.do(
            input_video_path=str(input_file),
            masked_subtitle_path=str(subtitle_file),
            muted_audio_path=str(audio_file),
            output_base=str(output_dir),
        )
