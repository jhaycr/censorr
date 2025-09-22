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
- exclude_sdh: boolean (SUBTITLE) – exclude hearing-impaired/SDH tracks
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
  "exclude_sdh": true,
  "priority": 0
}

// Select only forced English subtitles with "Forced" in title
{
  "type": "SUBTITLE",
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