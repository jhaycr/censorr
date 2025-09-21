"""Subtitle parsing utilities using pysubs2.

Provides utilities for:
- Parsing various subtitle formats (SRT, VTT, ASS, etc.)
- Normalizing subtitle text for analysis
- Extracting timing information
- Creating mute windows from subtitle content
"""
import re
import unicodedata
from pathlib import Path
from typing import List, Callable, Optional, Dict, Any
from pydantic import BaseModel, Field
import pysubs2
from src.models.common import MuteWindow


class SubtitleError(Exception):
    """Exception raised for subtitle-related errors."""
    pass


class SubtitleEntry(BaseModel):
    """A single subtitle entry with timing and text."""
    index: int = Field(..., description="Subtitle index/number")
    start: float = Field(..., description="Start time in seconds")
    end: float = Field(..., description="End time in seconds")
    text: str = Field(..., description="Original subtitle text")
    normalized_text: str = Field(..., description="Normalized text for analysis")
    
    @property
    def duration(self) -> float:
        """Get the duration of this subtitle entry."""
        return max(0.0, self.end - self.start)


class SubtitleParser:
    """Parser for subtitle files using pysubs2."""
    
    def __init__(self):
        """Initialize subtitle parser."""
        pass
    
    def parse_file(self, file_path: str) -> List[SubtitleEntry]:
        """Parse subtitle file and return entries.
        
        Args:
            file_path: Path to subtitle file
            
        Returns:
            List of SubtitleEntry objects
            
        Raises:
            SubtitleError: If parsing fails
        """
        path = Path(file_path)
        
        if not path.exists():
            raise SubtitleError(f"File not found: {file_path}")
        
        try:
            # Load subtitle file using pysubs2
            subs = pysubs2.load(file_path)
            
            entries = []
            for i, line in enumerate(subs, 1):
                # Convert milliseconds to seconds
                start_sec = line.start / 1000.0
                end_sec = line.end / 1000.0
                
                # Clean up text (remove SSA/ASS formatting)
                clean_text = self._clean_subtitle_text(line.text)
                normalized_text = self.normalize_text(clean_text)
                
                entry = SubtitleEntry(
                    index=i,
                    start=start_sec,
                    end=end_sec,
                    text=clean_text,
                    normalized_text=normalized_text
                )
                entries.append(entry)
            
            return entries
            
        except Exception as e:
            # Check if it's a format issue
            if "unsupported" in str(e).lower() or "format" in str(e).lower():
                raise SubtitleError(f"Unsupported subtitle format: {file_path}")
            else:
                raise SubtitleError(f"Failed to parse subtitle file: {e}")
    
    def normalize_text(self, text: str) -> str:
        """Normalize text for analysis.
        
        Args:
            text: Raw text to normalize
            
        Returns:
            Normalized text (lowercase, no punctuation, etc.)
        """
        if not text:
            return ""
        
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        
        # Handle HTML entities
        html_entities = {
            '&amp;': 'and',
            '&lt;': '',
            '&gt;': '',
            '&quot;': '',
            '&#39;': '',
            '&nbsp;': ' '
        }
        for entity, replacement in html_entities.items():
            text = text.replace(entity, replacement)
        
        # Normalize Unicode characters (remove accents)
        text = unicodedata.normalize('NFD', text)
        text = ''.join(char for char in text if unicodedata.category(char) != 'Mn')
        
        # Convert to lowercase
        text = text.lower()
        
        # Remove punctuation and numbers, replace with spaces
        text = re.sub(r'[^\w\s]', ' ', text)
        text = re.sub(r'_', ' ', text)  # Handle underscores specifically
        text = re.sub(r'\d+', '', text)
        
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def extract_timing_info(self, entries: List[SubtitleEntry]) -> Dict[str, float]:
        """Extract timing information from subtitle entries.
        
        Args:
            entries: List of subtitle entries
            
        Returns:
            Dictionary with timing statistics
        """
        if not entries:
            return {
                "total_duration": 0.0,
                "subtitle_count": 0,
                "first_subtitle": 0.0,
                "last_subtitle": 0.0,
                "coverage_percentage": 0.0
            }
        
        # Calculate coverage (total subtitle duration vs total time span)
        total_subtitle_duration = sum(entry.duration for entry in entries)
        first_subtitle = min(entry.start for entry in entries)
        last_subtitle = max(entry.end for entry in entries)
        total_duration = last_subtitle
        
        coverage_percentage = 0.0
        if total_duration > 0:
            coverage_percentage = (total_subtitle_duration / total_duration) * 100
        
        return {
            "total_duration": total_duration,
            "subtitle_count": len(entries),
            "first_subtitle": first_subtitle,
            "last_subtitle": last_subtitle,
            "coverage_percentage": coverage_percentage
        }
    
    def filter_by_text(self, entries: List[SubtitleEntry], 
                      filter_func: Callable[[str], bool]) -> List[SubtitleEntry]:
        """Filter subtitle entries by text content.
        
        Args:
            entries: List of subtitle entries
            filter_func: Function that takes normalized text and returns bool
            
        Returns:
            Filtered list of entries
        """
        return [entry for entry in entries if filter_func(entry.normalized_text)]
    
    def create_mute_windows_from_entries(self, entries: List[SubtitleEntry],
                                       filter_func: Callable[[str], bool],
                                       reason: str = "content",
                                       padding: float = 0.0) -> List[MuteWindow]:
        """Create mute windows from subtitle entries.
        
        Args:
            entries: List of subtitle entries
            filter_func: Function to determine which entries to mute
            reason: Reason for muting
            padding: Additional padding around mute window (seconds)
            
        Returns:
            List of MuteWindow objects
        """
        filtered_entries = self.filter_by_text(entries, filter_func)
        
        mute_windows = []
        for entry in filtered_entries:
            start_time = max(0.0, entry.start - padding)
            end_time = entry.end + padding
            
            mute_window = MuteWindow(
                start=start_time,
                end=end_time,
                reason=reason,
                source="SUBTITLE"
            )
            mute_windows.append(mute_window)
        
        return mute_windows
    
    def _clean_subtitle_text(self, text: str) -> str:
        """Clean subtitle text from SSA/ASS formatting and line breaks.
        
        Args:
            text: Raw subtitle text
            
        Returns:
            Cleaned text
        """
        if not text:
            return ""
        
        # Remove SSA/ASS style tags like {\i1}, {\b1}, etc.
        text = re.sub(r'{\\\w+\d*}', '', text)
        text = re.sub(r'{[^}]*}', '', text)
        
        # Replace line breaks with spaces
        text = text.replace('\\n', ' ').replace('\\N', ' ')
        text = text.replace('\n', ' ').replace('\r', ' ')
        
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text