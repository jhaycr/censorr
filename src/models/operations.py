"""Operation models and base classes."""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Set, TYPE_CHECKING
from pathlib import Path
from pydantic import BaseModel, Field, model_validator
from .artifacts import Artifact, ArtifactType

if TYPE_CHECKING:
    from .selectors import Selector


class OperationFlags(BaseModel):
    """Flags that control operation execution."""
    
    dry_run: bool = Field(False, description="Don't create files, just show what would happen")
    verbose: bool = Field(False, description="Verbose output")
    strategy: str = Field("default", description="Operation strategy to use")
    force: bool = Field(False, description="Overwrite existing output files")
    skip_existing: bool = Field(False, description="Skip processing if output already exists")
    parallel: bool = Field(False, description="Enable parallel execution of operations")
    max_jobs: int = Field(1, description="Maximum number of parallel jobs (implies parallel=True)")
    continue_on_qc_fail: bool = Field(False, description="Continue pipeline on QC failure (residual matches found)")
    continue_on_audio_qc_fail: bool = Field(False, description="Continue pipeline on audio QC failure (insufficient muting)")
    selectors: List['Selector'] = Field(default_factory=list, description="Track selectors for filtering operations")
    profanity_list_file: str | None = Field(None, description="Path to JSON profanity list file for subtitle masking")
    fuzzy_threshold: float | None = Field(None, description="Similarity threshold (0-100) for fuzzy profanity matching")
    subtitle_mode: str = Field("masked_only", description="How to handle subtitles in remux: 'all', 'masked_only', or 'none'")
    create_subtitle_sidecar: bool = Field(False, description="Create sidecar subtitle files alongside remuxed video")
    sidecar_tag: str = Field("censorr", description="Tag to use in sidecar subtitle filenames (censorr or clean)")
    
    @model_validator(mode='after')
    def validate_flags(self):
        """Validate flag combinations and apply automatic adjustments."""
        # If max_jobs > 1, automatically enable parallel
        if self.max_jobs > 1:
            self.parallel = True
        
        # Force and skip_existing are mutually exclusive
        if self.force and self.skip_existing:
            raise ValueError("force and skip_existing flags cannot be used together")
        
        # Validate max_jobs is positive
        if self.max_jobs <= 0:
            raise ValueError("max_jobs must be a positive integer")
        
        return self


class Operation(ABC):
    """Base class for all pipeline operations."""
    
    def __init__(self, name: str):
        self.name = name
    
    @property
    @abstractmethod
    def consumes(self) -> Set[ArtifactType]:
        """Return the set of artifact types this operation consumes."""
        pass
    
    @property
    @abstractmethod
    def produces(self) -> Set[ArtifactType]:
        """Return the set of artifact types this operation produces."""
        pass
    
    @abstractmethod
    def run(
        self, 
        inputs: List[Artifact], 
        workdir: Path, 
        flags: OperationFlags
    ) -> List[Artifact]:
        """Execute the operation.
        
        Args:
            inputs: List of input artifacts
            workdir: Working directory for outputs
            flags: Execution flags
            
        Returns:
            List of produced artifacts
            
        Raises:
            ValueError: If required inputs are missing
            RuntimeError: If operation fails
        """
        pass
    
    def validate_inputs(self, inputs: List[Artifact]) -> None:
        """Validate that required inputs are present."""
        input_types = {artifact.type for artifact in inputs}
        if not self.consumes.issubset(input_types):
            missing = self.consumes - input_types
            raise ValueError(f"Missing required input types: {missing}")


class OperationResult(BaseModel):
    """Result of an operation execution."""
    
    operation: str = Field(..., description="Operation name")
    inputs: List[str] = Field(..., description="Input artifact paths")
    outputs: List[str] = Field(..., description="Output artifact paths")
    success: bool = Field(..., description="Whether operation succeeded")
    error: str = Field("", description="Error message if failed")
    logs: List[str] = Field(default_factory=list, description="Operation logs")


# Rebuild the model to resolve forward references
def _rebuild_models():
    """Rebuild models to resolve forward references."""
    try:
        from .selectors import Selector  # noqa: F401
        OperationFlags.model_rebuild()
    except ImportError:
        # Selector not available yet, will be rebuilt later
        pass

_rebuild_models()