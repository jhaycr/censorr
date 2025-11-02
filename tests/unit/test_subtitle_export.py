"""Unit tests for subtitle_export operation."""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import json

from src.models.artifacts import Artifact, ArtifactType
from src.models.operations import OperationFlags
from src.ops.subtitle_export import SubtitleExportOperation, SubtitleFormat
from src.utils.subtitle_parser import SubtitleEntry, SubtitleError


class TestSubtitleExportOperation:
    """Test cases for SubtitleExportOperation."""
    
    def test_operation_creation(self):
        """Test operation can be created with correct properties."""
        op = SubtitleExportOperation()
        
        assert op.name == "subtitle_export"
        assert op.description == "Export subtitles and metadata to external files"
        assert ArtifactType.SUBTITLE in op.consumes
        assert ArtifactType.VIDEO in op.consumes
        assert ArtifactType.SIDECAR in op.produces
        assert hasattr(op, 'parser')
    
    def test_operation_creation_with_format(self):
        """Test operation creation with specific format."""
        op = SubtitleExportOperation(format=SubtitleFormat.JSON)
        
        assert op.format == SubtitleFormat.JSON
        
        op = SubtitleExportOperation(format=SubtitleFormat.XML)
        assert op.format == SubtitleFormat.XML
    
    @patch('src.ops.subtitle_export.SubtitleParser')
    def test_run_with_subtitle_artifacts_srt_format(self, mock_parser_class):
        """Test operation exports subtitle in SRT format."""
        # Setup mocks
        mock_parser = mock_parser_class.return_value
        mock_entries = [
            SubtitleEntry(index=1, start=0.0, end=2.0, text="Hello world", normalized_text="hello world"),
            SubtitleEntry(index=2, start=2.5, end=4.0, text="This is great", normalized_text="this is great")
        ]
        mock_parser.parse_file.return_value = mock_entries
        
        # Test data
        workdir = Path("/tmp/test")
        subtitle_artifact = Artifact(
            type=ArtifactType.SUBTITLE,
            path="/path/to/subtitle.srt",
            metadata={"language": "en", "track": "0"}
        )
        flags = OperationFlags()
        
        # Execute operation
        op = SubtitleExportOperation(format=SubtitleFormat.SRT)
        with patch.object(Path, 'write_text') as mock_write:
            results = op.run([subtitle_artifact], workdir, flags)
        
        # Verify results
        assert len(results) == 1
        result = results[0]
        assert result.type == ArtifactType.SIDECAR
        assert result.path == str(workdir / "sidecar.srt")
        assert result.metadata["format"] == "srt"
        assert result.metadata["source_artifacts"] == [subtitle_artifact.path]
        
        # Verify SRT content was written
        mock_write.assert_called_once()
        written_content = mock_write.call_args[0][0]
        assert "Hello world" in written_content
        assert "00:00:00,000 --> 00:00:02,000" in written_content
    
    @patch('src.ops.subtitle_export.SubtitleParser')
    def test_run_with_subtitle_artifacts_json_format(self, mock_parser_class):
        """Test operation exports subtitle in JSON format."""
        # Setup mocks
        mock_parser = mock_parser_class.return_value
        mock_entries = [
            SubtitleEntry(index=1, start=0.0, end=2.0, text="Hello world", normalized_text="hello world")
        ]
        mock_parser.parse_file.return_value = mock_entries
        
        # Test data
        workdir = Path("/tmp/test")
        subtitle_artifact = Artifact(
            type=ArtifactType.SUBTITLE,
            path="/path/to/subtitle.srt",
            metadata={"language": "en", "track": "0"}
        )
        flags = OperationFlags()
        
        # Execute operation
        op = SubtitleExportOperation(format=SubtitleFormat.JSON)
        with patch.object(Path, 'write_text') as mock_write:
            results = op.run([subtitle_artifact], workdir, flags)
        
        # Verify results
        assert len(results) == 1
        result = results[0]
        assert result.type == ArtifactType.SIDECAR
        assert result.path == str(workdir / "sidecar.json")
        assert result.metadata["format"] == "json"
        
        # Verify JSON content was written
        mock_write.assert_called_once()
        written_content = mock_write.call_args[0][0]
        data = json.loads(written_content)
        assert "subtitles" in data
        assert len(data["subtitles"]) == 1
        assert data["subtitles"][0]["text"] == "Hello world"
    
    @patch('src.ops.subtitle_export.SubtitleParser')
    def test_run_with_multiple_subtitle_artifacts(self, mock_parser_class):
        """Test operation with multiple subtitle artifacts."""
        # Setup mocks
        mock_parser = mock_parser_class.return_value
        
        def mock_parse_file(path):
            if "sub1" in path:
                return [SubtitleEntry(index=1, start=0.0, end=2.0, text="First sub", normalized_text="first sub")]
            else:
                return [SubtitleEntry(index=1, start=3.0, end=5.0, text="Second sub", normalized_text="second sub")]
        
        mock_parser.parse_file.side_effect = mock_parse_file
        
        # Test data
        workdir = Path("/tmp/test")
        subtitle1 = Artifact(
            type=ArtifactType.SUBTITLE,
            path="/path/to/sub1.srt",
            metadata={"language": "en", "track": "0"}
        )
        subtitle2 = Artifact(
            type=ArtifactType.SUBTITLE,
            path="/path/to/sub2.srt",
            metadata={"language": "en", "track": "1"}
        )
        flags = OperationFlags()
        
        # Execute operation
        op = SubtitleExportOperation(format=SubtitleFormat.JSON)
        with patch.object(Path, 'write_text') as mock_write:
            results = op.run([subtitle1, subtitle2], workdir, flags)
        
        # Verify results
        assert len(results) == 1
        result = results[0]
        assert len(result.metadata["source_artifacts"]) == 2
        
        # Verify content includes both subtitles
        written_content = mock_write.call_args[0][0]
        data = json.loads(written_content)
        assert len(data["subtitles"]) == 2
    
    def test_run_with_video_artifact_metadata(self):
        """Test operation exports video metadata."""
        # Test data
        workdir = Path("/tmp/test")
        video_artifact = Artifact(
            type=ArtifactType.VIDEO,
            path="/path/to/video.mp4",
            metadata={
                "duration": 120.5,
                "resolution": "1920x1080",
                "codec": "h264",
                "bitrate": "5000k"
            }
        )
        flags = OperationFlags()
        
        # Execute operation
        op = SubtitleExportOperation(format=SubtitleFormat.JSON)
        with patch.object(Path, 'write_text') as mock_write:
            results = op.run([video_artifact], workdir, flags)
        
        # Verify results
        assert len(results) == 1
        result = results[0]
        assert result.metadata["format"] == "json"
        
        # Verify metadata was exported
        written_content = mock_write.call_args[0][0]
        data = json.loads(written_content)
        assert "video" in data
        assert data["video"]["duration"] == 120.5
        assert data["video"]["resolution"] == "1920x1080"
    
    def test_run_dry_run(self):
        """Test operation in dry-run mode."""
        # Test data
        workdir = Path("/tmp/test")
        subtitle_artifact = Artifact(
            type=ArtifactType.SUBTITLE,
            path="/path/to/subtitle.srt",
            metadata={"language": "en"}
        )
        flags = OperationFlags(dry_run=True)
        
        # Execute operation
        op = SubtitleExportOperation(format=SubtitleFormat.SRT)
        results = op.run([subtitle_artifact], workdir, flags)
        
        # Verify results
        assert len(results) == 1
        result = results[0]
        assert result.type == ArtifactType.SIDECAR
        assert result.path == str(workdir / "sidecar.srt")
        assert result.metadata["planned"] is True
    
    def test_run_no_artifacts(self):
        """Test operation with no valid artifacts."""
        op = SubtitleExportOperation()
        workdir = Path("/tmp/test")
        flags = OperationFlags()
        
        # Test with audio artifact (not supported)
        audio_artifact = Artifact(
            type=ArtifactType.AUDIO,
            path="/path/to/audio.mp3",
            metadata={}
        )
        
        with pytest.raises(ValueError, match="No subtitle or video artifacts found"):
            op.run([audio_artifact], workdir, flags)
    
    @patch('src.ops.subtitle_export.SubtitleParser')
    def test_run_with_parser_error(self, mock_parser_class):
        """Test operation with subtitle parser error."""
        # Setup mock to raise error
        mock_parser = mock_parser_class.return_value
        mock_parser.parse_file.side_effect = SubtitleError("Invalid format")
        
        # Test data
        workdir = Path("/tmp/test")
        subtitle_artifact = Artifact(
            type=ArtifactType.SUBTITLE,
            path="/path/to/subtitle.srt",
            metadata={"language": "en"}
        )
        flags = OperationFlags()
        
        # Execute operation
        op = SubtitleExportOperation()
        with pytest.raises(RuntimeError, match="Failed to parse subtitle file"):
            op.run([subtitle_artifact], workdir, flags)
    
    @patch('src.ops.subtitle_export.SubtitleParser')
    def test_export_srt_format(self, mock_parser_class):
        """Test SRT format export."""
        mock_parser = mock_parser_class.return_value
        
        op = SubtitleExportOperation()
        entries = [
            SubtitleEntry(index=1, start=0.0, end=2.5, text="Hello world", normalized_text="hello world"),
            SubtitleEntry(index=2, start=3.0, end=5.5, text="This is great", normalized_text="this is great")
        ]
        
        content = op._export_srt_format(entries)
        
        # Verify SRT format
        lines = content.split('\n')
        assert '1' in lines
        assert '00:00:00,000 --> 00:00:02,500' in lines
        assert 'Hello world' in lines
        assert '2' in lines
        assert '00:00:03,000 --> 00:00:05,500' in lines
        assert 'This is great' in lines
    
    def test_export_json_format(self):
        """Test JSON format export."""
        op = SubtitleExportOperation()
        
        subtitle_entries = [
            SubtitleEntry(index=1, start=0.0, end=2.0, text="Hello", normalized_text="hello")
        ]
        video_metadata = {"duration": 120.0, "resolution": "1920x1080"}
        source_artifacts = ["/path/to/sub.srt"]
        
        content = op._export_json_format(subtitle_entries, video_metadata, source_artifacts)
        data = json.loads(content)
        
        # Verify JSON structure
        assert "metadata" in data
        assert "subtitles" in data
        assert "video" in data
        assert data["metadata"]["format"] == "json"
        assert data["metadata"]["source_artifacts"] == source_artifacts
        assert len(data["subtitles"]) == 1
        assert data["subtitles"][0]["text"] == "Hello"
        assert data["video"]["duration"] == 120.0
    
    def test_export_xml_format(self):
        """Test XML format export."""
        op = SubtitleExportOperation()
        
        subtitle_entries = [
            SubtitleEntry(index=1, start=0.0, end=2.0, text="Hello", normalized_text="hello")
        ]
        video_metadata = {"duration": 120.0}
        source_artifacts = ["/path/to/sub.srt"]
        
        content = op._export_xml_format(subtitle_entries, video_metadata, source_artifacts)
        
        # Verify XML structure
        assert "<?xml version=" in content
        assert "<sidecar>" in content
        assert "<subtitles>" in content
        assert "<subtitle" in content
        assert "<text>Hello</text>" in content
        assert "<video>" in content
        assert "<duration>120.0</duration>" in content
    
    def test_format_srt_timestamp(self):
        """Test SRT timestamp formatting."""
        op = SubtitleExportOperation()
        
        # Test various timestamps
        assert op._format_srt_timestamp(0.0) == "00:00:00,000"
        assert op._format_srt_timestamp(2.5) == "00:00:02,500"
        assert op._format_srt_timestamp(65.123) == "00:01:05,123"
        assert op._format_srt_timestamp(3661.456) == "01:01:01,456"
    
    def test_validate_inputs(self):
        """Test input validation."""
        op = SubtitleExportOperation()
        
        # Valid inputs
        subtitle_artifact = Artifact(
            type=ArtifactType.SUBTITLE,
            path="/path/to/subtitle.srt",
            metadata={"language": "en"}
        )
        video_artifact = Artifact(
            type=ArtifactType.VIDEO,
            path="/path/to/video.mp4",
            metadata={}
        )
        
        # Should not raise
        workdir = Path("/tmp/test")
        flags = OperationFlags(dry_run=True)
        results = op.run([subtitle_artifact, video_artifact], workdir, flags)
        assert len(results) == 1
    
    @patch('src.ops.subtitle_export.SubtitleParser')
    def test_verbose_mode(self, mock_parser_class):
        """Test operation in verbose mode."""
        # Setup mocks
        mock_parser = mock_parser_class.return_value
        mock_entries = [
            SubtitleEntry(index=1, start=0.0, end=2.0, text="Hello", normalized_text="hello")
        ]
        mock_parser.parse_file.return_value = mock_entries
        
        # Test data
        workdir = Path("/tmp/test")
        subtitle_artifact = Artifact(
            type=ArtifactType.SUBTITLE,
            path="/path/to/subtitle.srt",
            metadata={"language": "en"}
        )
        flags = OperationFlags(verbose=True)
        
        # Execute operation
        op = SubtitleExportOperation(format=SubtitleFormat.JSON)
        with patch.object(Path, 'write_text'), patch('builtins.print') as mock_print:
            results = op.run([subtitle_artifact], workdir, flags)
        
        # Verify verbose output was printed
        assert mock_print.called
        print_calls = [call[0][0] for call in mock_print.call_args_list]
        assert any("subtitle entries" in call for call in print_calls)
        assert any("format" in call for call in print_calls)