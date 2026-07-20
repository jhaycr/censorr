# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

Censorr v2: censors profanity in media files for the Plex/Sonarr/Radarr ecosystem —
mutes profane audio spans, masks profane subtitle text, and publishes a **new clean
copy** into a separate `*-clean` root (originals are never modified). Runs as a direct
CLI and as a two-role service (FastAPI webhooks + file-queue worker). Core runtime
dependency: FFmpeg ≥ 6 on PATH.

This is a ground-up rewrite; the v1 codebase lives in the `~/Code/Censorr2` checkout
(same repo, branch `feature/webhook-preset`) as reference only. The authoritative design
is `.sop/planning/design/detailed-design.md` in that checkout (requirement IDs R1–R16,
N1–N7 used in comments refer to it), amended by `idea-honing.md` Q18 (webhook tag
gating; separate movie clean root).

## Commands

```bash
pip install -e .[dev,serve]          # install (editable, all extras)

pytest                               # full suite (needs ffmpeg on PATH)
pytest -m "not ffmpeg and not docker"  # fast pure-logic tests (CI fast job)
pytest -m ffmpeg                     # integration tests on synthesized media
pytest -m docker                     # container build + e2e smoke (needs docker)
pytest tests/unit/test_matcher.py::TestAllowlistSuppression  # one test

ruff check .                         # lint (includes pep8-naming)
mypy censorr                         # strict type-check
docker compose up -d --build         # serve + work stack

censorr process movie.mkv --dry-run  # run the CLI
```

All three gates (pytest, ruff, mypy) must be green before committing.

## Architecture

Domain-based packages; dependency arrows only point downward. `naming/` and `detect/`
are **pure** (no filesystem writes, no subprocess); `media/` (+ `audio/qc.py`) are the
only FFmpeg subprocess sites, always args-as-list, never a shell.

```
censorr/
├── cli/        main.py (typer commands), views.py (rich rendering)
├── service/    app.py (FastAPI factory), arr_models.py, routes_webhooks.py,
│               routes_jobs.py, worker.py (queue claim loop), logging.py (JSON lines)
├── pipeline/   context.py (PipelineContext + QCReport), stages.py (all stage fns),
│               runner.py (stage sequences), fingerprint.py (idempotency + skip-check),
│               job.py (Job/JobRecord), errors.py (exit-code taxonomy),
│               library.py (reprocess/reconcile walks), retention.py (GC)
├── subtitles/  io.py (pysubs2), select.py (track selection), mask.py, qc.py
├── audio/      windows.py (mute-window providers), qc.py (RMS measurement)
├── detect/     wordlist.py, matcher.py (fuzzy matching + allowlist)
├── naming/     plex.py (THE Plex path contract, pure), models.py
├── media/      probe.py (ffprobe), ffmpeg.py (remux), progress.py (heartbeats)
├── config/     schema.py (TOML schema), load.py (precedence), presets.py
├── queue/      file_queue.py (atomic-rename job queue)
└── wordlists/  default.json (packaged data)
```

### Pipeline

Both the CLI and the worker run exactly this stage sequence (`pipeline/runner.py`):

```
probe → select_tracks → acquire_subtitles → detect → plan_windows
      → mask_subtitles → plan_names → remux → verify → publish
```

Stages are pure-ish functions `(PipelineContext, workdir) -> PipelineContext`. A stage
setting `ctx.outcome` (e.g. `no_text_subtitles`, `skipped_clean`, `language_mismatch`)
short-circuits everything after it — the R16 degraded modes are visible outcomes, never
silent proceeds. `PLANNING_STAGES` (through plan_names) is what `inspect`/`--dry-run`
run; publish is always last, so a failed job never leaves partial files in a library.

### Key invariants (do not weaken)

- **Under-muting is never acceptable**: mute windows = full subtitle-entry span +
  `buffer_s` each side; providers may narrow toward a word post-MVP but never below
  word boundary + buffer. `verify` measures RMS of every window in the actual output.
- **Output ≠ source, structurally**: `naming/plex.py` raises `JobValidationError` if the
  planned path equals the source; sources are additionally mounted read-only in compose.
- **The output file is the idempotency store** (R10): the job fingerprint (source
  size+mtime + content-affecting settings + wordlist hash + app version — deliberately
  path-independent and `service.*`-independent) is embedded as `CENSORR_FINGERPRINT`
  MKV metadata; skip-checks read it back. No separate cache to corrupt.
- **QC is symmetric** (R14): under-mute/under-mask AND over-mute/over-mask budgets;
  control-audio integrity is measured within the output, never cross-file.
- **Track identity flows through typed fields only** — never path substrings (a chief
  v1 bug class).
- **Never shell-interpolate** (N3): FFmpeg args as lists; filtergraphs go through
  `-filter_complex_script` files.

### Exit-code / error taxonomy (`pipeline/errors.py`)

`0` ok · `2` skipped (a JobResult, not an exception) · `3` `JobValidationError`
(deterministic, no retry) · `4` `QCError` (deterministic, no retry, workdir kept) ·
`1` `TransientError` (worker retries up to `max_retries`).

### Service path

`serve` (sources mounted read-only for the UI's path browser, Q19; no clean roots, no
media writes) parses native Arr webhook payloads, applies the Q18 tag gate
(`service.require_tags`, default `["censorr"]`), maps path prefixes (pure string logic),
resolves the preset name (query > tag map > media-type default), and dedup-enqueues.
`work` claims via atomic rename, does existence/fingerprint prechecks, re-resolves
config with the job's preset, renews its lease on every progress tick, re-stats the
source right before publish (Arr upgrade mid-job → `TransientError` → retry sees the
new file), and writes atomic `JobRecord`s served by `GET /jobs/{id}`.

## Testing conventions

`tests/unit/` (pure logic, no FFmpeg — CI fast job), `tests/contract/` (CLI exit codes,
API payload branches via TestClient), `tests/integration/` (`@pytest.mark.ffmpeg`,
real FFmpeg over lavfi-synthesized fixtures from `tests/fixtures.py` — no binary media
in git; `@pytest.mark.docker` for container smoke). Prefer real FFmpeg/filesystem over
mocks; mock only for failure injection (e.g. the worker's `on_stage` hook). The v1 test
assertions were the ported spec for the matcher and queue semantics.

Note: the dense 15 s fixtures legitimately exceed the 5% over-mute QC budget — QC-passing
scenarios use `qc_pass_fixture` (90 s); the dense ones double as QC-failure cases.

## Decision history

When behavior seems ambiguous, check `idea-honing.md` (in the Censorr2 checkout's
`.sop/planning/`) for the Q1–Q18 decision record before guessing; if still ambiguous,
ask Josh rather than inventing behavior.
