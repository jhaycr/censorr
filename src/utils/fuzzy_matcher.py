"""Fuzzy matching utilities using RapidFuzz.

Provides utilities for:
- Fuzzy string matching with configurable thresholds
- Allow-list based profanity detection
- Text normalization for better matching
- Batch matching operations
"""
import re
import unicodedata
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator
from rapidfuzz import fuzz


class FuzzyMatchError(Exception):
    """Exception raised for fuzzy matching errors."""
    pass


class MatchResult(BaseModel):
    """Result of a fuzzy matching operation."""
    query: str = Field(..., description="Original query string")
    target: str = Field(..., description="Target string that was matched against")
    score: float = Field(..., description="Similarity score (0-100)")
    is_match: bool = Field(..., description="Whether this is considered a match")
    normalized_query: str = Field(..., description="Normalized query string")
    normalized_target: str = Field(..., description="Normalized target string")


class FuzzyMatcher:
    """Fuzzy string matcher using RapidFuzz."""
    
    def __init__(self, 
                 similarity_threshold: float = 80.0,
                 allow_list: Optional[List[str]] = None,
                 normalization_enabled: bool = True):
        """Initialize fuzzy matcher.
        
        Args:
            similarity_threshold: Minimum similarity score to consider a match (0-100)
            allow_list: List of strings to match against
            normalization_enabled: Whether to normalize text before matching
            
        Raises:
            FuzzyMatchError: If threshold is invalid
        """
        if not 0 <= similarity_threshold <= 100:
            raise FuzzyMatchError("Similarity threshold must be between 0 and 100")
        
        self.similarity_threshold = similarity_threshold
        self.allow_list = allow_list or []
        self.normalization_enabled = normalization_enabled
    
    def normalize_text(self, text: str) -> str:
        """Normalize text for better matching.
        
        Args:
            text: Text to normalize
            
        Returns:
            Normalized text
        """
        if not text:
            return ""
        
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
    
    def match(self, query: str, target: str) -> MatchResult:
        """Match two strings and return result.
        
        Args:
            query: Query string
            target: Target string to match against
            
        Returns:
            MatchResult with similarity score and match status
        """
        # Normalize if enabled
        if self.normalization_enabled:
            normalized_query = self.normalize_text(query)
            normalized_target = self.normalize_text(target)
        else:
            normalized_query = query
            normalized_target = target
        
        # Calculate similarity score
        if not normalized_query and not normalized_target:
            # Both empty - perfect match
            score = 100.0
        elif not normalized_query or not normalized_target:
            # One empty - no match
            score = 0.0
        else:
            # Use RapidFuzz ratio for similarity
            score = fuzz.ratio(normalized_query, normalized_target)
        
        # Determine if this is a match
        is_match = score >= self.similarity_threshold
        
        return MatchResult(
            query=query,
            target=target,
            score=score,
            is_match=is_match,
            normalized_query=normalized_query,
            normalized_target=normalized_target
        )
    
    def match_against_allow_list(self, query: str) -> List[MatchResult]:
        """Match query against all items in allow list.
        
        Args:
            query: Query string to match
            
        Returns:
            List of MatchResult objects, sorted by score descending
        """
        if not self.allow_list:
            return []
        
        results = []
        for target in self.allow_list:
            result = self.match(query, target)
            results.append(result)
        
        # Sort by score descending
        results.sort(key=lambda x: x.score, reverse=True)
        
        return results
    
    def find_best_match(self, query: str) -> Optional[MatchResult]:
        """Find the best match for query in allow list.
        
        Args:
            query: Query string to match
            
        Returns:
            Best MatchResult if any match found, None otherwise
        """
        results = self.match_against_allow_list(query)
        
        # Return first result if it's a match
        if results and results[0].is_match:
            return results[0]
        
        return None
    
    def contains_profanity(self, text: str) -> bool:
        """Check if text contains any profanity from allow list.
        
        Args:
            text: Text to check for profanity
            
        Returns:
            True if profanity found, False otherwise
        """
        if not self.allow_list:
            return False
        
        # Split text into words and check each
        words = self._extract_words(text)
        
        for word in words:
            if self.find_best_match(word):
                return True
        
        return False
    
    def extract_profanity_matches(self, text: str) -> List[MatchResult]:
        """Extract all profanity matches from text.
        
        Args:
            text: Text to analyze
            
        Returns:
            List of MatchResult objects for profanity found
        """
        if not self.allow_list:
            return []
        
        words = self._extract_words(text)
        matches = []
        
        for word in words:
            results = self.match_against_allow_list(word)
            # Add only the matching results
            matches.extend([r for r in results if r.is_match])
        
        return matches
    
    def _extract_words(self, text: str) -> List[str]:
        """Extract words from text for analysis.
        
        Args:
            text: Text to extract words from
            
        Returns:
            List of words
        """
        if self.normalization_enabled:
            text = self.normalize_text(text)
        
        # Split on whitespace and filter empty strings
        words = [word for word in text.split() if word]
        
        return words