"""Tests for filename parsing and sidecar naming utilities."""
import pytest
import tempfile
import os
from pathlib import Path
from src.utils.filename_utils import (
    parse_title_and_edition,
    ensure_movie_edition_tag,
    is_episode_filename,
    build_sidecar_subtitle_path,
    handle_sidecar_collision
)


class TestFilenameUtils:
    """Test filename parsing utilities."""
    
    def test_parse_title_and_edition_no_existing_tag(self):
        """Test parsing filename with no existing edition tag."""
        cases = [
            "Movie Title (2024).mkv",
            "Another Movie (2021) BluRay.mp4",
            "/path/to/Simple Title.avi",
        ]
        
        for filename in cases:
            base_title, edition = parse_title_and_edition(filename)
            assert edition is None
            # Should return the stem without extension
            expected = Path(filename).stem
            assert base_title == expected
    
    def test_parse_title_and_edition_with_existing_tag(self):
        """Test parsing filename with existing edition tag."""
        cases = [
            ("Movie (2024) {edition-Director's Cut}.mkv", "Movie (2024)", "Director's Cut"),
            ("Film {edition-Extended}.mp4", "Film", "Extended"),
            ("Title (2021) {edition-Unrated} BluRay.avi", "Title (2021) BluRay", "Unrated"),
            ("Movie {EDITION-REMASTERED}.mkv", "Movie", "REMASTERED"),  # Case insensitive
        ]
        
        for filename, expected_base, expected_edition in cases:
            base_title, edition = parse_title_and_edition(filename)
            assert base_title == expected_base
            assert edition == expected_edition
    
    def test_ensure_movie_edition_tag_no_existing(self):
        """Test adding edition tag when none exists."""
        cases = [
            ("Movie (2024).mkv", "Movie (2024) {edition-Censorr}.mkv"),
            ("Simple Title.mp4", "Simple Title {edition-Censorr}.mp4"),
            ("/path/Film (2021) BluRay.avi", "/path/Film (2021) {edition-Censorr} BluRay.avi"),
        ]
        
        for input_path, expected in cases:
            result = ensure_movie_edition_tag(input_path)
            assert result == expected
    
    def test_ensure_movie_edition_tag_with_existing(self):
        """Test idempotency - no change when edition tag already exists."""
        files_with_editions = [
            "Movie (2024) {edition-Director's Cut}.mkv",
            "Film {edition-Extended}.mp4",
            "/path/Title {edition-Unrated}.avi",
        ]
        
        for filename in files_with_editions:
            result = ensure_movie_edition_tag(filename)
            assert result == filename  # Should be unchanged
    
    def test_ensure_movie_edition_tag_custom_tag(self):
        """Test using custom edition tag."""
        result = ensure_movie_edition_tag("Movie (2024).mkv", "Clean")
        assert result == "Movie (2024) {edition-Clean}.mkv"
    
    def test_is_episode_filename(self):
        """Test episode detection patterns."""
        episode_cases = [
            "Show Name - S01E03.mkv",
            "Series S1E1.mp4", 
            "TV Show Season 1 Episode 5.avi",
            "Show.S02E10.BluRay.mkv",
            "Series 1x05.mp4",
        ]
        
        movie_cases = [
            "Movie Title (2024).mkv",
            "Film Name.mp4",
            "Documentary.avi",
        ]
        
        for filename in episode_cases:
            assert is_episode_filename(filename), f"Should detect episode: {filename}"
        
        for filename in movie_cases:
            assert not is_episode_filename(filename), f"Should not detect episode: {filename}"
    
    def test_build_sidecar_subtitle_path(self):
        """Test sidecar subtitle path generation."""
        cases = [
            ("Movie (2024).mkv", "en", "censorr", "Movie (2024).en.censorr.srt"),
            ("/path/Film Title.mp4", "es", "clean", "/path/Film Title.es.clean.srt"),
            ("Movie (2021) {edition-Extended}.avi", "EN", "censorr", "Movie (2021).en.censorr.srt"),  # Edition stripped, language lowercased
        ]
        
        for video_path, lang, tag, expected in cases:
            result = build_sidecar_subtitle_path(video_path, lang, tag)
            assert result == expected
    
    def test_build_sidecar_subtitle_path_normalization(self):
        """Test title normalization in sidecar paths."""
        # Test whitespace normalization
        result = build_sidecar_subtitle_path("Movie   With   Spaces.mkv", "en", "censorr")
        assert result == "Movie With Spaces.en.censorr.srt"
        
        # Test language lowercasing
        result = build_sidecar_subtitle_path("Movie.mkv", "EN", "censorr")
        assert result == "Movie.en.censorr.srt"


