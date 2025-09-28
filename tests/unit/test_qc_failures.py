"""Unit tests for QC failure behavior and continue_on_qc_fail flag."""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import json

from src.models.artifacts import Artifact, ArtifactType
from src.models.operations import OperationFlags
from src.ops.mask_subtitles import MaskSubtitlesOperation
from src.utils.subtitle_parser import SubtitleEntry
from src.utils.fuzzy_matcher import MatchResult


class TestQCFailureBehavior:
    """Test cases for QC failure scenarios and continue_on_qc_fail flag."""
    
    @patch('src.ops.mask_subtitles.SubtitleParser')
    @patch('src.ops.mask_subtitles.FuzzyMatcher')
    def test_qc_failure_default_abort(self, mock_matcher_class, mock_parser_class):
        """Test that QC failure aborts by default when residual matches found."""
        # Setup mocks
        mock_parser = mock_parser_class.return_value
        mock_matcher = mock_matcher_class.return_value
        
        # Mock subtitle entries
        mock_entries = [
            SubtitleEntry(index=1, start=0.0, end=2.0, text="This is damn good", normalized_text="this is damn good")
        ]
        mock_parser.parse_file.return_value = mock_entries
        mock_parser.normalize_text.side_effect = lambda text: text.lower()
        
        # Mock profanity detection
        def mock_find_matches_in_text(text):
            if "damn" in text.lower():
                return [MatchResult(query="damn", target="damn", score=95.0, is_match=True, 
                                  normalized_query="damn", normalized_target="damn", window_text="damn")]
            return []
        
        mock_matcher.find_matches_in_text.side_effect = mock_find_matches_in_text
        
        # Test data
        workdir = Path("/tmp/test")
        input_artifact = Artifact(
            type=ArtifactType.SUBTITLE,
            path="/path/to/subtitle.srt",
            metadata={"language": "en"}
        )
        flags = OperationFlags(continue_on_qc_fail=False)  # Default behavior
        
        op = MaskSubtitlesOperation()
        
        # Mock QC to return residual matches (failure)
        qc_report = {
            "residual_matches": 1,
            "report_path": "/tmp/test/qc_report.json",
            "matches": [{"text": "damn", "confidence": 95.0}]
        }
        
        with patch.object(Path, 'write_text'), \
             patch.object(op, '_run_quality_check', return_value=qc_report):
            
            # Should raise RuntimeError for QC failure
            with pytest.raises(RuntimeError) as exc_info:
                op.run([input_artifact], workdir, flags)
            
            assert "Quality check failed" in str(exc_info.value)
            assert "1 residual profane matches" in str(exc_info.value)
    
    @patch('src.ops.mask_subtitles.SubtitleParser')
    @patch('src.ops.mask_subtitles.FuzzyMatcher')
    def test_qc_failure_continue_override(self, mock_matcher_class, mock_parser_class):
        """Test that continue_on_qc_fail allows pipeline to continue despite QC failure."""
        # Setup mocks
        mock_parser = mock_parser_class.return_value
        mock_matcher = mock_matcher_class.return_value
        
        # Mock subtitle entries
        mock_entries = [
            SubtitleEntry(index=1, start=0.0, end=2.0, text="This is damn good", normalized_text="this is damn good")
        ]
        mock_parser.parse_file.return_value = mock_entries
        mock_parser.normalize_text.side_effect = lambda text: text.lower()
        
        # Mock profanity detection
        def mock_find_matches_in_text(text):
            if "damn" in text.lower():
                return [MatchResult(query="damn", target="damn", score=95.0, is_match=True,
                                  normalized_query="damn", normalized_target="damn", window_text="damn")]
            return []
        
        mock_matcher.find_matches_in_text.side_effect = mock_find_matches_in_text
        
        # Test data
        workdir = Path("/tmp/test")
        input_artifact = Artifact(
            type=ArtifactType.SUBTITLE,
            path="/path/to/subtitle.srt",
            metadata={"language": "en"}
        )
        flags = OperationFlags(continue_on_qc_fail=True)  # Override to continue
        
        op = MaskSubtitlesOperation()
        
        # Mock QC to return residual matches (failure)
        qc_report = {
            "residual_matches": 2,
            "report_path": "/tmp/test/qc_report.json",
            "matches": [{"text": "damn", "confidence": 95.0}]
        }
        
        with patch.object(Path, 'write_text') as mock_write, \
             patch.object(op, '_run_quality_check', return_value=qc_report):
            
            # Should continue and return result with QC metadata
            results = op.run([input_artifact], workdir, flags)
            
            assert len(results) == 1
            result = results[0]
            assert result.type == ArtifactType.SUBTITLE
            
            # Verify QC metadata is attached (only when residual matches > 0)
            assert "qc" in result.metadata
            qc_metadata = result.metadata["qc"]
            assert qc_metadata is not None
            assert qc_metadata["residual_matches"] == 2
            assert qc_metadata["report_path"] == "/tmp/test/qc_report.json"
            # Note: the implementation doesn't add status field, just the raw QC results
    
    @patch('src.ops.mask_subtitles.SubtitleParser')
    @patch('src.ops.mask_subtitles.FuzzyMatcher')
    def test_qc_success_no_residuals(self, mock_matcher_class, mock_parser_class):
        """Test QC success path when no residual matches found."""
        # Setup mocks
        mock_parser = mock_parser_class.return_value
        mock_matcher = mock_matcher_class.return_value
        
        # Mock clean subtitle entries (after masking)
        mock_entries = [
            SubtitleEntry(index=1, start=0.0, end=2.0, text="This is **** good", normalized_text="this is **** good")
        ]
        mock_parser.parse_file.return_value = mock_entries
        mock_parser.normalize_text.side_effect = lambda text: text.lower()
        
        # Mock no profanity found in masked content
        mock_matcher.find_matches_in_text.return_value = []
        
        # Test data
        workdir = Path("/tmp/test")
        input_artifact = Artifact(
            type=ArtifactType.SUBTITLE,
            path="/path/to/subtitle.srt",
            metadata={"language": "en"}
        )
        flags = OperationFlags()
        
        op = MaskSubtitlesOperation()
        
        # Mock QC to return no residual matches (success)
        qc_report = {
            "residual_matches": 0,
            "report_path": "/tmp/test/qc_report.json",
            "matches": []
        }
        
        with patch.object(Path, 'write_text') as mock_write, \
             patch.object(op, '_run_quality_check', return_value=qc_report):
            
            # Should succeed normally
            results = op.run([input_artifact], workdir, flags)
            
            assert len(results) == 1
            result = results[0]
            assert result.type == ArtifactType.SUBTITLE
            
            # Verify QC metadata behavior (only attached when residual matches > 0)
            assert "qc" in result.metadata
            qc_metadata = result.metadata["qc"]
            # When no residual matches, qc metadata is None per implementation
            assert qc_metadata is None
    
    @patch('src.ops.mask_subtitles.SubtitleParser')
    @patch('src.ops.mask_subtitles.FuzzyMatcher')
    def test_qc_with_allowlist_handling(self, mock_matcher_class, mock_parser_class):
        """Test QC behavior with allow-list entries that should not be flagged as residuals."""
        # Setup mocks
        mock_parser = mock_parser_class.return_value
        mock_matcher = mock_matcher_class.return_value
        
        # Mock subtitle entries with allowed terms
        mock_entries = [
            SubtitleEntry(index=1, start=0.0, end=2.0, text="Hell's Kitchen is great", normalized_text="hell's kitchen is great")
        ]
        mock_parser.parse_file.return_value = mock_entries
        mock_parser.normalize_text.side_effect = lambda text: text.lower()
        
        # Mock profanity detection that finds "hell" but it's in allow-list context
        def mock_find_matches_in_text(text):
            if "hell" in text.lower() and "kitchen" not in text.lower():
                return [MatchResult(query="hell", target="hell", score=98.0, is_match=True,
                                  normalized_query="hell", normalized_target="hell", window_text="hell")]
            return []
        
        mock_matcher.find_matches_in_text.side_effect = mock_find_matches_in_text
        
        # Test data
        workdir = Path("/tmp/test")
        input_artifact = Artifact(
            type=ArtifactType.SUBTITLE,
            path="/path/to/subtitle.srt",
            metadata={"language": "en"}
        )
        flags = OperationFlags()
        
        op = MaskSubtitlesOperation()
        
        # Mock QC that properly handles allow-list (no residuals)
        qc_report = {
            "residual_matches": 0,
            "report_path": "/tmp/test/qc_report.json",
            "matches": [],
            "allowlist_filtered": 1  # "Hell's Kitchen" was filtered out
        }
        
        with patch.object(Path, 'write_text'), \
             patch.object(op, '_run_quality_check', return_value=qc_report):
            
            # Should succeed with allow-list handling
            results = op.run([input_artifact], workdir, flags)
            
            assert len(results) == 1
            result = results[0]
            
            # Verify QC metadata behavior (only attached when residual matches > 0)
            assert "qc" in result.metadata
            qc_metadata = result.metadata["qc"]
            # When no residual matches, qc metadata is None per implementation
            assert qc_metadata is None


