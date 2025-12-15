"""Language utilities."""
from typing import List, Set


# Standard language code mappings
LANGUAGE_MAP = {
    "en": {"en", "eng", "english"},
    "es": {"es", "spa", "spanish"},
    "fr": {"fr", "fra", "french"},
    "de": {"de", "deu", "german"},
    "ja": {"ja", "jpn", "japanese"},
    "zh": {"zh", "zho", "chinese"},
    "pt": {"pt", "por", "portuguese"},
    "ru": {"ru", "rus", "russian"},
    "ar": {"ar", "ara", "arabic"},
    "it": {"it", "ita", "italian"},
}


def normalize_languages(lang_list: List[str]) -> Set[str]:
    """Expand language codes/names to all variants.
    
    Args:
        lang_list: List of language codes or names (e.g., ['en', 'English', 'fra'])
        
    Returns:
        Set of all normalized language variants (lowercase)
    """
    normalized = set()
    for lang in lang_list:
        lang_lower = lang.lower()
        # Check if it's a key in the map
        if lang_lower in LANGUAGE_MAP:
            normalized.update(LANGUAGE_MAP[lang_lower])
        else:
            # Check if it's a value in any map entry
            found = False
            for variants in LANGUAGE_MAP.values():
                if lang_lower in variants:
                    normalized.update(variants)
                    found = True
                    break
            if not found:
                # Not in map, add as-is
                normalized.add(lang_lower)
    return normalized


def is_language_match(stream_language: str, filter_languages: List[str]) -> bool:
    """Check if a stream language matches any filter language.
    
    Args:
        stream_language: Language code from stream (e.g., 'eng', 'en')
        filter_languages: List of filter language codes/names
        
    Returns:
        True if stream language matches any filter
    """
    if not filter_languages:
        return False
    
    normalized_filters = normalize_languages(filter_languages)
    return stream_language.lower() in normalized_filters
