"""Tests for core data models."""
import pytest
from pathlib import Path
from src.models.artifacts import Artifact, ArtifactType
from src.models.selectors import Selector
from src.models.operations import Operation, OperationFlags
from src.models.common import MuteWindow, AuditLogEntry


class TestArtifact:
    """Test Artifact model."""
    
    def test_artifact_creation(self):
        """Test basic artifact creation."""
        artifact = Artifact(
            type=ArtifactType.VIDEO,
            path="/test/movie.mkv",
            metadata={"codec": "h264", "language": "en"}
        )
        assert artifact.type == ArtifactType.VIDEO
        assert artifact.path == "/test/movie.mkv"
        assert artifact.metadata["codec"] == "h264"
    
    def test_subtitle_artifact_requires_language(self):
        """Test that subtitle artifacts must have language."""
        with pytest.raises(ValueError, match="SUBTITLE artifacts must have language"):
            Artifact(
                type=ArtifactType.SUBTITLE,
                path="/test/subs.srt",
                metadata={"format": "srt"}
            )
    
    def test_subtitle_artifact_with_language(self):
        """Test subtitle artifact with proper language."""
        artifact = Artifact(
            type=ArtifactType.SUBTITLE,
            path="/test/subs.srt",
            metadata={"language": "en", "format": "srt", "forced": False}
        )
        assert artifact.metadata["language"] == "en"
        assert artifact.metadata["forced"] is False


class TestSelector:
    """Test Selector model."""
    
    def test_selector_creation(self):
        """Test basic selector creation."""
        selector = Selector(
            type=ArtifactType.SUBTITLE,
            language="en",
            forced=False,
            priority=0
        )
        assert selector.type == ArtifactType.SUBTITLE
        assert selector.language == "en"
        assert selector.forced is False
    
    def test_selector_audio_with_role(self):
        """Test audio selector with role field."""
        selector = Selector(
            type=ArtifactType.AUDIO,
            language="en",
            role="main",
            priority=0
        )
        assert selector.role == "main"
    
    def test_selector_invalid_field_for_type(self):
        """Test that invalid fields for type are rejected."""
        with pytest.raises(ValueError, match="forced field is only valid for SUBTITLE"):
            Selector(
                type=ArtifactType.AUDIO,
                language="en",
                forced=True,
                priority=0
            )


class TestOperation:
    """Test Operation base class."""
    
    def test_operation_flags(self):
        """Test operation flags creation."""
        flags = OperationFlags(dry_run=True, verbose=True)
        assert flags.dry_run is True
        assert flags.verbose is True
    
    def test_operation_flags_defaults(self):
        """Test operation flags defaults."""
        flags = OperationFlags()
        assert flags.dry_run is False
        assert flags.verbose is False


class TestMuteWindow:
    """Test MuteWindow model."""
    
    def test_mute_window_creation(self):
        """Test basic mute window creation."""
        window = MuteWindow(
            start=10.5,
            end=15.2,
            reason="profanity detected",
            source="SUBTITLE"
        )
        assert window.start == 10.5
        assert window.end == 15.2
        assert window.reason == "profanity detected"
    
    def test_mute_window_validation(self):
        """Test mute window validation."""
        with pytest.raises(ValueError, match="start must be less than end"):
            MuteWindow(
                start=15.0,
                end=10.0,
                reason="test",
                source="SUBTITLE"
            )
    
    def test_mute_window_negative_start(self):
        """Test mute window rejects negative start."""
        with pytest.raises(ValueError, match="start must be >= 0"):
            MuteWindow(
                start=-5.0,
                end=10.0,
                reason="test",
                source="SUBTITLE"
            )


class TestAuditLogEntry:
    """Test AuditLogEntry model."""
    
    def test_audit_log_entry_creation(self):
        """Test audit log entry creation."""
        entry = AuditLogEntry(
            op="mask_subtitles",
            level="info",
            message="Masked 3 profane words",
            details={"words_masked": 3, "total_cues": 50}
        )
        assert entry.op == "mask_subtitles"
        assert entry.level == "info"
        assert entry.details["words_masked"] == 3