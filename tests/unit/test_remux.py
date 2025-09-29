"""Unit tests for remux operation (updated to reflect edition tagging and audio prioritization)."""
import pytest
from pathlib import Path
from unittest.mock import patch

from src.models.artifacts import Artifact, ArtifactType
from src.models.operations import OperationFlags
from src.ops.remux import RemuxOperation


def _return_output_side_effect(*args, **kwargs):
    # Always return the provided output path so tests see the edition-tagged filename
    if "output" in kwargs:
        return kwargs["output"]
    # Fallback positional (video_input, output, ...)
    return args[1] if len(args) > 1 else None


class TestRemuxOperation:
    """Test cases for RemuxOperation."""

    def test_operation_creation(self):
        op = RemuxOperation()
        assert op.consumes == {ArtifactType.VIDEO, ArtifactType.AUDIO, ArtifactType.SUBTITLE}
        assert op.produces == {ArtifactType.VIDEO}

    @patch('src.ops.remux.FFmpegAdapter')
    def test_run_with_all_track_types(self, mock_ffmpeg_class):
        mock_ffmpeg = mock_ffmpeg_class.return_value
        mock_ffmpeg.remux.side_effect = _return_output_side_effect

        workdir = Path("/tmp/test")
        video_artifact = Artifact(type=ArtifactType.VIDEO, path="/path/to/video.mp4", metadata={"original": True})
        # Use path pattern containing 'extract_audio' so prioritization treats as extracted audio
        audio_artifact = Artifact(type=ArtifactType.AUDIO, path="output/test/extract_audio/999/audio_track_1.wav", metadata={"mute_windows_applied": 3})
        subtitle_artifact = Artifact(type=ArtifactType.SUBTITLE, path="/path/to/subtitles.srt", metadata={"masked": True, "language": "en"})
        flags = OperationFlags(subtitle_mode="all")

        op = RemuxOperation()
        results = op.run([video_artifact, audio_artifact, subtitle_artifact], workdir, flags)

        assert len(results) == 1
        result = results[0]
        assert result.type == ArtifactType.VIDEO
        assert "{edition-Censorr}" in Path(result.path).name
        assert result.metadata["audio_tracks"] == 1
        assert result.metadata["subtitle_tracks"] == 1

        mock_ffmpeg.remux.assert_called_once()
        kwargs = mock_ffmpeg.remux.call_args.kwargs
        assert kwargs["video_input"] == video_artifact.path
        assert kwargs["audio_tracks"] == [audio_artifact.path]
        assert kwargs["subtitle_tracks"] == [subtitle_artifact.path]

    @patch('src.ops.remux.FFmpegAdapter')
    def test_run_video_only(self, mock_ffmpeg_class):
        mock_ffmpeg = mock_ffmpeg_class.return_value
        mock_ffmpeg.remux.side_effect = _return_output_side_effect

        workdir = Path("/tmp/test")
        video_artifact = Artifact(type=ArtifactType.VIDEO, path="/path/to/video.mp4", metadata={"original": True})
        flags = OperationFlags()

        op = RemuxOperation()
        results = op.run([video_artifact], workdir, flags)

        assert len(results) == 1
        result = results[0]
        assert result.type == ArtifactType.VIDEO
        assert "{edition-Censorr}" in Path(result.path).name
        assert result.metadata["audio_tracks"] == 0
        assert result.metadata["subtitle_tracks"] == 0
        mock_ffmpeg.remux.assert_called_once()
        kwargs = mock_ffmpeg.remux.call_args.kwargs
        assert kwargs["audio_tracks"] == [] and kwargs["subtitle_tracks"] == []

    @patch('src.ops.remux.FFmpegAdapter')
    def test_run_multiple_audio_tracks(self, mock_ffmpeg_class):
        mock_ffmpeg = mock_ffmpeg_class.return_value
        mock_ffmpeg.remux.side_effect = _return_output_side_effect

        workdir = Path("/tmp/test")
        video_artifact = Artifact(type=ArtifactType.VIDEO, path="/path/to/video.mp4", metadata={})
        audio1 = Artifact(type=ArtifactType.AUDIO, path="output/test/extract_audio/111/audio_track_1.wav", metadata={"language": "en"})
        audio2 = Artifact(type=ArtifactType.AUDIO, path="output/test/extract_audio/222/audio_track_2.wav", metadata={"language": "es"})
        flags = OperationFlags()

        op = RemuxOperation()
        results = op.run([video_artifact, audio1, audio2], workdir, flags)
        assert len(results) == 1
        assert results[0].metadata["audio_tracks"] == 2
        audio_tracks = mock_ffmpeg.remux.call_args.kwargs["audio_tracks"]
        assert set(audio_tracks) == {audio1.path, audio2.path}

    @patch('src.ops.remux.FFmpegAdapter')
    def test_run_multiple_subtitle_tracks(self, mock_ffmpeg_class):
        mock_ffmpeg = mock_ffmpeg_class.return_value
        mock_ffmpeg.remux.side_effect = _return_output_side_effect

        workdir = Path("/tmp/test")
        video_artifact = Artifact(type=ArtifactType.VIDEO, path="/path/to/video.mp4", metadata={})
        sub1 = Artifact(type=ArtifactType.SUBTITLE, path="/path/to/subtitles_en.srt", metadata={"language": "en"})
        sub2 = Artifact(type=ArtifactType.SUBTITLE, path="/path/to/subtitles_es.srt", metadata={"language": "es"})
        flags = OperationFlags(subtitle_mode="all")

        op = RemuxOperation()
        results = op.run([video_artifact, sub1, sub2], workdir, flags)
        assert len(results) == 1
        assert results[0].metadata["subtitle_tracks"] == 2
        subtitle_tracks = mock_ffmpeg.remux.call_args.kwargs["subtitle_tracks"]
        assert set(subtitle_tracks) == {sub1.path, sub2.path}

    @patch('src.ops.remux.FFmpegAdapter')
    def test_run_dry_run(self, mock_ffmpeg_class):
        mock_ffmpeg = mock_ffmpeg_class.return_value
        # No side effect needed (dry run skips remux)

        workdir = Path("/tmp/test")
        video_artifact = Artifact(type=ArtifactType.VIDEO, path="/path/to/video.mp4", metadata={})
        audio_artifact = Artifact(type=ArtifactType.AUDIO, path="output/test/extract_audio/333/audio_track_1.wav", metadata={})
        flags = OperationFlags(dry_run=True)

        op = RemuxOperation()
        results = op.run([video_artifact, audio_artifact], workdir, flags)
        assert len(results) == 1
        assert "remuxed_" in results[0].path
        assert "{edition-Censorr}" in Path(results[0].path).name
        assert results[0].metadata["audio_tracks"] == 1
        mock_ffmpeg.remux.assert_not_called()

    @patch('src.ops.remux.FFmpegAdapter')
    def test_run_ffmpeg_error(self, mock_ffmpeg_class):
        mock_ffmpeg = mock_ffmpeg_class.return_value
        mock_ffmpeg.remux.side_effect = Exception("FFmpeg failed")

        workdir = Path("/tmp/test")
        video_artifact = Artifact(type=ArtifactType.VIDEO, path="/path/to/video.mp4", metadata={})
        flags = OperationFlags()

        op = RemuxOperation()
        with pytest.raises(RuntimeError, match="Failed to remux video"):
            op.run([video_artifact], workdir, flags)

    def test_run_no_video_artifact(self):
        op = RemuxOperation()
        audio_artifact = Artifact(type=ArtifactType.AUDIO, path="/path/to/audio_track_1.wav", metadata={})
        workdir = Path("/tmp/test")
        flags = OperationFlags()
        with pytest.raises(ValueError, match="No video artifacts found"):
            op.run([audio_artifact], workdir, flags)

    def test_run_multiple_video_artifacts(self):
        op = RemuxOperation()
        v1 = Artifact(type=ArtifactType.VIDEO, path="/path/to/video1.mp4", metadata={})
        v2 = Artifact(type=ArtifactType.VIDEO, path="/path/to/video2.mp4", metadata={})
        workdir = Path("/tmp/test")
        flags = OperationFlags()
        with pytest.raises(ValueError, match="Multiple video artifacts found"):
            op.run([v1, v2], workdir, flags)

    def test_generate_output_path(self):
        op = RemuxOperation()
        workdir = Path("/tmp/test")
        out = op._generate_output_path("/path/to/video.mp4", workdir)
        assert out.startswith("/tmp/test/remuxed_") and out.endswith(".mp4")
        out2 = op._generate_output_path("/path/to/video.mkv", workdir)
        assert out2.endswith(".mkv")

    @patch('src.ops.remux.FFmpegAdapter')
    def test_verbose_mode(self, mock_ffmpeg_class):
        mock_ffmpeg = mock_ffmpeg_class.return_value
        mock_ffmpeg.remux.side_effect = _return_output_side_effect

        workdir = Path("/tmp/test")
        video = Artifact(type=ArtifactType.VIDEO, path="/path/to/video.mp4", metadata={})
        audio = Artifact(type=ArtifactType.AUDIO, path="/path/to/audio_track_1.wav", metadata={})
        sub = Artifact(type=ArtifactType.SUBTITLE, path="/path/to/subtitles.srt", metadata={"language": "en"})
        flags = OperationFlags(verbose=True)

        op = RemuxOperation()
        with patch('builtins.print') as mock_print:
            op.run([video, audio, sub], workdir, flags)
        assert mock_print.called
        printed = "\n".join(str(c[0][0]) for c in mock_print.call_args_list)
        assert "audio tracks" in printed
        assert "subtitle tracks" in printed
        assert "Remuxing video" in printed

    @patch('src.ops.remux.FFmpegAdapter')
    def test_preserve_video_metadata(self, mock_ffmpeg_class):
        mock_ffmpeg = mock_ffmpeg_class.return_value
        mock_ffmpeg.remux.side_effect = _return_output_side_effect

        workdir = Path("/tmp/test")
        video = Artifact(type=ArtifactType.VIDEO, path="/path/to/video.mp4", metadata={
            "original_format": "h264",
            "duration": 3600.0,
            "resolution": "1920x1080"
        })
        flags = OperationFlags()

        op = RemuxOperation()
        results = op.run([video], workdir, flags)
        meta = results[0].metadata
        assert meta["original_format"] == "h264"
        assert meta["duration"] == 3600.0
        assert meta["resolution"] == "1920x1080"

    def test_prioritize_audio_artifacts(self):
        op = RemuxOperation()
        extracted = Artifact(type=ArtifactType.AUDIO, path="output/test/extract_audio/123/audio_track_1.wav", metadata={"source": "extracted"})
        muted = Artifact(type=ArtifactType.AUDIO, path="output/test/mute_audio/456/muted_audio_track_1.wav", metadata={"source": "muted"})
        workdir = Path("/tmp/test")
        r1 = op._prioritize_audio_artifacts([extracted], workdir)
        assert len(r1) == 1 and r1[0].path == extracted.path
        r2 = op._prioritize_audio_artifacts([muted], workdir)
        assert len(r2) == 1 and r2[0].path == muted.path
        r3 = op._prioritize_audio_artifacts([extracted, muted], workdir)
        assert len(r3) == 1 and muted.path in r3[0].path
        r4 = op._prioritize_audio_artifacts([], workdir)
        assert len(r4) == 0

    @patch('src.ops.remux.FFmpegAdapter')
    def test_run_prioritizes_muted_audio(self, mock_ffmpeg_class):
        mock_ffmpeg = mock_ffmpeg_class.return_value
        mock_ffmpeg.remux.side_effect = _return_output_side_effect

        workdir = Path("/tmp/test")
        video = Artifact(type=ArtifactType.VIDEO, path="/path/to/video.mp4", metadata={})
        extracted = Artifact(type=ArtifactType.AUDIO, path="output/test/extract_audio/123/audio_track_1.wav", metadata={"source": "extracted"})
        muted = Artifact(type=ArtifactType.AUDIO, path="output/test/mute_audio/456/muted_audio_track_1.wav", metadata={"source": "muted"})
        flags = OperationFlags()
        op = RemuxOperation()
        results = op.run([video, extracted, muted], workdir, flags)
        mock_ffmpeg.remux.assert_called_once()
        audio_tracks = mock_ffmpeg.remux.call_args.kwargs["audio_tracks"]
        assert audio_tracks == [muted.path]
        assert results[0].metadata["audio_tracks"] == 1

    def test_subtitle_mode_masked_only(self):
        op = RemuxOperation()
        extracted = Artifact(type=ArtifactType.SUBTITLE, path="output/test/extract_subtitles/123/subtitle.srt", metadata={"language": "en"})
        merged = Artifact(type=ArtifactType.SUBTITLE, path="output/test/merge_subtitles/456/merged_subtitles.srt", metadata={"language": "en", "merged_from": ["s1", "s2"]})
        masked = Artifact(type=ArtifactType.SUBTITLE, path="output/test/mask_subtitles/789/masked_subtitles.srt", metadata={"language": "en", "profanity_filtered": True})
        r1 = op._get_masked_subtitles_only([extracted, merged, masked])
        assert len(r1) == 1 and r1[0].path == masked.path
        r2 = op._get_masked_subtitles_only([extracted, merged])
        assert len(r2) == 1 and r2[0].path == merged.path
        r3 = op._get_masked_subtitles_only([extracted])
        assert len(r3) == 0

    @patch('src.ops.remux.FFmpegAdapter')
    def test_subtitle_modes(self, mock_ffmpeg_class):
        mock_ffmpeg = mock_ffmpeg_class.return_value
        mock_ffmpeg.remux.side_effect = _return_output_side_effect

        workdir = Path("/tmp/test")
        video = Artifact(type=ArtifactType.VIDEO, path="/path/to/video.mp4", metadata={})
        masked = Artifact(type=ArtifactType.SUBTITLE, path="output/test/mask_subtitles/789/masked_subtitles.srt", metadata={"language": "en", "profanity_filtered": True})
        op = RemuxOperation()

        flags = OperationFlags(subtitle_mode="masked_only")
        r1 = op.run([video, masked], workdir, flags)
        assert r1[0].metadata["subtitle_tracks"] == 1

        flags = OperationFlags(subtitle_mode="none")
        r2 = op.run([video, masked], workdir, flags)
        assert r2[0].metadata["subtitle_tracks"] == 0

        flags = OperationFlags(subtitle_mode="all")
        r3 = op.run([video, masked], workdir, flags)
        assert r3[0].metadata["subtitle_tracks"] == 1