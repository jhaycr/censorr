"""Tests for registry and planner."""
import pytest
from pathlib import Path
from src.models.artifacts import Artifact, ArtifactType
from src.models.operations import Operation, OperationFlags
from src.planner.registry import OperationRegistry
from src.planner.planner import Planner, ExecutionPlan


class MockOperation(Operation):
    """Mock operation for testing."""
    
    def __init__(self, name: str, consumes: set, produces: set):
        super().__init__(name)
        self._consumes = consumes
        self._produces = produces
    
    @property
    def consumes(self):
        return self._consumes
    
    @property
    def produces(self):
        return self._produces
    
    def run(self, inputs, workdir, flags):
        return []


class TestOperationRegistry:
    """Test OperationRegistry."""
    
    def test_registry_creation(self):
        """Test basic registry creation."""
        registry = OperationRegistry()
        assert len(registry.operations) == 0
    
    def test_register_operation(self):
        """Test registering an operation."""
        registry = OperationRegistry()
        op = MockOperation("test_op", {ArtifactType.VIDEO}, {ArtifactType.AUDIO})
        
        registry.register(op)
        assert len(registry.operations) == 1
        assert "test_op" in registry.operations
        assert registry.operations["test_op"] == op
    
    def test_register_duplicate_operation(self):
        """Test that registering duplicate operations raises error."""
        registry = OperationRegistry()
        op1 = MockOperation("test_op", {ArtifactType.VIDEO}, {ArtifactType.AUDIO})
        op2 = MockOperation("test_op", {ArtifactType.AUDIO}, {ArtifactType.SUBTITLE})
        
        registry.register(op1)
        with pytest.raises(ValueError, match="Operation 'test_op' already registered"):
            registry.register(op2)
    
    def test_get_producers_for_type(self):
        """Test finding producers for artifact type."""
        registry = OperationRegistry()
        op1 = MockOperation("extract_audio", {ArtifactType.VIDEO}, {ArtifactType.AUDIO})
        op2 = MockOperation("extract_subs", {ArtifactType.VIDEO}, {ArtifactType.SUBTITLE})
        op3 = MockOperation("merge_subs", {ArtifactType.SUBTITLE}, {ArtifactType.SUBTITLE})
        
        registry.register(op1)
        registry.register(op2)
        registry.register(op3)
        
        audio_producers = registry.get_producers_for_type(ArtifactType.AUDIO)
        assert len(audio_producers) == 1
        assert audio_producers[0].name == "extract_audio"
        
        subtitle_producers = registry.get_producers_for_type(ArtifactType.SUBTITLE)
        assert len(subtitle_producers) == 2
        producer_names = {op.name for op in subtitle_producers}
        assert producer_names == {"extract_subs", "merge_subs"}


class TestPlanner:
    """Test Planner."""
    
    def test_planner_creation(self):
        """Test planner creation."""
        registry = OperationRegistry()
        planner = Planner(registry)
        assert planner.registry == registry
    
    def test_plan_simple_extraction(self):
        """Test planning a simple extraction."""
        registry = OperationRegistry()
        extract_op = MockOperation("extract_audio", {ArtifactType.VIDEO}, {ArtifactType.AUDIO})
        registry.register(extract_op)
        
        planner = Planner(registry)
        
        video_artifact = Artifact(
            type=ArtifactType.VIDEO,
            path="/test/movie.mkv",
            metadata={"codec": "h264"}
        )
        
        plan = planner.plan(
            provided_artifacts=[video_artifact],
            target_types={ArtifactType.AUDIO}
        )
        
        assert len(plan.operations) == 1
        assert plan.operations[0].name == "extract_audio"
    
    def test_plan_no_producer_available(self):
        """Test planning when no producer is available."""
        registry = OperationRegistry()
        planner = Planner(registry)
        
        with pytest.raises(ValueError, match="No producer found for artifact type"):
            planner.plan(
                provided_artifacts=[],
                target_types={ArtifactType.AUDIO}
            )
    
    def test_plan_target_already_provided(self):
        """Test planning when target is already provided."""
        registry = OperationRegistry()
        planner = Planner(registry)
        
        audio_artifact = Artifact(
            type=ArtifactType.AUDIO,
            path="/test/audio.wav",
            metadata={"codec": "pcm"}
        )
        
        plan = planner.plan(
            provided_artifacts=[audio_artifact],
            target_types={ArtifactType.AUDIO}
        )
        
        assert len(plan.operations) == 0  # No operations needed


class TestExecutionPlan:
    """Test ExecutionPlan."""
    
    def test_execution_plan_creation(self):
        """Test execution plan creation."""
        op = MockOperation("test_op", {ArtifactType.VIDEO}, {ArtifactType.AUDIO})
        plan = ExecutionPlan(operations=[op])
        
        assert len(plan.operations) == 1
        assert plan.operations[0] == op