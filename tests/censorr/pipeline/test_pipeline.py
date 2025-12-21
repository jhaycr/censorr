import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from censorr.pipeline import RunPipeline


def test_run_pipeline_invokes_commands_and_returns_output(tmp_path):
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    input_video = tmp_path / "video.mkv"
    input_video.write_text("vid")

    mock_extract = MagicMock()
    mock_extract.do.return_value = (
        str(output_dir / "merged_subtitles.srt"),
        [str(output_dir / "subtitle_0_eng.srt")],
    )
    (output_dir / "merged_subtitles.srt").write_text("test")
    (output_dir / "subtitle_0_eng.srt").write_text("test")

    mock_mask = MagicMock()
    mock_mask.do.return_value = None
    (output_dir / "masked_subtitles.srt").write_text("masked")
    (output_dir / "profanity_matches.csv").write_text("start_ms,end_ms\n1000,2000\n")

    mock_audio = MagicMock()
    mock_audio.do.return_value = str(output_dir / "audio.wav")
    (output_dir / "audio.wav").write_bytes(b"RIFF")

    mock_mute = MagicMock()
    mock_mute.do.return_value = (
        str(output_dir / "muted.wav"),
        str(output_dir / "windows.json"),
    )
    (output_dir / "muted.wav").write_bytes(b"RIFF")
    (output_dir / "windows.json").write_text("[]")

    mock_qc = MagicMock()
    mock_qc.do.return_value = str(output_dir / "qc.json")
    (output_dir / "qc.json").write_text(json.dumps({}))

    mock_remux = MagicMock()
    mock_remux.do.return_value = str(output_dir / "final.mkv")
    (output_dir / "final.mkv").write_bytes(b"FINAL")

    with patch("censorr.commands.subtitle_extract_and_merge.SubtitleExtractAndMerge", return_value=mock_extract), \
        patch("censorr.commands.subtitle_mask.SubtitleMask", return_value=mock_mask), \
        patch("censorr.commands.audio_extract.AudioExtract", return_value=mock_audio), \
        patch("censorr.commands.audio_mute.AudioMute", return_value=mock_mute), \
        patch("censorr.commands.audio_qc.AudioQC", return_value=mock_qc), \
        patch("censorr.commands.video_remux.VideoRemux", return_value=mock_remux):

        pipeline = RunPipeline()
        result = pipeline.run(
            input_file_path=str(input_video),
            output_dir=str(output_dir),
            include_language=["en"],
            cleanup=False,
        )

    assert result == str(output_dir / "final.mkv")
    mock_extract.do.assert_called_once()
    mock_mask.do.assert_called_once()
    mock_audio.do.assert_called_once()
    mock_mute.do.assert_called_once()
    mock_qc.do.assert_called_once()
    mock_remux.do.assert_called_once()


def test_run_pipeline_cleanup(tmp_path):
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    input_video = tmp_path / "video.mkv"
    input_video.write_text("vid")

    mock_extract = MagicMock()
    mock_extract.do.return_value = (
        str(output_dir / "merged_subtitles.srt"),
        [str(output_dir / "subtitle_0_eng.srt")],
    )
    (output_dir / "merged_subtitles.srt").write_text("test")
    (output_dir / "subtitle_0_eng.srt").write_text("test")

    mock_mask = MagicMock()
    mock_mask.do.return_value = None
    (output_dir / "masked_subtitles.srt").write_text("masked")
    (output_dir / "profanity_matches.csv").write_text("start_ms,end_ms\n1000,2000\n")

    mock_audio = MagicMock()
    mock_audio.do.return_value = str(output_dir / "audio.wav")
    (output_dir / "audio.wav").write_bytes(b"RIFF")

    mock_mute = MagicMock()
    mock_mute.do.return_value = (
        str(output_dir / "muted.wav"),
        str(output_dir / "windows.json"),
    )
    (output_dir / "muted.wav").write_bytes(b"RIFF")
    (output_dir / "windows.json").write_text("[]")

    mock_qc = MagicMock()
    mock_qc.do.return_value = str(output_dir / "qc.json")
    (output_dir / "qc.json").write_text(json.dumps({}))

    mock_remux = MagicMock()
    mock_remux.do.return_value = str(output_dir / "final.mkv")
    (output_dir / "final.mkv").write_bytes(b"FINAL")

    with patch("censorr.commands.subtitle_extract_and_merge.SubtitleExtractAndMerge", return_value=mock_extract), \
        patch("censorr.commands.subtitle_mask.SubtitleMask", return_value=mock_mask), \
        patch("censorr.commands.audio_extract.AudioExtract", return_value=mock_audio), \
        patch("censorr.commands.audio_mute.AudioMute", return_value=mock_mute), \
        patch("censorr.commands.audio_qc.AudioQC", return_value=mock_qc), \
        patch("censorr.commands.video_remux.VideoRemux", return_value=mock_remux):

        pipeline = RunPipeline()
        result = pipeline.run(
            input_file_path=str(input_video),
            output_dir=str(output_dir),
            include_language=["en"],
            cleanup=True,
        )

    # Pipeline returns the final output path
    assert result == str(output_dir / "final.mkv")
    # Cleanup should have removed intermediates
    assert not (output_dir / "merged_subtitles.srt").exists()
    assert not (output_dir / "masked_subtitles.srt").exists()
    assert not (output_dir / "profanity_matches.csv").exists()
    assert not (output_dir / "audio.wav").exists()
    assert not (output_dir / "muted.wav").exists()
    assert not (output_dir / "windows.json").exists()
    assert not (output_dir / "qc.json").exists()
    # Final output remains
    assert (output_dir / "final.mkv").exists()
