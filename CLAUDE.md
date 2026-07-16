# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Censorr is a CLI tool (and companion webhook/worker services) that censors audio and subtitles in media
files — muting profane audio segments and masking profane subtitle text — and integrates with Plex/Radarr/
Sonarr via Custom Script or webhook triggers. Core runtime dependency: FFmpeg on PATH.

## Commands

```bash
# Install (editable, with dev deps)
pip install -e .[dev]

# Run the full test suite
pytest

# Run one test file / one test
pytest tests/unit/test_fuzzy_matcher.py
pytest tests/unit/test_fuzzy_matcher.py::test_fuzzy_matcher_detects_spelling_variations

# Test subsets (see Architecture > Testing below for what each layer covers)
pytest tests/unit/
pytest tests/contract/
pytest tests/integration/

# Lint / format / type-check
black src tests
ruff check src tests
mypy src

# PR size gate (mirrors CI; caps at 400 additions / 400 deletions / 10 files)
scripts/check-pr-size.sh [base_branch]

# Run the CLI locally
censorr process movie.mkv --preset movies --output ./output
censorr process movie.mkv --dry-run --verbose
censorr list-operations
censorr explain

# Docker Compose (long-running worker + webhook services)
docker compose up -d
docker exec censorr-cli censorr process "/data/media/movies/Movie (2024)/Movie.mkv" --preset movies --output /app/workdir/output
```

There is no Makefile; the commands above are the canonical entry points. `censorr` is registered as a
console script (`src.cli.main:app`) via `pyproject.toml`.

## Architecture

### Pipeline model: Artifact → Operation → Planner → Executor

The core abstraction is a small dataflow pipeline, not a monolithic processing function:

- **`Artifact`** (`src/models/artifacts.py`) — a typed unit of data flowing through the pipeline
  (`VIDEO`, `AUDIO`, `SUBTITLE`, `SIDECAR`), always a file path plus a metadata dict (language, codec,
  forced flag, QC results, etc.).
- **`Operation`** (`src/models/operations.py`) — abstract base with `consumes: Set[ArtifactType]`,
  `produces: Set[ArtifactType]`, and `run(inputs, workdir, flags) -> List[Artifact]`. Each concrete
  operation lives in `src/ops/` as its own module (single responsibility — one file per pipeline step).
- **`OperationRegistry`** (`src/planner/registry.py`) — operations register themselves by name; the
  registry is the only place that knows the full set of available operations (open for extension, no
  changes needed to planner/executor to add a new op).
- **`Planner`** (`src/planner/planner.py`) — given already-available artifacts and a set of target
  artifact types, resolves which operations must run. Honors an explicit `requested_operations` order
  when the caller specifies `--operations`; otherwise picks the first producer per needed artifact type
  (see the `TODO`s in that file — dependency-aware planning and priority selection are intentionally
  unimplemented; today the CLI mostly drives fixed preset operation lists rather than relying on planning).
- **`Executor`** (`src/planner/executor.py`) — runs an `ExecutionPlan` in order. Per operation it: builds
  input artifacts via `_find_inputs` (type-based matching, with special-cased logic for subtitles —
  always pass all subtitle artifacts through — and for `audio_qc`/`video_remux`, which need specific
  artifact selection among multiple candidates), checks the on-disk cache, executes if not cached, writes
  a manifest, and accumulates outputs into the running artifact list for downstream operations.

### Pipeline flow (default `process` command)

```
VIDEO ─┬─ subtitle_extract ─→ SUBTITLE ─ subtitle_merge ─→ SUBTITLE ─ subtitle_mask ─→ SUBTITLE ─┐
       │                                                                                          ├─ subtitle_qc (pass-through + QC metadata)
       └─ audio_extract ─→ AUDIO ─ audio_mute ─→ AUDIO ─ audio_qc (pass-through + QC metadata) ───┘
                                                                                                    │
                                                                                     video_remux ───┴──→ VIDEO (+ optional SIDECAR via subtitle_export)
```

QC operations (`audio_qc`, `subtitle_qc`) are pass-through: they consume and re-produce the same
artifact type, annotating it with pass/fail metadata rather than transforming the file. Whether a QC
failure aborts the pipeline is controlled by `continue_on_qc_fail` / `continue_on_audio_qc_fail`.

### Caching and idempotency

