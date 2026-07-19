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

**Answer (amended by Josh mid-process):** **Git worktree of this repo** — `~/Code/censorr-rewrite` on new branch `rewrite/v2`, created from the tip of `feature/webhook-preset` (commit `201f4d0`, which includes all latest fixes plus these planning docs). v1 stays intact and runnable in the main checkout (`~/Code/Censorr2`) for reference; the rewrite shares git history/remote. All outstanding work was committed before the worktree was created.

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

**Answer:** **New file, clean-only + sidecar** (Option A). Non-destructive default; muted audio is the only audio track; masked subs embedded; Plex-standard sidecar also written; original file untouched.

---

## Q7: Episode (TV) destination default

Movies get `{edition-Censorr}` in the same folder. Plex has no editions for TV — where do clean episodes go by default?

- **Option A — Separate clean root (recommended)**: e.g. `/data/media/tv-clean/Show/Season 01/...` mirroring show/season structure. Point a *separate Plex library* at it → real access control (managed users see only the clean library). Your current tv preset already uses this (`separate_root: /data/media/tv/General_Clean`).
- **Option B — Tagged show folder in same root**: `Show [Censorr]/Season 01/...` — shows up in the same Plex library as a separate show entry; no access control, and the "[Censorr]" suffix pollutes the library title matching.
- **Option C — Plex versions (same folder)**: clean file next to original as another "version" — but versions are user-selectable, so no restriction value.

**Answer:** **Separate clean root** (Option A). Mirror `Show/Season NN/` structure under a configurable clean root; separate Plex library provides access control. Keep tagged-show-folder as a configurable alternative policy.

---

## Q8: Subtitle sidecar naming tokens

Plex recognizes only `forced`, `sdh`, `cc` as flag tokens (`Stem.en.sdh.srt`). v1 inserts a non-standard `censorr`/`clean` token (`Stem.en.censorr.srt`).

- **Option A — Plex-standard only (recommended)**: sidecar is `<video_stem>.<lang>.srt` (plus `.sdh` only if the source track was SDH). The video stem already signals censored (edition tag for movies; clean root for TV) — the extra token adds no Plex value and risks misparsing.
- **Option B — Keep the custom token**: human-greppable at a glance, at the risk of Plex treating the name nonstandardly.
- **Option C — Standard default + opt-in custom token** via config.

**Answer:** **Keep the custom `.censorr` token** (Option B) — Josh explicitly prefers `<video_stem>.<lang>.censorr.srt` despite it being outside Plex's documented tokens (it works in his setup and keeps clean subs greppable on disk). v2 keeps v1's sidecar convention: `Stem.en.censorr.srt`. Design note: place the custom token AFTER the language code and keep the stem exactly matching the video so Plex's stem+language matching still functions; `forced`/`sdh` flags, when present, should follow Plex placement.

---

## Q9: Caching & resumability model

v1 has content-addressed per-operation caching (fingerprint keys, manifests, artifact reconstruction) — the source of several recent metadata-loss bugs.

- **Option A — Job-level idempotency only (recommended)**: each job gets a workdir; before processing, check "does the expected output already exist and match?" → skip (unless `--force`). A failed job's workdir can be resumed stage-by-stage via simple stage-completion markers. No fingerprint keys, no manifest reconstruction.
- **Option B — Port v1's per-op cache**: maximal reuse across different jobs touching the same file, at the cost of the complexity that caused v1's cache bugs.
- **Option C — No caching at all**: simplest; re-runs redo all work (extract+mask is fast, but mute+remux on a 40 GB remux is not).

**Answer:** **Job-fingerprint idempotency** (expanded Option A after clarification). Josh raised two concerns that shaped the final model: (1) *disk ballooning* — solved by retention policy: intermediates deleted immediately on success (only a small job-record JSON survives for the status API), failed workdirs kept with TTL (~7 days) and swept by a GC on worker startup/periodically, `--keep-intermediates` debug override; (2) *config-change invalidation* — solved by a job fingerprint (source identity + resolved effective settings + profanity-list content hash + app version) stored in the job record; fingerprint mismatch auto-reprocesses and replaces the output, `--force` remains the manual override, and a bulk `reprocess` command re-submits a library and only redoes stale-fingerprint files. No per-operation cache; resume-after-failure works stage-by-stage within a retained failed workdir only when the fingerprint is unchanged.

