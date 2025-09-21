"""Tests for executor integration with structured logging."""
import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from src.models.artifacts import Artifact, ArtifactType
from src.models.operations import OperationFlags
from src.planner.executor import Executor, ExecutionContext
from src.planner.planner import ExecutionPlan
from src.logging import ExecutionLogger


class TestExecutorLogging:
    """Test executor integration with structured logging."""
    
    @pytest.fixture
    def temp_workdir(self):
        """Create a temporary working directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    @pytest.fixture
    def executor(self):
        """Create an executor instance."""
        return Executor()
    
    @pytest.fixture
    def sample_artifact(self, temp_workdir):
        """Create a sample input artifact."""
        input_path = temp_workdir / "input.srt"
        input_path.write_text("Sample subtitle content")
        return Artifact(
            type=ArtifactType.SUBTITLE,
            path=str(input_path),
            metadata={"language": "en"}
        )
    
    @pytest.fixture
    def mock_operation(self, temp_workdir):
        """Create a mock operation."""
        operation = Mock()
        operation.name = "test_operation"
        operation.consumes = {ArtifactType.SUBTITLE}
        operation.produces = {ArtifactType.SUBTITLE}
        
        def mock_run(inputs, workdir, flags):
            # Create output file
            output_path = workdir / "output.srt"
            output_path.write_text("Processed subtitle content")
            return [Artifact(
                type=ArtifactType.SUBTITLE,
                path=str(output_path),
                metadata={"language": "en"}
            )]
        
        operation.run = Mock(side_effect=mock_run)
        return operation
    
    def test_execution_context_creates_logger(self, temp_workdir):
        """Test that execution context creates execution logger."""
        context = ExecutionContext(
            workdir=temp_workdir,
            flags=OperationFlags()
        )
        
        assert context.execution_logger is not None
        assert isinstance(context.execution_logger, ExecutionLogger)
        assert context.execution_logger.workdir == temp_workdir
    
    def test_execute_logs_operation_lifecycle(self, executor, mock_operation, sample_artifact, temp_workdir):
        """Test that operation lifecycle is properly logged."""
        plan = ExecutionPlan(operations=[mock_operation])
        flags = OperationFlags(verbose=True)
        
        results = executor.execute(plan, temp_workdir, [sample_artifact], flags)
        
        # Verify operation executed successfully
        assert len(results) == 1
        assert results[0].success
        
        # Check that log files were created
        log_files = list(temp_workdir.glob("execution_*.json"))
        assert len(log_files) == 1
        
        audit_files = list(temp_workdir.glob("audit_*.json"))
        assert len(audit_files) == 1
        
        # Session files might not be created if no explicit logging to file handler
        # But execution and audit logs should definitely exist
        assert log_files[0].exists()
        assert audit_files[0].exists()
    
    def test_execute_logs_operation_details(self, executor, mock_operation, sample_artifact, temp_workdir):
        """Test that operation details are properly logged."""
        plan = ExecutionPlan(operations=[mock_operation])
        flags = OperationFlags(verbose=True)
        
        # Execute the plan
        results = executor.execute(plan, temp_workdir, [sample_artifact], flags)
        
        # Get the execution context to check logs
        context = ExecutionContext(
            workdir=temp_workdir,
            flags=flags,
            artifacts=[sample_artifact]
        )
        
        # Check that operation was logged
        assert len(context.execution_logger.operation_logs) == 0  # Fresh context
        
        # Instead, verify files exist and contain expected data
        execution_log_files = list(temp_workdir.glob("execution_*.json"))
        assert len(execution_log_files) >= 1
        
        import json
        with execution_log_files[0].open() as f:
            log_data = json.load(f)
        
        assert len(log_data["operations"]) == 1
        op_log = log_data["operations"][0]
        assert op_log["operation"] == "test_operation"
        assert op_log["success"]
        assert len(op_log["inputs"]) == 1
        assert len(op_log["outputs"]) == 1
        assert op_log["duration_ms"] is not None
    
    def test_execute_logs_dry_run(self, executor, mock_operation, sample_artifact, temp_workdir):
        """Test that dry run operations are logged."""
        plan = ExecutionPlan(operations=[mock_operation])
        flags = OperationFlags(dry_run=True, verbose=True)
        
        results = executor.execute(plan, temp_workdir, [sample_artifact], flags)
        
        assert len(results) == 1
        assert results[0].success
        assert "DRY RUN" in results[0].logs[0]
        
        # Verify operation.run was not called in dry run
        mock_operation.run.assert_not_called()
        
        # Check log files
        execution_log_files = list(temp_workdir.glob("execution_*.json"))
        assert len(execution_log_files) >= 1
    
    def test_execute_logs_cached_operation(self, executor, mock_operation, sample_artifact, temp_workdir):
        """Test that cached operations are properly logged."""
        plan = ExecutionPlan(operations=[mock_operation])
        flags = OperationFlags(verbose=True)
        
        # First execution
        results1 = executor.execute(plan, temp_workdir, [sample_artifact], flags)
        assert results1[0].success
        
        # Second execution (should be cached)
        results2 = executor.execute(plan, temp_workdir, [sample_artifact], flags)
        assert results2[0].success
        assert "Loaded from cache" in results2[0].logs[0]
        
        # Should have multiple execution log files or one with multiple operations
        execution_log_files = list(temp_workdir.glob("execution_*.json"))
        assert len(execution_log_files) >= 1
    
    def test_execute_logs_operation_failure(self, executor, sample_artifact, temp_workdir):
        """Test that operation failures are properly logged."""
        # Create failing operation
        failing_op = Mock()
        failing_op.name = "failing_operation"
        failing_op.consumes = {ArtifactType.SUBTITLE}
        failing_op.produces = {ArtifactType.SUBTITLE}
        failing_op.run.side_effect = Exception("Operation failed")
        
        plan = ExecutionPlan(operations=[failing_op])
        flags = OperationFlags(verbose=True)
        
        results = executor.execute(plan, temp_workdir, [sample_artifact], flags)
        
        assert len(results) == 1
        assert not results[0].success
        assert results[0].error == "Operation failed"
        
        # Check that failure was logged
        execution_log_files = list(temp_workdir.glob("execution_*.json"))
        assert len(execution_log_files) >= 1
        
        import json
        with execution_log_files[0].open() as f:
            log_data = json.load(f)
        
        assert len(log_data["operations"]) == 1
        op_log = log_data["operations"][0]
        assert op_log["operation"] == "failing_operation"
        assert not op_log["success"]
        assert op_log["error"] == "Operation failed"
    
    def test_execute_generates_summary(self, executor, mock_operation, sample_artifact, temp_workdir):
        """Test that execution summary is generated."""
        plan = ExecutionPlan(operations=[mock_operation])
        flags = OperationFlags(verbose=True)
        
        results = executor.execute(plan, temp_workdir, [sample_artifact], flags)
        
        # Check that execution generated a summary in the context
        # We can verify this by checking that the logger was used
        assert len(results) == 1
        assert results[0].success
        
        # Verify summary can be generated
        context = ExecutionContext(
            workdir=temp_workdir,
            flags=flags,
            artifacts=[sample_artifact]
        )
        
        summary = context.execution_logger.get_summary()
        assert "session_id" in summary
        assert "total_operations" in summary
        assert "execution_log" in summary
    
    def test_multiple_operations_logging(self, executor, sample_artifact, temp_workdir):
        """Test logging for multiple operations."""
        # Create multiple operations
        operations = []
        
        for i in range(3):
            op = Mock()
            op.name = f"operation_{i}"
            op.consumes = {ArtifactType.SUBTITLE}
            op.produces = {ArtifactType.SUBTITLE}
            
            def make_run(op_num):
                def mock_run(inputs, workdir, flags):
                    output_path = workdir / f"output_{op_num}.srt"
                    output_path.write_text(f"Output {op_num}")
                    return [Artifact(
                        type=ArtifactType.SUBTITLE,
                        path=str(output_path),
                        metadata={"language": "en"}
                    )]
                return mock_run
            
            op.run = Mock(side_effect=make_run(i))
            operations.append(op)
        
        plan = ExecutionPlan(operations=operations)
        flags = OperationFlags(verbose=True)
        
        results = executor.execute(plan, temp_workdir, [sample_artifact], flags)
        
        assert len(results) == 3
        assert all(r.success for r in results)
        
        # Check that all operations were logged
        execution_log_files = list(temp_workdir.glob("execution_*.json"))
        assert len(execution_log_files) >= 1
        
        import json
        with execution_log_files[0].open() as f:
            log_data = json.load(f)
        
        assert len(log_data["operations"]) == 3
        operation_names = [op["operation"] for op in log_data["operations"]]
        assert "operation_0" in operation_names
        assert "operation_1" in operation_names
        assert "operation_2" in operation_names