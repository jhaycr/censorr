"""Operation registry for managing available operations."""
from typing import Dict, List
from ..models.operations import Operation
from ..models.artifacts import ArtifactType


class OperationRegistry:
    """Registry for managing available operations."""
    
    def __init__(self):
        self.operations: Dict[str, Operation] = {}
    
    def register(self, operation: Operation) -> None:
        """Register an operation.
        
        Args:
            operation: Operation to register
            
        Raises:
            ValueError: If operation name already registered
        """
        if operation.name in self.operations:
            raise ValueError(f"Operation '{operation.name}' already registered")
        
        self.operations[operation.name] = operation
    
    def get_operation(self, name: str) -> Operation:
        """Get operation by name.
        
        Args:
            name: Operation name
            
        Returns:
            Operation instance
            
        Raises:
            KeyError: If operation not found
        """
        if name not in self.operations:
            raise KeyError(f"Operation '{name}' not found")
        
        return self.operations[name]
    
    def get_producers_for_type(self, artifact_type: ArtifactType) -> List[Operation]:
        """Get all operations that can produce the given artifact type.
        
        Args:
            artifact_type: Type of artifact to find producers for
            
        Returns:
            List of operations that produce this artifact type
        """
        producers = []
        for operation in self.operations.values():
            if artifact_type in operation.produces:
                producers.append(operation)
        
        return producers
    
    def list_operations(self) -> List[str]:
        """List all registered operation names.
        
        Returns:
            List of operation names
        """
        return list(self.operations.keys())