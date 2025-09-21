"""Unit tests for extract_audio operation."""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from src.models.artifacts import Artifact, ArtifactType
from src.models.operations import OperationFlags
from src.ops.extract_audio import ExtractAudioOperation
from src.adapters.ffmpeg import FFmpegError, MediaInfo, TrackInfo


class TestExtractAudioOperation:
    """Test cases for ExtractAudioOperation."""
    
    def test_operation_creation(self):
        """Test operation can be created with correct properties."""
        op = ExtractAudioOperation()
        
        assert op.name == "extract_audio"
        assert op.description == "Extract audio tracks from video files using FFmpeg"
        assert ArtifactType.VIDEO in op.consumes
        assert ArtifactType.AUDIO in op.produces
        assert hasattr(op, 'ffmpeg')
    
    def test_operation_creation_with_format(self):
        """Test operation creation with specific audio format."""
        op = ExtractAudioOperation(audio_format="mp3")
        
        assert op.audio_format == "mp3"
        
        op = ExtractAudioOperation(audio_format="flac")
        assert op.audio_format == "flac"
    
    @patch('src.ops.extract_audio.FFmpegAdapter')
    def test_run_with_audio_tracks(self, mock_ffmpeg_class):
        """Test operation extracts audio tracks from video."""
        # Setup mocks
        mock_ffmpeg = mock_ffmpeg_class.return_value
        
        # Mock audio tracks
        audio_tracks = [
            TrackInfo(index=0, type="audio", codec="aac", language="en"),
            TrackInfo(index=1, type="audio", codec="ac3", language="en")
        ]
        
        media_info = MediaInfo(
            format="matroska",
            tracks=[
                TrackInfo(index=0, type="video", codec="h264"),
                audio_tracks[0],
                audio_tracks[1]
            ]
        )
        
        mock_ffmpeg.probe.return_value = media_info
        mock_ffmpeg.extract_audio.return_value = "/tmp/test/audio_track_0.wav"
        
        # Test data
        workdir = Path("/tmp/test")
        video_artifact = Artifact(
            type=ArtifactType.VIDEO,
            path="/path/to/video.mp4",
            metadata={}
        )
        flags = OperationFlags()
        
        # Execute operation
        op = ExtractAudioOperation()
        results = op.run([video_artifact], workdir, flags)
        
        # Verify results
        assert len(results) == 2  # Two audio tracks
        
        audio_tracks = media_info.get_audio_tracks()
        for i, result in enumerate(results):
            assert result.type == ArtifactType.AUDIO
            assert result.metadata["track"] == str(audio_tracks[i].index)
            assert result.metadata["codec"] == audio_tracks[i].codec
            assert result.metadata["language"] == audio_tracks[i].language
            assert result.metadata["source_file"] == video_artifact.path
        
        # Verify FFmpeg was called correctly
        assert mock_ffmpeg.extract_audio.call_count == 2
    
    @patch('src.ops.extract_audio.FFmpegAdapter')
    def test_run_with_track_filter(self, mock_ffmpeg_class):
        """Test operation with specific track selection."""
        # Setup mocks
        mock_ffmpeg = mock_ffmpeg_class.return_value
        
        audio_tracks = [
            TrackInfo(index=0, type="audio", codec="aac", language="en"),
            TrackInfo(index=1, type="audio", codec="ac3", language="fr")
        ]
        
        media_info = MediaInfo(
            format="matroska",
            tracks=[
                TrackInfo(index=0, type="video", codec="h264"),
                audio_tracks[0],
                audio_tracks[1]
            ]
        )
        
        mock_ffmpeg.probe.return_value = media_info
        mock_ffmpeg.extract_audio.return_value = "/tmp/test/audio_track_0.wav"
        
        # Test data with language filter
        workdir = Path("/tmp/test")
        video_artifact = Artifact(
            type=ArtifactType.VIDEO,
            path="/path/to/video.mp4",
            metadata={}
        )
        flags = OperationFlags()
        
        # Execute operation with language filter
        op = ExtractAudioOperation(language_filter="en")
        results = op.run([video_artifact], workdir, flags)
        
        # Verify only English track was extracted
        assert len(results) == 1
        assert results[0].metadata["language"] == "en"
        assert mock_ffmpeg.extract_audio.call_count == 1
    
    @patch('src.ops.extract_audio.FFmpegAdapter')
    def test_run_no_audio_tracks(self, mock_ffmpeg_class):
        """Test operation with video file containing no audio tracks."""
        # Setup mocks
        mock_ffmpeg = mock_ffmpeg_class.return_value
        
        media_info = MediaInfo(
            format="matroska",
            tracks=[TrackInfo(index=0, type="video", codec="h264")]  # No audio tracks
        )
        
        mock_ffmpeg.probe.return_value = media_info
        
        # Test data
        workdir = Path("/tmp/test")
        video_artifact = Artifact(
            type=ArtifactType.VIDEO,
            path="/path/to/video.mp4",
            metadata={}
        )
        flags = OperationFlags()
        
        # Execute operation
        op = ExtractAudioOperation()
        results = op.run([video_artifact], workdir, flags)
        
        # Verify no audio artifacts returned
        assert len(results) == 0
        mock_ffmpeg.extract_audio.assert_not_called()
    
    @patch('src.ops.extract_audio.FFmpegAdapter')
    def test_run_dry_run(self, mock_ffmpeg_class):
        """Test operation in dry-run mode."""
        # Setup mocks
        mock_ffmpeg = mock_ffmpeg_class.return_value
        
        audio_tracks = [
            TrackInfo(index=1, type="audio", codec="aac", language="en")
        ]
        
        media_info = MediaInfo(
            format="matroska",
            tracks=[
                TrackInfo(index=0, type="video", codec="h264"),
                audio_tracks[0]
            ]
        )
        
        mock_ffmpeg.probe.return_value = media_info
        
        # Test data
        workdir = Path("/tmp/test")
        video_artifact = Artifact(
            type=ArtifactType.VIDEO,
            path="/path/to/video.mp4",
            metadata={}
        )
        flags = OperationFlags(dry_run=True)
        
        # Execute operation
        op = ExtractAudioOperation()
        results = op.run([video_artifact], workdir, flags)
        
        # Verify results
        assert len(results) == 1
        result = results[0]
        assert result.type == ArtifactType.AUDIO
        assert result.metadata["planned"] is True
        assert result.metadata["track"] == str(audio_tracks[0].index)
        
        # Verify FFmpeg extract was not called in dry run
        mock_ffmpeg.extract_audio.assert_not_called()
    
    @patch('src.ops.extract_audio.FFmpegAdapter')
    def test_run_ffmpeg_error(self, mock_ffmpeg_class):
        """Test operation with FFmpeg error."""
        # Setup mock to raise error
        mock_ffmpeg = mock_ffmpeg_class.return_value
        mock_ffmpeg.probe.side_effect = FFmpegError("FFmpeg failed")
        
        # Test data
        workdir = Path("/tmp/test")
        video_artifact = Artifact(
            type=ArtifactType.VIDEO,
            path="/path/to/video.mp4",
            metadata={}
        )
        flags = OperationFlags()
        
        # Execute operation
        op = ExtractAudioOperation()
        with pytest.raises(RuntimeError, match="Failed to probe video file"):
            op.run([video_artifact], workdir, flags)
    
    def test_run_no_video_artifact(self):
        """Test operation with no video artifacts."""
        op = ExtractAudioOperation()
        workdir = Path("/tmp/test")
        flags = OperationFlags()
        
        # Test with subtitle artifact
        subtitle_artifact = Artifact(
            type=ArtifactType.SUBTITLE,
            path="/path/to/subtitle.srt",
            metadata={"language": "en"}
        )
        
        with pytest.raises(ValueError, match="No video artifacts found"):
            op.run([subtitle_artifact], workdir, flags)
    
    @patch('src.ops.extract_audio.FFmpegAdapter')
    def test_extract_audio_with_custom_format(self, mock_ffmpeg_class):
        """Test audio extraction with custom format."""
        # Setup mocks
        mock_ffmpeg = mock_ffmpeg_class.return_value
        
        audio_tracks = [
            TrackInfo(index=1, type="audio", codec="aac", language="en")
        ]
        
        media_info = MediaInfo(
            format="matroska",
            tracks=[
                TrackInfo(index=0, type="video", codec="h264"),
                audio_tracks[0]
            ]
        )
        
        mock_ffmpeg.probe.return_value = media_info
        mock_ffmpeg.extract_audio.return_value = "/tmp/test/audio_track_0.mp3"
        
        # Test data
        workdir = Path("/tmp/test")
        video_artifact = Artifact(
            type=ArtifactType.VIDEO,
            path="/path/to/video.mp4",
            metadata={}
        )
        flags = OperationFlags()
        
        # Execute operation with MP3 format
        op = ExtractAudioOperation(audio_format="mp3")
        results = op.run([video_artifact], workdir, flags)
        
        # Verify MP3 format was used
        assert len(results) == 1
        assert results[0].path.endswith(".mp3")
        
        # Verify FFmpeg was called with correct format
        call_args = mock_ffmpeg.extract_audio.call_args
        assert call_args[1]["audio_format"] == "mp3"
    
    @patch('src.ops.extract_audio.FFmpegAdapter')
    def test_filter_audio_tracks_by_language(self, mock_ffmpeg_class):
        """Test _filter_audio_tracks method with language filter."""
        op = ExtractAudioOperation(language_filter="en")
        
        audio_tracks = [
            TrackInfo(index=1, type="audio", codec="aac", language="en"),
            TrackInfo(index=2, type="audio", codec="ac3", language="fr"),
            TrackInfo(index=3, type="audio", codec="aac", language="en")
        ]
        
        filtered_tracks = op._filter_audio_tracks(audio_tracks)
        
        # Should only return English tracks
        assert len(filtered_tracks) == 2
        assert all(track.language == "en" for track in filtered_tracks)
    
    @patch('src.ops.extract_audio.FFmpegAdapter')
    def test_filter_audio_tracks_no_filter(self, mock_ffmpeg_class):
        """Test _filter_audio_tracks method without filter."""
        op = ExtractAudioOperation()  # No language filter
        
        audio_tracks = [
            TrackInfo(index=1, type="audio", codec="aac", language="en"),
            TrackInfo(index=2, type="audio", codec="ac3", language="fr")
        ]
        
        filtered_tracks = op._filter_audio_tracks(audio_tracks)
        
        # Should return all tracks
        assert len(filtered_tracks) == 2
    
    @patch('src.ops.extract_audio.FFmpegAdapter')
    def test_validate_inputs(self, mock_ffmpeg_class):
        """Test input validation."""
        # Setup mock
        mock_ffmpeg = mock_ffmpeg_class.return_value
        mock_ffmpeg.probe.return_value = MediaInfo(
            format="matroska", tracks=[]
        )
        
        op = ExtractAudioOperation()

        # Valid input
        video_artifact = Artifact(
            type=ArtifactType.VIDEO,
            path="/path/to/video.mp4",
            metadata={}
        )

        # Should not raise
        workdir = Path("/tmp/test")
        flags = OperationFlags(dry_run=True)
        results = op.run([video_artifact], workdir, flags)

        # Should return empty list when no audio tracks
        assert isinstance(results, list)
        assert len(results) == 0

        # Invalid input - no video artifacts
        audio_artifact = Artifact(
            type=ArtifactType.AUDIO,
            path="/path/to/audio.wav",
            metadata={}
        )

        with pytest.raises(ValueError, match="No video artifacts found"):
            op.run([audio_artifact], workdir, flags)    @patch('src.ops.extract_audio.FFmpegAdapter')
    @patch('src.ops.extract_audio.FFmpegAdapter')
    def test_verbose_mode(self, mock_ffmpeg_class):
        """Test operation in verbose mode."""
        # Setup mocks
        mock_ffmpeg = mock_ffmpeg_class.return_value
        
        audio_tracks = [
            TrackInfo(index=1, type="audio", codec="aac", language="en")
        ]
        
        media_info = MediaInfo(
            format="matroska",
            tracks=[
                TrackInfo(index=0, type="video", codec="h264"),
                audio_tracks[0]
            ]
        )
        
        mock_ffmpeg.probe.return_value = media_info
        mock_ffmpeg.extract_audio.return_value = "/tmp/test/audio_track_0.wav"
        
        # Test data
        workdir = Path("/tmp/test")
        video_artifact = Artifact(
            type=ArtifactType.VIDEO,
            path="/path/to/video.mp4",
            metadata={}
        )
        flags = OperationFlags(verbose=True)
        
        # Execute operation
        op = ExtractAudioOperation()
        with patch('builtins.print') as mock_print:
            results = op.run([video_artifact], workdir, flags)
        
        # Verify verbose output was printed
        assert mock_print.called
        print_calls = [call[0][0] for call in mock_print.call_args_list]
        assert any("audio tracks in" in call for call in print_calls)
        assert any("Extracting audio track" in call for call in print_calls)