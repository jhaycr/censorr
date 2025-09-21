"""Common data structures used across the censorr package."""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field, field_validator


class MuteWindow(BaseModel):
    """Represents a time window where audio should be muted."""
    
    start: float = Field(..., description="Start time in seconds")
    end: float = Field(..., description="End time in seconds")
    reason: str = Field(..., description="Reason for muting")
    source: str = Field(..., description="Source of the mute window (SUBTITLE|EXTERNAL)")
    
    @field_validator('start')
    @classmethod
    def start_must_be_positive(cls, v):
        if v < 0:
            raise ValueError('start must be >= 0')
        return v
    
    @field_validator('end')
    @classmethod
    def end_must_be_after_start(cls, v, info):
        if 'start' in info.data and v <= info.data['start']:
            raise ValueError('start must be less than end')
        return v


class LogLevel(str, Enum):
    """Log levels for audit entries."""
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


class AuditLogEntry(BaseModel):
    """Represents an entry in the audit log."""
    
    op: str = Field(..., description="Operation name")
    time: datetime = Field(default_factory=datetime.now, description="Timestamp")
    level: LogLevel = Field(..., description="Log level")
    message: str = Field(..., description="Log message")
    details: Dict[str, Any] = Field(default_factory=dict, description="Additional details")


class ManifestEntry(BaseModel):
    """Represents an entry in the operation manifest for caching."""
    
    op: str = Field(..., description="Operation name")
    inputs: list[Dict[str, str]] = Field(..., description="Input artifacts with checksums")
    outputs: list[Dict[str, str]] = Field(..., description="Output artifacts with checksums")
    params: Dict[str, Any] = Field(default_factory=dict, description="Operation parameters")
    timestamp: datetime = Field(default_factory=datetime.now, description="Execution timestamp")