class TestSidecarCollisionHandling:
    """Test sidecar file collision handling."""
    
    def test_handle_sidecar_collision_no_existing_file(self):
        """Test when target file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = os.path.join(tmpdir, "movie.en.censorr.srt")
            result = handle_sidecar_collision(target_path, "dummy_checksum")
            assert result == target_path
    
    def test_handle_sidecar_collision_identical_content(self):
        """Test when existing file has identical content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = os.path.join(tmpdir, "movie.en.censorr.srt")
            content = b"Test subtitle content"
            
            # Create existing file
            with open(target_path, 'wb') as f:
                f.write(content)
            
            # Calculate checksum of same content
            import hashlib
            checksum = hashlib.md5(content).hexdigest()
            
            result = handle_sidecar_collision(target_path, checksum)
            assert result == target_path  # Should reuse existing
    
    def test_handle_sidecar_collision_different_content(self):
        """Test when existing file has different content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = os.path.join(tmpdir, "movie.en.censorr.srt")
            
            # Create existing file with different content
            with open(target_path, 'w') as f:
                f.write("Different content")
            
            # Try to write with different checksum
            result = handle_sidecar_collision(target_path, "different_checksum")
            
            # Should get numbered version
            expected = os.path.join(tmpdir, "movie.en.censorr-2.srt")
            assert result == expected
    
    def test_handle_sidecar_collision_multiple_collisions(self):
        """Test handling multiple numbered collisions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = os.path.join(tmpdir, "movie.en.censorr.srt")
            
            # Create several existing files
            for i in range(1, 4):  # Create base, -2, -3
                if i == 1:
                    path = base_path
                else:
                    path = os.path.join(tmpdir, f"movie.en.censorr-{i}.srt")
                
                with open(path, 'w') as f:
                    f.write(f"Content {i}")
            
            # Try to add another with different content
            result = handle_sidecar_collision(base_path, "new_checksum")
            
            # Should get -4 version
            expected = os.path.join(tmpdir, "movie.en.censorr-4.srt")
            assert result == expected
    
    def test_handle_sidecar_collision_find_matching_numbered(self):
        """Test finding matching content in numbered collision."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = os.path.join(tmpdir, "movie.en.censorr.srt")
            content = b"Matching content"
            
            # Create base file with different content
            with open(base_path, 'w') as f:
                f.write("Different content")
            
            # Create -2 file with matching content
            numbered_path = os.path.join(tmpdir, "movie.en.censorr-2.srt")
            with open(numbered_path, 'wb') as f:
                f.write(content)
            
            # Try to write same content - should find the -2 file
            import hashlib
            checksum = hashlib.md5(content).hexdigest()
            result = handle_sidecar_collision(base_path, checksum)
            assert result == numbered_path


class TestEdgeCase:
    """Test edge cases and error conditions."""
    
    def test_parse_title_malformed_edition_tag(self):
        """Test handling malformed edition tags."""
        cases = [
            "Movie {edition-}.mkv",  # Empty edition
            "Movie {edition.mkv",    # Unclosed brace
            "Movie edition-test}.mkv",  # No opening brace
        ]
        
        for filename in cases:
            base_title, edition = parse_title_and_edition(filename)
            # Should not detect malformed tags as editions
            assert edition is None
            assert base_title == Path(filename).stem
    
    def test_whitespace_normalization(self):
        """Test that whitespace is properly normalized."""
        test_cases = [
            "Movie   With    Lots   Of   Spaces",
            "  Leading and trailing  ",
            "Movie\t\nWith\tWeird\nWhitespace",
        ]
        
        for title in test_cases:
            # Test in context of edition tag addition
            path = f"{title}.mkv"
            result = ensure_movie_edition_tag(path)
            
            # Result should have normalized whitespace
            base_part = result.replace("{edition-Censorr}", "").replace(".mkv", "").strip()
            assert "   " not in base_part  # No triple spaces
            assert not base_part.startswith(" ")  # No leading space
            assert not base_part.endswith(" ")   # No trailing space