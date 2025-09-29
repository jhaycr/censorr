"""Unit tests for subtitle title filtering in selectors."""
import pytest
from src.models.artifacts import Artifact, ArtifactType
from src.models.selectors import Selector


class TestSubtitleTitleFiltering:
    """Test subtitle title filtering functionality."""
    
    def test_null_empty_title_considered_main(self):
        """Test that null/empty titles are considered as main/full tracks."""
        selector = Selector(type=ArtifactType.SUBTITLE, language="en")
        
        # Null title artifact
        artifact_null = Artifact(
            type=ArtifactType.SUBTITLE,
            path="/test.srt",
            metadata={"language": "en", "title": None}
        )
        
        # Empty title artifact
        artifact_empty = Artifact(
            type=ArtifactType.SUBTITLE,
            path="/test2.srt", 
            metadata={"language": "en", "title": ""}
        )
        
        # Both should match (considered main/full)
        assert selector.matches(artifact_null)
        assert selector.matches(artifact_empty)
    
    def test_include_forced_and_full(self):
        """Test including both forced and full subtitle tracks."""
        selector = Selector(
            type=ArtifactType.SUBTITLE,
            language="en",
            title_include=["forced"],  # Include tracks with "forced" in title
        )
        
        # Full track (empty title, should match as main/full)
        full_track = Artifact(
            type=ArtifactType.SUBTITLE,
            path="/full.srt",
            metadata={"language": "en", "title": "", "forced": False}
        )
        
        # Forced track (has "forced" in title)
        forced_track = Artifact(
            type=ArtifactType.SUBTITLE, 
            path="/forced.srt",
            metadata={"language": "en", "title": "English Forced", "forced": True}
        )
        
        # Commentary track (should not match)
        commentary_track = Artifact(
            type=ArtifactType.SUBTITLE,
            path="/commentary.srt",
            metadata={"language": "en", "title": "Commentary", "forced": False}
        )
        
        # Only forced track should match (full track doesn't have "forced" in title)
        assert not selector.matches(full_track)  # No "forced" in empty title
        assert selector.matches(forced_track)
        assert not selector.matches(commentary_track)
    
    def test_exclude_sdh_synonyms(self):
        """Test exclusion of SDH/HI synonym tracks using title_exclude patterns."""
        selector = Selector(
            type=ArtifactType.SUBTITLE,
            language="en",
            title_exclude=["sdh", "hi", "cc", "hearing impaired", "closed captions"]
        )
        
        test_cases = [
            ("English", True),  # Normal track should match
            ("English [SDH]", False),  # SDH should be excluded
            ("English (HI)", False),  # HI should be excluded  
            ("English CC", False),  # CC should be excluded
            ("English Hearing Impaired", False),  # Full phrase should be excluded
            ("English Closed Captions", False),  # Full phrase should be excluded
            ("", True),  # Empty title should match (main/full)
        ]
        
        for title, should_match in test_cases:
            artifact = Artifact(
                type=ArtifactType.SUBTITLE,
                path=f"/test_{title.replace(' ', '_').replace('[', '').replace(']', '')}.srt",
                metadata={"language": "en", "title": title}
            )
            assert selector.matches(artifact) == should_match, f"Failed for title: '{title}'"
    
    def test_regex_include(self):
        """Test regex pattern inclusion."""
        selector = Selector(
            type=ArtifactType.SUBTITLE,
            language="en",
            title_regex=[r"English\s+(Forced|Full)"]
        )
        
        test_cases = [
            ("English Forced", True),
            ("English Full", True), 
            ("English SDH", False),
            ("French Forced", False),  # Wrong language in title
            ("", False),  # Empty doesn't match regex
        ]
        
        for title, should_match in test_cases:
            artifact = Artifact(
                type=ArtifactType.SUBTITLE,
                path=f"/test_{title.replace(' ', '_')}.srt",
                metadata={"language": "en", "title": title}
            )
            assert selector.matches(artifact) == should_match, f"Failed for title: '{title}'"
    
    def test_exclude_precedence_over_include(self):
        """Test that exclusion takes precedence over inclusion."""
        selector = Selector(
            type=ArtifactType.SUBTITLE,
            language="en",
            title_include=["English"],  # Include anything with "English"
            title_exclude=["SDH"]  # But exclude anything with "SDH"
        )
        
        # Should match: has "English" but not "SDH"
        normal_track = Artifact(
            type=ArtifactType.SUBTITLE,
            path="/normal.srt",
            metadata={"language": "en", "title": "English"}
        )
        
        # Should NOT match: has "English" but also "SDH" (exclusion wins)
        sdh_track = Artifact(
            type=ArtifactType.SUBTITLE,
            path="/sdh.srt", 
            metadata={"language": "en", "title": "English SDH"}
        )
        
        assert selector.matches(normal_track)
        assert not selector.matches(sdh_track)
    
    def test_case_insensitive_matching(self):
        """Test that title matching is case-insensitive."""
        selector = Selector(
            type=ArtifactType.SUBTITLE,
            language="en",
            title_include=["forced"]
        )
        
        test_cases = [
            "FORCED",
            "Forced", 
            "forced",
            "English FORCED",
            "english forced",
        ]
        
        for title in test_cases:
            artifact = Artifact(
                type=ArtifactType.SUBTITLE,
                path=f"/test_{title.replace(' ', '_')}.srt",
                metadata={"language": "en", "title": title}
            )
            assert selector.matches(artifact), f"Failed for case-insensitive title: '{title}'"
    
    def test_title_normalization(self):
        """Test title normalization (brackets, whitespace) using title_exclude patterns."""
        selector = Selector(
            type=ArtifactType.SUBTITLE,
            language="en", 
            title_exclude=["sdh"]
        )
        
        # These should all be detected as SDH despite formatting differences
        sdh_variants = [
            "[SDH]",
            "(SDH)",
            "  [  SDH  ]  ",
            "[SDH",  # Missing closing bracket
            "SDH]",  # Missing opening bracket
        ]
        
        for title in sdh_variants:
            artifact = Artifact(
                type=ArtifactType.SUBTITLE,
                path=f"/test_{hash(title)}.srt",
                metadata={"language": "en", "title": title}
            )
            # All should be excluded (not match) due to SDH detection
            assert not selector.matches(artifact), f"Failed to exclude SDH variant: '{title}'"
    
    def test_invalid_regex_handling(self):
        """Test graceful handling of invalid regex patterns."""
        selector = Selector(
            type=ArtifactType.SUBTITLE,
            language="en",
            title_regex=["[invalid", "valid.*pattern"]  # First regex is invalid
        )
        
        # Should match the valid pattern
        artifact_match = Artifact(
            type=ArtifactType.SUBTITLE,
            path="/match.srt",
            metadata={"language": "en", "title": "valid test pattern"}
        )
        
        # Should not match either pattern
        artifact_no_match = Artifact(
            type=ArtifactType.SUBTITLE,
            path="/no_match.srt", 
            metadata={"language": "en", "title": "completely different"}
        )
        
        # Invalid regex should be skipped, valid one should work
        assert selector.matches(artifact_match)
        assert not selector.matches(artifact_no_match)


class TestSelectorValidation:
    """Test selector field validation."""
    
    def test_title_fields_only_for_subtitle(self):
        """Test that title fields are only valid for SUBTITLE type."""
        # These should work for SUBTITLE
        Selector(
            type=ArtifactType.SUBTITLE,
            title_include=["forced"]
        )
        
        # These should fail for other types
        with pytest.raises(ValueError, match="title filtering fields are only valid for SUBTITLE type"):
            Selector(
                type=ArtifactType.AUDIO,
                title_include=["test"]
            )
        
        with pytest.raises(ValueError, match="title filtering fields are only valid for SUBTITLE type"):
            Selector(
                type=ArtifactType.VIDEO,
                title_exclude=["test"]
            )
    

