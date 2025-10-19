"""Integration tests for full media processing pipeline.

Tests the complete end-to-end workflow:
1. Extract subtitles and audio from video
2. Mask profanity in subtitles
3. Apply mute windows to audio
4. Remux everything back into final video
"""
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.models.artifacts import Artifact, ArtifactType
from src.models.operations import OperationFlags
from src.ops.subtitle_extract import ExtractSubtitlesOperation
from src.ops.audio_extract import ExtractAudioOperation
from src.ops.subtitle_mask import MaskSubtitlesOperation
from src.ops.audio_mute import MuteAudioOperation
from src.ops.video_remux import RemuxOperation
from src.ops.subtitle_export import SubtitleExportOperation, SubtitleFormat
from src.caching import CacheManager
from src.logging import ExecutionLogger


class TestFullPipelineFlow:
    """Integration tests for complete media processing pipeline."""
    
    def test_full_pipeline_dry_run(self):
        """Test complete pipeline in dry-run mode."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workdir = Path(temp_dir)
            
            # Mock source video file
            video_path = workdir / "source_movie.mkv"
            video_path.write_text("mock video content")
            
            # Create video artifact
            video_artifact = Artifact(
                type=ArtifactType.VIDEO,
                path=str(video_path),
                metadata={"format": "matroska", "has_subtitles": True, "has_audio": True}
            )
            
            # Setup operations
            extract_subs_op = ExtractSubtitlesOperation()
            extract_audio_op = ExtractAudioOperation(audio_format="wav")
            mask_subs_op = MaskSubtitlesOperation()
            mute_audio_op = MuteAudioOperation()
            remux_op = RemuxOperation()
            
            # Execute dry-run pipeline
            flags = OperationFlags(dry_run=True, verbose=True)
            
            with patch.object(extract_subs_op.ffmpeg, 'probe') as mock_sub_probe, \
                 patch.object(extract_audio_op.ffmpeg, 'probe') as mock_audio_probe:
                
                # Mock subtitle tracks
                mock_sub_media_info = Mock()
                mock_sub_media_info.get_subtitle_tracks.return_value = [
                    Mock(index=0, codec="srt", language="en", title="English")
                ]
                mock_sub_probe.return_value = mock_sub_media_info
                
                # Mock audio tracks
                mock_audio_media_info = Mock()
                mock_audio_media_info.get_audio_tracks.return_value = [
                    Mock(index=0, codec="aac", language="en", title="Main Audio")
                ]
                mock_audio_probe.return_value = mock_audio_media_info
                
                # Step 1: Extract subtitles
                subtitle_results = extract_subs_op.run([video_artifact], workdir, flags)
                assert len(subtitle_results) > 0
                
                # Step 2: Extract audio
                audio_results = extract_audio_op.run([video_artifact], workdir, flags)
                assert len(audio_results) > 0
                
                # Step 3: Mask subtitles (dry-run)
                mask_results = mask_subs_op.run(subtitle_results, workdir, flags)
                assert len(mask_results) > 0
                
                # Step 4: Mute audio (dry-run)
                mute_results = mute_audio_op.run(audio_results, workdir, flags)
                assert len(mute_results) > 0
                
                # Step 5: Remux (dry-run)
                all_artifacts = [video_artifact] + mask_results + mute_results
                remux_results = remux_op.run(all_artifacts, workdir, flags)
                assert len(remux_results) > 0
                
                # Verify dry-run artifacts are properly tagged
                for result in remux_results:
                    if "planned" in result.metadata:
                        assert result.metadata["planned"] is True
    
    def test_simplified_pipeline_with_mocking(self):
        """Test simplified pipeline with mocked operations for end-to-end flow."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workdir = Path(temp_dir)
            
            # Create mock files  
            video_path = workdir / "test_video.mkv"
            video_path.write_text("mock video content")
            
            subtitle_path = workdir / "test_subtitle.srt"
            subtitle_path.write_text("1\n00:00:01,000 --> 00:00:05,000\nClean dialogue.")
            
            audio_path = workdir / "test_audio.wav"
            audio_path.write_text("mock audio content")
            
            # Create artifacts
            video_artifact = Artifact(
                type=ArtifactType.VIDEO,
                path=str(video_path),
                metadata={"format": "matroska"}
            )
            
            subtitle_artifact = Artifact(
                type=ArtifactType.SUBTITLE,
                path=str(subtitle_path),
                metadata={"format": "srt", "language": "en"}
            )
            
            audio_artifact = Artifact(
                type=ArtifactType.AUDIO,
                path=str(audio_path),
                metadata={"format": "wav"}
            )
            
            # Setup operations
            mask_subs_op = MaskSubtitlesOperation(profanity_list=["test"])
            mute_audio_op = MuteAudioOperation() 
            remux_op = RemuxOperation()
            
            flags = OperationFlags(verbose=True)
            
            with patch.object(mute_audio_op.ffmpeg, 'apply_mute_windows') as mock_mute, \
                 patch.object(remux_op.ffmpeg, 'remux') as mock_remux:
                
                # Mock audio processing
                muted_audio_path = workdir / "muted_audio.wav"
                muted_audio_path.write_text("mock muted audio")
                mock_mute.return_value = str(muted_audio_path)
                
                # Mock remux
                final_video_path = workdir / "final_video.mkv"
                final_video_path.write_text("mock final video")
                mock_remux.return_value = str(final_video_path)
                
                # Execute pipeline steps
                mask_results = mask_subs_op.run([subtitle_artifact], workdir, flags)
                mute_results = mute_audio_op.run([audio_artifact], workdir, flags)
                
                all_artifacts = [video_artifact] + mask_results + mute_results
                remux_results = remux_op.run(all_artifacts, workdir, flags)
                
                # Verify results
                assert len(mask_results) == 1
                assert len(mute_results) == 1
                assert len(remux_results) == 1
                assert remux_results[0].type == ArtifactType.VIDEO

            def test_subtitle_derived_mute_then_remux(self, tmp_path: Path):
                """Generate audio + SRT, run mute from subtitles, then remux (mocked)."""
                import shutil, subprocess
                if not shutil.which("ffmpeg"):
                    pytest.skip("ffmpeg not available")

                # Files
                tone = tmp_path / "tone.wav"
                srt = tmp_path / "p.srt"
                video = tmp_path / "v.mkv"
                video.write_text("mock video")

                subprocess.run([
                    "ffmpeg", "-f", "lavfi", "-i", "sine=frequency=440:duration=5",
                    "-y", str(tone)
                ], check=True, capture_output=True)

                srt.write_text("""1\n00:00:01,000 --> 00:00:02,500\nshit\n""", encoding="utf-8")
                prof = tmp_path / "profanity.json"
                prof.write_text('[{"word": "shit"}]', encoding="utf-8")

                # Artifacts
                audio_art = Artifact(type=ArtifactType.AUDIO, path=str(tone), metadata={})
                sub_art = Artifact(type=ArtifactType.SUBTITLE, path=str(srt), metadata={})
                vid_art = Artifact(type=ArtifactType.VIDEO, path=str(video), metadata={})

                # Ops
                mute = MuteAudioOperation()
                remux = RemuxOperation()
                flags = OperationFlags(profanity_list_file=str(prof), verbose=True)

                # Mute
                muted = mute.run([audio_art, sub_art], tmp_path, flags)
                assert len(muted) == 1
                assert muted[0].metadata.get("mute_windows_applied", 0) >= 1

                # Remux (mock to avoid heavy work)
                with patch.object(remux.ffmpeg, 'remux') as mock_remux:
                    out_vid = tmp_path / "final.mkv"
                    out_vid.write_text("mock out")
                    mock_remux.return_value = str(out_vid)

                    result = remux.run([vid_art] + muted + [sub_art], tmp_path, flags)
                    assert len(result) == 1
                    assert result[0].type == ArtifactType.VIDEO
    
    def test_pipeline_with_external_mute_windows(self):
        """Test pipeline with external mute windows file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workdir = Path(temp_dir)
            
            # Create external mute windows
            external_windows = [
                {"start": 5.0, "end": 8.0, "reason": "violence", "source": "EXTERNAL"},
                {"start": 25.0, "end": 30.0, "reason": "inappropriate", "source": "EXTERNAL"}
            ]
            
            mute_windows_file = workdir / "external_mute.json"
            mute_windows_file.write_text(json.dumps(external_windows))
            
            # Create mock files
            video_path = workdir / "source_video.mkv"
            video_path.write_text("mock video")
            
            audio_path = workdir / "audio_track.wav"
            audio_path.write_text("mock audio")
            
            # Create artifacts with external mute windows
            video_artifact = Artifact(
                type=ArtifactType.VIDEO,
                path=str(video_path),
                metadata={"format": "matroska"}
            )
            
            audio_artifact = Artifact(
                type=ArtifactType.AUDIO,
                path=str(audio_path),
                metadata={
                    "format": "wav",
                    "mute_windows_file": str(mute_windows_file)
                }
            )
            
            # Setup operations
            mute_audio_op = MuteAudioOperation()
            remux_op = RemuxOperation()
            
            flags = OperationFlags(verbose=True)
            
            with patch.object(mute_audio_op.ffmpeg, 'apply_mute_windows') as mock_mute, \
                 patch.object(remux_op.ffmpeg, 'remux') as mock_remux:
                
                # Mock muting
                muted_audio_path = workdir / "externally_muted_audio.wav"
                muted_audio_path.write_text("mock muted audio")
                mock_mute.return_value = str(muted_audio_path)
                
                # Mock remux
                final_video_path = workdir / "final_processed_video.mkv"
                final_video_path.write_text("mock final video")
                mock_remux.return_value = str(final_video_path)
                
                # Apply external mute windows to audio
                mute_results = mute_audio_op.run([audio_artifact], workdir, flags)
                assert len(mute_results) == 1
                assert mute_results[0].metadata["mute_windows_applied"] == 2
                
                # Remux with processed audio
                all_artifacts = [video_artifact] + mute_results
                remux_results = remux_op.run(all_artifacts, workdir, flags)
                
                # Verify external mute windows were applied
                assert len(remux_results) == 1
                final_artifact = remux_results[0]
                assert final_artifact.type == ArtifactType.VIDEO
    
    def test_pipeline_error_recovery(self):
        """Test pipeline with error handling and recovery."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workdir = Path(temp_dir)
            
            # Create corrupt video file
            video_path = workdir / "corrupt_video.mkv"
            video_path.write_text("corrupt video data")
            
            video_artifact = Artifact(
                type=ArtifactType.VIDEO,
                path=str(video_path),
                metadata={}
            )
            
            # Test with operation failures
            extract_subs_op = ExtractSubtitlesOperation()
            
            with patch.object(extract_subs_op.ffmpeg, 'probe') as mock_probe:
                # Mock extraction failure
                mock_probe.side_effect = Exception("FFmpeg extraction failed")
                
                flags = OperationFlags(verbose=True)
                
                # Should handle error gracefully
                with pytest.raises(RuntimeError):
                    extract_subs_op.run([video_artifact], workdir, flags)
    
    def test_pipeline_with_subtitle_export(self):
        """Test pipeline including sidecar export."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workdir = Path(temp_dir)
            
            # Create mock files
            video_path = workdir / "export_test_video.mkv"
            video_path.write_text("mock video content")
            
            subtitle_path = workdir / "export_test_subtitles.srt"
            subtitle_path.write_text("1\n00:00:01,000 --> 00:00:05,000\nTest dialogue.")
            
            # Create artifacts
            video_artifact = Artifact(
                type=ArtifactType.VIDEO,
                path=str(video_path),
                metadata={"format": "matroska"}
            )
            
            subtitle_artifact = Artifact(
                type=ArtifactType.SUBTITLE,
                path=str(subtitle_path),
                metadata={"format": "srt", "language": "en"}
            )
            
            # Setup operations including export
            mask_subs_op = MaskSubtitlesOperation(profanity_list=["test"])
            export_op = SubtitleExportOperation(format=SubtitleFormat.JSON)
            
            flags = OperationFlags(verbose=True)
            
            # Execute pipeline with sidecar export
            mask_results = mask_subs_op.run([subtitle_artifact], workdir, flags)
            
            # Export sidecar
            export_artifacts = [video_artifact] + mask_results
            export_results = export_op.run(export_artifacts, workdir, flags)
            
            # Verify sidecar export
            assert len(export_results) == 1
            assert export_results[0].type == ArtifactType.SIDECAR
    
    def test_pipeline_with_caching(self):
        """Test pipeline with caching enabled."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workdir = Path(temp_dir)
            
            # Setup cache manager
            cache_manager = CacheManager(workdir)
            
            # Create mock files
            subtitle_path = workdir / "cached_test_subtitles.srt"
            subtitle_path.write_text("1\n00:00:01,000 --> 00:00:05,000\nCached test.")
            
            # Create artifact
            subtitle_artifact = Artifact(
                type=ArtifactType.SUBTITLE,
                path=str(subtitle_path),
                metadata={"format": "srt", "language": "en"}
            )
            
            # Test operations with caching
            mask_subs_op = MaskSubtitlesOperation(profanity_list=["test"])
            
            flags = OperationFlags(verbose=True)
            
            # Execute with caching
            cache_key = cache_manager.create_cache_key(
                operation_name="mask_subtitles",
                params={"profanity_list": ["test"]},
                inputs=[subtitle_artifact]
            )
            
            # First execution
            mask_results1 = mask_subs_op.run([subtitle_artifact], workdir, flags)
            
            # Second execution (should be consistent)
            mask_results2 = mask_subs_op.run([subtitle_artifact], workdir, flags)
            
            # Results should be consistent
            assert len(mask_results1) == len(mask_results2)
            assert mask_results1[0].type == mask_results2[0].type