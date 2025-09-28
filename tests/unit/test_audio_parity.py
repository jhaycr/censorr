"""
Unit tests for audio parity enforcement in remux operations.
"""
import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from src.ops.remux import RemuxOperation
from src.adapters.ffmpeg import FFmpegAdapter, TrackInfo, MediaInfo
from src.models.artifacts import Artifact, ArtifactType
from src.models.operations import OperationFlags


class TestAudioParityEnforcement:
    """Test cases for audio parity verification (Task 59)."""
    
    def test_verify_audio_parity_match(self):
        """Test successful audio parity verification."""
        adapter = FFmpegAdapter()
        
        # Mock probe results
        original_track = TrackInfo(
            index=0, type="audio", codec="aac", 
            channels=2, sample_rate="48000"
        )
        remuxed_track = TrackInfo(
            index=0, type="audio", codec="aac",
            channels=2, sample_rate="48000"
        )
        
        with patch.object(adapter, 'probe') as mock_probe:
            mock_probe.side_effect = [
                MediaInfo(format="wav", tracks=[original_track]),
                MediaInfo(format="mkv", tracks=[remuxed_track])
            ]
            
            result = adapter.verify_audio_parity("original.wav", "remuxed.mkv", 0)
            
            assert result["status"] == "match"
            assert result["message"] == "Audio parity verified"
    
    def test_verify_audio_parity_mismatch(self):
        """Test audio parity verification with mismatches."""
        adapter = FFmpegAdapter()
        
        # Mock probe results with mismatches
        original_track = TrackInfo(
            index=0, type="audio", codec="aac",
            channels=2, sample_rate="48000"
        )
        remuxed_track = TrackInfo(
            index=0, type="audio", codec="mp3",  # Different codec
            channels=1, sample_rate="44100"     # Different channels/sample rate
        )
        
        with patch.object(adapter, 'probe') as mock_probe:
            mock_probe.side_effect = [
                MediaInfo(format="wav", tracks=[original_track]),
                MediaInfo(format="mkv", tracks=[remuxed_track])
            ]
            
            result = adapter.verify_audio_parity("original.wav", "remuxed.mkv", 0)
            
            assert result["status"] == "mismatch"
            assert len(result["mismatches"]) == 3  # codec, channels, sample_rate
            assert "codec: aac != mp3" in result["mismatches"]
            assert "channels: 2 != 1" in result["mismatches"]
            assert "sample_rate: 48000 != 44100" in result["mismatches"]
    
    def test_remux_audio_parity_strict_mode_failure(self):
        """Test remux fails in strict mode when audio parity check fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workdir = Path(tmpdir)
            
            # Create test artifacts
            video_artifact = Artifact(
                type=ArtifactType.VIDEO,
                path=str(workdir / "test.mkv"),
                metadata={"format": "mkv"}
            )
            audio_artifact = Artifact(
                type=ArtifactType.AUDIO,
                path=str(workdir / "muted_audio_track_0.wav"),
                metadata={"track_index": 0}
            )
            
            # Create fake input files
            (workdir / "test.mkv").touch()
            (workdir / "muted_audio_track_0.wav").touch()
            
            remux_op = RemuxOperation()
            flags = OperationFlags(strict_audio_parity=True, dry_run=False)
            
            # Mock FFmpeg methods
            with patch.object(remux_op.ffmpeg, 'remux') as mock_remux, \
                 patch.object(remux_op.ffmpeg, 'verify_audio_parity') as mock_verify:
                
                mock_remux.return_value = str(workdir / "remuxed_test.mkv")
                mock_verify.return_value = {
                    "status": "mismatch",
                    "mismatches": ["codec: aac != mp3"],
                    "original": {"codec": "aac", "channels": 2, "sample_rate": "48000"},
                    "remuxed": {"codec": "mp3", "channels": 2, "sample_rate": "48000"}
                }
                
                # Should raise RuntimeError in strict mode
                with pytest.raises(RuntimeError, match="Audio parity check failed in strict mode"):
                    remux_op.run([video_artifact, audio_artifact], workdir, flags)
    
    def test_remux_audio_parity_warn_mode_continues(self):
        """Test remux continues with warning when audio parity check fails in non-strict mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workdir = Path(tmpdir)
            
            # Create test artifacts
            video_artifact = Artifact(
                type=ArtifactType.VIDEO,
                path=str(workdir / "test.mkv"),
                metadata={"format": "mkv"}
            )
            audio_artifact = Artifact(
                type=ArtifactType.AUDIO,
                path=str(workdir / "muted_audio_track_0.wav"),
                metadata={"track_index": 0}
            )
            
            # Create fake input files
            (workdir / "test.mkv").touch()
            (workdir / "muted_audio_track_0.wav").touch()
            
            remux_op = RemuxOperation() 
            flags = OperationFlags(strict_audio_parity=False, dry_run=False)  # Non-strict mode
            
            # Mock FFmpeg methods
            with patch.object(remux_op.ffmpeg, 'remux') as mock_remux, \
                 patch.object(remux_op.ffmpeg, 'verify_audio_parity') as mock_verify:
                
                mock_remux.return_value = str(workdir / "remuxed_test.mkv")
                mock_verify.return_value = {
                    "status": "mismatch",
                    "mismatches": ["codec: aac != mp3"],
                    "original": {"codec": "aac", "channels": 2, "sample_rate": "48000"},
                    "remuxed": {"codec": "mp3", "channels": 2, "sample_rate": "48000"}
                }
                
                # Should NOT raise an exception - should complete with warning
                results = remux_op.run([video_artifact, audio_artifact], workdir, flags)
                
                assert len(results) == 1
                assert results[0].type == ArtifactType.VIDEO