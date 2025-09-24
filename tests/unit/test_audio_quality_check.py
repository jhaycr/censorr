"""Unit tests for audio quality check operation."""

import json
import tempfile
import wave
import audioop
from pathlib import Path
from unittest.mock import Mock

import pytest

from src.ops.audio_quality_check import AudioQualityCheckOperation
from src.models.artifacts import Artifact, ArtifactType
from src.models.operations import OperationFlags


class TestAudioQualityCheckOperation:
    """Test suite for AudioQualityCheckOperation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.operation = AudioQualityCheckOperation()

    def test_operation_metadata(self):
        """Test operation metadata."""
        assert self.operation.name == "audio_quality_check"
        assert self.operation.consumes == {ArtifactType.AUDIO}
        assert self.operation.produces == {ArtifactType.AUDIO}

    def test_creates_generated_tone_and_analysis(self):
        """Test energy analysis with a generated tone."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workdir = Path(temp_dir)
            
            # Create a test WAV file with tone and silence
            audio_path = workdir / "test_audio.wav"
            sample_rate = 44100
            duration = 2  # 2 seconds
            
            # Generate frames: tone for first second, silence for second second
            frames = []
            for i in range(sample_rate * duration):
                if i < sample_rate:  # First second: tone
                    value = int(32767 * 0.5)  # Half volume
                else:  # Second second: silence
                    value = 0
                frames.append(value)
            
            # Write WAV file
            with wave.open(str(audio_path), 'w') as wav_file:
                wav_file.setnchannels(1)  # Mono
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(audioop.lin2lin(bytes(
                    sum(([b & 0xff, (b >> 8) & 0xff] for b in frames), [])
                ), 1, 2))
            
            # Create mute windows covering the tone part (should detect as failure)
            mute_windows = [{"start": 0.0, "end": 1.0, "reason": "test", "source": "TEST"}]
            mute_windows_file = workdir / "mute_windows.json"
            mute_windows_file.write_text(json.dumps(mute_windows))
            
            # Create audio artifact
            audio_artifact = Artifact(
                type=ArtifactType.AUDIO,
                path=str(audio_path),
                metadata={"mute_windows_file": str(mute_windows_file)}
            )
            
            # Test with continue_on_audio_qc_fail flag to get results despite failure
            flags = OperationFlags(continue_on_audio_qc_fail=True)
            results = self.operation.run([audio_artifact], workdir, flags)
            
            # Verify results
            assert len(results) == 1
            result = results[0]
            assert result.type == ArtifactType.AUDIO
            assert result.path == str(audio_path)  # Pass-through
            
            # Check QC metadata
            qc_data = result.metadata.get("quality_check", {})
            assert qc_data["operation"] == "audio_quality_check"
            assert qc_data["status"] == "FAIL"
            assert "energy_analysis" in qc_data
            
            energy_analysis = qc_data["energy_analysis"]
            assert "muted_segments_analyzed" in energy_analysis
            assert "control_segments_analyzed" in energy_analysis
            assert "average_db_reduction" in energy_analysis
            assert qc_data["failed_windows"] > 0  # Should detect insufficient muting

    def test_no_mute_windows_file(self):
        """Test behavior when no mute windows file is provided."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workdir = Path(temp_dir)
            
            # Create minimal audio file
            audio_path = workdir / "test_audio.wav"
            with wave.open(str(audio_path), 'w') as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(44100)
                wav_file.writeframes(b'\x00\x00' * 1000)  # 1000 silent samples
            
            # Create audio artifact without mute windows
            audio_artifact = Artifact(
                type=ArtifactType.AUDIO,
                path=str(audio_path),
                metadata={}
            )
            
            # Run operation
            flags = OperationFlags()
            results = self.operation.run([audio_artifact], workdir, flags)
            
            # Should skip analysis but still return artifact
            assert len(results) == 1
            result = results[0]
            assert result.type == ArtifactType.AUDIO
            qc_data = result.metadata.get("quality_check", {})
            assert qc_data["status"] == "SKIPPED"
            assert qc_data["reason"] == "No mute windows file found"

    def test_dry_run(self):
        """Test dry run mode."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workdir = Path(temp_dir)
            
            audio_artifact = Artifact(
                type=ArtifactType.AUDIO,
                path="/fake/path.wav",
                metadata={"mute_windows_file": "/fake/mute.json"}
            )
            
            flags = OperationFlags(dry_run=True)
            results = self.operation.run([audio_artifact], workdir, flags)
            
            assert len(results) == 1
            result = results[0]
            assert result.path == "/fake/path.wav"  # Pass-through
            qc_data = result.metadata.get("quality_check", {})
            assert qc_data["status"] == "SKIPPED"
            assert qc_data["reason"] == "Dry run mode"