---

## Q10: Word-level audio muting (scope check)

v1 mutes the **entire subtitle entry** (±0.2 s padding) containing a profanity — often a full sentence to kill one word. Word-level precision requires audio-to-text alignment (e.g., faster-whisper transcription or forced alignment), a heavyweight optional dependency.

- **Option A — Out of MVP; design the seam (recommended)**: v2 ships with subtitle-entry-level muting (v1 behavior), but the mute-window *provider* is an interface so a transcription-based provider can be added later without touching the pipeline.
- **Option B — In scope for MVP**: include faster-whisper word alignment from day one (adds model downloads, GPU/CPU tradeoffs, large dependency).
- **Option C — Not interested ever**: hard-code entry-level muting.

**Answer:** **Out of MVP; design the seam** (Option A). MVP mutes at subtitle-line granularity; `MuteWindowProvider` is an interface so transcription/alignment-based providers can be added post-MVP.

---

## Q11: Configuration format & the zero-input experience

Two related decisions: config file format, and what "minimal inputs" means concretely.

Proposed zero-input contract:
- `censorr process movie.mkv` with NO config file and NO flags → works: bundled default profanity list, `movies`/`tv` preset auto-picked by media-type detection, English subtitles preferred, clean-only new-file output next to the source (movies) / under `<source_root>-clean` fallback (TV, when no clean root configured... or same-folder tagged fallback).
- Config file only needed to customize: paths, presets, profanity list, Arr mappings.

