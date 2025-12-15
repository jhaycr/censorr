import json
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from censorr.cli.main import run


@pytest.fixture
def tmp_files(tmp_path):
    """Create temporary input video, config files, and output directory."""
    input_video = tmp_path / "video.mkv"
    input_video.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")

    config_dir = tmp_path / "config"
    config_dir.mkdir()

    profanity_config = config_dir / "profanity_list.json"
    profanity_config.write_text(json.dumps(["damn"]))

    app_config = config_dir / "app_config.json"
    app_config.write_text(json.dumps({"audio_qc_threshold_db": 20.0}))

    output_dir = tmp_path / "output"
    output_dir.mkdir()

    return {
        "input_video": str(input_video),
        "config_dir": str(config_dir),
        "profanity_config": str(profanity_config),
        "app_config": str(app_config),
        "output_dir": str(output_dir),
    }


def test_run_calls_all_commands(tmp_files, monkeypatch):
    """Verify that run command calls all constituent commands in order."""
    input_video = tmp_files["input_video"]
    output_dir = tmp_files["output_dir"]
    profanity_config = tmp_files["profanity_config"]
    app_config = tmp_files["app_config"]

    # Mock all command classes
    mock_extract = MagicMock()
    mock_extract.do.return_value = (
        f"{output_dir}/merged_subtitles.srt",
        [f"{output_dir}/subtitle_0_eng.srt"],
    )

    mock_mask = MagicMock()
    mock_mask.do.return_value = None

    mock_audio_extract = MagicMock()
    mock_audio_extract.do.return_value = f"{output_dir}/audio_eng.wav"

    mock_mute = MagicMock()
    mock_mute.do.return_value = (f"{output_dir}/muted_audio.wav", f"{output_dir}/mute_windows.json")

    mock_qc = MagicMock()
    mock_qc.do.return_value = f"{output_dir}/qc_report.json"

    mock_remux = MagicMock()
    mock_remux.do.return_value = f"{output_dir}/final_video.mkv"

    # Create necessary files for pipeline
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    Path(f"{output_dir}/merged_subtitles.srt").write_text("test")
    Path(f"{output_dir}/masked_subtitles.srt").write_text("test")
    Path(f"{output_dir}/profanity_matches.csv").write_text("start_ms,end_ms\n1000,2000\n")
    Path(f"{output_dir}/audio_eng.wav").write_bytes(b"RIFF")
    Path(f"{output_dir}/muted_audio.wav").write_bytes(b"RIFF")
    Path(f"{output_dir}/mute_windows.json").write_text("[]")
    Path(f"{output_dir}/qc_report.json").write_text("{}")

    with patch("censorr.commands.subtitle_extract_and_merge.SubtitleExtractAndMerge", return_value=mock_extract), \
         patch("censorr.commands.subtitle_mask.SubtitleMask", return_value=mock_mask), \
         patch("censorr.commands.audio_extract.AudioExtract", return_value=mock_audio_extract), \
         patch("censorr.commands.audio_mute.AudioMute", return_value=mock_mute), \
         patch("censorr.commands.audio_qc.AudioQC", return_value=mock_qc), \
         patch("censorr.commands.video_remux.VideoRemux", return_value=mock_remux), \
         patch("censorr.cli.main._default_config_path", return_value=profanity_config), \
         patch("censorr.cli.main._default_app_config_path", return_value=app_config):
        
        result = run(
            input_file_path=input_video,
            output_dir=output_dir,
            include_language=["en"],
            include_title=None,
            include_any=None,
            exclude_language=None,
            exclude_title=None,
            exclude_any=None,
            config_path=profanity_config,
            default_threshold=85.0,
            qc_threshold_db=None,
            app_config_path=app_config,
            remux_mode="replace",
            remux_naming_mode="movie",
            remux_output_base=None,
            cleanup=False,
        )

        # Verify all commands were called
        assert mock_extract.do.called, "SubtitleExtractAndMerge.do not called"
        assert mock_mask.do.called, "SubtitleMask.do not called"
        assert mock_audio_extract.do.called, "AudioExtract.do not called"
        assert mock_mute.do.called, "AudioMute.do not called"
        assert mock_qc.do.called, "AudioQC.do not called"
        assert mock_remux.do.called, "VideoRemux.do not called"

        # Verify return value
        assert result == f"{output_dir}/final_video.mkv"


