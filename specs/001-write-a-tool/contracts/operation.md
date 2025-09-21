# Operation Contract

An Operation is a composable pipeline step with explicit inputs and outputs.

## Interface
- name: string (stable identifier)
- consumes: set of Artifact types (e.g., {VIDEO}, {SUBTITLE}, {AUDIO, SUBTITLE})
- produces: set of Artifact types
- run(inputs, workdir, flags) -> outputs
  - inputs: array<Artifact> matching `consumes`
  - workdir: string; Operation MUST write outputs here (or subfolders)
  - flags:
    - dryRun: boolean (no side effects)
    - verbose: boolean
    - strategy: string (optional; operation-specific)
  - returns: array<Artifact> matching `produces`

## Guarantees
- Single Responsibility: do one thing.
- Deterministic outputs: names based on inputs + op purpose.
- Idempotency: if outputs exist and inputs unchanged (per manifest), MUST be a no-op unless forced.
- Observability: log start/end, inputs/outputs, and external tool stdout/stderr paths.

## Errors & Recovery
- Missing required input: fail with message specifying required types.
- External tool failure: capture stdout/stderr, return non-zero status/error with path to logs.
- Validation failure: refuse to produce outputs; leave prior artifacts intact.

## Examples (Non-normative)
- extract_subtitles: consumes VIDEO; produces SUBTITLE
- merge_subtitles: consumes SUBTITLE*; produces SUBTITLE
- mask_subtitles: consumes SUBTITLE; produces SUBTITLE
- extract_audio: consumes VIDEO; produces AUDIO
- mute_audio: consumes AUDIO + SUBTITLE or AUDIO + MuteWindows; produces AUDIO
- remux: consumes VIDEO + {AUDIO,SUBTITLE}*; produces VIDEO
- export_sidecar: consumes SUBTITLE; produces SUBTITLE (sidecar file)
- qc_subtitles: consumes SUBTITLE; produces report (log only)