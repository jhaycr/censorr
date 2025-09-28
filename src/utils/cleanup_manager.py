"""
Intermediate artifact cleanup manager.

Manages tracking and cleanup of intermediate artifacts produced during pipeline execution.
"""
import logging
import os
from pathlib import Path
from typing import List, Set, Dict, Any
from dataclasses import dataclass, field


@dataclass
class CleanupManager:
    """Manages intermediate artifacts and their cleanup."""
    
    # Artifacts produced by operations
    intermediate_artifacts: Set[str] = field(default_factory=set)
    
    # Artifacts that should be preserved (final outputs, user inputs)
    preserved_artifacts: Set[str] = field(default_factory=set)
    
    # Dependencies: artifact -> set of artifacts it depends on
    dependencies: Dict[str, Set[str]] = field(default_factory=dict)
    
    def __post_init__(self):
        """Initialize logger."""
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def register_intermediate(self, artifact_path: str, dependencies: List[str] = None):
        """Register an intermediate artifact for potential cleanup.
        
        Args:
            artifact_path: Path to intermediate artifact
            dependencies: List of artifact paths this depends on
        """
        artifact_path_str = str(artifact_path)
        self.intermediate_artifacts.add(artifact_path_str)
        
        if dependencies:
            deps_set = {str(dep) for dep in dependencies}
            self.dependencies[artifact_path_str] = deps_set
            self.logger.debug(f"Registered intermediate artifact: {artifact_path_str} (deps: {deps_set})")
        else:  
            self.logger.debug(f"Registered intermediate artifact: {artifact_path_str}")
    
    def register_preserved(self, artifact_path: str):
        """Register an artifact that should be preserved (not cleaned up).
        
        Args:
            artifact_path: Path to artifact to preserve
        """
        artifact_path_str = str(artifact_path)
        self.preserved_artifacts.add(artifact_path_str)
        self.logger.debug(f"Registered preserved artifact: {artifact_path_str}")
    
    def cleanup_intermediates(self, persist_intermediate: bool = False) -> Dict[str, Any]:
        """Clean up intermediate artifacts that are no longer needed.
        
        Args:
            persist_intermediate: If True, skip cleanup and preserve all intermediates
            
        Returns:
            Dictionary with cleanup results
        """
        if persist_intermediate:
            self.logger.info("Intermediate cleanup skipped (persist_intermediate=True)")
            return {
                "status": "skipped",
                "reason": "persist_intermediate flag set",
                "intermediate_count": len(self.intermediate_artifacts),
                "preserved_count": len(self.preserved_artifacts)
            }
        
        # Find artifacts safe to delete
        cleanable = self.intermediate_artifacts - self.preserved_artifacts
        
        # Remove artifacts that are dependencies of preserved artifacts
        for preserved in self.preserved_artifacts:
            if preserved in self.dependencies:
                cleanable -= self.dependencies[preserved]
        
        # Also check transitive dependencies
        for intermediate in list(cleanable):
            if self._is_dependency_of_preserved(intermediate):
                cleanable.discard(intermediate)
        
        # Perform cleanup
        cleaned = []
        failed = []
        
        for artifact_path in cleanable:
            try:
                if Path(artifact_path).exists():
                    os.remove(artifact_path)
                    cleaned.append(artifact_path)
                    self.logger.info(f"✓ Cleaned intermediate artifact: {artifact_path}")
                else:
                    self.logger.debug(f"Intermediate artifact already missing: {artifact_path}")
            except Exception as e:
                failed.append({"path": artifact_path, "error": str(e)})
                self.logger.warning(f"Failed to clean intermediate artifact {artifact_path}: {e}")
        
        result = {
            "status": "completed",
            "cleaned_count": len(cleaned),
            "failed_count": len(failed),
            "preserved_count": len(self.preserved_artifacts),
            "cleaned_paths": cleaned,
            "failed_cleanups": failed
        }
        
        if cleaned:
            self.logger.info(f"Intermediate cleanup completed: {len(cleaned)} files cleaned, {len(failed)} failed")
        
        return result
    
    def _is_dependency_of_preserved(self, artifact_path: str) -> bool:
        """Check if an artifact is a transitive dependency of any preserved artifact.
        
        Args:
            artifact_path: Path to check
            
        Returns:
            True if artifact is needed by a preserved artifact
        """
        # Simple approach: check if any preserved artifact depends on this one
        for preserved in self.preserved_artifacts:
            if preserved in self.dependencies:
                if artifact_path in self.dependencies[preserved]:
                    return True
                # Could add deeper transitive checking here if needed
        return False
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of tracked artifacts.
        
        Returns:
            Summary dictionary
        """
        return {
            "intermediate_count": len(self.intermediate_artifacts),
            "preserved_count": len(self.preserved_artifacts),
            "dependency_count": len(self.dependencies),
            "intermediate_artifacts": sorted(list(self.intermediate_artifacts)),
            "preserved_artifacts": sorted(list(self.preserved_artifacts))
        }