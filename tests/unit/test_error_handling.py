"""Tests for enhanced error handling framework."""
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock

import pytest

from src.error_handling import ExternalToolRunner, ExternalToolResult


class TestExternalToolResult:
    """Test ExternalToolResult dataclass."""
    
    def test_successful_result(self):
        """Test successful result creation."""
        result = ExternalToolResult(
            success=True,
            result="output",
            duration_ms=100.5
        )
        
        assert result.success is True
        assert result.result == "output"
        assert result.error is None
        assert result.duration_ms == 100.5
        assert result.preserved_artifacts == []
        assert result.logs == []
    
    def test_failed_result(self):
        """Test failed result creation."""
        result = ExternalToolResult(
            success=False,
            error="Command failed",
            preserved_artifacts=["file1.tmp", "file2.tmp"]
        )
        
        assert result.success is False
        assert result.result is None
        assert result.error == "Command failed"
        assert result.preserved_artifacts == ["file1.tmp", "file2.tmp"]


class TestExternalToolRunner:
    """Test ExternalToolRunner class."""
    
    def test_init_without_logger(self):
        """Test initialization without logger."""
        runner = ExternalToolRunner()
        assert runner.execution_logger is None
        assert runner.log_entry is None
        assert runner.preserved_artifacts == []
    
    def test_init_with_logger(self):
        """Test initialization with logger."""
        logger = Mock()
        log_entry = Mock()
        
        runner = ExternalToolRunner(logger, log_entry)
        assert runner.execution_logger is logger
        assert runner.log_entry is log_entry
    
    def test_successful_function_execution(self):
        """Test successful function execution."""
        runner = ExternalToolRunner()
        
        def test_func(x, y):
            return x + y
        
        result = runner.run_with_error_handling(test_func, 2, 3)
        
        assert result.success is True
        assert result.result == 5
        assert result.error is None
        assert result.duration_ms is not None
        assert result.duration_ms > 0
    
    def test_failed_function_execution(self):
        """Test failed function execution."""
        runner = ExternalToolRunner()
        
        def test_func():
            raise ValueError("Test error")
        
        result = runner.run_with_error_handling(test_func)
        
        assert result.success is False
        assert result.result is None
        assert result.error == "Test error"
        assert result.duration_ms is not None
        assert result.duration_ms > 0
    
    def test_execution_with_logging(self):
        """Test execution with logging."""
        logger = Mock()
        log_entry = Mock()
        runner = ExternalToolRunner(logger, log_entry)
        
        def test_func():
            return "success"
        
        result = runner.run_with_error_handling(
            test_func,
            operation_name="test_operation"
        )
        
        assert result.success is True
        assert result.result == "success"
        
        # Verify logging calls
        assert logger.add_operation_log.call_count == 2
        logger.add_operation_log.assert_any_call(
            log_entry, "Starting test_operation"
        )
    
    def test_artifact_preservation(self):
        """Test artifact preservation on error."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workdir = Path(temp_dir)
            
            # Create test artifacts
            test_file1 = workdir / "test1.txt"
            test_file2 = workdir / "test2.log"
            test_file1.write_text("content1")
            test_file2.write_text("content2")
            
            runner = ExternalToolRunner()
            
            def failing_func():
                raise RuntimeError("Operation failed")
            
            result = runner.run_with_error_handling(
                failing_func,
                preserve_artifacts_on_error=True,
                artifact_patterns=["*.txt", "*.log"],
                workdir=workdir
            )
            
            assert result.success is False
            assert result.error == "Operation failed"
            assert len(result.preserved_artifacts) == 2
            
            # Check that artifacts were preserved
            preserve_dir = workdir / "preserved_artifacts"
            assert preserve_dir.exists()
            assert (preserve_dir / "test1.txt").exists()
            assert (preserve_dir / "test2.log").exists()
    
    def test_artifact_preservation_specific_patterns(self):
        """Test artifact preservation with specific patterns."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workdir = Path(temp_dir)
            
            # Create test artifacts
            test_file1 = workdir / "audio.wav"
            test_file2 = workdir / "video.mp4"
            test_file3 = workdir / "subtitle.srt"
            test_file1.write_text("audio content")
            test_file2.write_text("video content")
            test_file3.write_text("subtitle content")
            
            runner = ExternalToolRunner()
            
            def failing_func():
                raise RuntimeError("Operation failed")
            
            result = runner.run_with_error_handling(
                failing_func,
                preserve_artifacts_on_error=True,
                artifact_patterns=["*.wav", "*.srt"],
                workdir=workdir
            )
            
            assert result.success is False
            assert len(result.preserved_artifacts) == 2
            
            # Check that only matching artifacts were preserved
            preserve_dir = workdir / "preserved_artifacts"
            assert (preserve_dir / "audio.wav").exists()
            assert (preserve_dir / "subtitle.srt").exists()
            assert not (preserve_dir / "video.mp4").exists()
    
    def test_no_artifact_preservation_when_disabled(self):
        """Test that artifacts are not preserved when disabled."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workdir = Path(temp_dir)
            
            # Create test artifact
            test_file = workdir / "test.txt"
            test_file.write_text("content")
            
            runner = ExternalToolRunner()
            
            def failing_func():
                raise RuntimeError("Operation failed")
            
            result = runner.run_with_error_handling(
                failing_func,
                preserve_artifacts_on_error=False,
                workdir=workdir
            )
            
            assert result.success is False
            assert result.preserved_artifacts == []
            
            # Check that no preservation directory was created
            preserve_dir = workdir / "preserved_artifacts"
            assert not preserve_dir.exists()
    
    def test_ffmpeg_adapter_integration(self):
        """Test integration with FFmpeg adapter."""
        logger = Mock()
        log_entry = Mock()
        runner = ExternalToolRunner(logger, log_entry)
        
        # Mock FFmpeg adapter
        ffmpeg_adapter = Mock()
        ffmpeg_adapter.set_execution_logger = Mock()
        ffmpeg_adapter.probe = Mock(return_value="probe_result")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            workdir = Path(temp_dir)
            
            result = runner.run_ffmpeg_with_recovery(
                ffmpeg_adapter, 'probe', workdir, "input.mp4"
            )
            
            assert result.success is True
            assert result.result == "probe_result"
            
            # Verify adapter setup
            ffmpeg_adapter.set_execution_logger.assert_called_once_with(logger, log_entry)
            ffmpeg_adapter.probe.assert_called_once_with("input.mp4")
    
    def test_ffmpeg_adapter_error_handling(self):
        """Test FFmpeg adapter error handling."""
        runner = ExternalToolRunner()
        
        # Mock FFmpeg adapter that raises error
        ffmpeg_adapter = Mock()
        ffmpeg_adapter.set_execution_logger = Mock()
        ffmpeg_adapter.extract_audio = Mock(side_effect=RuntimeError("FFmpeg failed"))
        
        with tempfile.TemporaryDirectory() as temp_dir:
            workdir = Path(temp_dir)
            
            result = runner.run_ffmpeg_with_recovery(
                ffmpeg_adapter, 'extract_audio', workdir,
                "input.mp4", "output.wav"
            )
            
            assert result.success is False
            assert result.error == "FFmpeg failed"
    
    def test_artifact_patterns_for_methods(self):
        """Test artifact pattern selection for different methods."""
        runner = ExternalToolRunner()
        
        # Test various method patterns
        assert "*.wav" in runner._get_artifact_patterns_for_method("extract_audio")
        assert "*.srt" in runner._get_artifact_patterns_for_method("extract_subtitles")
        assert "*.mkv" in runner._get_artifact_patterns_for_method("remux")
        assert runner._get_artifact_patterns_for_method("probe") == []
        assert runner._get_artifact_patterns_for_method("unknown_method") == ["*"]