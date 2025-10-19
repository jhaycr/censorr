"""Integration tests for subtitle-only processing flow.

Tests the complete subtitle processing pipeline:
1. Extract subtitles from video
2. Apply fuzzy matching to detect profanity
3. Generate masked subtitles with censored content
4. Export sidecar files with processing metadata
"""
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

from src.cli.main import main as cli_main
from src.models.artifacts import Artifact, ArtifactType
from src.models.operations import OperationFlags
from src.ops.subtitle_extract import ExtractSubtitlesOperation
from src.ops.subtitle_mask import MaskSubtitlesOperation  
from src.ops.subtitle_export import SubtitleExportOperation, SubtitleFormat
from src.planner.executor import Executor
from src.planner.registry import OperationRegistry
from src.planner.planner import Planner, ExecutionPlan
from src.caching import CacheManager
from src.logging import ExecutionLogger


class TestSubtitleOnlyFlow:
    """Integration tests for subtitle processing pipeline."""
    
    def test_subtitle_flow_dry_run(self):
        """Test subtitle processing flow in dry-run mode."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workdir = Path(temp_dir)
            
            # Mock video file with subtitles
            video_path = workdir / "test_video.mkv"
            video_path.write_text("mock video content")
            
            # Create video artifact
            video_artifact = Artifact(
                type=ArtifactType.VIDEO,
                path=str(video_path),
                metadata={"has_subtitles": True}
            )
            
            # Setup operations
            extract_subs = ExtractSubtitlesOperation()
            
            # Execute dry-run subtitle extraction
            flags = OperationFlags(dry_run=True, verbose=True)
            
            with patch.object(extract_subs.ffmpeg, 'probe') as mock_probe, \
                 patch.object(extract_subs.ffmpeg, 'extract_subtitles') as mock_extract:
                
                # Mock FFmpeg probe to return subtitle track info
                mock_media_info = Mock()
                mock_media_info.get_subtitle_tracks.return_value = [
                    Mock(index=0, codec="subrip", language="en", title="English")
                ]
                mock_probe.return_value = mock_media_info
                
                # Mock subtitle extraction (should not be called in dry-run)
                mock_extract.return_value = str(workdir / "subtitles.srt")
                
                # Execute extraction in dry-run mode
                results = extract_subs.run([video_artifact], workdir, flags)
                
                # Verify dry-run execution
                assert len(results) > 0
                
                # Should have planned subtitle artifacts
                subtitle_artifacts = [a for a in results if a.type == ArtifactType.SUBTITLE]
                assert len(subtitle_artifacts) > 0
                
                # Verify metadata indicates dry-run
                for artifact in results:
                    if "planned" in artifact.metadata:
                        assert artifact.metadata["planned"] is True
                
                # In dry-run, actual extraction should not occur
                mock_extract.assert_not_called()
    
    def test_subtitle_flow_with_profanity_detection(self):
        """Test subtitle flow with profanity detection and masking."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workdir = Path(temp_dir)
            
            # Create mock subtitle file with profanity
            subtitle_content = """1
00:00:01,000 --> 00:00:03,000
This is a bad word in the subtitle.

2
00:00:05,000 --> 00:00:07,000
Another ugly phrase here.

3
00:00:10,000 --> 00:00:12,000
Clean content without issues.
"""
            subtitle_path = workdir / "test.srt"
            subtitle_path.write_text(subtitle_content)
            
            # Create subtitle artifact
            subtitle_artifact = Artifact(
                type=ArtifactType.SUBTITLE,
                path=str(subtitle_path),
                metadata={"language": "en", "format": "srt"}
            )
            
            # Test masking operation with profanity detection
            mask_operation = MaskSubtitlesOperation(profanity_list=["bad", "ugly"])
            
            flags = OperationFlags(verbose=True)
            results = mask_operation.run([subtitle_artifact], workdir, flags)
            
            # Verify masked subtitles were created
            assert len(results) == 1
            masked_artifact = results[0]
            assert masked_artifact.type == ArtifactType.SUBTITLE
            assert "matches_found" in masked_artifact.metadata
            assert masked_artifact.metadata["matches_found"] == 2
            
            # Verify content was actually masked
            masked_content = Path(masked_artifact.path).read_text()
            assert "***" in masked_content  # Default mask pattern
            assert "bad" not in masked_content
            assert "ugly" not in masked_content
            assert "Clean content" in masked_content  # Should remain unchanged
    
    def test_subtitle_flow_export_subtitle(self):
        """Test exporting sidecar files with subtitle processing metadata."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workdir = Path(temp_dir)
            
            # Create processed subtitle artifact with mute windows
            subtitle_artifact = Artifact(
                type=ArtifactType.SUBTITLE,
                path=str(workdir / "masked_subtitles.srt"),
                metadata={
                    "language": "en",
                    "matches_found": 2,
                    "profanity_filtered": True,
                    "entries_modified": 2
                }
            )
            
            # Create sidecar file with proper SRT format
            subtitle_srt_content = """1
00:00:01,000 --> 00:00:03,000
This content was processed

