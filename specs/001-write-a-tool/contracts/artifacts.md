# Artifact Contract

Artifacts are immutable outputs/inputs for Operations.

## Types
- VIDEO: container file; may include embedded audio/subtitles.
- AUDIO: audio track file (extracted or remux target).
- SUBTITLE: subtitle file (SRT/WEBVTT).

## Common Fields
- type: enum { VIDEO, AUDIO, SUBTITLE }
- path: string
- metadata: object
  - language: string (ISO 639-1)
  - codec/format: string
  - title: string
  - forced: boolean (SUBTITLE)
  - channels/layout: string (AUDIO)

## Invariants
- Artifacts are read-only after creation.
- Paths are absolute or workdir-relative and MUST exist.
- Metadata MUST reflect actual file properties (validated on creation).

## Validation
- On creation, validate file existence and parsability (for SUBTITLE) or probe (for AUDIO/VIDEO).
- For SUBTITLE outputs, ensure cue ordering and numbering (SRT) or valid WEBVTT.

## Naming
- Embedded subtitle title: "<Language Name> [CLEAN]"
- Embedded audio title: "<Language Name> (Clean Muted)"
- Sidecar subtitle filename: "<Title>.<lang>.clean.srt" by default