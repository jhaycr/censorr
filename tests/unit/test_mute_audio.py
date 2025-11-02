"""Unit tests for mute_audio operation."""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, call

from src.models.artifacts import Artifact, ArtifactType
from src.models.common import MuteWindow
from src.models.operations import OperationFlags
from src.ops.audio_mute import MuteAudioOperation


class TestMuteAudioOperation:
    """Test cases for MuteAudioOperation."""

    def test_operation_creation(self):
        """Test operation can be created."""
        op = MuteAudioOperation()
        # Now consumes AUDIO, SUBTITLE, and VIDEO for deriving windows and external files
        assert op.consumes == {ArtifactType.AUDIO, ArtifactType.SUBTITLE, ArtifactType.VIDEO}
        assert op.produces == {ArtifactType.AUDIO}

    @patch('src.ops.audio_mute.FFmpegAdapter')
    def test_run_with_mute_windows(self, mock_ffmpeg_class):
        """Test running operation with mute windows."""
        # Setup mocks
        mock_ffmpeg = mock_ffmpeg_class.return_value
        mock_ffmpeg.apply_mute_windows.return_value = "/tmp/test/muted_audio.wav"
        
        # Test data
        workdir = Path("/tmp/test")
        audio_artifact = Artifact(
            type=ArtifactType.AUDIO,
            path="/path/to/audio.wav",
            metadata={"mute_windows": [
                {"start": 10.0, "end": 15.0, "reason": "profanity", "source": "SUBTITLE"},
                {"start": 30.0, "end": 35.0, "reason": "content", "source": "EXTERNAL"}
            ]}
        )
        flags = OperationFlags()
        
        # Execute operation
        op = MuteAudioOperation()
        results = op.run([audio_artifact], workdir, flags)
        
        # Verify results
        assert len(results) == 1
        assert results[0].type == ArtifactType.AUDIO
        assert results[0].path == "/tmp/test/muted_audio.wav"
        assert "mute_windows_applied" in results[0].metadata
        assert results[0].metadata["mute_windows_applied"] == 2
        
        # Verify FFmpeg call
        mock_ffmpeg.apply_mute_windows.assert_called_once()
        call_args = mock_ffmpeg.apply_mute_windows.call_args
        assert call_args.kwargs['input_path'] == "/path/to/audio.wav"
        assert call_args.kwargs['output_path'] == "/tmp/test/muted_audio.wav"
        mute_windows = call_args.kwargs['mute_windows']
        assert len(mute_windows) == 2
        assert mute_windows[0].start == 10.0
        assert mute_windows[0].end == 15.0

    @patch('src.ops.audio_mute.FFmpegAdapter')
    def test_run_no_mute_windows(self, mock_ffmpeg_class):
        """Test running operation with no mute windows."""
        # Setup mocks
        mock_ffmpeg = mock_ffmpeg_class.return_value
        mock_ffmpeg.apply_mute_windows.return_value = "/tmp/test/muted_audio.wav"
        
        # Test data - no mute_windows in metadata
        workdir = Path("/tmp/test")
        audio_artifact = Artifact(
            type=ArtifactType.AUDIO,
            path="/path/to/audio.wav",
            metadata={}
        )
        flags = OperationFlags()
        
        # Execute operation
        op = MuteAudioOperation()
        results = op.run([audio_artifact], workdir, flags)
        
        # Verify results
        assert len(results) == 1
        assert results[0].type == ArtifactType.AUDIO
        assert results[0].path == "/tmp/test/muted_audio.wav"
        assert results[0].metadata["mute_windows_applied"] == 0
        
        # Verify FFmpeg call with empty mute windows
        mock_ffmpeg.apply_mute_windows.assert_called_once()
        call_args = mock_ffmpeg.apply_mute_windows.call_args
        mute_windows = call_args.kwargs['mute_windows']
        assert len(mute_windows) == 0

    @patch('src.ops.audio_mute.FFmpegAdapter')
    def test_run_dry_run(self, mock_ffmpeg_class):
        """Test operation in dry-run mode."""
        # Setup mocks
        mock_ffmpeg = mock_ffmpeg_class.return_value
        
        # Test data
        workdir = Path("/tmp/test")
        audio_artifact = Artifact(
            type=ArtifactType.AUDIO,
            path="/path/to/audio.wav",
            metadata={"mute_windows": [
                {"start": 10.0, "end": 15.0, "reason": "profanity", "source": "SUBTITLE"}
            ]}
        )
        flags = OperationFlags(dry_run=True)
        
        # Execute operation
        op = MuteAudioOperation()
        results = op.run([audio_artifact], workdir, flags)
        
        # Verify results
        assert len(results) == 1
        assert results[0].type == ArtifactType.AUDIO
        assert "muted_" in results[0].path
        assert results[0].metadata["mute_windows_applied"] == 1
        
        # Verify FFmpeg was not called
        mock_ffmpeg.apply_mute_windows.assert_not_called()

    @patch('src.ops.audio_mute.FFmpegAdapter')
    def test_run_ffmpeg_error(self, mock_ffmpeg_class):
        """Test handling FFmpeg errors."""
        # Setup mocks
        mock_ffmpeg = mock_ffmpeg_class.return_value
        mock_ffmpeg.apply_mute_windows.side_effect = Exception("FFmpeg failed")
        
        # Test data
        workdir = Path("/tmp/test")
        audio_artifact = Artifact(
            type=ArtifactType.AUDIO,
            path="/path/to/audio.wav",
            metadata={"mute_windows": [
                {"start": 10.0, "end": 15.0, "reason": "profanity", "source": "SUBTITLE"}
            ]}
        )
        flags = OperationFlags()
        
        # Execute operation and expect error
        op = MuteAudioOperation()
        with pytest.raises(RuntimeError, match="Failed to apply mute windows"):
            op.run([audio_artifact], workdir, flags)

    def test_run_no_audio_artifact(self):
        """Test operation fails with no audio artifacts."""
        op = MuteAudioOperation()
        
        video_artifact = Artifact(
            type=ArtifactType.VIDEO,
            path="/path/to/video.mp4",
            metadata={}
        )
        
        workdir = Path("/tmp/test")
        flags = OperationFlags()
        
        with pytest.raises(ValueError, match="No audio artifacts found"):
            op.run([video_artifact], workdir, flags)

    @patch('src.ops.audio_mute.FFmpegAdapter')
    def test_run_with_external_mute_windows_file(self, mock_ffmpeg_class):
        """Test operation with external mute windows file."""
        # Setup mocks
        mock_ffmpeg = mock_ffmpeg_class.return_value
        mock_ffmpeg.apply_mute_windows.return_value = "/tmp/test/muted_audio.wav"
        
        # Create temporary mute windows file
        mute_windows_content = '''[
    {"start": 5.0, "end": 8.0, "reason": "explicit", "source": "EXTERNAL"},
    {"start": 20.0, "end": 25.0, "reason": "violence", "source": "EXTERNAL"}
]'''
        
        with patch('builtins.open', create=True) as mock_open:
            with patch('json.load') as mock_json_load:
                mock_json_load.return_value = [
                    {"start": 5.0, "end": 8.0, "reason": "explicit", "source": "EXTERNAL"},
                    {"start": 20.0, "end": 25.0, "reason": "violence", "source": "EXTERNAL"}
                ]
                
                # Test data
                workdir = Path("/tmp/test")
                audio_artifact = Artifact(
                    type=ArtifactType.AUDIO,
                    path="/path/to/audio.wav",
                    metadata={"mute_windows_file": "/path/to/mute_windows.json"}
                )
                flags = OperationFlags()
                
                # Execute operation
                op = MuteAudioOperation()
                results = op.run([audio_artifact], workdir, flags)
                
                # Verify results
                assert len(results) == 1
                assert results[0].metadata["mute_windows_applied"] == 2
                
                # Verify file was read
                mock_open.assert_called_with("/path/to/mute_windows.json", 'r')

    @patch('src.ops.audio_mute.FFmpegAdapter')
    def test_run_with_both_metadata_and_file(self, mock_ffmpeg_class):
        """Test operation with both metadata mute windows and external file."""
        # Setup mocks
        mock_ffmpeg = mock_ffmpeg_class.return_value
        mock_ffmpeg.apply_mute_windows.return_value = "/tmp/test/muted_audio.wav"
        
        with patch('builtins.open', create=True) as mock_open:
            with patch('json.load') as mock_json_load:
                mock_json_load.return_value = [
                    {"start": 5.0, "end": 8.0, "reason": "external", "source": "EXTERNAL"}
                ]
                
                # Test data
                workdir = Path("/tmp/test")
                audio_artifact = Artifact(
                    type=ArtifactType.AUDIO,
                    path="/path/to/audio.wav",
                    metadata={
                        "mute_windows": [
                            {"start": 10.0, "end": 15.0, "reason": "subtitle", "source": "SUBTITLE"}
                        ],
                        "mute_windows_file": "/path/to/mute_windows.json"
                    }
                )
                flags = OperationFlags()
                
                # Execute operation
                op = MuteAudioOperation()
                results = op.run([audio_artifact], workdir, flags)
                
                # Verify results - should combine both sources
                assert len(results) == 1
                assert results[0].metadata["mute_windows_applied"] == 2
                
                # Verify FFmpeg call contains both windows
                call_args = mock_ffmpeg.apply_mute_windows.call_args
                mute_windows = call_args.kwargs['mute_windows']
                assert len(mute_windows) == 2

    @patch('src.ops.audio_mute.FFmpegAdapter')
    def test_generate_output_path(self, mock_ffmpeg_class):
        """Test output path generation."""
        op = MuteAudioOperation()
        
        # Test basic path generation
        workdir = Path("/tmp/test")
        input_path = "/path/to/audio.wav"
        output_path = op._generate_output_path(input_path, workdir)
        
        assert output_path.startswith("/tmp/test/muted_")
        assert output_path.endswith(".wav")
        
        # Test different extension
        input_path = "/path/to/audio.mp3"
        output_path = op._generate_output_path(input_path, workdir)
        assert output_path.endswith(".mp3")

    def test_parse_mute_windows_from_metadata(self):
        """Test parsing mute windows from metadata."""
        op = MuteAudioOperation()
        
        # Test valid metadata
        metadata = [
            {"start": 10.0, "end": 15.0, "reason": "profanity", "source": "SUBTITLE"},
            {"start": 30.0, "end": 35.0, "reason": "content", "source": "EXTERNAL"}
        ]
        
        windows = op._parse_mute_windows_from_metadata(metadata)
        assert len(windows) == 2
        assert isinstance(windows[0], MuteWindow)
        assert windows[0].start == 10.0
        assert windows[0].reason == "profanity"

    def test_parse_mute_windows_invalid_data(self):
        """Test parsing invalid mute window data."""
        op = MuteAudioOperation()
        
        # Test invalid data
        metadata = [
            {"start": "invalid", "end": 15.0, "reason": "profanity", "source": "SUBTITLE"}
        ]
        
        with pytest.raises(ValueError, match="Invalid mute window data"):
            op._parse_mute_windows_from_metadata(metadata)

    @patch('src.ops.audio_mute.FFmpegAdapter')
    def test_verbose_mode(self, mock_ffmpeg_class):
        """Test operation in verbose mode."""
        # Setup mocks
        mock_ffmpeg = mock_ffmpeg_class.return_value
        mock_ffmpeg.apply_mute_windows.return_value = "/tmp/test/muted_audio.wav"
        
        # Test data
        workdir = Path("/tmp/test")
        audio_artifact = Artifact(
            type=ArtifactType.AUDIO,
            path="/path/to/audio.wav",
            metadata={"mute_windows": [
                {"start": 10.0, "end": 15.0, "reason": "profanity", "source": "SUBTITLE"}
            ]}
        )
        flags = OperationFlags(verbose=True)
        
        # Execute operation
        op = MuteAudioOperation()
        with patch('builtins.print') as mock_print:
            results = op.run([audio_artifact], workdir, flags)
        
        # Verify verbose output was printed
        assert mock_print.called
        print_calls = [call[0][0] for call in mock_print.call_args_list]
        assert any("mute windows for" in call for call in print_calls)
        assert any("Applying mute windows" in call for call in print_calls)