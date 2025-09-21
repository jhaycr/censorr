"""Planning logic for operation execution."""
from typing import List, Set, Dict, Optional
from dataclasses import dataclass
from ..models.artifacts import Artifact, ArtifactType
from ..models.operations import Operation
from .registry import OperationRegistry


@dataclass
class ExecutionPlan:
    """Represents a planned sequence of operations."""
    
    operations: List[Operation]
    
    def __len__(self) -> int:
        """Return number of operations in plan."""
        return len(self.operations)
    
    def is_empty(self) -> bool:
        """Check if plan has no operations."""
        return len(self.operations) == 0


class Planner:
    """Plans operation execution to achieve target artifacts."""
    
    def __init__(self, registry: OperationRegistry):
        self.registry = registry
    
    def plan(
        self, 
        provided_artifacts: List[Artifact], 
        target_types: Set[ArtifactType],
        strategy: str = "default"
    ) -> ExecutionPlan:
        """Plan operations to produce target artifacts.
        
        Args:
            provided_artifacts: Already available artifacts
            target_types: Set of artifact types to produce
            strategy: Planning strategy to use
            
        Returns:
            ExecutionPlan with ordered operations
            
        Raises:
            ValueError: If no producer available for required type
        """
        # Track which artifact types we already have
        available_types = {artifact.type for artifact in provided_artifacts}
        
        # Remove targets we already have
        needed_types = target_types - available_types
        
        if not needed_types:
            # All targets already provided
            return ExecutionPlan(operations=[])
        
        # Simple planning: find producer for each needed type
        # TODO: Handle dependencies between operations
        operations = []
        
        for artifact_type in needed_types:
            producers = self.registry.get_producers_for_type(artifact_type)
            
            if not producers:
                raise ValueError(f"No producer found for artifact type: {artifact_type}")
            
            # Use first producer for now (TODO: implement priority selection)
            producer = producers[0]
            
            # Check if producer's requirements are satisfied
            # For now, assume they are (TODO: recursive planning)
            operations.append(producer)
        
        return ExecutionPlan(operations=operations)
    
    def explain_plan(
        self, 
        provided_artifacts: List[Artifact], 
        target_types: Set[ArtifactType]
    ) -> Dict[str, str]:
        """Explain why each operation was selected.
        
        Args:
            provided_artifacts: Already available artifacts
            target_types: Set of artifact types to produce
            
        Returns:
            Dictionary mapping operation names to explanations
        """
        plan = self.plan(provided_artifacts, target_types)
        
        explanations = {}
        for operation in plan.operations:
            produced_types = ", ".join(operation.produces)
            explanations[operation.name] = f"Produces: {produced_types}"
        
        return explanations