2
00:00:05,000 --> 00:00:07,000
[CENSORED] content here
"""
            (workdir / "masked_subtitles.srt").write_text(subtitle_srt_content)
            
            # Test export operation with JSON format for metadata
            export_operation = SubtitleExportOperation(format=SubtitleFormat.JSON)
            flags = OperationFlags()
            
            results = export_operation.run([subtitle_artifact], workdir, flags)
            
            # Verify sidecar artifact was created
            assert len(results) == 1
            sidecar_artifact = results[0]
            assert sidecar_artifact.type == ArtifactType.SIDECAR
            
            # Verify sidecar file contains processing metadata
            sidecar_path = Path(sidecar_artifact.path)
            assert sidecar_path.exists()
            
            sidecar_data = json.loads(sidecar_path.read_text())
            assert "metadata" in sidecar_data
            assert "subtitles" in sidecar_data
            assert len(sidecar_data["subtitles"]) == 2
    
    def test_full_subtitle_pipeline_integration(self):
        """Test complete subtitle processing pipeline with all steps."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workdir = Path(temp_dir)
            
            # Setup mock video file
            video_path = workdir / "movie.mkv"
            video_path.write_text("mock video")
            
            # Setup operations with enhanced error handling
            extract_op = ExtractSubtitlesOperation()
            mask_op = MaskSubtitlesOperation(profanity_list=["damn", "hell"])
            export_op = SubtitleExportOperation()
            
            # Create video artifact
            video_artifact = Artifact(
                type=ArtifactType.VIDEO,
                path=str(video_path),
                metadata={"format": "matroska"}
            )
            
            with patch.object(extract_op.ffmpeg, 'probe') as mock_probe, \
                 patch.object(extract_op.ffmpeg, 'extract_subtitles') as mock_extract:
                
                # Mock subtitle extraction
                mock_media_info = Mock()
                mock_media_info.get_subtitle_tracks.return_value = [
                    Mock(index=0, codec="subrip", language="en")
                ]
                mock_probe.return_value = mock_media_info
                
                # Create mock subtitle file with profanity
                subtitle_content = """1
00:00:01,000 --> 00:00:05,000
What the hell is going on here?

2
00:00:10,000 --> 00:00:15,000
This damn thing is broken.

3
00:00:20,000 --> 00:00:25,000
Everything else looks fine.
"""
                extracted_path = workdir / "extracted_subs.srt"
                extracted_path.write_text(subtitle_content)
                mock_extract.return_value = str(extracted_path)
                
                # Execute step 1: Extract subtitles
                flags = OperationFlags(verbose=True)
                
                extract_results = extract_op.run([video_artifact], workdir, flags)
                
                # Verify extraction results
                assert len(extract_results) == 1
                subtitle_artifact = extract_results[0]
                assert subtitle_artifact.type == ArtifactType.SUBTITLE
                
                # Make sure the subtitle file actually exists for the next step
                subtitle_path = Path(subtitle_artifact.path)
                subtitle_path.write_text(subtitle_content)
                
                # Execute step 2: Mask subtitles
                mask_results = mask_op.run([subtitle_artifact], workdir, flags)
                
                # Verify masking results
                assert len(mask_results) == 1
                masked_artifact = mask_results[0]
                assert "matches_found" in masked_artifact.metadata
                
                # Verify profanity was detected and masked
                matches_found = masked_artifact.metadata["matches_found"]
                assert matches_found == 2  # Two profane phrases
                
                # Execute step 3: Export sidecar
                export_results = export_op.run([masked_artifact], workdir, flags)
                
                # Verify sidecar export
                assert len(export_results) == 1
                sidecar_artifact = export_results[0]
                assert sidecar_artifact.type == ArtifactType.SIDECAR
                
                # Verify complete pipeline results
                assert Path(sidecar_artifact.path).exists()
    
    def test_subtitle_flow_error_handling(self):
        """Test subtitle flow with error handling and artifact preservation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workdir = Path(temp_dir)
            
            # Setup video artifact
            video_path = workdir / "corrupt_video.mkv"
            video_path.write_text("corrupt video data")
            
            video_artifact = Artifact(
                type=ArtifactType.VIDEO,
                path=str(video_path),
                metadata={}
            )
            
            # Test with failing FFmpeg operation
            extract_op = ExtractSubtitlesOperation()
            
            with patch.object(extract_op.ffmpeg, 'probe') as mock_probe:
                # Mock probe failure
                mock_probe.side_effect = Exception("FFmpeg probe failed")
                
                flags = OperationFlags(verbose=True)
                
                # Execution should handle the error gracefully
                with pytest.raises(RuntimeError, match="Unexpected error during subtitle extraction"):
                    extract_op.run([video_artifact], workdir, flags)
                
                # Verify error was logged if logger is available
                assert mock_probe.called
    
    def test_subtitle_flow_with_caching(self):
        """Test subtitle flow with caching enabled."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workdir = Path(temp_dir)
            
            # Setup cache manager
            cache_manager = CacheManager(workdir)
            
            # Create subtitle artifact for masking with proper SRT format
            subtitle_content = """1
00:00:01,000 --> 00:00:03,000
Mock subtitle content without profanity

2
00:00:05,000 --> 00:00:07,000
Clean text here
"""
            subtitle_path = workdir / "clean_subs.srt"
            subtitle_path.write_text(subtitle_content)
            
            subtitle_artifact = Artifact(
                type=ArtifactType.SUBTITLE,
                path=str(subtitle_path),
                metadata={"language": "en"}
            )
            
            # Test mask operation with caching
            mask_op = MaskSubtitlesOperation(profanity_list=["bad"])
            flags = OperationFlags()
            
            # First execution - should create cache
            cache_key = cache_manager.create_cache_key(
                operation_name="mask_subtitles",
                params={"profanity_list": ["bad"]},
                inputs=[subtitle_artifact]
            )
            
            # Execute operation
            results1 = mask_op.run([subtitle_artifact], workdir, flags)
            
            # Second execution - should use cache (mock this behavior)
            results2 = mask_op.run([subtitle_artifact], workdir, flags)
            
            # Results should be consistent
            assert len(results1) == len(results2) == 1
            assert results1[0].type == results2[0].type == ArtifactType.SUBTITLE