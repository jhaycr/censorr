"""Tests for subtitle parser utilities."""
import pytest
from pathlib import Path
import tempfile
from datetime import timedelta
from src.utils.subtitle_parser import SubtitleParser, SubtitleEntry, SubtitleError
from src.models.common import MuteWindow


class TestSubtitleParser:
    """Test SubtitleParser."""
    
    def test_parser_creation(self):
        """Test subtitle parser creation."""
        parser = SubtitleParser()
        assert parser is not None
    
    def test_parse_srt_file(self):
        """Test parsing SRT subtitle file."""
        srt_content = """1
00:00:01,000 --> 00:00:03,000
Hello world

2
00:00:05,500 --> 00:00:07,200
This is a test

3
00:00:10,000 --> 00:00:12,500
Some profanity here damn it
"""
        
        parser = SubtitleParser()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False) as tmp:
            tmp.write(srt_content)
            tmp.flush()
            
            entries = parser.parse_file(tmp.name)
            
            assert len(entries) == 3
            
            # Check first entry
            assert entries[0].index == 1
            assert entries[0].start == 1.0
            assert entries[0].end == 3.0
            assert entries[0].text == "Hello world"
            assert entries[0].normalized_text == "hello world"
            
            # Check second entry
            assert entries[1].index == 2
            assert entries[1].start == 5.5
            assert entries[1].end == 7.2
            assert entries[1].text == "This is a test"
            
            # Check third entry
            assert entries[2].index == 3
            assert entries[2].start == 10.0
            assert entries[2].end == 12.5
            assert "profanity" in entries[2].text.lower()
    
    def test_parse_vtt_file(self):
        """Test parsing VTT subtitle file."""
        vtt_content = """WEBVTT

00:01.000 --> 00:03.000
Hello world

00:05.500 --> 00:07.200
This is a test
"""
        
        parser = SubtitleParser()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.vtt', delete=False) as tmp:
            tmp.write(vtt_content)
            tmp.flush()
            
            entries = parser.parse_file(tmp.name)
            
            assert len(entries) == 2
            assert entries[0].text == "Hello world"
            assert entries[1].text == "This is a test"
    
    def test_parse_nonexistent_file(self):
        """Test parsing non-existent file."""
        parser = SubtitleParser()
        
        with pytest.raises(SubtitleError, match="File not found"):
            parser.parse_file("/nonexistent/file.srt")
    
    def test_parse_invalid_format(self):
        """Test parsing invalid subtitle format."""
        invalid_content = "This is not a valid subtitle file"
        
        parser = SubtitleParser()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as tmp:
            tmp.write(invalid_content)
            tmp.flush()
            
            with pytest.raises(SubtitleError, match="Unsupported subtitle format"):
                parser.parse_file(tmp.name)
    
    def test_normalize_text(self):
        """Test text normalization."""
        parser = SubtitleParser()
        
        # Test basic normalization
        assert parser.normalize_text("Hello World!") == "hello world"
        assert parser.normalize_text("  Multiple   Spaces  ") == "multiple spaces"
        assert parser.normalize_text("Special-Characters_123") == "special characters"
        assert parser.normalize_text("") == ""
        
        # Test Unicode handling
        assert parser.normalize_text("Café résumé") == "cafe resume"
        assert parser.normalize_text("naïve") == "naive"
    
    def test_extract_timing_info(self):
        """Test extracting timing information."""
        parser = SubtitleParser()
        
        entries = [
            SubtitleEntry(index=1, start=1.0, end=3.0, text="Hello", normalized_text="hello"),
            SubtitleEntry(index=2, start=5.0, end=7.0, text="World", normalized_text="world"),
            SubtitleEntry(index=3, start=10.0, end=12.0, text="Test", normalized_text="test")
        ]
        
        timing_info = parser.extract_timing_info(entries)
        
        assert timing_info["total_duration"] == 12.0
        assert timing_info["subtitle_count"] == 3
        assert timing_info["first_subtitle"] == 1.0
        assert timing_info["last_subtitle"] == 12.0
        assert timing_info["coverage_percentage"] == pytest.approx(50.0, rel=1e-2)  # 6/12 seconds
    
    def test_filter_by_text(self):
        """Test filtering entries by text content."""
        parser = SubtitleParser()
        
        entries = [
            SubtitleEntry(index=1, start=1.0, end=3.0, text="Hello world", normalized_text="hello world"),
            SubtitleEntry(index=2, start=5.0, end=7.0, text="Damn profanity", normalized_text="damn profanity"),
            SubtitleEntry(index=3, start=10.0, end=12.0, text="Clean text", normalized_text="clean text"),
            SubtitleEntry(index=4, start=15.0, end=17.0, text="More damn words", normalized_text="more damn words")
        ]
        
        # Filter for entries containing profanity
        filtered = parser.filter_by_text(entries, lambda text: "damn" in text.lower())
        
        assert len(filtered) == 2
        assert filtered[0].index == 2
        assert filtered[1].index == 4
    
    def test_create_mute_windows_from_entries(self):
        """Test creating mute windows from subtitle entries."""
        parser = SubtitleParser()
        
        entries = [
            SubtitleEntry(index=1, start=1.0, end=3.0, text="Clean text", normalized_text="clean text"),
            SubtitleEntry(index=2, start=5.0, end=7.0, text="Profanity damn", normalized_text="profanity damn"),
            SubtitleEntry(index=3, start=10.0, end=12.0, text="More clean text", normalized_text="more clean text"),
            SubtitleEntry(index=4, start=15.0, end=17.0, text="Shit happens", normalized_text="shit happens")
        ]
        
        # Create mute windows for entries containing profanity
        mute_windows = parser.create_mute_windows_from_entries(
            entries,
            lambda text: any(word in text.lower() for word in ["damn", "shit"]),
            reason="profanity"
        )
        
        assert len(mute_windows) == 2
        
        # Check first mute window
        assert mute_windows[0].start == 5.0
        assert mute_windows[0].end == 7.0
        assert mute_windows[0].reason == "profanity"
        assert mute_windows[0].source == "SUBTITLE"
        
        # Check second mute window
        assert mute_windows[1].start == 15.0
        assert mute_windows[1].end == 17.0
        assert mute_windows[1].reason == "profanity"
        assert mute_windows[1].source == "SUBTITLE"