`CacheManager` (`src/caching/`) fingerprints each operation invocation from its name, input artifacts,
and relevant params (including a sorted selector fingerprint, so language/title filters correctly bust
the cache) and stores results under a manifest in the workdir. The executor consults this before running
an operation and reconstructs output `Artifact`s from the manifest on a hit — re-running with unchanged
inputs must not reprocess. `--force` bypasses the cache; `--skip-existing` is mutually exclusive with
`--force` (enforced by a `model_validator` on `OperationFlags`).

### Configuration and presets

`Config` (`src/models/config.py`) loads with fallback precedence: `--config` path → `./config/censorr.json`
→ `~/.config/censorr/config.json` → built-in defaults. Named **presets** (e.g. `movies`, `tv` in
`config/censorr.json`) bundle an operation list, default flags, a language selector policy, and an output/
destination policy. In `process` (`src/cli/main.py`), precedence for any given setting is: **explicit CLI
flag > preset flags > project/user config > built-in smart default**. Output placement is governed by
`output_mode` (`REMUX_ORIGINAL_VIDEO` in place, or `REMUX_NEW_FILE`) plus a `DestinationPolicy`
(`subfolder_tag` with a tag like `[Censorr]`, or `separate_root`). Movies get a Plex `{edition-Censorr}`
tag on output; episodes don't.

### Webhook + queue + worker (Arr integration)

Two separate long-running services, each with its own minimal Dockerfile (`Dockerfile.web` has no
FFmpeg; `Dockerfile.tool` does):

- **`src/webhook/wsgi_app.py`** — a plain WSGI app (served via Gunicorn, see `docker-entrypoint.sh`)
  exposing `/webhook`, `/healthz`/`/status`. It validates the payload shape, applies a tag allowlist
  (`CENSORR_WEBHOOK_ALLOWLIST`, default `censorr_profile`), optionally checks a shared secret
  (`CENSORR_WEBHOOK_SECRET`), and enqueues a job — it does **not** invoke FFmpeg itself.
- **`src/queue/file_queue.py`** — a dependency-free, crash-safe file-based job queue. Jobs move atomically
  through `incoming/ → processing/ → done/` or `failed/` by `os.replace` renames; stale leases in
  `processing/` are recovered on the next poll. This is intentionally not a message broker — it's designed
  to survive container restarts with zero external services.
- **`src/worker/runner.py`** — polls the queue, claims a job, and shells out to
  `python -m src.cli.main webhook` with the job payload on stdin. Exit code contract: `0` = accepted,
  `2` = ignored (not an error — e.g. unknown preset), `3` = permanent validation failure (no retry),
  anything else = transient (retried up to `max_retries`, then moved to `failed/`).
- The `webhook` CLI command (`src/cli/main.py`) reads that same JSON payload from stdin, resolves
  `tags.censorr_preset` against configured presets, and calls `process()` programmatically for each path
  in `mediaPaths` — the webhook/worker path and the direct CLI path converge on the same `process` logic.

### Governance documents (read before large changes)

- **`CONSTITUTION.md`** (and its mirror `.specify/memory/constitution.md`) is the authoritative source for
  non-functional rules: PR size caps (≤400 additions/≤400 deletions/≤10 files, stacked PRs beyond that),
  commit message structure, test-first requirement, heartbeat/logging format for long-running FFmpeg work
  (`HEARTBEAT` token, UTC ISO-8601 timestamps, disable via `CENSORR_NO_HEARTBEAT=1`), and security rules
  (never shell-interpolate external input — always pass args as lists).
- **`.kiro/steering/*.md`** — supplementary conventions: naming (`snake_case` modules, noun-verb operation
  names like `subtitle_extract`), commit format (`<type>(<scope>): <subject>`), and testing philosophy
  (prefer real FFmpeg/filesystem over mocks; mock only for failure injection or non-deterministic
  isolation). Note the idealized `src/lib/` + `src/services/` layout shown there does not match the actual
  tree (`src/ops/`, `src/planner/`, `src/models/`, `src/utils/`, `src/webhook/`, `src/worker/`,
  `src/queue/`) — trust the real tree over that document.
- **`specs/`** — per-feature requirements/plan/contracts (spec-kit style). Look here for the FR-XXX
  identifiers referenced by the constitution and for the original design rationale behind a subsystem.

### Testing

`tests/` mirrors a priority order the project cares about: `contract/` (public interfaces — CLI/webhook
contracts) → `integration/` (multi-component, e.g. full pipeline, worker e2e, preset e2e) → `unit/`
(isolated logic — fuzzy matching, caching, filename utils, etc.). Prefer exercising real FFmpeg/filesystem
behavior in integration tests over mocking; reserve mocks for failure injection.
