"""Tests for the structured logging system."""
import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from src.logging import ExecutionLogger, OperationLogEntry
from src.models.artifacts import Artifact, ArtifactType
from src.models.common import LogLevel


class TestOperationLogEntry:
    """Test operation log entry functionality."""
    
    def test_operation_log_entry_creation(self):
        """Test creating an operation log entry."""
        start_time = datetime.now()
        entry = OperationLogEntry(
            operation="test_op",
            start_time=start_time,
            success=False,
            workdir="/tmp/test"
        )
        
        assert entry.operation == "test_op"
        assert entry.start_time == start_time
        assert entry.end_time is None
        assert entry.duration_ms is None
        assert not entry.success
        assert entry.workdir == "/tmp/test"
    
    def test_mark_finished_success(self):
        """Test marking operation as finished successfully."""
        start_time = datetime.now()
        entry = OperationLogEntry(
            operation="test_op",
            start_time=start_time,
            success=False,
            workdir="/tmp/test"
        )
        
        entry.mark_finished(True)
        
        assert entry.success
        assert entry.end_time is not None
        assert entry.duration_ms is not None
        assert entry.duration_ms >= 0
        assert entry.error is None
    
    def test_mark_finished_with_error(self):
        """Test marking operation as finished with error."""
        start_time = datetime.now()
        entry = OperationLogEntry(
            operation="test_op",
            start_time=start_time,
            success=False,
            workdir="/tmp/test"
        )
        
        entry.mark_finished(False, "Something went wrong")
        
        assert not entry.success
        assert entry.end_time is not None
        assert entry.duration_ms is not None
        assert entry.error == "Something went wrong"


