"""Unit tests ensuring mute windows are derived from subtitles.

These tests validate that MuteAudioOperation derives mute windows from subtitle
artifacts using the profanity matcher and the provided profanity list, and that
windows are merged and passed to FFmpeg.
"""
from pathlib import Path
from unittest.mock import patch

from src.models.artifacts import Artifact, ArtifactType
from src.models.operations import OperationFlags
from src.ops.audio_mute import MuteAudioOperation


def _write_srt(tmp: Path, name: str, content: str) -> Path:
    p = tmp / name
    p.write_text(content, encoding="utf-8")
    return p


@patch("src.ops.audio_mute.FFmpegAdapter")
def test_derive_mute_windows_from_subtitles(mock_ffmpeg, tmp_path: Path):
    # Create a simple SRT with one profane line between 1s and 3s
    srt = _write_srt(
        tmp_path,
        "sample.srt",
        """1\n00:00:01,000 --> 00:00:03,000\nHoly shit, that was close!\n\n2\n00:00:05,000 --> 00:00:06,000\nClean line.\n""",
    )

    # Artifacts: audio + subtitle
    audio_art = Artifact(type=ArtifactType.AUDIO, path=str(tmp_path / "a.wav"), metadata={})
    sub_art = Artifact(type=ArtifactType.SUBTITLE, path=str(srt), metadata={"language": "en"})

    # Profanity list file
    prof = tmp_path / "profanity.json"
    prof.write_text('[{"word": "shit"}]', encoding="utf-8")

    # Operation
    op = MuteAudioOperation()
    flags = OperationFlags(profanity_list_file=str(prof), verbose=True)

    # Mock ffmpeg apply to avoid running external tool
    mock_ffmpeg.return_value.apply_mute_windows.return_value = str(tmp_path / "muted.wav")

    results = op.run([audio_art, sub_art], tmp_path, flags)

    # Validate
    assert len(results) == 1
    assert results[0].metadata["mute_windows_applied"] >= 1
    # The muting window should include the (1s,3s) entry +/- padding
    args = mock_ffmpeg.return_value.apply_mute_windows.call_args[1]
    windows = args["mute_windows"]
    assert any(w.start <= 1.0 and w.end >= 3.0 for w in windows)


@patch("src.ops.audio_mute.FFmpegAdapter")
def test_masked_subtitle_uses_original_when_available(mock_ffmpeg, tmp_path: Path):
    # Create original and masked subtitles
    orig = _write_srt(
        tmp_path,
        "orig.srt",
        """1\n00:00:02,000 --> 00:00:04,000\nYou piece of shit.\n""",
    )
    masked = _write_srt(
        tmp_path,
        "masked_subtitles.srt",
        """1\n00:00:02,000 --> 00:00:04,000\nYou piece of ****.\n""",
    )

    audio_art = Artifact(type=ArtifactType.AUDIO, path=str(tmp_path / "a.wav"), metadata={})
    masked_art = Artifact(
        type=ArtifactType.SUBTITLE,
        path=str(masked),
        metadata={"original_file": str(orig), "language": "en"}
    )

    prof = tmp_path / "profanity.json"
    prof.write_text('[{"word": "shit"}, {"word": "piece of shit"}]', encoding="utf-8")

    op = MuteAudioOperation()
    flags = OperationFlags(profanity_list_file=str(prof), verbose=True)
    mock_ffmpeg.return_value.apply_mute_windows.return_value = str(tmp_path / "muted.wav")

    results = op.run([audio_art, masked_art], tmp_path, flags)
    assert len(results) == 1
    assert results[0].metadata["mute_windows_applied"] >= 1