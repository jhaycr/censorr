"""Selector models for filtering and prioritizing tracks."""
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator
from .artifacts import ArtifactType


class Selector(BaseModel):
    """Unified selector for filtering tracks across all artifact types."""
    
    type: ArtifactType = Field(..., description="Artifact type to select")
    language: Optional[str] = Field(None, description="ISO 639-1 language code")
    role: Optional[str] = Field(None, description="Role (AUDIO only: main, commentary)")
    codec: Optional[str] = Field(None, description="Codec filter (AUDIO/VIDEO)")
    forced: Optional[bool] = Field(None, description="Forced flag (SUBTITLE only)")
    prefer: List[str] = Field(default_factory=list, description="Preference ranking hints")
    first_only: bool = Field(False, description="Select only first match")
    priority: int = Field(0, description="Selection priority (lower = higher priority)")
    
    @field_validator('forced')
    @classmethod
    def forced_only_for_subtitle(cls, v, info):
        """Ensure forced field is only used for SUBTITLE type."""
        if v is not None and info.data.get('type') != ArtifactType.SUBTITLE:
            raise ValueError('forced field is only valid for SUBTITLE type')
        return v
    
    @field_validator('role')
    @classmethod
    def role_only_for_audio(cls, v, info):
        """Ensure role field is only used for AUDIO type."""
        if v is not None and info.data.get('type') != ArtifactType.AUDIO:
            raise ValueError('role field is only valid for AUDIO type')
        return v
    
    def matches(self, artifact) -> bool:
        """Check if this selector matches the given artifact."""
        # Import here to avoid circular import
        from .artifacts import Artifact
        
        if not isinstance(artifact, Artifact):
            return False
            
        if artifact.type != self.type:
            return False
            
        if self.language and artifact.get_language() != self.language:
            return False
            
        if self.codec and artifact.get_codec() != self.codec:
            return False
            
        if self.forced is not None and artifact.is_forced() != self.forced:
            return False
            
        if self.role and artifact.metadata.get('role') != self.role:
            return False
            
        return True