class TestQCReportGeneration:
    """Test QC report file generation and format."""
    
    @patch('src.ops.mask_subtitles.SubtitleParser')
    @patch('src.ops.mask_subtitles.FuzzyMatcher')
    def test_qc_report_file_generation(self, mock_matcher_class, mock_parser_class):
        """Test that QC generates proper report files."""
        # Setup mocks
        mock_parser = mock_parser_class.return_value
        mock_matcher = mock_matcher_class.return_value
        
        mock_entries = [
            SubtitleEntry(index=1, start=0.0, end=2.0, text="This is damn good", normalized_text="this is damn good")
        ]
        mock_parser.parse_file.return_value = mock_entries
        mock_parser.normalize_text.side_effect = lambda text: text.lower()
        
        def mock_find_matches_in_text(text):
            if "damn" in text.lower():
                return [MatchResult(query="damn", target="damn", score=95.0, is_match=True,
                                  normalized_query="damn", normalized_target="damn", window_text="damn")]
            return []
        
        mock_matcher.find_matches_in_text.side_effect = mock_find_matches_in_text
        
        # Test data
        workdir = Path("/tmp/test")
        input_artifact = Artifact(
            type=ArtifactType.SUBTITLE,
            path="/path/to/subtitle.srt",
            metadata={"language": "en"}
        )
        flags = OperationFlags(continue_on_qc_fail=True)
        
        op = MaskSubtitlesOperation()
        
        # Mock QC report generation
        qc_report_path = workdir / "qc_report.json"
        qc_report = {
            "residual_matches": 1,
            "report_path": str(qc_report_path),
            "matches": [
                {
                    "text": "damn",
                    "confidence": 95.0,
                    "position": {"start": 8, "end": 12},
                    "context": "This is damn good"
                }
            ],
            "timestamp": "2025-01-27T10:30:00Z",
            "input_file": "/path/to/subtitle.srt"
        }
        
        with patch.object(Path, 'write_text') as mock_write, \
             patch.object(op, '_run_quality_check', return_value=qc_report), \
             patch.object(Path, 'exists', return_value=True):
            
            results = op.run([input_artifact], workdir, flags)
            
            # Verify QC report path is in metadata
            result = results[0]
            qc_metadata = result.metadata["qc"]
            assert qc_metadata["report_path"] == str(qc_report_path)
            
            # The actual report file writing would be tested in the QC implementation
            # Here we just verify the path is correctly passed through