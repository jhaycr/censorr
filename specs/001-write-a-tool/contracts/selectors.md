# Selector Contract (Unified)

Selectors filter and prioritize tracks across VIDEO, AUDIO, and SUBTITLE types.

## Schema
- Location: `selector.schema.json` (repository root)
- Validation: CLI validates `--selectors-json` against this schema.

## Fields
- type: enum { VIDEO, AUDIO, SUBTITLE }
- language: string (ISO 639-1)
- role: string (AUDIO) – e.g., main, commentary
- codec: string (AUDIO/VIDEO)
- forced: boolean (SUBTITLE)
- title_include: array<string> (SUBTITLE) – include tracks with titles containing these substrings
- title_exclude: array<string> (SUBTITLE) – exclude tracks with titles containing these substrings  
- title_regex: array<string> (SUBTITLE) – include tracks with titles matching these regex patterns
- prefer: array<string> – ranking hints
- firstOnly: boolean – select only first match if true
- priority: integer – lower is higher priority

## Semantics
- Apply selectors in ascending priority.
- When multiple tracks match and firstOnly=false (default), select all.
- Forced-only fallback: If requested forced-only but only main exists, fallback to best main in language (unless strict-selector is true).
- Title filtering precedence: excludes win over includes. If title_include is specified but no patterns match, the track is rejected. SDH exclusion applied before includes.
- Title matching: case-insensitive substring matching on normalized titles (brackets/parens stripped, whitespace collapsed).

## Examples
```
[
  { "type": "SUBTITLE", "language": "en", "forced": false, "priority": 0 },
  { "type": "AUDIO", "language": "en", "role": "main", "priority": 0 }
]
```

### Subtitle Title Filtering Examples
```
// Select English full + forced, exclude SDH/HI
{
  "type": "SUBTITLE",
  "language": "en", 
  "title_exclude": ["sdh", "hi", "cc"],
  "priority": 0
}

// Select only forced English subtitles with "Forced" in title
{
  "type": "SUBTITLE",
  "language": "en",
  "title_include": ["Forced"],
  "priority": 0
}

// Use regex to match specific patterns
{
  "type": "SUBTITLE", 
  "language": "en",
  "title_regex": ["English.*(Forced|Full)"],
  "title_exclude": ["sdh", "hi", "cc"],
  "priority": 0
}

// Exclude specific subtitle types
{
  "type": "SUBTITLE",
  "language": "en",
  "title_exclude": ["Commentary", "Director"],
  "priority": 0
}
```

### Precedence Rules
1. Exclusions (title_exclude) are applied first and take precedence
2. If any exclusion pattern matches, the track is rejected
3. If title_include patterns are specified, at least one must match
4. If title_regex patterns are specified, at least one must match  
5. Case-insensitive matching with title normalization (strip brackets/parens, collapse whitespace)

### CLI Integration
The following CLI flags automatically create subtitle selectors:
- `--language en` creates basic language filter
- `--exclude-sdh` adds SDH exclusion 
- `--subtitle-title-include "forced,full"` adds inclusion patterns
- `--subtitle-title-exclude "commentary"` adds exclusion patterns
- `--subtitle-title-regex "English.*Forced"` adds regex patterns

When both CLI flags and `--selectors-json` are provided, structured selectors take precedence.
  "language": "en",
  "forced": true,
  "title_include": ["forced"],
  "priority": 0
}

// Select tracks matching regex pattern, exclude specific patterns
{
  "type": "SUBTITLE", 
  "language": "en",
  "title_regex": ["^English(?!.*SDH)"],
  "title_exclude": ["commentary"],
  "priority": 0
}
```