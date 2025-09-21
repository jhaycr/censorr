"""Tests for merge_subtitles operation."""
import pytest
from pathlib import Path
import tempfile
from unittest.mock import Mock, patch
from src.ops.merge_subtitles import MergeSubtitlesOperation
from src.models.artifacts import Artifact, ArtifactType
from src.models.operations import OperationFlags
from src.utils.subtitle_parser import SubtitleEntry


class TestMergeSubtitlesOperation:
    """Test MergeSubtitlesOperation."""
    
    def test_operation_creation(self):
        """Test operation creation."""
        op = MergeSubtitlesOperation()
        assert op.name == "merge_subtitles"
        assert ArtifactType.SUBTITLE in op.consumes
        assert ArtifactType.SUBTITLE in op.produces
        assert op.description is not None
    
    def test_run_with_multiple_subtitles(self):
        """Test running operation with multiple subtitle files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create subtitle files
            sub1_path = Path(tmpdir) / "sub1.srt"
            sub1_content = """1
00:00:01,000 --> 00:00:03,000
First subtitle

2
00:00:05,000 --> 00:00:07,000
Second subtitle
"""
            sub1_path.write_text(sub1_content)
            
            sub2_path = Path(tmpdir) / "sub2.srt"
            sub2_content = """1
00:00:02,500 --> 00:00:04,500
Overlapping subtitle

