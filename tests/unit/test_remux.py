"""Unit tests for remux operation."""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, call

from src.models.artifacts import Artifact, ArtifactType
from src.models.operations import OperationFlags
from src.ops.remux import RemuxOperation


class TestRemuxOperation:
    """Test cases for RemuxOperation."""

    def test_operation_creation(self):
        """Test operation can be created."""
        op = RemuxOperation()
        assert op.consumes == {ArtifactType.VIDEO, ArtifactType.AUDIO, ArtifactType.SUBTITLE}
        assert op.produces == {ArtifactType.VIDEO}

    @patch('src.ops.remux.FFmpegAdapter')
    def test_run_with_all_track_types(self, mock_ffmpeg_class):
        """Test running operation with video, audio, and subtitle tracks."""
        # Setup mocks
        mock_ffmpeg = mock_ffmpeg_class.return_value
        mock_ffmpeg.remux.return_value = "/tmp/test/remuxed_video.mp4"
        
        # Test data
        workdir = Path("/tmp/test")
        video_artifact = Artifact(
            type=ArtifactType.VIDEO,
            path="/path/to/video.mp4",
            metadata={"original": True}
        )
        audio_artifact = Artifact(
            type=ArtifactType.AUDIO,
            path="/path/to/audio.wav",
            metadata={"mute_windows_applied": 3}
        )
        subtitle_artifact = Artifact(
            type=ArtifactType.SUBTITLE,
            path="/path/to/subtitles.srt",
            metadata={"masked": True, "language": "en"}
        )
        flags = OperationFlags(subtitle_mode="all")
        
        # Execute operation
        op = RemuxOperation()
        results = op.run([video_artifact, audio_artifact, subtitle_artifact], workdir, flags)
        
        # Verify results
        assert len(results) == 1
        assert results[0].type == ArtifactType.VIDEO
        assert results[0].path == "/tmp/test/remuxed_video.mp4"
        assert "input_video" in results[0].metadata
        assert "audio_tracks" in results[0].metadata
        assert "subtitle_tracks" in results[0].metadata
        assert results[0].metadata["audio_tracks"] == 1
        assert results[0].metadata["subtitle_tracks"] == 1
        
        # Verify FFmpeg call
        mock_ffmpeg.remux.assert_called_once_with(
            video_input="/path/to/video.mp4",
            output="/tmp/test/remuxed_video.mp4",
            audio_tracks=["/path/to/audio.wav"],
            subtitle_tracks=["/path/to/subtitles.srt"]
        )

    @patch('src.ops.remux.FFmpegAdapter')
    def test_run_video_only(self, mock_ffmpeg_class):
        """Test running operation with only video (no remuxing needed)."""
        # Setup mocks
        mock_ffmpeg = mock_ffmpeg_class.return_value
        mock_ffmpeg.remux.return_value = "/tmp/test/remuxed_video.mp4"
        
        # Test data - only video artifact
        workdir = Path("/tmp/test")
        video_artifact = Artifact(
            type=ArtifactType.VIDEO,
            path="/path/to/video.mp4",
            metadata={"original": True}
        )
        flags = OperationFlags()
        
        # Execute operation
        op = RemuxOperation()
        results = op.run([video_artifact], workdir, flags)
        
        # Verify results
        assert len(results) == 1
        assert results[0].type == ArtifactType.VIDEO
        assert results[0].path == "/tmp/test/remuxed_video.mp4"
        assert results[0].metadata["audio_tracks"] == 0
        assert results[0].metadata["subtitle_tracks"] == 0
        
        # Verify FFmpeg call with empty tracks
        mock_ffmpeg.remux.assert_called_once_with(
            video_input="/path/to/video.mp4",
            output="/tmp/test/remuxed_video.mp4",
            audio_tracks=[],
            subtitle_tracks=[]
        )

    @patch('src.ops.remux.FFmpegAdapter')
    def test_run_multiple_audio_tracks(self, mock_ffmpeg_class):
        """Test running operation with multiple audio tracks."""
        # Setup mocks
        mock_ffmpeg = mock_ffmpeg_class.return_value
        mock_ffmpeg.remux.return_value = "/tmp/test/remuxed_video.mp4"
        
        # Test data
        workdir = Path("/tmp/test")
        video_artifact = Artifact(
            type=ArtifactType.VIDEO,
            path="/path/to/video.mp4",
            metadata={}
        )
        audio_artifact1 = Artifact(
            type=ArtifactType.AUDIO,
            path="/path/to/audio1.wav",
            metadata={"language": "en"}
        )
        audio_artifact2 = Artifact(
            type=ArtifactType.AUDIO,
            path="/path/to/audio2.wav",
            metadata={"language": "es"}
        )
        flags = OperationFlags()
        
        # Execute operation
        op = RemuxOperation()
        results = op.run([video_artifact, audio_artifact1, audio_artifact2], workdir, flags)
        
        # Verify results
        assert len(results) == 1
        assert results[0].metadata["audio_tracks"] == 2
        
        # Verify FFmpeg call
        call_args = mock_ffmpeg.remux.call_args
        audio_tracks = call_args.kwargs["audio_tracks"]
        assert len(audio_tracks) == 2
        assert "/path/to/audio1.wav" in audio_tracks
        assert "/path/to/audio2.wav" in audio_tracks

    @patch('src.ops.remux.FFmpegAdapter')
    def test_run_multiple_subtitle_tracks(self, mock_ffmpeg_class):
        """Test running operation with multiple subtitle tracks."""
        # Setup mocks
        mock_ffmpeg = mock_ffmpeg_class.return_value
        mock_ffmpeg.remux.return_value = "/tmp/test/remuxed_video.mp4"
        
        # Test data
        workdir = Path("/tmp/test")
        video_artifact = Artifact(
            type=ArtifactType.VIDEO,
            path="/path/to/video.mp4",
            metadata={}
        )
        subtitle_artifact1 = Artifact(
            type=ArtifactType.SUBTITLE,
            path="/path/to/subtitles_en.srt",
            metadata={"language": "en"}
        )
        subtitle_artifact2 = Artifact(
            type=ArtifactType.SUBTITLE,
            path="/path/to/subtitles_es.srt",
            metadata={"language": "es"}
        )
        flags = OperationFlags(subtitle_mode="all")
        
        # Execute operation
        op = RemuxOperation()
        results = op.run([video_artifact, subtitle_artifact1, subtitle_artifact2], workdir, flags)
        
        # Verify results
        assert len(results) == 1
        assert results[0].metadata["subtitle_tracks"] == 2
        
        # Verify FFmpeg call
        call_args = mock_ffmpeg.remux.call_args
        subtitle_tracks = call_args.kwargs["subtitle_tracks"]
        assert len(subtitle_tracks) == 2
        assert "/path/to/subtitles_en.srt" in subtitle_tracks
        assert "/path/to/subtitles_es.srt" in subtitle_tracks

    @patch('src.ops.remux.FFmpegAdapter')
    def test_run_dry_run(self, mock_ffmpeg_class):
        """Test operation in dry-run mode."""
        # Setup mocks
        mock_ffmpeg = mock_ffmpeg_class.return_value
        
        # Test data
        workdir = Path("/tmp/test")
        video_artifact = Artifact(
            type=ArtifactType.VIDEO,
            path="/path/to/video.mp4",
            metadata={}
        )
        audio_artifact = Artifact(
            type=ArtifactType.AUDIO,
            path="/path/to/audio.wav",
            metadata={}
        )
        flags = OperationFlags(dry_run=True)
        
        # Execute operation
        op = RemuxOperation()
        results = op.run([video_artifact, audio_artifact], workdir, flags)
        
        # Verify results
        assert len(results) == 1
        assert results[0].type == ArtifactType.VIDEO
        assert "remuxed_" in results[0].path
        assert results[0].metadata["audio_tracks"] == 1
        
        # Verify FFmpeg was not called
        mock_ffmpeg.remux.assert_not_called()

    @patch('src.ops.remux.FFmpegAdapter')
    def test_run_ffmpeg_error(self, mock_ffmpeg_class):
        """Test handling FFmpeg errors."""
        # Setup mocks
        mock_ffmpeg = mock_ffmpeg_class.return_value
        mock_ffmpeg.remux.side_effect = Exception("FFmpeg failed")
        
        # Test data
        workdir = Path("/tmp/test")
        video_artifact = Artifact(
            type=ArtifactType.VIDEO,
            path="/path/to/video.mp4",
            metadata={}
        )
        flags = OperationFlags()
        
        # Execute operation and expect error
        op = RemuxOperation()
        with pytest.raises(RuntimeError, match="Failed to remux video"):
            op.run([video_artifact], workdir, flags)

    def test_run_no_video_artifact(self):
        """Test operation fails with no video artifacts."""
        op = RemuxOperation()
        
        audio_artifact = Artifact(
            type=ArtifactType.AUDIO,
            path="/path/to/audio.wav",
            metadata={}
        )
        
        workdir = Path("/tmp/test")
        flags = OperationFlags()
        
        with pytest.raises(ValueError, match="No video artifacts found"):
            op.run([audio_artifact], workdir, flags)

    def test_run_multiple_video_artifacts(self):
        """Test operation fails with multiple video artifacts."""
        op = RemuxOperation()
        
        video_artifact1 = Artifact(
            type=ArtifactType.VIDEO,
            path="/path/to/video1.mp4",
            metadata={}
        )
        video_artifact2 = Artifact(
            type=ArtifactType.VIDEO,
            path="/path/to/video2.mp4",
            metadata={}
        )
        
        workdir = Path("/tmp/test")
        flags = OperationFlags()
        
        with pytest.raises(ValueError, match="Multiple video artifacts found"):
            op.run([video_artifact1, video_artifact2], workdir, flags)

    @patch('src.ops.remux.FFmpegAdapter')
    def test_generate_output_path(self, mock_ffmpeg_class):
        """Test output path generation."""
        op = RemuxOperation()
        
        # Test basic path generation
        workdir = Path("/tmp/test")
        input_path = "/path/to/video.mp4"
        output_path = op._generate_output_path(input_path, workdir)
        
        assert output_path.startswith("/tmp/test/remuxed_")
        assert output_path.endswith(".mp4")
        
        # Test different extension
        input_path = "/path/to/video.mkv"
        output_path = op._generate_output_path(input_path, workdir)
        assert output_path.endswith(".mkv")

    @patch('src.ops.remux.FFmpegAdapter')
    def test_verbose_mode(self, mock_ffmpeg_class):
        """Test operation in verbose mode."""
        # Setup mocks
        mock_ffmpeg = mock_ffmpeg_class.return_value
        mock_ffmpeg.remux.return_value = "/tmp/test/remuxed_video.mp4"
        
        # Test data
        workdir = Path("/tmp/test")
        video_artifact = Artifact(
            type=ArtifactType.VIDEO,
            path="/path/to/video.mp4",
            metadata={}
        )
        audio_artifact = Artifact(
            type=ArtifactType.AUDIO,
            path="/path/to/audio.wav",
            metadata={}
        )
        subtitle_artifact = Artifact(
            type=ArtifactType.SUBTITLE,
            path="/path/to/subtitles.srt",
            metadata={"language": "en"}
        )
        flags = OperationFlags(verbose=True)
        
        # Execute operation
        op = RemuxOperation()
        with patch('builtins.print') as mock_print:
            results = op.run([video_artifact, audio_artifact, subtitle_artifact], workdir, flags)
        
        # Verify verbose output was printed
        assert mock_print.called
        print_calls = [call[0][0] for call in mock_print.call_args_list]
        assert any("audio tracks" in call for call in print_calls)
        assert any("subtitle tracks" in call for call in print_calls)
        assert any("Remuxing video" in call for call in print_calls)

    @patch('src.ops.remux.FFmpegAdapter')
    def test_preserve_video_metadata(self, mock_ffmpeg_class):
        """Test that video metadata is preserved in the result."""
        # Setup mocks
        mock_ffmpeg = mock_ffmpeg_class.return_value
        mock_ffmpeg.remux.return_value = "/tmp/test/remuxed_video.mp4"
        
        # Test data
        workdir = Path("/tmp/test")
        video_artifact = Artifact(
            type=ArtifactType.VIDEO,
            path="/path/to/video.mp4",
            metadata={
                "original_format": "h264",
                "duration": 3600.0,
                "resolution": "1920x1080"
            }
        )
        flags = OperationFlags()
        
        # Execute operation
        op = RemuxOperation()
        results = op.run([video_artifact], workdir, flags)
        
        # Verify video metadata is preserved
        assert results[0].metadata["original_format"] == "h264"
        assert results[0].metadata["duration"] == 3600.0
        assert results[0].metadata["resolution"] == "1920x1080"

    def test_prioritize_audio_artifacts(self):
        """Test audio artifact prioritization logic."""
        op = RemuxOperation()
        
        # Create test artifacts
        extracted_audio = Artifact(
            type=ArtifactType.AUDIO,
            path="output/test/extract_audio/123/audio_track_1.wav",
            metadata={"source": "extracted"}
        )
        
        muted_audio = Artifact(
            type=ArtifactType.AUDIO,
            path="output/test/mute_audio/456/muted_audio_track_1.wav",
            metadata={"source": "muted"}
        )
        
        # Test 1: Only extracted audio
        result = op._prioritize_audio_artifacts([extracted_audio])
        assert len(result) == 1
        assert result[0].path == extracted_audio.path
        
        # Test 2: Only muted audio
        result = op._prioritize_audio_artifacts([muted_audio])
        assert len(result) == 1
        assert result[0].path == muted_audio.path
        
        # Test 3: Both extracted and muted audio (should prefer muted)
        result = op._prioritize_audio_artifacts([extracted_audio, muted_audio])
        assert len(result) == 1
        assert result[0].path == muted_audio.path
        
        # Test 4: Empty list
        result = op._prioritize_audio_artifacts([])
        assert len(result) == 0

    @patch('src.ops.remux.FFmpegAdapter')
    def test_run_prioritizes_muted_audio(self, mock_ffmpeg_class):
        """Test that remux operation prioritizes muted audio over extracted audio."""
        # Setup mocks
        mock_ffmpeg = mock_ffmpeg_class.return_value
        mock_ffmpeg.remux.return_value = "/tmp/test/remuxed_video.mp4"
        
        # Test data
        workdir = Path("/tmp/test")
        video_artifact = Artifact(
            type=ArtifactType.VIDEO,
            path="/path/to/video.mp4",
            metadata={}
        )
        
        extracted_audio = Artifact(
            type=ArtifactType.AUDIO,
            path="output/test/extract_audio/123/audio_track_1.wav",
            metadata={"source": "extracted"}
        )
        
        muted_audio = Artifact(
            type=ArtifactType.AUDIO,
            path="output/test/mute_audio/456/muted_audio_track_1.wav",
            metadata={"source": "muted"}
        )
        
        flags = OperationFlags()
        
        # Execute operation with both extracted and muted audio
        op = RemuxOperation()
        results = op.run([video_artifact, extracted_audio, muted_audio], workdir, flags)
        
        # Verify remux was called with muted audio only
        mock_ffmpeg.remux.assert_called_once()
        call_args = mock_ffmpeg.remux.call_args
        assert call_args[1]["audio_tracks"] == [muted_audio.path]
        
        # Verify result metadata
        assert len(results) == 1
        assert results[0].metadata["audio_tracks"] == 1

    def test_subtitle_mode_masked_only(self):
        """Test subtitle filtering for masked_only mode."""
        op = RemuxOperation()
        
        # Create test artifacts
        extracted_subtitle = Artifact(
            type=ArtifactType.SUBTITLE,
            path="output/test/extract_subtitles/123/subtitle.srt",
            metadata={"language": "en"}
        )
        
        merged_subtitle = Artifact(
            type=ArtifactType.SUBTITLE,
            path="output/test/merge_subtitles/456/merged_subtitles.srt",
            metadata={"language": "en", "merged_from": ["sub1.srt", "sub2.srt"]}
        )
        
        masked_subtitle = Artifact(
            type=ArtifactType.SUBTITLE,
            path="output/test/mask_subtitles/789/masked_subtitles.srt",
            metadata={"language": "en", "profanity_filtered": True}
        )
        
        # Test 1: Only masked subtitle should be selected
        result = op._get_masked_subtitles_only([extracted_subtitle, merged_subtitle, masked_subtitle])
        assert len(result) == 1
        assert result[0].path == masked_subtitle.path
        
        # Test 2: Fallback to merged when no masked available
        result = op._get_masked_subtitles_only([extracted_subtitle, merged_subtitle])
        assert len(result) == 1
        assert result[0].path == merged_subtitle.path
        
        # Test 3: Empty when nothing matches
        result = op._get_masked_subtitles_only([extracted_subtitle])
        assert len(result) == 0

    @patch('src.ops.remux.FFmpegAdapter')
    def test_subtitle_modes(self, mock_ffmpeg_class):
        """Test different subtitle modes in remux operation."""
        # Setup mocks
        mock_ffmpeg = mock_ffmpeg_class.return_value
        mock_ffmpeg.remux.return_value = "/tmp/test/remuxed_video.mp4"
        
        # Test data
        workdir = Path("/tmp/test")
        video_artifact = Artifact(
            type=ArtifactType.VIDEO,
            path="/path/to/video.mp4",
            metadata={}
        )
        
        masked_subtitle = Artifact(
            type=ArtifactType.SUBTITLE,
            path="output/test/mask_subtitles/789/masked_subtitles.srt",
            metadata={"language": "en", "profanity_filtered": True}
        )
        
        # Test mode: masked_only (default)
        flags = OperationFlags(subtitle_mode="masked_only")
        op = RemuxOperation()
        results = op.run([video_artifact, masked_subtitle], workdir, flags)
        assert results[0].metadata["subtitle_tracks"] == 1
        
        # Test mode: none
        flags = OperationFlags(subtitle_mode="none")
        results = op.run([video_artifact, masked_subtitle], workdir, flags)
        assert results[0].metadata["subtitle_tracks"] == 0
        
        # Test mode: all
        flags = OperationFlags(subtitle_mode="all")
        results = op.run([video_artifact, masked_subtitle], workdir, flags)
        assert results[0].metadata["subtitle_tracks"] == 1