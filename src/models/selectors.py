"""Selector models for filtering and prioritizing tracks."""
import re
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
    
    # Subtitle-specific title filtering fields
    title_include: List[str] = Field(default_factory=list, description="Include tracks with titles containing these substrings (SUBTITLE only)")
    title_exclude: List[str] = Field(default_factory=list, description="Exclude tracks with titles containing these substrings (SUBTITLE only)")
    title_regex: List[str] = Field(default_factory=list, description="Include tracks with titles matching these regex patterns (SUBTITLE only)")
    exclude_sdh: bool = Field(False, description="Exclude hearing-impaired/SDH tracks (SUBTITLE only)")
    
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
    
    @field_validator('title_include', 'title_exclude', 'title_regex')
    @classmethod
    def title_fields_only_for_subtitle(cls, v, info):
        """Ensure title fields are only used for SUBTITLE type."""
        if v and info.data.get('type') != ArtifactType.SUBTITLE:
            raise ValueError('title filtering fields are only valid for SUBTITLE type')
        return v
    
    @field_validator('exclude_sdh')
    @classmethod
    def exclude_sdh_only_for_subtitle(cls, v, info):
        """Ensure exclude_sdh field is only used for SUBTITLE type."""
        if v and info.data.get('type') != ArtifactType.SUBTITLE:
            raise ValueError('exclude_sdh field is only valid for SUBTITLE type')
        return v
    
    def _normalize_title(self, title: Optional[str]) -> str:
        """Normalize title for matching: case-insensitive, strip brackets/parens, collapse whitespace."""
        if not title:
            return ""
        
        # Remove surrounding brackets/parentheses and normalize
        normalized = re.sub(r'^[\[\(]*|[\]\)]*$', '', title.strip())
        normalized = re.sub(r'\s+', ' ', normalized).strip().lower()
        return normalized
    
    def _is_sdh_title(self, title: Optional[str]) -> bool:
        """Check if title indicates hearing-impaired/SDH content."""
        if not title:
            return False
        
        normalized = self._normalize_title(title)
        sdh_patterns = [
            'sdh', 'hi', 'cc', 'hearing impaired', 'closed captions',
            'deaf', 'hard of hearing', 'descriptive', 'audio description'
        ]
        
        return any(pattern in normalized for pattern in sdh_patterns)
    
    def _matches_title_filters(self, title: Optional[str]) -> bool:
        """Check if title matches include/exclude filters."""
        normalized_title = self._normalize_title(title)
        
        # Apply exclusions first (they take precedence)
        if self.title_exclude:
            for exclude_pattern in self.title_exclude:
                if exclude_pattern.lower() in normalized_title:
                    return False
        
        # Check SDH exclusion
        if self.exclude_sdh and self._is_sdh_title(title):
            return False
        
        # Apply inclusions
        if self.title_include:
            for include_pattern in self.title_include:
                if include_pattern.lower() in normalized_title:
                    return True
            # If includes are specified but none match, reject
            return False
        
        # Apply regex inclusions
        if self.title_regex:
            for regex_pattern in self.title_regex:
                try:
                    if re.search(regex_pattern, title or "", re.IGNORECASE):
                        return True
                except re.error:
                    # Invalid regex, skip
                    continue
            # If regex patterns are specified but none match, reject
            return False
        
        # If no title filters specified, accept (but may still be excluded by SDH)
        return True
    
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
        
        # Apply title filtering for subtitles
        if self.type == ArtifactType.SUBTITLE:
            title = artifact.metadata.get('title')
            if not self._matches_title_filters(title):
                return False
            
        return True