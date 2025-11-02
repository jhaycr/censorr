"""Tests for extract_subtitles operation."""
import pytest
from pathlib import Path
import tempfile
from unittest.mock import Mock, patch
from src.ops.subtitle_extract import ExtractSubtitlesOperation
from src.models.artifacts import Artifact, ArtifactType
from src.models.operations import OperationFlags


class TestExtractSubtitlesOperation:
    """Test ExtractSubtitlesOperation."""
    
    def test_operation_creation(self):
        """Test operation creation."""
        op = ExtractSubtitlesOperation()
        assert op.name == "subtitle_extract"
        assert ArtifactType.VIDEO in op.consumes
        assert ArtifactType.SUBTITLE in op.produces
        assert op.description is not None
    
    @patch('src.adapters.ffmpeg.FFmpegAdapter.probe')
    @patch('src.adapters.ffmpeg.FFmpegAdapter.extract_subtitles')
    def test_run_with_subtitles(self, mock_extract, mock_probe):
        """Test running operation with video containing subtitles."""
        # Setup mocks
        from src.adapters.ffmpeg import MediaInfo, TrackInfo
        
        mock_probe.return_value = MediaInfo(
            format="matroska",
            tracks=[
                TrackInfo(index=0, type="video", codec="h264"),
                TrackInfo(index=1, type="audio", codec="aac", language="en"),
                TrackInfo(index=2, type="subtitle", codec="subrip", language="en"),
                TrackInfo(index=3, type="subtitle", codec="subrip", language="es")
            ]
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create input video artifact
            video_path = Path(tmpdir) / "video.mkv"
            video_path.write_text("mock video")
            
            video_artifact = Artifact(
                type=ArtifactType.VIDEO,
                path=str(video_path),
                metadata={"duration": 120.0}
            )
            
            # Mock subtitle extraction
            def mock_extract_subtitles(input_path, output_path, track_index=0):
                Path(output_path).write_text("Mock subtitles")
                return output_path
            
            mock_extract.side_effect = mock_extract_subtitles
            
            # Create operation and run
            op = ExtractSubtitlesOperation()
            flags = OperationFlags()
            
            result = op.run([video_artifact], Path(tmpdir), flags)
            
            # Verify result
            assert len(result) == 2  # Two subtitle tracks extracted
            
            # Check artifacts
            for artifact in result:
                assert artifact.type == ArtifactType.SUBTITLE
                assert artifact.metadata.get("language") in ["en", "es"]
                assert Path(artifact.path).exists()
            
            # Verify FFmpeg calls
            mock_probe.assert_called_once()
            assert mock_extract.call_count == 2  # Two subtitle tracks
    
    @patch('src.adapters.ffmpeg.FFmpegAdapter.probe')
    def test_run_no_subtitles(self, mock_probe):
        """Test running operation with video containing no subtitles."""
        # Setup mock with no subtitle tracks
        from src.adapters.ffmpeg import MediaInfo, TrackInfo
        
        mock_probe.return_value = MediaInfo(
            format="mp4",
            tracks=[
                TrackInfo(index=0, type="video", codec="h264"),
                TrackInfo(index=1, type="audio", codec="aac", language="en")
            ]
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = Path(tmpdir) / "video.mp4"
            video_path.write_text("mock video")
            
            video_artifact = Artifact(
                type=ArtifactType.VIDEO,
                path=str(video_path),
                metadata={}
            )
            
            op = ExtractSubtitlesOperation()
            flags = OperationFlags()
            
            result = op.run([video_artifact], Path(tmpdir), flags)
            
            # Should return empty list
            assert len(result) == 0
    
    def test_run_dry_run(self):
        """Test running operation in dry-run mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = Path(tmpdir) / "video.mkv"
            video_path.write_text("mock video")
            
            video_artifact = Artifact(
                type=ArtifactType.VIDEO,
                path=str(video_path),
                metadata={}
            )
            
            op = ExtractSubtitlesOperation()
            flags = OperationFlags(dry_run=True)
            
            with patch.object(op.ffmpeg, 'probe') as mock_probe:
                from src.adapters.ffmpeg import MediaInfo, TrackInfo
                
                mock_probe.return_value = MediaInfo(
                    format="matroska",
                    tracks=[
                        TrackInfo(index=0, type="video", codec="h264"),
                        TrackInfo(index=1, type="subtitle", codec="subrip", language="en")
                    ]
                )
                
                result = op.run([video_artifact], Path(tmpdir), flags)
                
                # Should return planned artifacts but not create files
                assert len(result) == 1
                assert not Path(result[0].path).exists()  # Not actually created
    
    @patch('src.adapters.ffmpeg.FFmpegAdapter.probe')
    def test_run_ffmpeg_error(self, mock_probe):
        """Test handling FFmpeg errors."""
        from src.adapters.ffmpeg import FFmpegError
        
        mock_probe.side_effect = FFmpegError("Failed to probe file")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = Path(tmpdir) / "video.mkv"
            video_path.write_text("mock video")
            
            video_artifact = Artifact(
                type=ArtifactType.VIDEO,
                path=str(video_path),
                metadata={}
            )
            
            op = ExtractSubtitlesOperation()
            flags = OperationFlags()
            
            # Should raise RuntimeError
            with pytest.raises(RuntimeError, match="Failed to probe file"):
                op.run([video_artifact], Path(tmpdir), flags)
    
    def test_run_no_video_artifact(self):
        """Test running operation without video artifact."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create non-video artifact
            audio_artifact = Artifact(
                type=ArtifactType.AUDIO,
                path="/path/to/audio.wav",
                metadata={}
            )
            
            op = ExtractSubtitlesOperation()
            flags = OperationFlags()
            
            # Should raise ValueError
            with pytest.raises(ValueError, match="No video artifact found"):
                op.run([audio_artifact], Path(tmpdir), flags)
    
    def test_validate_inputs(self):
        """Test input validation."""
        op = ExtractSubtitlesOperation()
        
        # Valid input
        video_artifact = Artifact(
            type=ArtifactType.VIDEO,
            path="/path/to/video.mkv",
            metadata={}
        )
        
        # Should not raise
        op.validate_inputs([video_artifact])
        
        # Invalid input
        audio_artifact = Artifact(
            type=ArtifactType.AUDIO,
            path="/path/to/audio.wav",
            metadata={}
        )
        
        # Should raise ValueError
        with pytest.raises(ValueError, match="Missing required input types"):
            op.validate_inputs([audio_artifact])