class TestExecutionLogger:
    """Test execution logger functionality."""
    
    @pytest.fixture
    def temp_workdir(self):
        """Create a temporary working directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    @pytest.fixture
    def execution_logger(self, temp_workdir):
        """Create an execution logger."""
        return ExecutionLogger(temp_workdir, session_id="test_session")
    
    @pytest.fixture
    def sample_artifact(self, temp_workdir):
        """Create a sample artifact."""
        artifact_path = temp_workdir / "sample.srt"
        artifact_path.write_text("Sample subtitle content")
        return Artifact(
            type=ArtifactType.SUBTITLE,
            path=str(artifact_path),
            metadata={"language": "en"}
        )
    
    def test_execution_logger_initialization(self, temp_workdir):
        """Test execution logger initialization."""
        logger = ExecutionLogger(temp_workdir, session_id="test_session")
        
        assert logger.workdir == temp_workdir
        assert logger.session_id == "test_session"
        assert logger.execution_log_path == temp_workdir / "execution_test_session.json"
        assert logger.audit_log_path == temp_workdir / "audit_test_session.json"
        assert len(logger.operation_logs) == 0
        assert len(logger.audit_entries) == 0
    
    def test_execution_logger_auto_session_id(self, temp_workdir):
        """Test execution logger with auto-generated session ID."""
        logger = ExecutionLogger(temp_workdir)
        
        assert logger.session_id is not None
        assert len(logger.session_id) > 0
        assert "_" in logger.session_id  # Should be timestamp format
    
    def test_start_operation(self, execution_logger, sample_artifact, temp_workdir):
        """Test starting operation logging."""
        flags = {"verbose": True, "dry_run": False}
        
        log_entry = execution_logger.start_operation(
            "test_operation", [sample_artifact], temp_workdir, flags
        )
        
        assert log_entry.operation == "test_operation"
        assert log_entry.start_time is not None
        assert log_entry.end_time is None
        assert not log_entry.success
        assert len(log_entry.inputs) == 1
        assert log_entry.inputs[0]["type"] == "ArtifactType.SUBTITLE"
        assert log_entry.inputs[0]["path"] == sample_artifact.path
        assert log_entry.inputs[0]["exists"]
        assert log_entry.inputs[0]["size_bytes"] > 0
        assert log_entry.workdir == str(temp_workdir)
        assert log_entry.flags == flags
        
        # Check that it was added to the logger
        assert len(execution_logger.operation_logs) == 1
        assert len(execution_logger.audit_entries) == 1
    
    def test_finish_operation_success(self, execution_logger, sample_artifact, temp_workdir):
        """Test finishing operation successfully."""
        # Start operation
        log_entry = execution_logger.start_operation(
            "test_operation", [sample_artifact], temp_workdir, {}
        )
        
        # Create output artifact
        output_path = temp_workdir / "output.srt"
        output_path.write_text("Processed content")
        output_artifact = Artifact(
            type=ArtifactType.SUBTITLE,
            path=str(output_path),
            metadata={"language": "en"}
        )
        
        # Finish operation
        execution_logger.finish_operation(log_entry, True, [output_artifact])
        
        assert log_entry.success
        assert log_entry.end_time is not None
        assert log_entry.duration_ms is not None
        assert len(log_entry.outputs) == 1
        assert log_entry.outputs[0]["type"] == "ArtifactType.SUBTITLE"
        assert log_entry.outputs[0]["path"] == str(output_path)
        assert log_entry.outputs[0]["exists"]
        assert log_entry.error is None
        
        # Check audit entries
        assert len(execution_logger.audit_entries) == 2  # Start + finish
        finish_entry = execution_logger.audit_entries[1]
        assert finish_entry.level == LogLevel.INFO
        assert "Completed operation" in finish_entry.message
    
    def test_finish_operation_failure(self, execution_logger, sample_artifact, temp_workdir):
        """Test finishing operation with failure."""
        # Start operation
        log_entry = execution_logger.start_operation(
            "test_operation", [sample_artifact], temp_workdir, {}
        )
        
        # Finish with error
        execution_logger.finish_operation(log_entry, False, error="Operation failed")
        
        assert not log_entry.success
        assert log_entry.end_time is not None
        assert log_entry.error == "Operation failed"
        assert len(log_entry.outputs) == 0
        
        # Check audit entries
        finish_entry = execution_logger.audit_entries[1]
        assert finish_entry.level == LogLevel.ERROR
        assert "Failed operation" in finish_entry.message
        assert "Operation failed" in finish_entry.message
    
    def test_log_external_command(self, execution_logger, sample_artifact, temp_workdir):
        """Test logging external command execution."""
        # Start operation
        log_entry = execution_logger.start_operation(
            "test_operation", [sample_artifact], temp_workdir, {}
        )
        
        # Log external command
        command = ["ffmpeg", "-i", "input.mp4", "output.mp4"]
        stdout = "FFmpeg output here"
        stderr = "Some warning"
        
        execution_logger.log_external_command(
            log_entry, command, 0, stdout, stderr, 1500.0
        )
        
        assert len(log_entry.external_commands) == 1
        cmd_info = log_entry.external_commands[0]
        assert cmd_info["command"] == command
        assert cmd_info["exit_code"] == 0
        assert cmd_info["duration_ms"] == 1500.0
        assert cmd_info["stdout_path"] is not None
        assert cmd_info["stderr_path"] is not None
        
        # Check that stdout/stderr files were created
        stdout_path = Path(cmd_info["stdout_path"])
        stderr_path = Path(cmd_info["stderr_path"])
        assert stdout_path.exists()
        assert stderr_path.exists()
        assert stdout_path.read_text() == stdout
        assert stderr_path.read_text() == stderr
        
        # Check audit entry
        assert len(execution_logger.audit_entries) == 2  # Start + external command
        cmd_entry = execution_logger.audit_entries[1]
        assert cmd_entry.level == LogLevel.INFO
        assert "External command" in cmd_entry.message
    
    def test_log_external_command_failure(self, execution_logger, sample_artifact, temp_workdir):
        """Test logging failed external command."""
        # Start operation
        log_entry = execution_logger.start_operation(
            "test_operation", [sample_artifact], temp_workdir, {}
        )
        
        # Log failed external command
        command = ["ffmpeg", "-i", "missing.mp4"]
        execution_logger.log_external_command(log_entry, command, 1)
        
        assert len(log_entry.external_commands) == 1
        cmd_info = log_entry.external_commands[0]
        assert cmd_info["exit_code"] == 1
        
        # Check audit entry has error level
        cmd_entry = execution_logger.audit_entries[1]
        assert cmd_entry.level == LogLevel.ERROR
    
    def test_add_operation_log(self, execution_logger, sample_artifact, temp_workdir):
        """Test adding operation log messages."""
        # Start operation
        log_entry = execution_logger.start_operation(
            "test_operation", [sample_artifact], temp_workdir, {}
        )
        
        # Add log messages
        execution_logger.add_operation_log(log_entry, "Processing started")
        execution_logger.add_operation_log(log_entry, "Processing completed")
        
        assert len(log_entry.logs) == 2
        assert "Processing started" in log_entry.logs[0]
        assert "Processing completed" in log_entry.logs[1]
        # Check ISO timestamp format
        assert ":" in log_entry.logs[0]  # Timestamp should contain colons
    
    def test_add_audit_entry(self, execution_logger):
        """Test adding audit entries."""
        execution_logger.add_audit_entry(
            "test_op", LogLevel.WARN, "Warning message", {"detail": "value"}
        )
        
        assert len(execution_logger.audit_entries) == 1
        entry = execution_logger.audit_entries[0]
        assert entry.op == "test_op"
        assert entry.level == LogLevel.WARN
        assert entry.message == "Warning message"
        assert entry.details == {"detail": "value"}
    
    def test_save_logs(self, execution_logger, sample_artifact, temp_workdir):
        """Test saving logs to files."""
        # Create some log data
        log_entry = execution_logger.start_operation(
            "test_operation", [sample_artifact], temp_workdir, {}
        )
        execution_logger.finish_operation(log_entry, True)
        
        # Save logs
        execution_logger.save_logs()
        
        # Check execution log file
        assert execution_logger.execution_log_path.exists()
        with execution_logger.execution_log_path.open() as f:
            execution_data = json.load(f)
        
        assert execution_data["session_id"] == "test_session"
        assert len(execution_data["operations"]) == 1
        assert execution_data["operations"][0]["operation"] == "test_operation"
        
        # Check audit log file
        assert execution_logger.audit_log_path.exists()
        with execution_logger.audit_log_path.open() as f:
            audit_data = json.load(f)
        
        assert audit_data["session_id"] == "test_session"
        assert len(audit_data["entries"]) == 2  # Start + finish
    
    def test_get_summary(self, execution_logger, sample_artifact, temp_workdir):
        """Test getting execution summary."""
        # Create some operations
        log_entry1 = execution_logger.start_operation(
            "operation1", [sample_artifact], temp_workdir, {}
        )
        execution_logger.finish_operation(log_entry1, True)
        
        log_entry2 = execution_logger.start_operation(
            "operation2", [sample_artifact], temp_workdir, {}
        )
        execution_logger.finish_operation(log_entry2, False, error="Failed")
        
        # Get summary
        summary = execution_logger.get_summary()
        
        assert summary["session_id"] == "test_session"
        assert summary["total_operations"] == 2
        assert summary["successful_operations"] == 1
        assert summary["failed_operations"] == 1
        assert summary["total_duration_ms"] >= 0
        assert "execution_log" in summary
        assert "audit_log" in summary
    
    def test_missing_input_artifact(self, execution_logger, temp_workdir):
        """Test handling missing input artifacts."""
        missing_artifact = Artifact(
            type=ArtifactType.SUBTITLE,
            path=str(temp_workdir / "missing.srt"),
            metadata={"language": "en"}
        )
        
        log_entry = execution_logger.start_operation(
            "test_operation", [missing_artifact], temp_workdir, {}
        )
        
        assert len(log_entry.inputs) == 1
        assert not log_entry.inputs[0]["exists"]
        assert log_entry.inputs[0]["size_bytes"] == 0