def test_run_resolves_config_paths_from_defaults(tmp_files):
    """Verify that run resolves default config paths when not provided."""
    input_video = tmp_files["input_video"]
    output_dir = tmp_files["output_dir"]
    profanity_config = tmp_files["profanity_config"]
    app_config = tmp_files["app_config"]

    mock_extract = MagicMock()
    mock_extract.do.return_value = (f"{output_dir}/merged.srt", [])
    mock_mask = MagicMock()
    mock_mask.do.return_value = None
    mock_audio_extract = MagicMock()
    mock_audio_extract.do.return_value = f"{output_dir}/audio.wav"
    mock_mute = MagicMock()
    mock_mute.do.return_value = (f"{output_dir}/muted.wav", f"{output_dir}/windows.json")
    mock_qc = MagicMock()
    mock_qc.do.return_value = f"{output_dir}/qc.json"
    mock_remux = MagicMock()
    mock_remux.do.return_value = f"{output_dir}/final.mkv"

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    Path(f"{output_dir}/merged.srt").write_text("test")
    Path(f"{output_dir}/masked_subtitles.srt").write_text("test")
    Path(f"{output_dir}/profanity_matches.csv").write_text("start_ms,end_ms\n")
    Path(f"{output_dir}/audio.wav").write_bytes(b"RIFF")
    Path(f"{output_dir}/muted.wav").write_bytes(b"RIFF")
    Path(f"{output_dir}/windows.json").write_text("[]")
    Path(f"{output_dir}/qc.json").write_text("{}")

    with patch("censorr.commands.subtitle_extract_and_merge.SubtitleExtractAndMerge", return_value=mock_extract), \
         patch("censorr.commands.subtitle_mask.SubtitleMask", return_value=mock_mask), \
         patch("censorr.commands.audio_extract.AudioExtract", return_value=mock_audio_extract), \
         patch("censorr.commands.audio_mute.AudioMute", return_value=mock_mute), \
         patch("censorr.commands.audio_qc.AudioQC", return_value=mock_qc), \
         patch("censorr.commands.video_remux.VideoRemux", return_value=mock_remux), \
         patch("censorr.cli.main._default_config_path", return_value=profanity_config), \
         patch("censorr.cli.main._default_app_config_path", return_value=app_config):
        
        run(
            input_file_path=input_video,
            output_dir=output_dir,
            include_language=["en"],
            include_title=None,
            include_any=None,
            exclude_language=None,
            exclude_title=None,
            exclude_any=None,
            config_path=profanity_config,
            default_threshold=85.0,
            qc_threshold_db=None,
            app_config_path=app_config,
            remux_mode="replace",
            remux_naming_mode="movie",
            remux_output_base=None,
            cleanup=False,
        )

        # Verify commands were called with correct config paths
        mock_mask.do.assert_called()
        mock_extract.do.assert_called()


def test_run_with_cleanup_enabled(tmp_files):
    """Verify that cleanup removes intermediate files when enabled."""
    input_video = tmp_files["input_video"]
    output_dir = tmp_files["output_dir"]
    profanity_config = tmp_files["profanity_config"]
    app_config = tmp_files["app_config"]

    mock_extract = MagicMock()
    mock_extract.do.return_value = (
        f"{output_dir}/merged.srt",
        [f"{output_dir}/subtitle_0.srt"],
    )
    mock_mask = MagicMock()
    mock_mask.do.return_value = None
    mock_audio_extract = MagicMock()
    mock_audio_extract.do.return_value = f"{output_dir}/audio.wav"
    mock_mute = MagicMock()
    mock_mute.do.return_value = (f"{output_dir}/muted.wav", f"{output_dir}/windows.json")
    mock_qc = MagicMock()
    mock_qc.do.return_value = f"{output_dir}/qc.json"
    
    # Create the final output file after remux is called
    def remux_side_effect(**kwargs):
        Path(f"{output_dir}/final.mkv").write_bytes(b"FINAL")
        return f"{output_dir}/final.mkv"
    
    mock_remux = MagicMock()
    mock_remux.do.side_effect = remux_side_effect

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    Path(f"{output_dir}/merged.srt").write_text("test")
    Path(f"{output_dir}/subtitle_0.srt").write_text("test")
    Path(f"{output_dir}/masked_subtitles.srt").write_text("test")
    Path(f"{output_dir}/profanity_matches.csv").write_text("start_ms,end_ms\n")
    Path(f"{output_dir}/audio.wav").write_bytes(b"RIFF")
    Path(f"{output_dir}/muted.wav").write_bytes(b"RIFF")
    Path(f"{output_dir}/windows.json").write_text("[]")
    Path(f"{output_dir}/qc.json").write_text("{}")

    with patch("censorr.commands.subtitle_extract_and_merge.SubtitleExtractAndMerge", return_value=mock_extract), \
         patch("censorr.commands.subtitle_mask.SubtitleMask", return_value=mock_mask), \
         patch("censorr.commands.audio_extract.AudioExtract", return_value=mock_audio_extract), \
         patch("censorr.commands.audio_mute.AudioMute", return_value=mock_mute), \
         patch("censorr.commands.audio_qc.AudioQC", return_value=mock_qc), \
         patch("censorr.commands.video_remux.VideoRemux", return_value=mock_remux), \
         patch("censorr.cli.main._default_config_path", return_value=profanity_config), \
         patch("censorr.cli.main._default_app_config_path", return_value=app_config):
        
        run(
            input_file_path=input_video,
            output_dir=output_dir,
            include_language=["en"],
            include_title=None,
            include_any=None,
            exclude_language=None,
            exclude_title=None,
            exclude_any=None,
            config_path=profanity_config,
            default_threshold=85.0,
            qc_threshold_db=None,
            app_config_path=app_config,
            remux_mode="replace",
            remux_naming_mode="movie",
            remux_output_base=None,
            cleanup=True,  # Enable cleanup
        )

        # Verify intermediate files were deleted
        assert not Path(f"{output_dir}/merged.srt").exists()
        assert not Path(f"{output_dir}/subtitle_0.srt").exists()
        assert not Path(f"{output_dir}/masked_subtitles.srt").exists()
        assert not Path(f"{output_dir}/audio.wav").exists()
        assert not Path(f"{output_dir}/muted.wav").exists()
        assert not Path(f"{output_dir}/windows.json").exists()
        assert not Path(f"{output_dir}/qc.json").exists()

        # Final remux output should still exist (not cleaned up)
        assert Path(f"{output_dir}/final.mkv").exists()