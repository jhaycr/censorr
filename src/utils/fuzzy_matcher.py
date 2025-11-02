"""Fuzzy matching utilities using RapidFuzz.

Provides utilities for:
- Window-based fuzzy string matching with configurable thresholds
- Allow-list based profanity detection with morphology rules
- Per-term threshold configuration and aggressive variant detection
- Text normalization for better matching
- Multi-word phrase support
"""
import re
import unicodedata
from typing import List, Optional, Set, Dict, Any, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from src.models.profanity import ProfanityTerm
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
    method: str = Field(default="window", description="Matching method used")
    window_text: Optional[str] = Field(default=None, description="Text from sliding window that matched")


class FuzzyMatcher:
    """Window-based fuzzy string matcher using RapidFuzz with per-term configuration."""
    
    def __init__(self, 
                 similarity_threshold: float = 80.0,
                 allow_list: Optional[Union[List[str], List['ProfanityTerm']]] = None,
                 normalization_enabled: bool = True,
                 strategy: str = "window"):
        """Initialize fuzzy matcher.
        
        Args:
            similarity_threshold: Default minimum similarity score to consider a match (0-100)
            allow_list: List of strings or ProfanityTerm objects to match against
            normalization_enabled: Whether to normalize text before matching
            strategy: Matching strategy ("window" for new approach, "legacy" for old)
            
        Raises:
            FuzzyMatchError: If threshold is invalid
        """
        if not 0 <= similarity_threshold <= 100:
            raise FuzzyMatchError("Similarity threshold must be between 0 and 100")
        
        self.global_similarity_threshold = similarity_threshold
        self.normalization_enabled = normalization_enabled
        self.strategy = strategy
        
        # Initialize profanity terms and configuration
        self._initialize_profanity_terms(allow_list or [])
        
        # Morphology rules for single-word targets (allows fuck → fucking, fucker, etc.)
        self._allowed_suffixes = {"", "s", "ed", "er", "ing", "in"}
        
        # Aggressive variant detection suffixes for compound and morphological forms
        self._aggressive_suffixes = {
            "", "s", "ed", "er", "ing", "in", "ly", "ness", "able", "ible", 
            "ful", "less", "ward", "wise", "like", "ish", "ment", "tion", "sion"
        }
        
        # Common compound prefixes/suffixes for aggressive matching
        self._compound_patterns = {
            "un", "re", "pre", "mis", "dis", "over", "under", "out", "up", "down",
            "back", "fore", "anti", "pro", "semi", "multi", "non", "sub", "super",
            "inter", "intra", "extra", "ultra", "mega", "mini", "micro", "macro"
        }
        
        # Minimal English stopword set to prevent spurious matches
        self._stopwords: Set[str] = {
            "a", "an", "the", "and", "or", "but", "if", "then", "else",
            "of", "to", "in", "on", "for", "by", "with", "at", "from",
            "as", "is", "it", "its", "be", "are", "was", "were", "am",
            "he", "she", "they", "we", "you", "i", "me", "him", "her",
            "them", "us", "my", "your", "his", "their", "our"
        }
    
    def _initialize_profanity_terms(self, allow_list: Union[List[str], List['ProfanityTerm']]):
        """Initialize profanity terms and build lookup maps."""
        # Import here to avoid circular import
        from src.models.profanity import ProfanityTerm, normalize_profanity_list
        
        # Handle already normalized ProfanityTerm objects
        if isinstance(allow_list, list) and len(allow_list) > 0 and isinstance(allow_list[0], ProfanityTerm):
            self.profanity_terms = allow_list
        else:
            # Normalize allow_list to ProfanityTerm objects for internal consistency
            self.profanity_terms = normalize_profanity_list(allow_list, self.global_similarity_threshold)
        
        # Build lookup maps for efficient per-term configuration access
        self._term_thresholds: Dict[str, float] = {}
        self._aggressive_terms: Set[str] = set()
        
        for term in self.profanity_terms:
            effective_threshold = term.get_effective_threshold(self.global_similarity_threshold)
            normalized_word = self.normalize_text(term.word)
            self._term_thresholds[normalized_word] = effective_threshold
            if term.is_aggressive_variant_enabled():
                self._aggressive_terms.add(normalized_word)
    
    @property
    def allow_list(self) -> List[str]:
        """Get legacy allow_list for backward compatibility.
        
        Returns all terms from profanity_terms as a flat string list.
        """
        result = []
        for term in self.profanity_terms:
            result.append(term.word)
        return result
    
    @allow_list.setter  
    def allow_list(self, value: List[str]):
        """Set allow_list for backward compatibility.
        
        Converts string list to ProfanityTerm objects.
        """
        self._initialize_profanity_terms(value)
    
    @property
    def similarity_threshold(self) -> float:
        """Get legacy similarity_threshold for backward compatibility."""
        return self.global_similarity_threshold
    
    @similarity_threshold.setter
    def similarity_threshold(self, value: float):
        """Set legacy similarity_threshold for backward compatibility."""
        if not 0 <= value <= 100:
            raise FuzzyMatchError("Similarity threshold must be between 0 and 100")
        self.global_similarity_threshold = value
    
    def _get_effective_threshold(self, target: str) -> float:
        """Get the effective similarity threshold for a target term."""
        normalized_target = self.normalize_text(target)
        return self._term_thresholds.get(normalized_target, self.global_similarity_threshold)
    
    def _is_aggressive_enabled(self, target: str) -> bool:
        """Check if aggressive variant detection is enabled for a target term."""
        normalized_target = self.normalize_text(target)
        return normalized_target in self._aggressive_terms
    
    def normalize_text(self, text: str) -> str:
        """Normalize text for better matching.
        
        Args:
            text: Text to normalize
            
        Returns:
            Normalized text
        """
        if not text:
            return ""
        
        # Convert to lowercase
        text = text.lower()

        # Strip accents/diacritics (e.g., café -> cafe)
        text = unicodedata.normalize('NFKD', text)
        text = ''.join(ch for ch in text if not unicodedata.combining(ch))
        
        # Replace underscores, hyphens and apostrophes with spaces to preserve token boundaries
        # This prevents "fuckin'" -> "fuckin" (still a token) and avoids merging across punctuation
        text = re.sub(r"[-_']", " ", text)

        # Replace other punctuation with spaces (do not delete) to avoid concatenating tokens
        # Example: "D...Fuck" -> "D   Fuck" -> "d fuck" after normalization, so "fuck" is matchable
        text = re.sub(r'[^\w\s]', ' ', text)

        # Replace digits with spaces as well to avoid unwanted concatenation across numbers
        text = re.sub(r'\d+', ' ', text)
        
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
        if self.strategy == "window":
            return self._window_match(query, target)
        else:
            return self._legacy_match(query, target)
    
    def _window_match(self, query: str, target: str) -> MatchResult:
        """Window-based matching with morphology rules."""
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
            # Guard: stopwords cannot match profanities
            if normalized_query in self._stopwords:
                score = 0.0
            # Guard: extremely short tokens must match exactly
            elif min(len(normalized_query), len(normalized_target)) <= 3:
                score = 100.0 if normalized_query == normalized_target else 0.0
            else:
                # For single-word targets, apply morphology rules; otherwise use fuzzy ratio
                target_words = normalized_target.split()
                query_words = normalized_query.split()
                
                if len(target_words) == 1 and len(query_words) == 1:
                    score = self._morphology_match_score(normalized_query, normalized_target)
                else:
                    # Multi-word or mixed: use fuzzy ratio for leniency
                    score = fuzz.ratio(normalized_query, normalized_target)
        
        # Determine if this is a match
        is_match = score >= self.similarity_threshold
        
        return MatchResult(
            query=query,
            target=target,
            score=score,
            is_match=is_match,
            normalized_query=normalized_query,
            normalized_target=normalized_target,
            method="window"
        )
    
    def _morphology_match_score(self, query: str, target: str) -> float:
        """Calculate score with morphology rules for single words.
        
        Supports both default and aggressive variant detection based on 
        per-term configuration.
        """
        # Exact match
        if query == target:
            return 100.0
        
        # Get effective threshold and check if aggressive mode is enabled
        effective_threshold = self._get_effective_threshold(target)
        aggressive_enabled = self._is_aggressive_enabled(target)
        
        # Choose suffix set based on aggressive mode
        suffixes = self._aggressive_suffixes if aggressive_enabled else self._allowed_suffixes
        
        # Check if query is target + allowed suffix (target is root)
        for suffix in suffixes:
            if suffix and query == target + suffix:
                return 100.0
        
        # Check if target is query + allowed suffix (query is root)  
        for suffix in suffixes:
            if suffix and target == query + suffix:
                return 100.0
        
        # Aggressive variant detection: check compound patterns
        if aggressive_enabled:
            # Check if query contains target as substring with compound affixes
            query_lower = query.lower()
            target_lower = target.lower()
            
            # Check compound patterns: prefix + target or target + suffix
            for pattern in self._compound_patterns:
                if query_lower == pattern + target_lower or query_lower == target_lower + pattern:
                    return 100.0
                
            # Check for target embedded in query (e.g., "unfuckingbelievable" contains "fuck")
            if len(target_lower) >= 3 and target_lower in query_lower:
                # For embedded detection, we're more permissive about boundaries
                # This catches cases like "unfuckingbelievable" where "fuck" is embedded
                return 100.0
        
        # No morphological match - fall back to fuzzy ratio score
        return fuzz.ratio(query, target)
    
    def find_matches_in_text(self, text: str) -> List[MatchResult]:
        """Find all matches in text using sliding window approach.
        
        Args:
            text: Text to search for matches
            
        Returns:
            List of MatchResult objects for all matches found
        """
        if not self.allow_list:
            return []
        
        matches = []
        normalized_text = self.normalize_text(text) if self.normalization_enabled else text
        words = normalized_text.split()
        
        for target in self.allow_list:
            normalized_target = self.normalize_text(target) if self.normalization_enabled else target
            target_words = normalized_target.split()
            target_word_count = len(target_words)
            
            # Slide window over text
            for i in range(len(words) - target_word_count + 1):
                window_words = words[i:i + target_word_count]
                window_text = ' '.join(window_words)
                
                # Calculate score and check against per-term threshold
                if self.strategy == "window":
                    # Apply short-token guard here too
                    if min(len(window_text), len(normalized_target)) <= 3:
                        score = 100.0 if window_text == normalized_target else 0.0
                    elif target_word_count == 1:
                        score = self._morphology_match_score(window_text, normalized_target)
                    else:
                        score = fuzz.ratio(window_text, normalized_target)
                else:
                    # Multi-word or mixed: be strict — require exact normalized equality
                    score = 100.0 if window_text == normalized_target else 0.0
                
                # Use per-term threshold instead of global threshold
                effective_threshold = self._get_effective_threshold(target)
                
                if score >= effective_threshold:
                    # Skip stopwords
                    if window_text in self._stopwords:
                        continue
                        
                    matches.append(MatchResult(
                        query=window_text,
                        target=target,
                        score=score,
                        is_match=True,
                        normalized_query=window_text,
                        normalized_target=normalized_target,
                        method=self.strategy,
                        window_text=window_text
                    ))
        
        return matches
    
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
        matches = self.find_matches_in_text(text)
        return len(matches) > 0

    def extract_profanity_matches(self, text: str) -> List[MatchResult]:
        """Extract all profanity matches from text.
        
        Args:
            text: Text to analyze
            
        Returns:
            List of MatchResult objects for profanity found
        """
        return self.find_matches_in_text(text)

    def _legacy_match(self, query: str, target: str) -> MatchResult:
        """Legacy matching method for backwards compatibility."""
        # Normalize if enabled
        if self.normalization_enabled:
            normalized_query = self.normalize_text(query)
            normalized_target = self.normalize_text(target)
        else:
            normalized_query = query
            normalized_target = target
        
        # Calculate similarity score using old logic
        if not normalized_query and not normalized_target:
            score = 100.0
        elif not normalized_query or not normalized_target:
            score = 0.0
        else:
            score = fuzz.ratio(normalized_query, normalized_target)
        
        # Determine if this is a match
        is_match = score >= self.similarity_threshold
        
        return MatchResult(
            query=query,
            target=target,
            score=score,
            is_match=is_match,
            normalized_query=normalized_query,
            normalized_target=normalized_target,
            method="legacy"
        )