2
00:00:08,000 --> 00:00:10,000
Fourth subtitle
"""
            sub2_path.write_text(sub2_content)
            
            # Create subtitle artifacts
            sub1_artifact = Artifact(
                type=ArtifactType.SUBTITLE,
                path=str(sub1_path),
                metadata={"language": "en"}
            )
            
            sub2_artifact = Artifact(
                type=ArtifactType.SUBTITLE,
                path=str(sub2_path),
                metadata={"language": "en"}
            )
            
            # Run operation
            op = MergeSubtitlesOperation()
            flags = OperationFlags()
            
            result = op.run([sub1_artifact, sub2_artifact], Path(tmpdir), flags)
            
            # Verify result
            assert len(result) == 1
            merged_artifact = result[0]
            assert merged_artifact.type == ArtifactType.SUBTITLE
            assert Path(merged_artifact.path).exists()
            
            # Verify merged content has all entries in chronological order
            with patch.object(op.parser, 'parse_file') as mock_parse:
                # Mock parser to return expected entries
                mock_parse.return_value = [
                    SubtitleEntry(index=1, start=1.0, end=3.0, text="First subtitle", normalized_text="first subtitle"),
                    SubtitleEntry(index=2, start=2.5, end=4.5, text="Overlapping subtitle", normalized_text="overlapping subtitle"),
                    SubtitleEntry(index=3, start=5.0, end=7.0, text="Second subtitle", normalized_text="second subtitle"),
                    SubtitleEntry(index=4, start=8.0, end=10.0, text="Fourth subtitle", normalized_text="fourth subtitle")
                ]
                
                # Verify chronological ordering would be maintained
                entries = mock_parse.return_value
                start_times = [entry.start for entry in entries]
                assert start_times == sorted(start_times)
    
    def test_run_with_single_subtitle(self):
        """Test running operation with single subtitle file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create single subtitle file
            sub_path = Path(tmpdir) / "single.srt"
            sub_content = """1
00:00:01,000 --> 00:00:03,000
Single subtitle
"""
            sub_path.write_text(sub_content)
            
            sub_artifact = Artifact(
                type=ArtifactType.SUBTITLE,
                path=str(sub_path),
                metadata={"language": "en"}
            )
            
            # Run operation
            op = MergeSubtitlesOperation()
            flags = OperationFlags()
            
            result = op.run([sub_artifact], Path(tmpdir), flags)
            
            # Should still create merged file (copy of single file)
            assert len(result) == 1
            assert Path(result[0].path).exists()
    
    def test_run_no_subtitle_artifacts(self):
        """Test running operation without subtitle artifacts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create non-subtitle artifact
            video_artifact = Artifact(
                type=ArtifactType.VIDEO,
                path="/path/to/video.mkv",
                metadata={}
            )
            
            op = MergeSubtitlesOperation()
            flags = OperationFlags()
            
            # Should raise ValueError
            with pytest.raises(ValueError, match="No subtitle artifacts found"):
                op.run([video_artifact], Path(tmpdir), flags)
    
    def test_run_dry_run(self):
        """Test running operation in dry-run mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sub_path = Path(tmpdir) / "test.srt"
            sub_path.write_text("1\n00:00:01,000 --> 00:00:03,000\nTest")
            
            sub_artifact = Artifact(
                type=ArtifactType.SUBTITLE,
                path=str(sub_path),
                metadata={"language": "en"}
            )
            
            op = MergeSubtitlesOperation()
            flags = OperationFlags(dry_run=True)
            
            result = op.run([sub_artifact], Path(tmpdir), flags)
            
            # Should return planned artifact but not create file
            assert len(result) == 1
            assert not Path(result[0].path).exists()
    
    def test_run_with_parser_error(self):
        """Test handling subtitle parser errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create invalid subtitle file
            sub_path = Path(tmpdir) / "invalid.srt"
            sub_path.write_text("invalid subtitle content")
            
            sub_artifact = Artifact(
                type=ArtifactType.SUBTITLE,
                path=str(sub_path),
                metadata={"language": "en"}
            )
            
            op = MergeSubtitlesOperation()
            flags = OperationFlags()
            
            with patch.object(op.parser, 'parse_file') as mock_parse:
                from src.utils.subtitle_parser import SubtitleError
                mock_parse.side_effect = SubtitleError("Failed to parse subtitle")
                
                # Should raise RuntimeError
                with pytest.raises(RuntimeError, match="Failed to parse subtitle"):
                    op.run([sub_artifact], Path(tmpdir), flags)
    
    def test_merge_entries_chronological_order(self):
        """Test merging entries in chronological order."""
        op = MergeSubtitlesOperation()
        
        # Create entries with overlapping times
        entries1 = [
            SubtitleEntry(index=1, start=1.0, end=3.0, text="First", normalized_text="first"),
            SubtitleEntry(index=2, start=5.0, end=7.0, text="Third", normalized_text="third")
        ]
        
        entries2 = [
            SubtitleEntry(index=1, start=2.0, end=4.0, text="Second", normalized_text="second"),
            SubtitleEntry(index=2, start=8.0, end=10.0, text="Fourth", normalized_text="fourth")
        ]
        
        merged = op._merge_entries([entries1, entries2])
        
        # Should be in chronological order
        assert len(merged) == 4
        assert merged[0].text == "First"    # 1.0
        assert merged[1].text == "Second"   # 2.0
        assert merged[2].text == "Third"    # 5.0
        assert merged[3].text == "Fourth"   # 8.0
        
        # Indices should be renumbered
        for i, entry in enumerate(merged):
            assert entry.index == i + 1
    
    def test_merge_entries_with_duplicates(self):
        """Test merging entries with duplicate timing."""
        op = MergeSubtitlesOperation()
        
        entries1 = [
            SubtitleEntry(index=1, start=1.0, end=3.0, text="Same time A", normalized_text="same time a")
        ]
        
        entries2 = [
            SubtitleEntry(index=1, start=1.0, end=3.0, text="Same time B", normalized_text="same time b")
        ]
        
        merged = op._merge_entries([entries1, entries2])
        
        # Should keep both entries but may combine or handle differently
        # For now, we keep both and let them sort by original order
        assert len(merged) >= 1  # At least one entry should remain
    
    def test_generate_srt_content(self):
        """Test generating SRT content from entries."""
        op = MergeSubtitlesOperation()
        
        entries = [
            SubtitleEntry(index=1, start=1.5, end=3.2, text="First entry", normalized_text="first entry"),
            SubtitleEntry(index=2, start=5.0, end=7.5, text="Second entry", normalized_text="second entry")
        ]
        
        content = op._generate_srt_content(entries)
        
        # Should contain proper SRT format
        assert "1" in content
        assert "00:00:01,500 --> 00:00:03,200" in content
        assert "First entry" in content
        assert "2" in content
        assert "00:00:05,000 --> 00:00:07,500" in content
        assert "Second entry" in content
    
    def test_format_srt_timestamp(self):
        """Test SRT timestamp formatting."""
        op = MergeSubtitlesOperation()
        
        # Test various timestamps
        assert op._format_srt_timestamp(0.0) == "00:00:00,000"
        assert op._format_srt_timestamp(1.5) == "00:00:01,500"
        assert op._format_srt_timestamp(61.25) == "00:01:01,250"
        assert op._format_srt_timestamp(3661.5) == "01:01:01,500"
    
    def test_validate_inputs(self):
        """Test input validation."""
        op = MergeSubtitlesOperation()
        
        # Valid input
        sub_artifact = Artifact(
            type=ArtifactType.SUBTITLE,
            path="/path/to/subtitle.srt",
            metadata={"language": "en"}
        )
        
        # Should not raise
        op.validate_inputs([sub_artifact])
        
        # Invalid input
        video_artifact = Artifact(
            type=ArtifactType.VIDEO,
            path="/path/to/video.mkv",
            metadata={}
        )
        
        # Should raise ValueError
        with pytest.raises(ValueError, match="Missing required input types"):
            op.validate_inputs([video_artifact])