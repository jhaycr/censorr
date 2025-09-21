"""Artifact models for representing media components."""
from enum import Enum
from typing import Any, Dict, Optional
from pathlib import Path
from pydantic import BaseModel, Field, field_validator


class ArtifactType(str, Enum):
    """Types of artifacts in the pipeline."""
    VIDEO = "VIDEO"
    AUDIO = "AUDIO"
    SUBTITLE = "SUBTITLE"
    SIDECAR = "SIDECAR"


class Artifact(BaseModel):
    """Represents a media artifact (video, audio, or subtitle file)."""
    
    type: ArtifactType = Field(..., description="Type of artifact")
    path: str = Field(..., description="File path (absolute or workdir-relative)")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Artifact metadata")
    
    @field_validator('metadata')
    @classmethod
    def validate_subtitle_has_language(cls, v, info):
        """Ensure SUBTITLE artifacts have language metadata."""
        if info.data.get('type') == ArtifactType.SUBTITLE:
            if 'language' not in v:
                raise ValueError('SUBTITLE artifacts must have language in metadata')
        return v
    
    def get_language(self) -> Optional[str]:
        """Get the language code for this artifact."""
        return self.metadata.get('language')
    
    def get_codec(self) -> Optional[str]:
        """Get the codec/format for this artifact."""
        return self.metadata.get('codec') or self.metadata.get('format')
    
    def get_title(self) -> Optional[str]:
        """Get the display title for this artifact."""
        return self.metadata.get('title')
    
    def is_forced(self) -> bool:
        """Check if this is a forced subtitle track."""
        return self.type == ArtifactType.SUBTITLE and self.metadata.get('forced', False)