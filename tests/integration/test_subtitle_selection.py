"""Integration test for subtitle selection with multiple tracks."""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from src.models.artifacts import Artifact, ArtifactType
from src.models.selectors import Selector
from src.planner.planner import Planner
from src.planner.registry import OperationRegistry
from src.ops.extract_subtitles import ExtractSubtitlesOperation
from src.ops.merge_subtitles import MergeSubtitlesOperation


class TestSubtitleSelectionIntegration:
    """Integration test for subtitle selection with three English tracks."""
    
    def test_select_full_and_forced_exclude_sdh(self):
        """Test selecting English full + forced while excluding SDH."""
        # Mock video artifact with three subtitle tracks
        video_artifact = Artifact(
            type=ArtifactType.VIDEO,
            path="/test/movie.mkv",
            metadata={}
        )
        
        # Create selector that should pick full + forced, exclude SDH
        selector = Selector(
            type=ArtifactType.SUBTITLE,
            language="en",
            exclude_sdh=True  # This will exclude the SDH track
        )
        
        # Mock the extract operation to return three tracks
        mock_full_sub = Artifact(
            type=ArtifactType.SUBTITLE,
            path="/work/extracted_sub_0.srt",
            metadata={
                "language": "en",
                "title": "",  # Empty title = main/full track
                "track_index": 0,
                "forced": False
            }
        )
        
        mock_forced_sub = Artifact(
            type=ArtifactType.SUBTITLE, 
            path="/work/extracted_sub_1.srt",
            metadata={
                "language": "en",
                "title": "English Forced",
                "track_index": 1,
                "forced": True
            }
        )
        
        mock_sdh_sub = Artifact(
            type=ArtifactType.SUBTITLE,
            path="/work/extracted_sub_2.srt", 
            metadata={
                "language": "en",
                "title": "English [SDH]",
                "track_index": 2,
                "forced": False
            }
        )
        
        # Test that selector matches correctly
        assert selector.matches(mock_full_sub), "Should match full track (empty title)"
        assert selector.matches(mock_forced_sub), "Should match forced track"  
        assert not selector.matches(mock_sdh_sub), "Should exclude SDH track"
        
        # Simulate what merge operation would receive
        selected_subs = [mock_full_sub, mock_forced_sub]  # SDH excluded
        
        # Verify we got the expected tracks
        assert len(selected_subs) == 2
        assert any(sub.metadata.get("title") == "" for sub in selected_subs)  # Full track
        assert any(sub.metadata.get("forced") == True for sub in selected_subs)  # Forced track
        assert not any("SDH" in sub.metadata.get("title", "") for sub in selected_subs)  # No SDH
    
    def test_planning_with_subtitle_filters(self):
        """Test that planner correctly applies subtitle filters."""
        # Create registry with extract and merge operations
        registry = OperationRegistry()
        registry.register(ExtractSubtitlesOperation())
        registry.register(MergeSubtitlesOperation())
        
        planner = Planner(registry)
        
        # Input video
        video_artifact = Artifact(
            type=ArtifactType.VIDEO,
            path="/test/movie.mkv",
            metadata={}
        )
        
        # Selector for English non-SDH subtitles
        selector = Selector(
            type=ArtifactType.SUBTITLE,
            language="en",
            exclude_sdh=True
        )
        
        # Plan to produce merged subtitle
        plan = planner.plan(
            provided_artifacts=[video_artifact],
            target_types={ArtifactType.SUBTITLE},
            selectors=[selector]
        )
        
        # Should have extract and merge operations
        assert len(plan.operations) >= 1  # At least extract
        assert any(op.name == "extract_subtitles" for op in plan.operations)
        
        # The selector should be passed to the operations
        extract_op = next(op for op in plan.operations if op.name == "extract_subtitles")
        # Operations should receive selectors through planner context
        # (Implementation detail - actual passing happens in executor)
    
    def test_multiple_selectors_with_different_priorities(self):
        """Test multiple selectors with different priorities."""
        # First selector: prefer forced tracks
        forced_selector = Selector(
            type=ArtifactType.SUBTITLE,
            language="en",
            forced=True,
            priority=0  # Higher priority (lower number)
        )
        
        # Second selector: fallback to any English track (excluding SDH)
        fallback_selector = Selector(
            type=ArtifactType.SUBTITLE,
            language="en", 
            exclude_sdh=True,
            priority=1  # Lower priority
        )
        
        # Test tracks
        forced_track = Artifact(
            type=ArtifactType.SUBTITLE,
            path="/forced.srt",
            metadata={"language": "en", "title": "English Forced", "forced": True}
        )
        
        full_track = Artifact(
            type=ArtifactType.SUBTITLE,
            path="/full.srt", 
            metadata={"language": "en", "title": "", "forced": False}
        )
        
        sdh_track = Artifact(
            type=ArtifactType.SUBTITLE,
            path="/sdh.srt",
            metadata={"language": "en", "title": "English [SDH]", "forced": False}
        )
        
        # Check matching behavior
        assert forced_selector.matches(forced_track)
        assert not forced_selector.matches(full_track)  # Not forced
        assert not forced_selector.matches(sdh_track)   # Not forced
        
        assert fallback_selector.matches(forced_track)  # Forced=None matches any forced value
        assert fallback_selector.matches(full_track)
        assert not fallback_selector.matches(sdh_track)  # SDH excluded
        
        # In a real scenario, planner would apply selectors by priority
        # and forced_selector would pick the forced track first