class TestSubtitleEntry:
    """Test SubtitleEntry model."""
    
    def test_subtitle_entry_creation(self):
        """Test SubtitleEntry creation."""
        entry = SubtitleEntry(
            index=1,
            start=1.5,
            end=3.0,
            text="Hello world",
            normalized_text="hello world"
        )
        
        assert entry.index == 1
        assert entry.start == 1.5
        assert entry.end == 3.0
        assert entry.text == "Hello world"
        assert entry.normalized_text == "hello world"
    
    def test_subtitle_entry_duration(self):
        """Test subtitle entry duration calculation."""
        entry = SubtitleEntry(index=1, start=2.5, end=5.0, text="Test", normalized_text="test")
        assert entry.duration == 2.5
    
    def test_subtitle_entry_validation(self):
        """Test subtitle entry validation."""
        # Valid entry
        entry = SubtitleEntry(index=1, start=1.0, end=3.0, text="Test", normalized_text="test")
        assert entry.start < entry.end
        
        # Test that we can create entries with equal start/end (though unusual)
        entry2 = SubtitleEntry(index=2, start=5.0, end=5.0, text="Instant", normalized_text="instant")
        assert entry2.duration == 0.0


class TestSubtitleUtils:
    """Test subtitle utility functions."""
    
    def test_normalize_text_edge_cases(self):
        """Test text normalization edge cases."""
        parser = SubtitleParser()
        
        # Empty and whitespace
        assert parser.normalize_text("") == ""
        assert parser.normalize_text("   ") == ""
        assert parser.normalize_text("\n\t\r") == ""
        
        # HTML entities and tags
        assert parser.normalize_text("&amp; &lt; &gt;") == "and"
        assert parser.normalize_text("<i>italic</i> text") == "italic text"
        
        # Numbers and punctuation
        assert parser.normalize_text("Test 123, punctuation!") == "test punctuation"
        assert parser.normalize_text("one-two_three") == "one two three"
    
    def test_timing_edge_cases(self):
        """Test timing calculation edge cases."""
        parser = SubtitleParser()
        
        # Empty list
        timing_info = parser.extract_timing_info([])
        assert timing_info["total_duration"] == 0.0
        assert timing_info["subtitle_count"] == 0
        
        # Single entry
        entries = [SubtitleEntry(index=1, start=1.0, end=3.0, text="Single", normalized_text="single")]
        timing_info = parser.extract_timing_info(entries)
        assert timing_info["total_duration"] == 3.0
        assert timing_info["subtitle_count"] == 1
        assert timing_info["coverage_percentage"] == pytest.approx(66.67, rel=1e-2)  # 2/3 seconds