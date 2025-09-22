"""Contract tests for selector filtering in extract_subtitles operation."""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from src.ops.extract_subtitles import ExtractSubtitlesOperation
from src.models.artifacts import Artifact, ArtifactType
from src.models.operations import OperationFlags
from src.models.selectors import Selector
from src.adapters.ffmpeg import MediaInfo, TrackInfo


class TestExtractSubtitlesFiltering:
    """Contract tests for subtitle selector filtering."""
    
    def test_extract_subtitles_filters_by_language(self, tmp_path):
        """Test that extract_subtitles only extracts tracks matching language selector."""
        # Arrange
        operation = ExtractSubtitlesOperation()
        video_artifact = Artifact(
            type=ArtifactType.VIDEO,
            path="/fake/video.mkv",
            metadata={}
        )
        
        # Create selectors for English only
        english_selector = Selector(
            type=ArtifactType.SUBTITLE,
            language="en"
        )
        
        flags = OperationFlags(
            selectors=[english_selector],
            dry_run=False
        )
        
        # Mock media info with multiple language tracks
        mock_tracks = [
            TrackInfo(index=2, type="subtitle", codec="subrip", language="eng", title="Forced", forced=True),
            TrackInfo(index=3, type="subtitle", codec="subrip", language="eng", title=None, forced=False),
            TrackInfo(index=4, type="subtitle", codec="subrip", language="spa", title="Spanish", forced=False),
            TrackInfo(index=5, type="subtitle", codec="subrip", language="fra", title="French", forced=False),
        ]
        
        mock_media_info = MediaInfo(format="matroska", tracks=mock_tracks)
        
        with patch.object(operation.ffmpeg, 'probe') as mock_probe, \
             patch.object(operation.ffmpeg, 'extract_subtitles') as mock_extract:
            
            mock_probe.return_value = mock_media_info
            mock_extract.return_value = "/fake/output.srt"
            
            # Act
            results = operation.run([video_artifact], tmp_path, flags)
            
            # Assert - should only extract English tracks (2 calls)
            assert mock_extract.call_count == 2
            
            # Verify English tracks were extracted
            call_args = [call[1]['track_index'] for call in mock_extract.call_args_list]
            assert 0 in call_args  # English Forced (relative index 0)
            assert 1 in call_args  # English Main (relative index 1)
            
            # Verify Spanish and French tracks were NOT extracted
            assert 2 not in call_args  # Spanish should be filtered out
            assert 3 not in call_args  # French should be filtered out
            
            # Verify 2 subtitle artifacts were created
            assert len(results) == 2
            assert all(artifact.type == ArtifactType.SUBTITLE for artifact in results)
    
    def test_extract_subtitles_filters_by_title_include(self, tmp_path):
        """Test that extract_subtitles only extracts tracks with titles in include list."""
        # Arrange
        operation = ExtractSubtitlesOperation()
        video_artifact = Artifact(
            type=ArtifactType.VIDEO,
            path="/fake/video.mkv",
            metadata={}
        )
        
        # Create selector for forced tracks only
        forced_selector = Selector(
            type=ArtifactType.SUBTITLE,
            language="en",
            title_include=["Forced"]
        )
        
        flags = OperationFlags(
            selectors=[forced_selector],
            dry_run=False
        )
        
        # Mock media info with English tracks
        mock_tracks = [
            TrackInfo(index=2, type="subtitle", codec="subrip", language="eng", title="Forced", forced=True),
            TrackInfo(index=3, type="subtitle", codec="subrip", language="eng", title=None, forced=False),
            TrackInfo(index=4, type="subtitle", codec="subrip", language="eng", title="SDH", forced=False),
        ]
        
        mock_media_info = MediaInfo(format="matroska", tracks=mock_tracks)
        
        with patch.object(operation.ffmpeg, 'probe') as mock_probe, \
             patch.object(operation.ffmpeg, 'extract_subtitles') as mock_extract:
            
            mock_probe.return_value = mock_media_info
            mock_extract.return_value = "/fake/output.srt"
            
            # Act
            results = operation.run([video_artifact], tmp_path, flags)
            
            # Assert - should only extract Forced track (1 call)
            assert mock_extract.call_count == 1
            
            # Verify only Forced track was extracted
            call_args = [call[1]['track_index'] for call in mock_extract.call_args_list]
            assert 0 in call_args  # Forced track (relative index 0)
            
            # Verify 1 subtitle artifact was created
            assert len(results) == 1
            assert results[0].metadata['title'] == "Forced"
    
    def test_extract_subtitles_filters_exclude_sdh(self, tmp_path):
        """Test that extract_subtitles excludes SDH tracks when exclude_sdh=True."""
        # Arrange  
        operation = ExtractSubtitlesOperation()
        video_artifact = Artifact(
            type=ArtifactType.VIDEO,
            path="/fake/video.mkv",
            metadata={}
        )
        
        # Create selector that excludes SDH
        no_sdh_selector = Selector(
            type=ArtifactType.SUBTITLE,
            language="en",
            exclude_sdh=True
        )
        
        flags = OperationFlags(
            selectors=[no_sdh_selector],
            dry_run=False
        )
        
        # Mock media info with SDH and regular tracks
        mock_tracks = [
            TrackInfo(index=2, type="subtitle", codec="subrip", language="eng", title="Forced", forced=True),
            TrackInfo(index=3, type="subtitle", codec="subrip", language="eng", title=None, forced=False),
            TrackInfo(index=4, type="subtitle", codec="subrip", language="eng", title="SDH", forced=False),
        ]
        
        mock_media_info = MediaInfo(format="matroska", tracks=mock_tracks)
        
        with patch.object(operation.ffmpeg, 'probe') as mock_probe, \
             patch.object(operation.ffmpeg, 'extract_subtitles') as mock_extract:
            
            mock_probe.return_value = mock_media_info
            mock_extract.return_value = "/fake/output.srt"
            
            # Act
            results = operation.run([video_artifact], tmp_path, flags)
            
            # Assert - should extract Forced and Main, but NOT SDH (2 calls)
            assert mock_extract.call_count == 2
            
            # Verify SDH track was NOT extracted
            call_args = [call[1]['track_index'] for call in mock_extract.call_args_list]
            assert 0 in call_args  # Forced track 
            assert 1 in call_args  # Main track
            assert 2 not in call_args  # SDH track should be excluded
            
            # Verify 2 subtitle artifacts were created (no SDH)
            assert len(results) == 2
            assert all(artifact.metadata.get('title') != "SDH" for artifact in results)

    def test_extract_subtitles_no_selectors_extracts_all(self, tmp_path):
        """Test that extract_subtitles extracts all tracks when no selectors provided."""
        # Arrange
        operation = ExtractSubtitlesOperation()
        video_artifact = Artifact(
            type=ArtifactType.VIDEO,
            path="/fake/video.mkv",
            metadata={}
        )
        
        flags = OperationFlags(
            selectors=[],  # No selectors
            dry_run=False
        )
        
        # Mock media info with multiple tracks
        mock_tracks = [
            TrackInfo(index=2, type="subtitle", codec="subrip", language="eng", title="Forced", forced=True),
            TrackInfo(index=3, type="subtitle", codec="subrip", language="eng", title=None, forced=False),
            TrackInfo(index=4, type="subtitle", codec="subrip", language="spa", title="Spanish", forced=False),
        ]
        
        mock_media_info = MediaInfo(format="matroska", tracks=mock_tracks)
        
        with patch.object(operation.ffmpeg, 'probe') as mock_probe, \
             patch.object(operation.ffmpeg, 'extract_subtitles') as mock_extract:
            
            mock_probe.return_value = mock_media_info
            mock_extract.return_value = "/fake/output.srt"
            
            # Act
            results = operation.run([video_artifact], tmp_path, flags)
            
            # Assert - should extract all tracks (3 calls)
            assert mock_extract.call_count == 3
            
            # Verify 3 subtitle artifacts were created
            assert len(results) == 3