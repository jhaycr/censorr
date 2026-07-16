# Idea Honing: Censorr v2 Rebuild

Requirements clarification Q&A. Each question is recorded with the user's final answer.

## Standing requirement (stated by Josh mid-research, 2026-07-15)

The rewrite must be **clean and modular, easy for a human to follow**. This outranks cleverness: small modules with obvious names, minimal indirection, readable by a human without a map.

---

## Q1: Implementation language & stack

Should v2 stay on Python, or is this the moment to switch?

- **Option A — Python 3.12+ (recommended)**: Keeps typer/pydantic/rapidfuzz/pysubs2 ecosystem; v1's 60+ test files remain portable as an executable behavioral spec; FFmpeg subprocess glue is what Python does well; matches your existing tooling (black/ruff/mypy/pytest).
- **Option B — Go**: single static binary, nicer deploys; but rewrite loses the test-spec reuse and fuzzy-matching library maturity (rapidfuzz).
- **Option C — TypeScript/Node**: fine for the service half, weaker for the media-processing half.

**Answer:** **Python 3.12+** (Option A). Keep the typer/pydantic/rapidfuzz/pysubs2 ecosystem; port v1 tests as the behavioral spec.

---

## Q2: Where does v2 live?

New repository, or inside the existing Censorr2 repo?

- **Option A — New sibling repo/directory (recommended)**: e.g. `~/Code/censorr` (or `Censorr3`). True clean slate for the implementing agent; v1 stays runnable and diffable for reference; no risk of the agent "borrowing" v1 code paths or being confused by two source trees.
- **Option B — Same repo, new top-level package**: shares git history and CI, but the implementing agent must constantly distinguish old vs. new code, and the constitution's 400-line PR gates would fight a ground-up build.
- **Option C — Same repo, orphan branch**: clean tree, shared remote; slightly awkward day-to-day.

**Answer:** **New sibling repo** (Option A), e.g. `~/Code/censorr`. v1 (Censorr2) stays intact as reference.

---

## Q3: Service API shape

How should the v2 service ingest work from Sonarr/Radarr?

- **Option A — FastAPI accepting native Arr webhook payloads (recommended)**: endpoints like `/webhook/radarr` and `/webhook/sonarr` parse what Arr actually sends (`movieFile.path`, `episodeFile.path`, `eventType`, incl. `Test`); plus a generic `/jobs` endpoint for manual/scripted submissions and `/jobs/{id}` for status. FastAPI gives typed pydantic parsing and free OpenAPI docs.
- **Option B — Keep v1's custom payload + plain WSGI**: minimal deps, but keeps the integration gap (Arr can't natively call it; needs glue scripts).
- **Option C — Custom-script-first**: skip webhooks; ship a shim script reading Arr env vars that POSTs to a simple API. Works, but couples to container exec plumbing.

**Answer:** **FastAPI + native Arr payloads** (Option A). `/webhook/radarr`, `/webhook/sonarr`, generic `/jobs` submit, `/jobs/{id}` status, handle `Test` events. Optionally still ship a tiny custom-script shim as an alternative trigger.

---

## Q4: Preset selection precedence for incoming jobs

When a webhook arrives, how is the processing preset chosen? Proposed compositional precedence (highest wins):

1. Explicit query param on the webhook URL (`/webhook/radarr?preset=movies-strict`)
2. Arr tag mapping from config (Arr label tag like `censorr-strict` on the series/movie → preset)
3. Media-type default from payload shape (`movie` payload → `movies` preset, `series` payload → `tv` preset)

This means zero-config: pointing Radarr at `/webhook/radarr` with no params just works using the `movies` preset.

- **Option A — All three layers (recommended)**
- **Option B — Query param + media-type default only** (skip tag mapping; simpler, can add later)
- **Option C — Explicit only** (no defaults; unconfigured webhooks are ignored)

**Answer:** **All three layers** (Option A): query param > Arr tag mapping > media-type default. Zero-config webhook works out of the box.

---

## Q5: Queue & worker topology

How should the service execute jobs?

- **Option A — Keep the split: API container (no FFmpeg) + worker container (FFmpeg), file-based queue on a shared volume (recommended)**: v1's file queue is proven, zero-dependency, crash-safe. Change from v1: one image, role selected by command (`censorr serve` / `censorr work`), and the worker calls the pipeline as a library instead of shelling back into the CLI. The queue also becomes the job-status store served by `/jobs/{id}`.
- **Option B — Single container, FastAPI + in-process background worker**: simplest deploy (one service), but a crashed FFmpeg run takes the API down with it, and job durability across restarts needs the same file-state work anyway.
- **Option C — Real broker (Redis/RQ or similar)**: robust multi-worker scaling, but adds an external service for a single-host home-media tool — over-engineering.

**Answer:** **API + worker with file queue** (Option A). One image, role by command (`censorr serve` / `censorr work`); worker calls the pipeline as a library; queue directories back the `/jobs/{id}` status API.

---

## Q6: Default output behavior (safety & track policy)

Proposed defaults for a bare `censorr process <file>` and for webhook jobs:

- **Non-destructive by default**: always write a NEW file; never touch the original (v1's `REMUX_NEW_FILE` becomes the only default; in-place replacement becomes an explicit opt-in flag, if kept at all).
- **Clean-only container**: output contains video + **muted audio as the only/default audio track** (original profane track pruned) + masked subtitle embedded; original file remains next to it with all original tracks.
- **Subtitle sidecar also written by default** (Plex-standard naming) so subs work even when clients struggle with embedded tracks.

- **Option A — All of the above (recommended)**: guarantees family-safe output (no client can pick the profane track), original always preserved.
- **Option B — Keep both audio tracks** (muted default + original second): one file serves everyone, but any client/user can flip to the profane track — defeats the purpose for shared libraries.
- **Option C — In-place replacement default** (v1's original default): destructive; requires backup handling.

**Answer:** _pending_