Format options:
- **Option A — TOML (recommended)**: `censorr.toml` — comments allowed (JSON's biggest failing for config), Python-native parsing (`tomllib`), less indentation-fragile than YAML.
- **Option B — YAML**: familiar from docker-compose; whitespace-sensitive.
- **Option C — JSON (keep v1)**: no comments; but existing config carries over.

**Answer:** **TOML** (Option A), with the zero-input contract confirmed: bare `censorr process <file>` works with no config file; config exists only to customize.

---

## Q12: Modularization style (explicitly emphasized by Josh)

The rewrite must be "clean and modular, easy for a human to follow." Two common ways to slice a Python package:

- **Option A — Domain-based packages (recommended)**: top-level packages named after the *problem domain*, each readable in isolation:
  `censorr/subtitles/` (parse, select, mask, QC) · `censorr/audio/` (extract, mute-windows, mute, QC) · `censorr/detect/` (fuzzy matcher, profanity list) · `censorr/naming/` (pure path/name logic — the Plex rules live in ONE file) · `censorr/pipeline/` (stage runner, job model, fingerprint) · `censorr/media/` (ffmpeg/ffprobe adapter) · `censorr/service/` (FastAPI, queue, worker) · `censorr/cli/` (thin typer layer) · `censorr/config/` (schema, precedence, presets).
  A human asking "where do Plex names come from?" opens `naming/`; "why did it mute this?" opens `detect/` + `audio/`.
- **Option B — Layer-based (v1 style)**: `models/`, `ops/`, `utils/`, `adapters/` — groups by *kind of code* rather than *what it does*; related logic scatters across layers (v1's naming logic spans 3 utils + an op).
- **Option C — Flat single package**: ~15 modules in one directory; fine for small tools but this one has two applications (CLI + service) on a shared core.

**Answer:** **Domain-based packages** (Option A): `censorr/{subtitles,audio,detect,naming,pipeline,media,service,cli,config}`. Each package owns one problem domain and is readable in isolation; Plex naming rules live in exactly one place.

---

## Q13 (volunteered by Josh at checkpoint): Mute coverage guarantee

> "Muting the whole word, especially single-word, single-line instances of strong profanity is important. Note how I had mute buffers on each side."

**Requirement — under-muting is the failure mode that matters most:**
- Every mute window MUST fully encompass the profanity with a **buffer on each side** (v1 used ±0.2 s around the subtitle entry; v2 keeps side buffers as a first-class, configurable setting, default no smaller than v1's).
- Single-word, single-line subtitle entries of strong profanity are the critical case: the whole entry + buffers is muted; there is no "trim to fit" logic that could leak word edges.
- Audio QC must verify silence across the **entire** window including buffers.
- Constraint on the future word-alignment provider (Q10 seam): even with word-level timing, windows are always emitted with side buffers — precision narrows the window toward the word, never below word-boundaries + buffer. Erring on the side of over-muting is always acceptable; under-muting is not.

---

## Q14 (directed by Josh at design review): Alpine-based Docker deployment

> "The server version needs to run in a Docker image run by docker compose. Design and build a minimal docker compose based on alpine."

**Decision:** v2 ships one **Alpine-based** image (`python:3.12-alpine` + `apk add ffmpeg`), multi-stage build, installed with the `[serve]` extra; docker compose runs two services from that one image — `serve` (API, port 8000, queue volume only) and `work` (pipeline, queue + media + work volumes). Deployment-driven design simplification: the **API container mounts no media** — it does pure path-prefix mapping and enqueues; the **worker** performs the fingerprint check (a fingerprint needs the source file's size/mtime) and completes pre-clean jobs as `skipped`. This shrinks the API's attack surface and its volume config to just the queue.

---

## Q15 (challenged by Josh): Alpine vs python:3.12-slim — decided adversarially

> "Decide between python3.12-slim and alpine and adversarially review that choice. I want to be minimal in memory usage, but also secure for general usage. This is not a webapp that would be exposed to the public internet, hence no auth."

**Decision: Alpine stands** (full adversarial review with measured numbers: `research/base-image-decision.md`). Key facts: on Josh's two criteria (memory, LAN security) the bases effectively tie; measured tiebreakers favor Alpine — `/usr` after ffmpeg is 179 MB vs 543 MB (3×) and ffmpeg 8.1.2 vs 7.1.5. The strongest attack (future glibc-only wheel breaks the build) is mitigated by the curated pinned dep set and a **verified 2-line escape hatch** to slim; the `[align]` extra's torch/ctranslate2 deps are glibc-only but belong in a separate sidecar image on either base. Explicit **flip conditions** documented (glibc-only core dep, align-in-main-image, HW video encode in scope, or ≥2 real musl bugs). No auth by design (LAN-only); optional shared-secret retained in config as defense-in-depth.

---

## Q16 (directed by Josh): Subtitle delivery — embed vs sidecar; and symmetric QC

> "Recommend either the subtitle embed vs the sidecar, with a bias towards ease of use by a non-tech-savvy viewer. I don't want them to have to go and change the subtitles on the video they are watching. If they are watching my censored version, they should just get the muted audio and masked subtitles. Also add quality checks to ensure that we aren't over-muting or over-masking."

**Recommendation: EMBED-only by default** (amends Q6's "sidecar also written by default" and makes Q8's token apply only when sidecars are opted in):
- A sidecar creates a *second* subtitle entry in the player's list (duplicate "English" choices) and is the fragile path (stem-matching, PMS parsing regressions → "Unknown" entries) — both are exactly what confuses a non-tech viewer.
- Embedded delivery yields **exactly one full subtitle track**, correct language, guaranteed masked — no wrong choice exists.
- **Mute captions track** (borrowed from cleanvid's clean-SRT concept + Plex forced-sub behavior): a second embedded text track containing ONLY the masked entries, flagged `forced` + `default`. Players auto-display forced tracks of the audio's language, so during a muted span the viewer sees the masked caption with zero interaction — silence is never unexplained. Configurable off (`subtitles.mute_captions = true` default). Behavior depends on client/account auto-select settings — verify on Josh's clients during rollout; both `forced` and `default` dispositions set to maximize auto-selection.
- Sidecar becomes **opt-in** (`naming.write_sidecar = false` default; Q8's `.censorr` token governs its name when enabled).

**Symmetric QC (new)** — existing QC catches under-muting/under-masking; add over-censoring guards:
- *Over-muting*: total mute ratio budget (muted seconds / runtime, default fail >5%); max merged window duration (default 15 s); matched-entry ratio sanity (>20% of subtitle entries matched → warn); **control-audio integrity** — RMS of sampled non-window output audio must match the original within tolerance (catches filter bugs muting everything, cf. v1's 652f4a4); output duration parity with source.
- *Over-masking*: every altered word must map to a word-list match (with score) — no collateral edits; unmasked text must be byte-identical to the original; entry count/timings unchanged; masked-entry ratio budget (default warn >15%); QC report lists each masked word + match score so borderline fuzzy hits are auditable.
- All thresholds in `[qc]` config; violations → `QCFailure` (exit 4) unless the corresponding `continue_on_*` flag is set. Nuance vs R2: *per-window* generosity (buffers) is required; *file-level* over-censoring is a defect.

---

## Q17 (adversarial review #1 outcomes, decided by Josh 2026-07-16)

A subagent adversarial review (requested by Josh; findings + disposition in `research/adversarial-review-1.md`) surfaced four product decisions:

1. **Zero profanity matches** → **TV: publish a stream-copy remux into the clean root** (clean library stays complete, no re-encode); **movies: complete as `skipped_clean`** (no pointless edition duplicate). Configurable per preset (`[behavior] on_clean_tv/on_clean_movie`).
2. **Source already has an edition tag** → **combine**: `{edition-Director's Cut}` → `{edition-Director's Cut Censorr}`. Plus a hard structural invariant regardless: planned output path ≠ source path, else `JobValidationError` (protects the "original untouched" guarantee).
3. **No usable text subtitles** (none, or PGS/bitmap-only) → **skip with visible reason** (`no_text_subtitles`, exit 2, no retries; `fail_on_no_subtitles` escape) **and prioritize the subtitle-downloader seam (subliminal) as the first post-MVP addition** so these files become processable. Bitmap subtitle tracks are never passed into clean output (unmaskable text would leak).
4. **Audio language ≠ subtitle language** (anime) → **proceed in subtitles-only mode**: mask subs, stream-copy audio unmuted, omit captions track, skip audio QC, record `mode: subtitles_only`. Never a silent proceed; disable via `subtitles.allow_language_mismatch = false`.

Also noteworthy: review finding C5 (tv-clean not mounted in compose) was a **false positive** — the compose file already mounts it; adopted its valid residue (worker startup writability check on the clean root; "compose-validated" claim narrowed to config syntax). The design was rewritten in full (revision 2) rather than patch-edited — patch-editing is what caused the C1 propagation failure.

---

## Q18 (directed by Josh at Step 14 review, 2026-07-18)

> "Specific tags on shows or movies in Radarr or Sonarr will have those shows/movies drive the webhook events to create a censored version. Censored versions should be stored in separate roots so they do not clobber the default versions."

Two design amendments, decided via option review:

1. **Webhook tag gating, ON by default** (amends Q4/R8): new `[service] require_tags` config defaulting to `["censorr"]`. A `Download` event whose movie/series carries none of these tags → 200 `{status: ignored, reason: not_tagged}` — only tagged items produce censored versions, restoring v1's `CENSORR_WEBHOOK_ALLOWLIST` workflow. `arr_tag_presets` still separately maps tags → presets. Direct CLI and `POST /jobs` remain ungated (explicit submission is its own consent).
2. **Separate movie clean root** (amends Q7/R4): new `naming.movie_clean_root`; when unset, derived as `<movies-root>-clean` where the movies root is the parent of the movie's own folder (mirroring R5's tv derivation; too-shallow paths → `JobValidationError` instructing to set it explicitly). Movie folder structure mirrored under the clean root; filename keeps the `{edition-Censorr}` tag for greppability/Plex edition display. Rationale: same-folder editions never clobber (distinct filename, output≠source invariant) but are viewer-selectable within one library entry, providing no access control — a separate clean root + separate Plex library gives movies the same real access control TV already has. Movies whose sources sit flat in the library root (no per-movie folder) require an explicit `movie_clean_root`.
