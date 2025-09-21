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
- prefer: array<string> – ranking hints
- firstOnly: boolean – select only first match if true
- priority: integer – lower is higher priority

## Semantics
- Apply selectors in ascending priority.
- When multiple tracks match and firstOnly=false (default), select all.
- Forced-only fallback: If requested forced-only but only main exists, fallback to best main in language (unless strict-selector is true).

## Examples
```
[
  { "type": "SUBTITLE", "language": "en", "forced": false, "priority": 0 },
  { "type": "AUDIO", "language": "en", "role": "main", "priority": 0 }
]
```