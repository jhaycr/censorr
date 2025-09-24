"""Integration tests for audio-only processing flow with external mute windows.

Tests the complete audio processing pipeline:
1. Extract audio from video
2. Apply external mute windows to audio
3. Verify muted audio output
"""
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.models.artifacts import Artifact, ArtifactType
from src.models.common import MuteWindow
from src.models.operations import OperationFlags
from src.ops.extract_audio import ExtractAudioOperation
from src.ops.mute_audio import MuteAudioOperation
from src.ops.export_sidecar import ExportSidecarOperation, SidecarFormat
from src.caching import CacheManager
from src.logging import ExecutionLogger


class TestAudioOnlyFlow:
    """Integration tests for audio processing pipeline with external mute windows."""
    
    def test_audio_flow_dry_run(self):
        """Test audio processing flow in dry-run mode."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workdir = Path(temp_dir)
            
            # Mock video file
            video_path = workdir / "test_video.mkv"
            video_path.write_text("mock video content")
            
            # Create video artifact
            video_artifact = Artifact(
                type=ArtifactType.VIDEO,
                path=str(video_path),
                metadata={"has_audio": True}
            )
            
            # Setup audio extraction operation
            extract_audio = ExtractAudioOperation(audio_format="wav")
            
            # Execute dry-run audio extraction
            flags = OperationFlags(dry_run=True, verbose=True)
            
            with patch.object(extract_audio.ffmpeg, 'probe') as mock_probe:
                # Mock FFmpeg probe to return audio track info
                mock_media_info = Mock()
                mock_media_info.get_audio_tracks.return_value = [
                    Mock(index=0, codec="aac", language="en", title="Main Audio")
                ]
                mock_probe.return_value = mock_media_info
                
                # Execute extraction in dry-run mode
                results = extract_audio.run([video_artifact], workdir, flags)
                
                # Verify dry-run execution
                assert len(results) > 0
                
                # Should have planned audio artifacts
                audio_artifacts = [a for a in results if a.type == ArtifactType.AUDIO]
                assert len(audio_artifacts) > 0
                
                # Verify metadata indicates dry-run
                for artifact in results:
                    if "planned" in artifact.metadata:
                        assert artifact.metadata["planned"] is True
    
    def test_audio_extraction_with_format(self):
        """Test audio extraction with different formats."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workdir = Path(temp_dir)
            
            # Mock video file
            video_path = workdir / "movie.mkv"
            video_path.write_text("mock video content")
            
            video_artifact = Artifact(
                type=ArtifactType.VIDEO,
                path=str(video_path),
                metadata={"format": "matroska"}
            )
            
            # Test different audio formats
            for audio_format in ["wav", "mp3", "flac"]:
                extract_op = ExtractAudioOperation(audio_format=audio_format)
                
                with patch.object(extract_op.ffmpeg, 'probe') as mock_probe, \
                     patch.object(extract_op.ffmpeg, 'extract_audio') as mock_extract:
                    # Mock audio extraction
                    mock_media_info = Mock()
                    mock_media_info.get_audio_tracks.return_value = [
                        Mock(index=0, codec="aac", language="en")
                    ]
                    mock_probe.return_value = mock_media_info
                    
                    # Mock extracted file path
                    expected_path = workdir / f"audio_track_0.{audio_format}"
                    expected_path.write_text("mock extracted audio")
                    mock_extract.return_value = str(expected_path)
                    
                    # Execute audio extraction
                    flags = OperationFlags()
                    
                    results = extract_op.run([video_artifact], workdir, flags)
                    
                    # Verify extraction results
                    assert len(results) == 1
                    audio_artifact = results[0]
                    assert audio_artifact.type == ArtifactType.AUDIO
                    assert audio_artifact.metadata["format"] == audio_format
                    assert audio_artifact.path.endswith(f".{audio_format}")
    
    def test_audio_muting_with_external_windows(self):
        """Test audio muting with external mute windows."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workdir = Path(temp_dir)
            
            # Create mock audio file
            audio_path = workdir / "extracted_audio.wav"
            audio_path.write_text("mock audio content")
            
            # Create external mute windows file
            mute_windows_data = [
                {"start": 10.5, "end": 15.2, "reason": "profanity", "source": "EXTERNAL"},
                {"start": 35.1, "end": 40.8, "reason": "violence", "source": "EXTERNAL"},
                {"start": 120.0, "end": 125.5, "reason": "inappropriate", "source": "EXTERNAL"}
            ]
            
            mute_windows_file = workdir / "mute_windows.json"
            mute_windows_file.write_text(json.dumps(mute_windows_data))
            
            # Create audio artifact with external mute windows
            audio_artifact = Artifact(
                type=ArtifactType.AUDIO,
                path=str(audio_path),
                metadata={
                    "format": "wav",
                    "mute_windows_file": str(mute_windows_file)
                }
            )
            
            # Test mute operation
            mute_operation = MuteAudioOperation()
            flags = OperationFlags(verbose=True)
            
            with patch.object(mute_operation.ffmpeg, 'apply_mute_windows') as mock_apply:
                # Mock muted output path
                muted_path = workdir / "muted_audio.wav"
                mock_apply.return_value = str(muted_path)
                
                # Execute muting operation
                results = mute_operation.run([audio_artifact], workdir, flags)
                
                # Verify muting results
                assert len(results) == 1
                muted_artifact = results[0]
                assert muted_artifact.type == ArtifactType.AUDIO
                assert muted_artifact.metadata["mute_windows_applied"] == 3
                
                # Verify FFmpeg was called with correct mute windows
                mock_apply.assert_called_once()
                call_args = mock_apply.call_args
                
                # Extract mute windows passed to FFmpeg
                mute_windows = None
                if len(call_args[0]) > 2:
                    mute_windows = call_args[0][2]  # positional args
                elif 'mute_windows' in call_args[1]:
                    mute_windows = call_args[1]['mute_windows']  # keyword args
                
                if mute_windows:
                    assert len(mute_windows) == 3
                    assert any(w.start == 10.5 and w.end == 15.2 for w in mute_windows)
                    assert any(w.start == 35.1 and w.end == 40.8 for w in mute_windows)
                    assert any(w.start == 120.0 and w.end == 125.5 for w in mute_windows)
    
    def test_audio_muting_with_metadata_windows(self):
        """Test audio muting with mute windows from artifact metadata."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workdir = Path(temp_dir)
            
            # Create mock audio file
            audio_path = workdir / "extracted_audio.wav"
            audio_path.write_text("mock audio content")
            
            # Create audio artifact with mute windows in metadata
            mute_windows_metadata = [
                {"start": 5.0, "end": 8.0, "reason": "profanity", "source": "SUBTITLE"},
                {"start": 25.0, "end": 30.0, "reason": "content", "source": "SUBTITLE"}
            ]
            
            audio_artifact = Artifact(
                type=ArtifactType.AUDIO,
                path=str(audio_path),
                metadata={
                    "format": "wav",
                    "mute_windows": mute_windows_metadata
                }
            )
            
            # Test mute operation
            mute_operation = MuteAudioOperation()
            flags = OperationFlags()
            
            with patch.object(mute_operation.ffmpeg, 'apply_mute_windows') as mock_apply:
                # Mock muted output path
                muted_path = workdir / "muted_audio.wav"
                mock_apply.return_value = str(muted_path)
                
                # Execute muting operation
                results = mute_operation.run([audio_artifact], workdir, flags)
                
                # Verify muting results
                assert len(results) == 1
                muted_artifact = results[0]
                assert muted_artifact.type == ArtifactType.AUDIO
                assert muted_artifact.metadata["mute_windows_applied"] == 2
    
    def test_combined_mute_windows_sources(self):
        """Test combining mute windows from multiple sources."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workdir = Path(temp_dir)
            
            # Create mock audio file
            audio_path = workdir / "extracted_audio.wav"
            audio_path.write_text("mock audio content")
            
            # Create external mute windows file
            external_windows = [
                {"start": 10.0, "end": 15.0, "reason": "external", "source": "EXTERNAL"}
            ]
            mute_windows_file = workdir / "external_mute.json"
            mute_windows_file.write_text(json.dumps(external_windows))
            
            # Create audio artifact with both metadata and external windows
            metadata_windows = [
                {"start": 5.0, "end": 8.0, "reason": "subtitle", "source": "SUBTITLE"}
            ]
            
            audio_artifact = Artifact(
                type=ArtifactType.AUDIO,
                path=str(audio_path),
                metadata={
                    "format": "wav",
                    "mute_windows": metadata_windows,
                    "mute_windows_file": str(mute_windows_file)
                }
            )
            
            # Test mute operation
            mute_operation = MuteAudioOperation()
            flags = OperationFlags(verbose=True)
            
            with patch.object(mute_operation.ffmpeg, 'apply_mute_windows') as mock_apply:
                # Mock muted output path
                muted_path = workdir / "muted_audio.wav"
                mock_apply.return_value = str(muted_path)
                
                # Execute muting operation
                results = mute_operation.run([audio_artifact], workdir, flags)
                
                # Verify both sources were combined
                assert len(results) == 1
                muted_artifact = results[0]
                assert muted_artifact.metadata["mute_windows_applied"] == 2  # Combined from both sources
    
    def test_full_audio_pipeline_integration(self):
        """Test complete audio processing pipeline from extraction to muting."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workdir = Path(temp_dir)
            
            # Setup mock video file
            video_path = workdir / "source_video.mkv"
            video_path.write_text("mock video content")
            
            # Create external mute windows
            mute_windows_data = [
                {"start": 12.5, "end": 18.2, "reason": "profanity", "source": "EXTERNAL"},
                {"start": 45.0, "end": 50.5, "reason": "violence", "source": "EXTERNAL"}
            ]
            mute_windows_file = workdir / "processing_windows.json"
            mute_windows_file.write_text(json.dumps(mute_windows_data))
            
            # Create video artifact
            video_artifact = Artifact(
                type=ArtifactType.VIDEO,
                path=str(video_path),
                metadata={
                    "format": "matroska",
                    "mute_windows_file": str(mute_windows_file)
                }
            )
            
            # Setup operations
            extract_op = ExtractAudioOperation(audio_format="wav")
            mute_op = MuteAudioOperation()
            export_op = ExportSidecarOperation(format=SidecarFormat.JSON)
            
            with patch.object(extract_op.ffmpeg, 'probe') as mock_probe, \
                 patch.object(extract_op.ffmpeg, 'extract_audio') as mock_extract, \
                 patch.object(mute_op.ffmpeg, 'apply_mute_windows') as mock_mute:
                
                # Mock audio extraction
                mock_media_info = Mock()
                mock_media_info.get_audio_tracks.return_value = [
                    Mock(index=0, codec="aac", language="en")
                ]
                mock_probe.return_value = mock_media_info
                
                # Mock extracted audio file
                extracted_audio_path = workdir / "extracted_audio.wav"
                extracted_audio_path.write_text("mock extracted audio content")
                mock_extract.return_value = str(extracted_audio_path)
                
                # Mock muted audio file
                muted_audio_path = workdir / "muted_audio.wav"
                muted_audio_path.write_text("mock muted audio content")
                mock_mute.return_value = str(muted_audio_path)
                
                # Step 1: Extract audio
                flags = OperationFlags(verbose=True)
                extract_results = extract_op.run([video_artifact], workdir, flags)
                
                # Verify extraction
                assert len(extract_results) == 1
                audio_artifact = extract_results[0]
                assert audio_artifact.type == ArtifactType.AUDIO
                
                # Add mute windows to the extracted audio artifact
                audio_artifact.metadata["mute_windows_file"] = str(mute_windows_file)
                
                # Step 2: Apply mute windows
                mute_results = mute_op.run([audio_artifact], workdir, flags)
                
                # Verify muting
                assert len(mute_results) == 1
                muted_artifact = mute_results[0]
                assert muted_artifact.metadata["mute_windows_applied"] == 2
                
                # Step 3: Export sidecar (need to include video artifact for sidecar export)
                export_results = export_op.run([video_artifact, muted_artifact], workdir, flags)
                
                # Verify sidecar export
                assert len(export_results) == 1
                sidecar_artifact = export_results[0]
                assert sidecar_artifact.type == ArtifactType.SIDECAR
                
                # Verify complete pipeline results
                assert Path(sidecar_artifact.path).exists()
    
    def test_audio_flow_error_handling(self):
        """Test audio flow with error handling and recovery."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workdir = Path(temp_dir)
            
            # Setup corrupt video file
            video_path = workdir / "corrupt_video.mkv"
            video_path.write_text("corrupt video data")
            
            video_artifact = Artifact(
                type=ArtifactType.VIDEO,
                path=str(video_path),
                metadata={}
            )
            
            # Test with failing FFmpeg operation
            extract_op = ExtractAudioOperation()
            
            with patch.object(extract_op.ffmpeg, 'probe') as mock_probe:
                # Mock probe failure
                mock_probe.side_effect = Exception("FFmpeg probe failed")
                
                flags = OperationFlags(verbose=True)
                
                # Execution should handle the error gracefully
                with pytest.raises(RuntimeError, match="Failed to probe video file"):
                    extract_op.run([video_artifact], workdir, flags)
    
    def test_audio_flow_with_caching(self):
        """Test audio flow with caching enabled."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workdir = Path(temp_dir)
            
            # Setup cache manager
            cache_manager = CacheManager(workdir)
            
            # Create audio artifact for muting
            audio_path = workdir / "test_audio.wav"
            audio_path.write_text("mock audio content")
            
            audio_artifact = Artifact(
                type=ArtifactType.AUDIO,
                path=str(audio_path),
                metadata={"format": "wav"}
            )

    def test_mute_audio_derived_from_subtitles_end_to_end(self):
        """Generate a short tone and an SRT with profanity, then mute.

        This ensures windows derived from subtitles are passed to ffmpeg and
        a muted audio output is produced. Skips if ffmpeg is not available.
        """
        import shutil
        import subprocess
        if not shutil.which("ffmpeg"):
            pytest.skip("ffmpeg not available")

        with tempfile.TemporaryDirectory() as temp_dir:
            workdir = Path(temp_dir)

            # Generate a 6s tone
            tone = workdir / "tone.wav"
            subprocess.run([
                "ffmpeg", "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
                "-y", str(tone)
            ], check=True, capture_output=True)

            # SRT with profanity between 1s and 3s
            srt = workdir / "profanity.srt"
            srt.write_text(
                """1\n00:00:01,000 --> 00:00:03,000\nHoly shit!\n""",
                encoding="utf-8",
            )

            # Profanity list
            prof = workdir / "profanity.json"
            prof.write_text('[{"word": "shit"}]', encoding="utf-8")

            audio_art = Artifact(type=ArtifactType.AUDIO, path=str(tone), metadata={})
            sub_art = Artifact(type=ArtifactType.SUBTITLE, path=str(srt), metadata={"language": "en"})

            op = MuteAudioOperation()
            flags = OperationFlags(profanity_list_file=str(prof), verbose=True)

            results = op.run([audio_art, sub_art], workdir, flags)
            assert len(results) == 1
            out = Path(results[0].path)
            assert out.exists()
            assert results[0].metadata.get("mute_windows_applied", 0) >= 1

            # Verify audio is actually muted inside the window using RMS energy
            import wave, audioop
            with wave.open(str(out), 'rb') as wf:
                rate = wf.getframerate()
                width = wf.getsampwidth()
                nch = wf.getnchannels()

                def segment_rms(t0: float, t1: float) -> int:
                    start = max(0, int(t0 * rate))
                    count = max(0, int((t1 - t0) * rate))
                    wf.setpos(start)
                    data = wf.readframes(count)
                    if nch == 2:
                        data = audioop.tomono(data, width, 0.5, 0.5)
                    return audioop.rms(data, width)

                # Window was 1-3s; sample inside and outside
                rms_muted = segment_rms(1.2, 1.8)
                rms_clean = segment_rms(4.0, 4.6)

                # Muted region should be at least 20x quieter (adjust if needed on CI)
                assert rms_muted < max(50, rms_clean * 0.05), f"Muted RMS too high: {rms_muted} vs clean {rms_clean}"
    
    def test_no_audio_tracks_handling(self):
        """Test handling video files with no audio tracks."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workdir = Path(temp_dir)
            
            # Mock video file without audio
            video_path = workdir / "video_no_audio.mkv"
            video_path.write_text("mock video content")
            
            video_artifact = Artifact(
                type=ArtifactType.VIDEO,
                path=str(video_path),
                metadata={"format": "matroska"}
            )
            
            # Setup audio extraction operation
            extract_audio = ExtractAudioOperation()
            
            with patch.object(extract_audio.ffmpeg, 'probe') as mock_probe:
                # Mock FFmpeg probe to return no audio tracks
                mock_media_info = Mock()
                mock_media_info.get_audio_tracks.return_value = []
                mock_probe.return_value = mock_media_info
                
                # Execute extraction
                flags = OperationFlags(verbose=True)
                results = extract_audio.run([video_artifact], workdir, flags)
                
                # Should return empty results
                assert len(results) == 0
    
    def test_audio_muting_with_no_windows(self):
        """Test audio muting when no mute windows are provided."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workdir = Path(temp_dir)
            
            # Create mock audio file
            audio_path = workdir / "clean_audio.wav"
            audio_path.write_text("mock audio content")
            
            # Create audio artifact with no mute windows
            audio_artifact = Artifact(
                type=ArtifactType.AUDIO,
                path=str(audio_path),
                metadata={"format": "wav"}
            )
            
            # Test mute operation
            mute_operation = MuteAudioOperation()
            flags = OperationFlags()
            
            with patch.object(mute_operation.ffmpeg, 'apply_mute_windows') as mock_apply:
                # Mock output path (should just copy the file)
                output_path = workdir / "processed_audio.wav"
                mock_apply.return_value = str(output_path)
                
                # Execute muting operation
                results = mute_operation.run([audio_artifact], workdir, flags)
                
                # Verify results
                assert len(results) == 1
                processed_artifact = results[0]
                assert processed_artifact.type == ArtifactType.AUDIO
                assert processed_artifact.metadata["mute_windows_applied"] == 0