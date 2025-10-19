# Per-Word Fuzzy Threshold and Aggressive Variant Detection

This document describes the per-word fuzzy threshold and aggressive variant detection features implemented for profanity filtering.

## Overview

The profanity filtering system now supports:

1. **Per-word fuzzy threshold configuration** - Custom similarity thresholds for individual profanity terms
2. **Aggressive variant detection** - Advanced detection of morphological and compound variants
3. **Backward compatibility** - Existing string-based profanity lists continue to work

## Profanity List Format

The profanity list now supports both legacy string format and new structured format:

### Legacy Format (Still Supported)
```json
[
    "fuck",
    "shit",
    "damn"
]
```

### New Structured Format
```json
[
    {
        "word": "fuck",
        "fuzzy_threshold": 75,
        "variant_strategy": "aggressive",
        "aliases": ["f*ck", "f**k"]
    },
    {"word": "shit"},
    "damn"
]
```

### Mixed Format
```json
[
    "damn",
    {
        "word": "fuck",
        "fuzzy_threshold": 75,
        "variant_strategy": "aggressive"
    },
    {"word": "shit", "fuzzy_threshold": 95}
]
```

## Configuration Fields

### `word` (required)
The base profane word or phrase.

### `fuzzy_threshold` (optional)
Custom fuzzy similarity threshold for this term (0-100). If not specified, uses the global default (85).

- **Lower values** = more permissive (catches more variants but may have false positives)
- **Higher values** = more strict (fewer false positives but may miss variants)

**Length-Based Threshold Protection**: Words with ≤4 characters automatically get a minimum threshold of 95% to prevent false positives. For example:
- `"shit"` with `fuzzy_threshold: 80` → effective threshold becomes 95%
- `"fuck"` with no custom threshold → effective threshold becomes 95% (not 85%)
- `"bullshit"` with `fuzzy_threshold: 70` → effective threshold remains 70% (longer word)

This prevents false positives like "shirt" matching "shit" (88.89% < 95%).

### `variant_strategy` (optional)
Variant detection strategy. Valid values:
- `"default"` (default) - Standard morphological matching (e.g., "fuck" → "fucking", "fucker")
- `"aggressive"` - Enhanced detection including compound forms and embedded variants

### `aliases` (optional)
List of alternative spellings or forms that should be treated as equivalent to the main word.

## Aggressive Variant Detection

When `variant_strategy` is set to `"aggressive"`, the system detects:

### Standard Morphological Variants
- Suffixes: "", "s", "ed", "er", "ing", "in", "ly", "ness", "able", "ible", "ful", "less", etc.
- Examples: "fuck" → "fucking", "fuckable", "fucked"

### Compound Forms
- Prefix compounds: "unfuck", "refuck"
- Suffix compounds: "fuckup", "fuckward"
- Examples: "fuck" → "unfuck", "fuckup"

### Embedded Variants
- Target word embedded in larger compounds
- Examples: "fuck" → "unfuckingbelievable"

## Examples

### Example 1: Catching "fuckable" without explicit enumeration

**Before (required explicit listing):**
```json
[
    {"word": "fuck"},
    {"word": "fuckable"},
    {"word": "fucking"},
    {"word": "unfuckingbelievable"}
]
```

**After (automatic detection):**
```json
[
    {
        "word": "fuck",
        "variant_strategy": "aggressive"
    }
]
```

This automatically catches: "fuckable", "fucking", "unfuckingbelievable", "fuckup", "unfuck", etc.

### Example 2: Per-word thresholds

```json
[
    {
        "word": "strict_word",
        "fuzzy_threshold": 95
    },
    {
        "word": "lenient_word", 
        "fuzzy_threshold": 50
    }
]
```

- "strict_word" requires 95% similarity (very strict)
- "lenient_word" requires only 50% similarity (very permissive)

### Example 3: Mixed configuration

```json
[
    "standard_term",
    {
        "word": "fuck",
        "fuzzy_threshold": 75,
        "variant_strategy": "aggressive"
    },
    {
        "word": "sensitive_term",
        "fuzzy_threshold": 98
    }
]
```

## False Positive Prevention

### Automatic Length-Based Protection
Short words (≤4 characters) are automatically protected against false positives by enforcing a minimum 95% similarity threshold:

**Example: "shit" false positive fix**
```
Before: "shirt" → 88.89% similarity → INCORRECTLY MATCHED (above 85% threshold)
After:  "shirt" → 88.89% similarity → CORRECTLY REJECTED (below 95% threshold)
```

**Protected words include:**
- `"shit"` - prevents matching "shirt", "sit", "shift"
- `"fuck"` - prevents matching "duck", "tuck", "luck"  
- `"dick"` - prevents matching "deck", "sick", "pick"
- `"cunt"` - prevents matching "cant", "hunt", "punt"

### Custom Threshold Override
You can still set higher thresholds for short words if needed:
```json
{
    "word": "shit",
    "fuzzy_threshold": 98,  // Higher than 95% minimum
    "variant_strategy": "aggressive"
}
```

## Implementation Details

### Backward Compatibility
- Existing string-based profanity lists work unchanged
- Legacy `allow_list` property on `FuzzyMatcher` continues to function
- No breaking changes to existing APIs

### Performance
- Per-term configuration is cached in lookup maps for efficient access
- Aggressive detection adds minimal overhead for non-aggressive terms
- Morphological rules are optimized for common patterns

### Quality Control
- Post-masking QC uses the same per-term configuration as masking
- Ensures consistency between detection and verification phases
- Per-word settings are logged in verbose mode for observability

## Migration Guide

### For Simple Cases
No changes required - existing profanity lists continue to work.

### For Enhanced Detection
1. Identify words that frequently have variants (e.g., "fuck", "shit")
2. Convert them to structured format with `"variant_strategy": "aggressive"`
3. Optionally adjust `fuzzy_threshold` for fine-tuning
4. Remove explicit variant entries that will be caught automatically

### Example Migration
```json
// Before
[
    "fuck",
    "fuckable", 
    "fucking",
    "fucker",
    "unfuckingbelievable"
]

// After  
[
    {
        "word": "fuck",
        "variant_strategy": "aggressive"
    }
]
```

## Testing

The implementation includes comprehensive tests:

- Unit tests for `ProfanityTerm` model and `normalize_profanity_list`
- Fuzzy matcher tests for per-term thresholds and aggressive detection
- Integration tests for full text matching with variant detection
- Backward compatibility tests for legacy string lists

Run tests with:
```bash
python -m pytest tests/unit/test_per_word_fuzzy.py -v
```