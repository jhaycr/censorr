"""Unit tests for remux pruning behavior."""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.models.artifacts import Artifact, ArtifactType
from src.models.operations import OperationFlags
from src.ops.video_remux import RemuxOperation


def _return_output_side_effect(*args, **kwargs):
    """Mock side effect that returns the output path."""
    if "output" in kwargs:
        return kwargs["output"]
    return args[1] if len(args) > 1 else None


class TestRemuxPruning:
    """Test cases for pruning behavior in RemuxOperation."""

    @patch('src.ops.video_remux.FFmpegAdapter')
    def test_prune_keeps_only_muted_audio_and_masked_subtitle(self, mock_ffmpeg_class):
        """Verify pruning keeps only first muted audio and first masked subtitle."""
        mock_ffmpeg = mock_ffmpeg_class.return_value
        mock_ffmpeg.remux.side_effect = _return_output_side_effect

        workdir = Path("/tmp/test")
        video_artifact = Artifact(
            type=ArtifactType.VIDEO,
            path="/media/movies/Test Movie (2025)/Test Movie (2025).mkv",
            metadata={"original": True}
        )
        
        # Multiple audio tracks: extracted, muted1, muted2
        extracted_audio = Artifact(
            type=ArtifactType.AUDIO,
            path="output/test/extract_audio/999/audio_track_1.wav",
            metadata={"extracted": True}
        )
        muted_audio_1 = Artifact(
            type=ArtifactType.AUDIO,
            path="output/test/muted_audio/999/audio_track_1.wav",
            metadata={"mute_windows_applied": 5}
        )
        muted_audio_2 = Artifact(
            type=ArtifactType.AUDIO,
            path="output/test/muted_audio/999/audio_track_2.wav",
            metadata={"mute_windows_applied": 3}
        )
        
        # Multiple subtitle tracks: original, masked1, masked2
        original_sub = Artifact(
            type=ArtifactType.SUBTITLE,
            path="output/test/extract_subtitles/999/subtitle_track_1.srt",
            metadata={"language": "en"}
        )
        masked_sub_1 = Artifact(
            type=ArtifactType.SUBTITLE,
            path="output/test/masked_subtitles/999/subtitle_track_1.srt",
            metadata={"masked": True, "language": "en"}
        )
        masked_sub_2 = Artifact(
            type=ArtifactType.SUBTITLE,
            path="output/test/masked_subtitles/999/subtitle_track_2.srt",
            metadata={"masked": True, "language": "es"}
        )
        
        flags = OperationFlags(
            subtitle_mode="all",
            prune_non_clean_tracks=True
        )

        op = RemuxOperation()
        results = op.run(
            [video_artifact, extracted_audio, muted_audio_1, muted_audio_2,
             original_sub, masked_sub_1, masked_sub_2],
            workdir,
            flags
        )

        assert len(results) == 1
        result = results[0]
        assert result.type == ArtifactType.VIDEO
        assert "{edition-Censorr}" in Path(result.path).name
        
        # Verify remux was called with pruned tracks
        mock_ffmpeg.remux.assert_called_once()
        kwargs = mock_ffmpeg.remux.call_args.kwargs
        
        # Should have exactly 1 muted audio (first one)
        audio_tracks = kwargs["audio_tracks"]
        assert len(audio_tracks) == 1
        assert "muted_audio" in str(audio_tracks[0])
        assert "audio_track_1.wav" in str(audio_tracks[0])
        
        # Should have exactly 1 masked subtitle (first one)
        subtitle_tracks = kwargs["subtitle_tracks"]
        assert len(subtitle_tracks) == 1
        assert "masked_subtitles" in str(subtitle_tracks[0])
        assert "subtitle_track_1.srt" in str(subtitle_tracks[0])

    @patch('src.ops.video_remux.FFmpegAdapter')
    def test_prune_disabled_keeps_all_tracks(self, mock_ffmpeg_class):
        """Verify pruning disabled keeps all muted audio and masked subtitle tracks."""
        mock_ffmpeg = mock_ffmpeg_class.return_value
        mock_ffmpeg.remux.side_effect = _return_output_side_effect

        workdir = Path("/tmp/test")
        video_artifact = Artifact(
            type=ArtifactType.VIDEO,
            path="/media/movies/Test Movie (2025)/Test Movie (2025).mkv",
            metadata={"original": True}
        )
        
        muted_audio_1 = Artifact(
            type=ArtifactType.AUDIO,
            path="output/test/muted_audio/999/audio_track_1.wav",
            metadata={"mute_windows_applied": 5}
        )
        muted_audio_2 = Artifact(
            type=ArtifactType.AUDIO,
            path="output/test/muted_audio/999/audio_track_2.wav",
            metadata={"mute_windows_applied": 3}
        )
        
        masked_sub_1 = Artifact(
            type=ArtifactType.SUBTITLE,
            path="output/test/masked_subtitles/999/subtitle_track_1.srt",
            metadata={"masked": True, "language": "en"}
        )
        masked_sub_2 = Artifact(
            type=ArtifactType.SUBTITLE,
            path="output/test/masked_subtitles/999/subtitle_track_2.srt",
            metadata={"masked": True, "language": "es"}
        )
        
        flags = OperationFlags(
            subtitle_mode="all",
            prune_non_clean_tracks=False
        )

        op = RemuxOperation()
        results = op.run(
            [video_artifact, muted_audio_1, muted_audio_2, masked_sub_1, masked_sub_2],
            workdir,
            flags
        )

        assert len(results) == 1
        
        # Verify remux was called with all muted audio and masked subtitle tracks
        mock_ffmpeg.remux.assert_called_once()
        kwargs = mock_ffmpeg.remux.call_args.kwargs
        
        audio_tracks = kwargs["audio_tracks"]
        assert len(audio_tracks) == 2
        
        subtitle_tracks = kwargs["subtitle_tracks"]
        assert len(subtitle_tracks) == 2

    @patch('src.ops.video_remux.FFmpegAdapter')
    def test_prune_movie_applies_edition_tag(self, mock_ffmpeg_class):
        """Verify pruning with movie applies edition-Censorr tag."""
        mock_ffmpeg = mock_ffmpeg_class.return_value
        mock_ffmpeg.remux.side_effect = _return_output_side_effect

        workdir = Path("/tmp/test")
        video_artifact = Artifact(
            type=ArtifactType.VIDEO,
            path="/media/movies/Test Movie (2025)/Test Movie (2025).mkv",
            metadata={"original": True}
        )
        
        muted_audio = Artifact(
            type=ArtifactType.AUDIO,
            path="output/test/muted_audio/999/audio_track_1.wav",
            metadata={"mute_windows_applied": 5}
        )
        
        masked_sub = Artifact(
            type=ArtifactType.SUBTITLE,
            path="output/test/masked_subtitles/999/subtitle_track_1.srt",
            metadata={"masked": True, "language": "en"}
        )
        
        flags = OperationFlags(
            subtitle_mode="all",
            prune_non_clean_tracks=True
        )

        op = RemuxOperation()
        results = op.run([video_artifact, muted_audio, masked_sub], workdir, flags)

        assert len(results) == 1
        result = results[0]
        assert "{edition-Censorr}" in Path(result.path).name

    @patch('src.ops.video_remux.FFmpegAdapter')
    def test_prune_episode_skips_edition_tag(self, mock_ffmpeg_class):
        """Verify pruning with episode skips edition tag."""
        mock_ffmpeg = mock_ffmpeg_class.return_value
        mock_ffmpeg.remux.side_effect = _return_output_side_effect

        workdir = Path("/tmp/test")
        video_artifact = Artifact(
            type=ArtifactType.VIDEO,
            path="/media/tv/Test Show (2025)/Season 01/Test Show - S01E01.mkv",
            metadata={"original": True}
        )
        
        muted_audio = Artifact(
            type=ArtifactType.AUDIO,
            path="output/test/muted_audio/999/audio_track_1.wav",
            metadata={"mute_windows_applied": 5}
        )
        
        masked_sub = Artifact(
            type=ArtifactType.SUBTITLE,
            path="output/test/masked_subtitles/999/subtitle_track_1.srt",
            metadata={"masked": True, "language": "en"}
        )
        
        flags = OperationFlags(
            subtitle_mode="all",
            prune_non_clean_tracks=True
        )

        op = RemuxOperation()
        results = op.run([video_artifact, muted_audio, masked_sub], workdir, flags)

        assert len(results) == 1
        result = results[0]
        # Episode should NOT have edition tag
        assert "{edition-Censorr}" not in Path(result.path).name
        assert "S01E01" in Path(result.path).name

    @patch('src.ops.video_remux.FFmpegAdapter')
    def test_prune_no_muted_audio_falls_back_to_extracted(self, mock_ffmpeg_class):
        """Verify pruning without muted audio falls back to existing behavior."""
        mock_ffmpeg = mock_ffmpeg_class.return_value
        mock_ffmpeg.remux.side_effect = _return_output_side_effect

        workdir = Path("/tmp/test")
        video_artifact = Artifact(
            type=ArtifactType.VIDEO,
            path="/media/movies/Test Movie (2025)/Test Movie (2025).mkv",
            metadata={"original": True}
        )
        
        # Only extracted audio, no muted
        extracted_audio = Artifact(
            type=ArtifactType.AUDIO,
            path="output/test/extract_audio/999/audio_track_1.wav",
            metadata={"extracted": True}
        )
        
        masked_sub = Artifact(
            type=ArtifactType.SUBTITLE,
            path="output/test/masked_subtitles/999/subtitle_track_1.srt",
            metadata={"masked": True, "language": "en"}
        )
        
        flags = OperationFlags(
            subtitle_mode="all",
            prune_non_clean_tracks=True
        )

        op = RemuxOperation()
        results = op.run([video_artifact, extracted_audio, masked_sub], workdir, flags)

        assert len(results) == 1
        
        # Should still include extracted audio as fallback
        mock_ffmpeg.remux.assert_called_once()
        kwargs = mock_ffmpeg.remux.call_args.kwargs
        audio_tracks = kwargs["audio_tracks"]
        assert len(audio_tracks) == 1
        assert "extract_audio" in str(audio_tracks[0])

    @patch('src.ops.video_remux.FFmpegAdapter')
    def test_prune_no_masked_subtitle_omits_subtitles(self, mock_ffmpeg_class):
        """Verify pruning without masked subtitle results in no subtitles."""
        mock_ffmpeg = mock_ffmpeg_class.return_value
        mock_ffmpeg.remux.side_effect = _return_output_side_effect

        workdir = Path("/tmp/test")
        video_artifact = Artifact(
            type=ArtifactType.VIDEO,
            path="/media/movies/Test Movie (2025)/Test Movie (2025).mkv",
            metadata={"original": True}
        )
        
        muted_audio = Artifact(
            type=ArtifactType.AUDIO,
            path="output/test/muted_audio/999/audio_track_1.wav",
            metadata={"mute_windows_applied": 5}
        )
        
        # Only original subtitle, no masked
        original_sub = Artifact(
            type=ArtifactType.SUBTITLE,
            path="output/test/extract_subtitles/999/subtitle_track_1.srt",
            metadata={"language": "en"}
        )
        
        flags = OperationFlags(
            subtitle_mode="all",
            prune_non_clean_tracks=True
        )

        op = RemuxOperation()
        results = op.run([video_artifact, muted_audio, original_sub], workdir, flags)

        assert len(results) == 1
        
        # Should have no subtitles
        mock_ffmpeg.remux.assert_called_once()
        kwargs = mock_ffmpeg.remux.call_args.kwargs
        subtitle_tracks = kwargs["subtitle_tracks"]
        assert len(subtitle_tracks) == 0

    @patch('src.ops.video_remux.FFmpegAdapter')
    def test_prune_idempotent_with_clean_input(self, mock_ffmpeg_class):
        """Verify pruning is idempotent when input already has only clean tracks."""
        mock_ffmpeg = mock_ffmpeg_class.return_value
        mock_ffmpeg.remux.side_effect = _return_output_side_effect

        workdir = Path("/tmp/test")
        video_artifact = Artifact(
            type=ArtifactType.VIDEO,
            path="/media/movies/Test Movie (2025)/Test Movie (2025) {edition-Censorr}.mkv",
            metadata={"original": True}
        )
        
        # Only clean tracks
        muted_audio = Artifact(
            type=ArtifactType.AUDIO,
            path="output/test/muted_audio/999/audio_track_1.wav",
            metadata={"mute_windows_applied": 5}
        )
        
        masked_sub = Artifact(
            type=ArtifactType.SUBTITLE,
            path="output/test/masked_subtitles/999/subtitle_track_1.srt",
            metadata={"masked": True, "language": "en"}
        )
        
        flags = OperationFlags(
            subtitle_mode="all",
            prune_non_clean_tracks=True
        )

        op = RemuxOperation()
        results = op.run([video_artifact, muted_audio, masked_sub], workdir, flags)

        assert len(results) == 1
        result = results[0]
        
        # Should produce same output with edition tag
        assert "{edition-Censorr}" in Path(result.path).name
        
        # Should have exactly 1 audio and 1 subtitle
        mock_ffmpeg.remux.assert_called_once()
        kwargs = mock_ffmpeg.remux.call_args.kwargs
        assert len(kwargs["audio_tracks"]) == 1
        assert len(kwargs["subtitle_tracks"]) == 1
