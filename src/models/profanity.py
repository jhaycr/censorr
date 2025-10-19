"""Profanity term model for structured configuration support.

Handles both string and object entries with per-word fuzzy thresholds
and variant strategies for aggressive variant detection.
"""
from typing import List, Optional, Union, Dict, Any
from pydantic import BaseModel, Field


class ProfanityTerm(BaseModel):
    """A profanity term with optional per-word configuration."""
    
    word: str = Field(..., description="Base profane word or phrase")
    aliases: List[str] = Field(default_factory=list, description="Alternative spellings or forms")
    fuzzy_threshold: Optional[float] = Field(None, description="Custom fuzzy threshold for this term (0-100)")
    variant_strategy: str = Field("default", description="Variant detection strategy: 'default' or 'aggressive'")
    
    def get_all_terms(self) -> List[str]:
        """Get all terms including the main word and aliases."""
        return [self.word] + self.aliases
    
    def get_effective_threshold(self, global_default: float) -> float:
        """Get the effective fuzzy threshold for this term."""
        return self.fuzzy_threshold if self.fuzzy_threshold is not None else global_default
    
    def is_aggressive_variant_enabled(self) -> bool:
        """Check if aggressive variant detection is enabled for this term."""
        return self.variant_strategy == "aggressive"


def normalize_profanity_list(
    entries: List[Union[str, Dict[str, Any]]], 
    global_default_threshold: float = 85.0
) -> List[ProfanityTerm]:
    """Normalize a profanity list to ProfanityTerm objects.
    
    Args:
        entries: List of strings or dictionaries representing profanity terms
        global_default_threshold: Default fuzzy threshold when not specified per-term
        
    Returns:
        List of normalized ProfanityTerm objects
        
    Raises:
        ValueError: If entries are malformed
    """
    normalized = []
    
    for entry in entries:
        if isinstance(entry, str):
            # Simple string entry - use defaults
            normalized.append(ProfanityTerm(word=entry))
        elif isinstance(entry, dict):
            # Structured entry - validate and normalize
            if "word" not in entry:
                raise ValueError(f"Structured profanity entry missing required 'word' field: {entry}")
            
            # Validate variant_strategy if provided
            variant_strategy = entry.get("variant_strategy", "default")
            if variant_strategy not in ["default", "aggressive"]:
                raise ValueError(f"Invalid variant_strategy '{variant_strategy}', must be 'default' or 'aggressive'")
            
            # Validate fuzzy_threshold if provided
            fuzzy_threshold = entry.get("fuzzy_threshold")
            if fuzzy_threshold is not None:
                if not isinstance(fuzzy_threshold, (int, float)) or not (0 <= fuzzy_threshold <= 100):
                    raise ValueError(f"fuzzy_threshold must be a number between 0-100, got: {fuzzy_threshold}")
            
            normalized.append(ProfanityTerm(**entry))
        else:
            raise ValueError(f"Profanity entry must be string or dict, got {type(entry)}: {entry}")
    
    return normalized