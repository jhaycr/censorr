"""Tests for subtitle quality check operation."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.models.artifacts import Artifact, ArtifactType
from src.models.operations import OperationFlags
from src.ops.subtitle_qc import SubtitleQualityCheckOperation


class TestSubtitleQualityCheckOperation:
    """Test cases for SubtitleQualityCheckOperation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.operation = SubtitleQualityCheckOperation()
    
    def test_operation_name(self):
        """Test that operation has correct name."""
        assert self.operation.name == "subtitle_qc"
    
    def test_artifact_types(self):
        """Test that operation consumes and produces correct artifact types."""
        assert ArtifactType.SUBTITLE in self.operation.consumes
        assert ArtifactType.SUBTITLE in self.operation.produces
    
    @patch('src.ops.subtitle_qc.SubtitleParser')
    def test_qc_with_no_profanity(self, mock_parser_class):
        """Test QC operation with clean subtitles."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workdir = Path(tmpdir)
            
            # Create test subtitle file
            subtitle_file = workdir / "test.srt"
            subtitle_file.write_text("1\n00:00:01,000 --> 00:00:02,000\nClean content\n\n")
            
            # Mock parser
            mock_parser = mock_parser_class.return_value
            mock_parser.parse.return_value = [
                type('Entry', (), {'start_time': '00:00:01,000', 'end_time': '00:00:02,000', 'text': 'Clean content'})()
            ]
            
            # Create input artifact
            input_artifact = Artifact(
                type=ArtifactType.SUBTITLE,
                path=str(subtitle_file),
                metadata={}
            )
            
            # Create operation flags
            flags = OperationFlags(verbose=True)
            
            # Run operation
            results = self.operation.run([input_artifact], workdir, flags)
            
            # Verify results
            assert len(results) == 1
            result = results[0]
            assert result.type == ArtifactType.SUBTITLE
            assert "subtitle_qc" in result.metadata
            
            qc_data = result.metadata["subtitle_qc"]
            assert qc_data["operation"] == "subtitle_qc"
            assert qc_data["status"] == "SKIPPED"  # No profanity list provided
            assert qc_data["residual_terms"] == 0 or qc_data["residual_terms"] == []
    
    @patch('src.ops.subtitle_qc.SubtitleParser')
    @patch('src.ops.subtitle_qc.FuzzyMatcher')
    def test_qc_with_residual_profanity(self, mock_matcher_class, mock_parser_class):
        """Test QC operation finding residual profanity."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workdir = Path(tmpdir)
            
            # Create test subtitle file
            subtitle_file = workdir / "test.srt"
            subtitle_file.write_text("1\n00:00:01,000 --> 00:00:02,000\nBad word here\n\n")
            
            # Create profanity list file
            profanity_file = workdir / "profanity.json"
            profanity_file.write_text('["badword"]')
            
            # Mock parser
            mock_parser = mock_parser_class.return_value
            mock_parser.parse.return_value = [
                type('Entry', (), {'start_time': '00:00:01,000', 'end_time': '00:00:02,000', 'text': 'Bad word here'})()
            ]
            
            # Mock matcher
            mock_matcher = mock_matcher_class.return_value
            mock_matcher.find_matches.return_value = [
                {"term": "badword", "match": "Bad", "score": 90}
            ]
            
            # Create input artifact
            input_artifact = Artifact(
                type=ArtifactType.SUBTITLE,
                path=str(subtitle_file),
                metadata={}
            )
            
            # Create operation flags with profanity list
            flags = OperationFlags(verbose=True, profanity_list_file=str(profanity_file))
            
            # Run operation
            results = self.operation.run([input_artifact], workdir, flags)
            
            # Verify results
            assert len(results) == 1
            result = results[0]
            assert result.type == ArtifactType.SUBTITLE
            assert "subtitle_qc" in result.metadata
            
            qc_data = result.metadata["subtitle_qc"]
            assert qc_data["operation"] == "subtitle_qc"
            assert qc_data["status"] == "FAIL"
            assert qc_data["residual_terms"] == 1
            assert len(qc_data["matches"]) == 1
            assert qc_data["matches"][0]["matched_term"] == "badword"
    
    def test_no_input_artifacts(self):
        """Test operation with no input artifacts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workdir = Path(tmpdir)
            flags = OperationFlags()
            
            with pytest.raises(ValueError, match="No subtitle artifacts provided"):
                self.operation.run([], workdir, flags)
    
    def test_no_subtitle_artifact(self):
        """Test operation with wrong artifact type."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workdir = Path(tmpdir)
            flags = OperationFlags()
            
            # Create wrong artifact type
            input_artifact = Artifact(
                type=ArtifactType.AUDIO,
                path="/fake/path",
                metadata={}
            )
            
            with pytest.raises(ValueError, match="No subtitle artifact found"):
                self.operation.run([input_artifact], workdir, flags)