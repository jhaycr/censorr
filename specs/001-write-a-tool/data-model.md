# Data Model

This document defines the core data structures used by the CLI and pipeline.

## Artifact
- type: enum { VIDEO, AUDIO, SUBTITLE }
- path: string (absolute or workdir-relative)
- metadata: object
  - language: ISO 639-1 code (optional for VIDEO)
  - codec/format: string
  - forced: boolean (SUBTITLE only)
  - channels/layout: string (AUDIO only)
  - title: string (display name for players)

Validation:
- Path MUST exist for produced artifacts.
- SUBTITLE MUST have language; AUDIO SHOULD have language when known.

## Selector (Unified)
- type: enum { VIDEO, AUDIO, SUBTITLE }
- language: string (ISO 639-1)
- role: string (AUDIO only; e.g., main, commentary)
- codec: string (AUDIO/VIDEO)
- forced: boolean (SUBTITLE only)
- prefer: array<string> (ranking hints; e.g., ["forced", "main"]) 
- firstOnly: boolean (default false)
- priority: integer (lower = higher priority)

Validation:
- Must conform to `selector.schema.json` at repo root.
- Only fields valid for `type` may be set.

## Operation
- name: string (unique)
- consumes: array<Artifact.type>
- produces: array<Artifact.type>
- run(args):
  - inputs: array<Artifact>
  - workdir: string
  - flags: { dryRun: bool, verbose: bool }
  - returns: array<Artifact>

Errors:
- Missing required input type
- External tool failure (captured stdout/stderr)
- Incompatible artifacts

## MuteWindow
- start: float (seconds)
- end: float (seconds)
- reason: string (e.g., term matched)
- source: enum { SUBTITLE, EXTERNAL }

Validation:
- 0 <= start < end

## AuditLogEntry
- op: string
- time: ISO timestamp
- level: enum { info, warn, error }
- message: string
- details: object (before/after, paths, counts)

## ManifestEntry
- op: string
- inputs: array<{ path: string, checksum: string }>
- outputs: array<{ path: string, checksum: string }>
- params: object (relevant flags/config)
- timestamp: ISO timestamp