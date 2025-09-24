"""Unit tests for mask_subtitles operation."""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from src.models.artifacts import Artifact, ArtifactType
from src.models.operations import OperationFlags
from src.ops.mask_subtitles import MaskSubtitlesOperation
from src.utils.subtitle_parser import SubtitleEntry, SubtitleError
from src.utils.fuzzy_matcher import MatchResult


class TestMaskSubtitlesOperation:
    """Test cases for MaskSubtitlesOperation."""
    
    def test_operation_creation(self):
        """Test operation can be created with correct properties."""
        op = MaskSubtitlesOperation()
        
        assert op.name == "mask_subtitles"
        assert op.description == "Apply profanity filtering to subtitle content using fuzzy matching"
        assert ArtifactType.SUBTITLE in op.consumes
        assert ArtifactType.SUBTITLE in op.produces
        assert hasattr(op, 'parser')
        assert hasattr(op, 'matcher')
    
    @patch('src.ops.mask_subtitles.SubtitleParser')
    @patch('src.ops.mask_subtitles.FuzzyMatcher')
    def test_run_with_profanity_filtering(self, mock_matcher_class, mock_parser_class):
        """Test operation filters profanity from subtitle content."""
        # Setup mocks
        mock_parser = mock_parser_class.return_value
        mock_matcher = mock_matcher_class.return_value
        
        # Mock normalize_text to return lowercase
        mock_parser.normalize_text.side_effect = lambda text: text.lower()
        
        # Mock subtitle entries with profanity
        mock_entries = [
            SubtitleEntry(index=1, start=0.0, end=2.0, text="Hello world", normalized_text="hello world"),
            SubtitleEntry(index=2, start=2.5, end=4.0, text="This is damn good", normalized_text="this is damn good"),
            SubtitleEntry(index=3, start=5.0, end=7.0, text="What the hell", normalized_text="what the hell")
        ]
        mock_parser.parse_file.return_value = mock_entries
        
        # Mock profanity detection using the correct method
        def mock_find_matches_in_text(text):
            matches = []
            if "damn" in text.lower():
                matches.append(MatchResult(query="damn", target="damn", score=95.0, is_match=True, normalized_query="damn", normalized_target="damn", window_text="damn"))
            if "hell" in text.lower():
                matches.append(MatchResult(query="hell", target="hell", score=98.0, is_match=True, normalized_query="hell", normalized_target="hell", window_text="hell"))
            return matches
        
        mock_matcher.find_matches_in_text.side_effect = mock_find_matches_in_text
        
        # Test data
        workdir = Path("/tmp/test")
        input_artifact = Artifact(
            type=ArtifactType.SUBTITLE,
            path="/path/to/subtitle.srt",
            metadata={"language": "en"}
        )
        flags = OperationFlags()
        
        # Execute operation
        op = MaskSubtitlesOperation()
        # Mock quality check to pass
        with patch.object(Path, 'write_text') as mock_write, \
             patch.object(op, '_run_quality_check') as mock_qc:
            mock_qc.return_value = {"residual_matches": 0, "report_path": "/tmp/test/qc_report.json"}
            results = op.run([input_artifact], workdir, flags)
        
        # Verify results
        assert len(results) == 1
        result = results[0]
        assert result.type == ArtifactType.SUBTITLE
        assert result.path == str(workdir / "masked_subtitles.srt")
        assert result.metadata["language"] == "en"
        assert result.metadata["profanity_filtered"] is True
        assert "original_file" in result.metadata
        
        # Verify parser was called
        mock_parser.parse_file.assert_called_once_with("/path/to/subtitle.srt")
        
        # Verify output was written
        mock_write.assert_called_once()
        written_content = mock_write.call_args[0][0]
        assert "*" in written_content  # Profanity should be masked
    
    @patch('src.ops.mask_subtitles.SubtitleParser')
    @patch('src.ops.mask_subtitles.FuzzyMatcher')
    def test_run_no_profanity_found(self, mock_matcher_class, mock_parser_class):
        """Test operation with clean subtitle content."""
        # Setup mocks
        mock_parser = mock_parser_class.return_value
        mock_matcher = mock_matcher_class.return_value
        
        # Mock clean subtitle entries
        mock_entries = [
            SubtitleEntry(index=1, start=0.0, end=2.0, text="Hello world", normalized_text="hello world"),
            SubtitleEntry(index=2, start=2.5, end=4.0, text="This is great", normalized_text="this is great")
        ]
        mock_parser.parse_file.return_value = mock_entries
        mock_parser.normalize_text.side_effect = lambda text: text.lower()
        mock_matcher.contains_profanity.return_value = False
        mock_matcher.extract_profanity_matches.return_value = []
        
        # Test data
        workdir = Path("/tmp/test")
        input_artifact = Artifact(
            type=ArtifactType.SUBTITLE,
            path="/path/to/subtitle.srt",
            metadata={"language": "en"}
        )
        flags = OperationFlags()
        
        # Execute operation
        op = MaskSubtitlesOperation()
        # Mock quality check to pass
        with patch.object(Path, 'write_text') as mock_write, \
             patch.object(op, '_run_quality_check') as mock_qc:
            mock_qc.return_value = {"residual_matches": 0, "report_path": "/tmp/test/qc_report.json"}
            results = op.run([input_artifact], workdir, flags)
        
        # Verify results
        assert len(results) == 1
        result = results[0]
        assert result.metadata["profanity_filtered"] is False
        assert result.metadata["matches_found"] == 0
        
        # Verify content was written (subtitle file only, QC is mocked)
        assert mock_write.call_count >= 1
        # Check the first call which should be the subtitle file
        written_content = mock_write.call_args_list[0][0][0]
        assert "Hello world" in written_content
        assert "This is great" in written_content
    
    def test_run_no_subtitle_artifacts(self):
        """Test operation with no subtitle artifacts."""
        op = MaskSubtitlesOperation()
        workdir = Path("/tmp/test")
        flags = OperationFlags()
        
        # Test with non-subtitle artifact
        video_artifact = Artifact(
            type=ArtifactType.VIDEO,
            path="/path/to/video.mp4",
            metadata={}
        )
        
        with pytest.raises(ValueError, match="No subtitle artifacts found"):
            op.run([video_artifact], workdir, flags)
    
    @patch('src.ops.mask_subtitles.SubtitleParser')
    def test_run_dry_run(self, mock_parser_class):
        """Test operation in dry-run mode."""
        # Test data
        workdir = Path("/tmp/test")
        input_artifact = Artifact(
            type=ArtifactType.SUBTITLE,
            path="/path/to/subtitle.srt",
            metadata={"language": "en"}
        )
        flags = OperationFlags(dry_run=True)
        
        # Execute operation
        op = MaskSubtitlesOperation()
        results = op.run([input_artifact], workdir, flags)
        
        # Verify results
        assert len(results) == 1
        result = results[0]
        assert result.type == ArtifactType.SUBTITLE
        assert result.path == str(workdir / "masked_subtitles.srt")
        assert result.metadata["planned"] is True
        assert "original_file" in result.metadata
        
        # Verify parser was not called in dry run
        mock_parser_class.return_value.parse_file.assert_not_called()
    
    @patch('src.ops.mask_subtitles.SubtitleParser')
    def test_run_with_parser_error(self, mock_parser_class):
        """Test operation with subtitle parser error."""
        # Setup mock to raise error
        mock_parser = mock_parser_class.return_value
        mock_parser.parse_file.side_effect = SubtitleError("Invalid format")
        
        # Test data
        workdir = Path("/tmp/test")
        input_artifact = Artifact(
            type=ArtifactType.SUBTITLE,
            path="/path/to/subtitle.srt",
            metadata={"language": "en"}
        )
        flags = OperationFlags()
        
        # Execute operation
        op = MaskSubtitlesOperation()
        with pytest.raises(RuntimeError, match="Failed to parse subtitle file"):
            op.run([input_artifact], workdir, flags)
    
    @patch('src.ops.mask_subtitles.SubtitleParser')
    @patch('src.ops.mask_subtitles.FuzzyMatcher')
    def test_mask_text_profanity(self, mock_matcher_class, mock_parser_class):
        """Test _mask_text_profanity method."""
        mock_matcher = mock_matcher_class.return_value
        
        # Mock matches for individual words
        def mock_match_against_allow_list(word):
            if word.lower() == "damn":
                return [MatchResult(query="damn", target="damn", score=95.0, is_match=True, normalized_query="damn", normalized_target="damn", window_text="damn")]
            elif word.lower() == "hell":
                return [MatchResult(query="hell", target="hell", score=98.0, is_match=True, normalized_query="hell", normalized_target="hell", window_text="hell")]
            else:
                return []
        
        mock_matcher.match_against_allow_list.side_effect = mock_match_against_allow_list
        mock_matcher.allow_list = ["damn", "hell"]
        
        op = MaskSubtitlesOperation()
        
        # Test with profanity
        original_text = "This is damn good"
        # Create matches list manually
        matches = [MatchResult(query="damn", target="damn", score=95.0, is_match=True, normalized_query="damn", normalized_target="damn", window_text="damn")]
        masked_text = op._mask_text_profanity(original_text, matches)
        
        # Verify profanity is masked
        assert "****" in masked_text
        assert "damn" not in masked_text
    
    @patch('src.ops.mask_subtitles.SubtitleParser')
    @patch('src.ops.mask_subtitles.FuzzyMatcher')
    def test_mask_text_no_profanity(self, mock_matcher_class, mock_parser_class):
        """Test _mask_text_profanity with clean text."""
        mock_matcher = mock_matcher_class.return_value
        mock_matcher.match_against_allow_list.return_value = []
        mock_matcher.allow_list = ["damn", "hell"]
        
        op = MaskSubtitlesOperation()
        
        # Test with clean text
        original_text = "This is clean text"
        # Empty matches list for clean text
        matches = []
        masked_text = op._mask_text_profanity(original_text, matches)
        
        # Verify text is unchanged
        assert masked_text == original_text
    
    @patch('src.ops.mask_subtitles.SubtitleParser')
    @patch('src.ops.mask_subtitles.FuzzyMatcher')
    def test_generate_srt_content(self, mock_matcher_class, mock_parser_class):
        """Test SRT content generation."""
        op = MaskSubtitlesOperation()
        
        entries = [
            SubtitleEntry(index=1, start=0.0, end=2.5, text="Hello world", normalized_text="hello world"),
            SubtitleEntry(index=2, start=3.0, end=5.5, text="This is great", normalized_text="this is great")
        ]
        
        content = op._generate_srt_content(entries)
        
        # Verify SRT format
        lines = content.split('\n')
        assert '1' in lines
        assert '00:00:00,000 --> 00:00:02,500' in lines
        assert 'Hello world' in lines
        assert '2' in lines
        assert '00:00:03,000 --> 00:00:05,500' in lines
        assert 'This is great' in lines
    
    @patch('src.ops.mask_subtitles.SubtitleParser')
    @patch('src.ops.mask_subtitles.FuzzyMatcher')
    def test_format_srt_timestamp(self, mock_matcher_class, mock_parser_class):
        """Test SRT timestamp formatting."""
        op = MaskSubtitlesOperation()
        
        # Test various timestamps
        assert op._format_srt_timestamp(0.0) == "00:00:00,000"
        assert op._format_srt_timestamp(2.5) == "00:00:02,500"
        assert op._format_srt_timestamp(65.123) == "00:01:05,123"
        assert op._format_srt_timestamp(3661.456) == "01:01:01,456"
    
    def test_validate_inputs(self):
        """Test input validation."""
        op = MaskSubtitlesOperation()
        
        # Valid input
        sub_artifact = Artifact(
            type=ArtifactType.SUBTITLE,
            path="/path/to/subtitle.srt",
            metadata={"language": "en"}
        )
        
        # Should not raise
        workdir = Path("/tmp/test")
        flags = OperationFlags(dry_run=True)
        results = op.run([sub_artifact], workdir, flags)
        assert len(results) == 1
    
    @patch('src.ops.mask_subtitles.SubtitleParser')
    @patch('src.ops.mask_subtitles.FuzzyMatcher')
    def test_verbose_mode(self, mock_matcher_class, mock_parser_class):
        """Test operation in verbose mode."""
        # Setup mocks
        mock_parser = mock_parser_class.return_value
        mock_matcher = mock_matcher_class.return_value
        
        # Mock normalize_text to return lowercase
        mock_parser.normalize_text.side_effect = lambda text: text.lower()
        
        mock_entries = [
            SubtitleEntry(index=1, start=0.0, end=2.0, text="Hello damn world", normalized_text="hello damn world")
        ]
        mock_parser.parse_file.return_value = mock_entries
        
        # Mock profanity detection using the correct method
        def mock_find_matches_in_text(text):
            matches = []
            if "damn" in text.lower():
                matches.append(MatchResult(query="damn", target="damn", score=95.0, is_match=True, normalized_query="damn", normalized_target="damn", window_text="damn"))
            return matches
        
        mock_matcher.find_matches_in_text.side_effect = mock_find_matches_in_text
        
        # Test data
        workdir = Path("/tmp/test")
        input_artifact = Artifact(
            type=ArtifactType.SUBTITLE,
            path="/path/to/subtitle.srt",
            metadata={"language": "en"}
        )
        flags = OperationFlags(verbose=True)
        
        # Execute operation
        op = MaskSubtitlesOperation()
        # Mock quality check to pass
        with patch.object(Path, 'write_text'), \
             patch('builtins.print') as mock_print, \
             patch.object(op, '_run_quality_check') as mock_qc:
            mock_qc.return_value = {"residual_matches": 0, "report_path": "/tmp/test/qc_report.json"}
            results = op.run([input_artifact], workdir, flags)
        
        # Verify verbose output was printed
        assert mock_print.called
        print_calls = [call[0][0] for call in mock_print.call_args_list]
        # Check for any of the expected verbose messages
        assert any("mask_subtitles" in call for call in print_calls)