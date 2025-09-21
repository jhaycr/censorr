"""Tests for executor."""
import pytest
from pathlib import Path
import tempfile
from src.models.artifacts import Artifact, ArtifactType
from src.models.operations import Operation, OperationFlags, OperationResult
from src.planner.executor import Executor, ExecutionContext
from src.planner.planner import ExecutionPlan


class MockOperation(Operation):
    """Mock operation for testing."""
    
    def __init__(self, name: str, consumes: set, produces: set, should_fail: bool = False):
        super().__init__(name)
        self._consumes = consumes
        self._produces = produces
        self.should_fail = should_fail
        self.was_called = False
        self.call_args = None
    
    @property
    def consumes(self):
        return self._consumes
    
    @property
    def produces(self):
        return self._produces
    
    def run(self, inputs, workdir, flags):
        self.was_called = True
        self.call_args = (inputs, workdir, flags)
        
        if flags.dry_run:
            # In dry run, don't actually create files
            return []
        
        if self.should_fail:
            raise RuntimeError("Mock operation failed")
        
        # Create a mock output artifact
        output_path = workdir / f"{self.name}_output.txt"
        output_path.write_text("mock output")
        
        return [Artifact(
            type=list(self._produces)[0],
            path=str(output_path),
            metadata={"mock": True}
        )]


class TestExecutor:
    """Test Executor."""
    
    def test_executor_creation(self):
        """Test executor creation."""
        executor = Executor()
        assert executor is not None
    
    def test_execute_empty_plan(self):
        """Test executing an empty plan."""
        executor = Executor()
        plan = ExecutionPlan(operations=[])
        
        with tempfile.TemporaryDirectory() as tmpdir:
            results = executor.execute(plan, Path(tmpdir))
            assert len(results) == 0
    
    def test_execute_single_operation(self):
        """Test executing a single operation."""
        executor = Executor()
        
        op = MockOperation("test_op", {ArtifactType.VIDEO}, {ArtifactType.AUDIO})
        plan = ExecutionPlan(operations=[op])
        
        with tempfile.TemporaryDirectory() as tmpdir:
            workdir = Path(tmpdir)
            video_input = workdir / "input.mkv"
            video_input.write_text("mock video")
            
            artifacts = [Artifact(
                type=ArtifactType.VIDEO,
                path=str(video_input),
                metadata={"codec": "h264"}
            )]
            
            results = executor.execute(plan, workdir, artifacts)
            
            assert len(results) == 1
            assert results[0].operation == "test_op"
            assert results[0].success is True
            assert op.was_called
    
    def test_execute_dry_run(self):
        """Test executing in dry-run mode."""
        executor = Executor()
        
        op = MockOperation("test_op", {ArtifactType.VIDEO}, {ArtifactType.AUDIO})
        plan = ExecutionPlan(operations=[op])
        
        with tempfile.TemporaryDirectory() as tmpdir:
            workdir = Path(tmpdir)
            flags = OperationFlags(dry_run=True)
            
            results = executor.execute(plan, workdir, [], flags)
            
            assert len(results) == 1
            assert results[0].operation == "test_op"
            assert results[0].success is True
            # In dry-run mode, operation should not be called
            assert not op.was_called
    
    def test_execute_operation_failure(self):
        """Test handling operation failure."""
        executor = Executor()
        
        op = MockOperation("failing_op", {ArtifactType.VIDEO}, {ArtifactType.AUDIO}, should_fail=True)
        plan = ExecutionPlan(operations=[op])
        
        with tempfile.TemporaryDirectory() as tmpdir:
            workdir = Path(tmpdir)
            
            results = executor.execute(plan, workdir)
            
            assert len(results) == 1
            assert results[0].operation == "failing_op"
            assert results[0].success is False
            assert "Mock operation failed" in results[0].error
    
    def test_execute_verbose_mode(self):
        """Test executing in verbose mode."""
        executor = Executor()
        
        op = MockOperation("test_op", {ArtifactType.VIDEO}, {ArtifactType.AUDIO})
        plan = ExecutionPlan(operations=[op])
        
        with tempfile.TemporaryDirectory() as tmpdir:
            workdir = Path(tmpdir)
            flags = OperationFlags(verbose=True)
            
            results = executor.execute(plan, workdir, [], flags)
            
            assert len(results) == 1
            assert op.call_args[2].verbose is True


class TestExecutionContext:
    """Test ExecutionContext."""
    
    def test_execution_context_creation(self):
        """Test execution context creation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            context = ExecutionContext(
                workdir=Path(tmpdir),
                flags=OperationFlags()
            )
            
            assert context.workdir == Path(tmpdir)
            assert context.flags.dry_run is False
    
    def test_execution_context_with_flags(self):
        """Test execution context with custom flags."""
        with tempfile.TemporaryDirectory() as tmpdir:
            flags = OperationFlags(dry_run=True, verbose=True)
            context = ExecutionContext(
                workdir=Path(tmpdir),
                flags=flags
            )
            
            assert context.flags.dry_run is True
            assert context.flags.verbose is True