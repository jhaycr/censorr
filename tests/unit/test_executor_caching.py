"""Tests for the enhanced executor with caching support."""
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.models.artifacts import Artifact, ArtifactType
from src.models.operations import OperationFlags, OperationResult
from src.planner.executor import Executor, ExecutionContext
from src.planner.planner import ExecutionPlan
from src.caching import CacheManager


class TestExecutorCaching:
    """Test executor caching functionality."""
    
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
    
    def test_execution_context_with_cache_manager(self, temp_workdir):
        """Test that execution context creates cache manager."""
        context = ExecutionContext(
            workdir=temp_workdir,
            flags=OperationFlags()
        )
        
        assert context.cache_manager is not None
        assert isinstance(context.cache_manager, CacheManager)
        assert context.cache_manager.workdir == temp_workdir
    
    def test_execute_operation_first_time(self, executor, mock_operation, sample_artifact, temp_workdir):
        """Test executing operation for the first time (no cache)."""
        plan = ExecutionPlan(operations=[mock_operation])
        flags = OperationFlags(verbose=True)
        
        results = executor.execute(plan, temp_workdir, [sample_artifact], flags)
        
        assert len(results) == 1
        result = results[0]
        assert result.success
        assert result.operation == "test_operation"
        assert len(result.inputs) == 1
        assert len(result.outputs) == 1
        assert "Executed and cached in:" in result.logs[0]
        
        # Verify output file exists
        output_path = Path(result.outputs[0])
        assert output_path.exists()
        assert output_path.read_text() == "Processed subtitle content"
    
    def test_execute_operation_cached(self, executor, mock_operation, sample_artifact, temp_workdir):
        """Test executing operation when result is cached."""
        plan = ExecutionPlan(operations=[mock_operation])
        flags = OperationFlags(verbose=True)
        
        # First execution
        results1 = executor.execute(plan, temp_workdir, [sample_artifact], flags)
        assert results1[0].success
        
        # Reset the mock to verify it's not called again
        mock_operation.run.reset_mock()
        
        # Second execution (should use cache)
        results2 = executor.execute(plan, temp_workdir, [sample_artifact], flags)
        
        assert len(results2) == 1
        result = results2[0]
        assert result.success
        assert result.operation == "test_operation"
        assert "Loaded from cache:" in result.logs[0]
        
        # Verify operation.run was not called again
        mock_operation.run.assert_not_called()
    
    def test_execute_operation_force_flag(self, executor, mock_operation, sample_artifact, temp_workdir):
        """Test that force flag bypasses cache."""
        plan = ExecutionPlan(operations=[mock_operation])
        
        # First execution
        flags1 = OperationFlags(verbose=True)
        results1 = executor.execute(plan, temp_workdir, [sample_artifact], flags1)
        assert results1[0].success
        
        # Reset the mock
        mock_operation.run.reset_mock()
        
        # Second execution with force flag
        flags2 = OperationFlags(verbose=True, force=True)
        results2 = executor.execute(plan, temp_workdir, [sample_artifact], flags2)
        
        assert len(results2) == 1
        result = results2[0]
        assert result.success
        assert "Executed and cached in:" in result.logs[0]
        
        # Verify operation.run was called again
        mock_operation.run.assert_called_once()
    
    def test_execute_operation_skip_existing_flag(self, executor, mock_operation, sample_artifact, temp_workdir):
        """Test that skip_existing flag forces re-execution."""
        plan = ExecutionPlan(operations=[mock_operation])
        
        # First execution  
        flags1 = OperationFlags(verbose=True)
        results1 = executor.execute(plan, temp_workdir, [sample_artifact], flags1)
        assert results1[0].success
        
        # Reset the mock
        mock_operation.run.reset_mock()
        
        # Second execution with skip_existing flag
        flags2 = OperationFlags(verbose=True, skip_existing=True)
        results2 = executor.execute(plan, temp_workdir, [sample_artifact], flags2)
        
        assert len(results2) == 1
        result = results2[0]
        assert result.success
        assert "Executed and cached in:" in result.logs[0]
        
        # Verify operation.run was called again
        mock_operation.run.assert_called_once()
    
    def test_execute_operation_dry_run(self, executor, mock_operation, sample_artifact, temp_workdir):
        """Test dry run mode bypasses caching and execution."""
        plan = ExecutionPlan(operations=[mock_operation])
        flags = OperationFlags(dry_run=True, verbose=True)
        
        results = executor.execute(plan, temp_workdir, [sample_artifact], flags)
        
        assert len(results) == 1
        result = results[0]
        assert result.success
        assert result.operation == "test_operation"
        assert "DRY RUN: test_operation" in result.logs
        
        # Verify operation.run was not called
        mock_operation.run.assert_not_called()
    
    def test_execute_operation_cache_reconstruction(self, executor, mock_operation, sample_artifact, temp_workdir):
        """Test that cached artifacts are properly reconstructed."""
        plan = ExecutionPlan(operations=[mock_operation])
        flags = OperationFlags(verbose=True)
        
        # First execution
        results1 = executor.execute(plan, temp_workdir, [sample_artifact], flags)
        original_output_path = results1[0].outputs[0]
        
        # Second execution (cached)
        results2 = executor.execute(plan, temp_workdir, [sample_artifact], flags)
        cached_output_path = results2[0].outputs[0]
        
        # Paths should be the same
        assert original_output_path == cached_output_path
        
        # File content should be preserved
        assert Path(cached_output_path).read_text() == "Processed subtitle content"
    
    def test_execute_operation_artifact_type_detection(self, executor, sample_artifact, temp_workdir):
        """Test artifact type detection from file extensions."""
        # Create mock operations for different file types
        operations = []
        
        # Subtitle operation
        sub_op = Mock()
        sub_op.name = "sub_operation"
        sub_op.consumes = {ArtifactType.SUBTITLE}
        sub_op.produces = {ArtifactType.SUBTITLE}
        
        def sub_run(inputs, workdir, flags):
            output_path = workdir / "output.srt"
            output_path.write_text("subtitle")
            return [Artifact(type=ArtifactType.SUBTITLE, path=str(output_path), metadata={"language": "en"})]
        sub_op.run = sub_run
        operations.append(sub_op)
        
        # Audio operation
        audio_op = Mock()
        audio_op.name = "audio_operation"
        audio_op.consumes = {ArtifactType.SUBTITLE}
        audio_op.produces = {ArtifactType.AUDIO}
        
        def audio_run(inputs, workdir, flags):
            output_path = workdir / "output.mp3"
            output_path.write_text("audio")
            return [Artifact(type=ArtifactType.AUDIO, path=str(output_path), metadata={"channels": "stereo"})]
        audio_op.run = audio_run
        operations.append(audio_op)
        
        # Video operation
        video_op = Mock()
        video_op.name = "video_operation"
        video_op.consumes = {ArtifactType.SUBTITLE}
        video_op.produces = {ArtifactType.VIDEO}
        
        def video_run(inputs, workdir, flags):
            output_path = workdir / "output.mp4"
            output_path.write_text("video")
            return [Artifact(type=ArtifactType.VIDEO, path=str(output_path), metadata={"codec": "h264"})]
        video_op.run = video_run
        operations.append(video_op)
        
        plan = ExecutionPlan(operations=operations)
        flags = OperationFlags()
        
        # Execute all operations twice (second time should use cache)
        for i in range(2):
            results = executor.execute(plan, temp_workdir, [sample_artifact], flags)
            
            assert len(results) == 3
            assert all(r.success for r in results)
            
            if i == 1:  # Second execution should be from cache
                assert all("Loaded from cache:" in r.logs[0] for r in results)
    
    def test_execute_operation_failure_no_cache(self, executor, sample_artifact, temp_workdir):
        """Test that failed operations are not cached."""
        # Create failing operation
        failing_op = Mock()
        failing_op.name = "failing_operation"
        failing_op.consumes = {ArtifactType.SUBTITLE}
        failing_op.produces = {ArtifactType.SUBTITLE}
        failing_op.run.side_effect = Exception("Operation failed")
        
        plan = ExecutionPlan(operations=[failing_op])
        flags = OperationFlags()
        
        results = executor.execute(plan, temp_workdir, [sample_artifact], flags)
        
        assert len(results) == 1
        result = results[0]
        assert not result.success
        assert result.error == "Operation failed"
        
        # Verify no manifest is created for failed operation
        cache_manager = CacheManager(temp_workdir)
        cache_key = cache_manager.create_cache_key("failing_operation", [sample_artifact], {})
        op_dir = cache_manager.get_operation_dir("failing_operation", cache_key)
        manifest_path = cache_manager.get_manifest_path(op_dir)
        
        # Manifest should not exist since operation failed
        assert not manifest_path.exists()