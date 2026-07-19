# Censorr v2 — Implementation Plan

**For the implementing agent**: Build in the git worktree `~/Code/censorr-rewrite` (branch `rewrite/v2`). The authoritative spec is `.sop/planning/design/detailed-design.md` (revision 2) — this plan tells you *what order* to build in, not *what* to build; when this plan and the design disagree, the design wins. Requirement IDs (R1–R16, N1–N7) refer to the design. The v1 codebase at `~/Code/Censorr2/src` + `tests/` is reference-only: consult its test assertions as behavioral spec where the design says so; never copy v1 code wholesale. Work test-first: each step lists tests that must exist and fail before the implementation makes them pass. Commit per step (or smaller), message format `feat(scope): ...` / `test(scope): ...`.

Deployment artifacts (`Dockerfile`, `docker/entrypoint.sh`, `docker-compose.yml`, `.env.example`) already exist in the worktree — do not rewrite them; Step 15 validates against them.

## Checklist

- [x] Step 1: Project scaffold — installable package, tooling, `censorr version`
- [x] Step 2: Config — TOML schema, precedence, `ResolvedConfig`
- [x] Step 3: Test fixtures + `media/probe`
- [x] Step 4: `detect/` — wordlist + matcher (v1 semantics, allowlist)
- [x] Step 5: `subtitles/` — io, select, mask (+ captions doc)
- [x] Step 6: `naming/` — classify + plan_names golden table
- [x] Step 7: `audio/windows` — providers, buffering, merging
- [x] Step 8: `pipeline/` — context, runner, fingerprint; `censorr inspect` + `process --dry-run`
- [x] Step 9: `media/ffmpeg` remux — first real end-to-end clean file
- [x] Step 10: `verify` — symmetric QC
- [x] Step 11: `publish` + degraded modes + fingerprint skip
- [x] Step 12: `reprocess`, `reconcile`, retention GC
- [x] Step 13: `queue/` + `censorr work`
- [x] Step 14: `service/` — FastAPI webhooks + jobs API (+ Q18: tag gating, movie clean root)
- [x] Step 15: Docker build, compose e2e, README

---

### Step 1: Project scaffold

**Objective**: Installable `censorr` package with tooling and an empty-but-real CLI.
Create `pyproject.toml` (core deps + `[serve]`/`[dev]` extras per N1; ruff with `N` rules + mypy strict per N6; pytest config with `ffmpeg` marker), the package skeleton from design §4 (packages with empty `__init__.py`, no stub logic), `censorr/cli/main.py` with typer app exposing only `version`, and CI workflow (fast job + ffmpeg job).
**Tests**: `tests/contract/test_cli.py::test_version` via typer runner.
**Demo**: `pip install -e .[dev] && censorr version && pytest && ruff check . && mypy censorr` all green.

### Step 2: Config

**Objective**: `config/` — pydantic schema mirroring the design §4 TOML exactly, loader with file discovery (`--config` > `./censorr.toml` > `~/.config/censorr/censorr.toml` > defaults), one-shot precedence resolution (CLI explicit > preset > file > defaults) producing frozen `ResolvedConfig`. Relative paths resolve against the config file's directory. Bundle `censorr/wordlists/default.json` (schema per R1; seed content: port v1's `config/profanity_list.json` words).
**Tests**: precedence matrix; empty/absent file valid; invalid keys rejected; preset overlay; relative-path resolution.
**Demo**: `python -c` snippet loads an empty TOML and prints a fully-defaulted `ResolvedConfig`.

### Step 3: Test fixtures + probe

**Objective**: `tests/fixtures.py` building lavfi fixtures per research/test-fixtures.md (session-scoped cache keyed by recipe hash) — at minimum: movie-named, episode-named-in-tree, multi-subtitle (en/en-SDH-titled/es), multi-audio (aac stereo + ac3 5.1), no-subtitle, PGS-only (mux a tiny bitmap sub or skip-if-impossible with a documented alternative), language-mismatch (jpn audio + eng subs). Known-profanity SRT at known timestamps using words from the bundled list. Then `media/probe.py`: ffprobe JSON → `MediaInfo`/`StreamInfo` (codec, language, disposition, titles, duration).
**Tests** (`@pytest.mark.ffmpeg`): each fixture builds; probe returns expected typed streams.
**Demo**: `pytest tests/integration/test_probe.py -v` shows typed stream info from synthesized media.

### Step 4: detect/

**Objective**: `wordlist.py` (load/merge bundled + user list + allowlist, content hash for fingerprinting) and `matcher.py` porting v1 `FuzzyMatcher` semantics on rapidfuzz.
**Before writing code**: read v1's `tests/unit/test_fuzzy_matcher.py`, `test_per_word_fuzzy.py`, `test_allowlist.py` and port their assertions as the spec (N5). Port `src/utils/fuzzy_matcher.py` *semantics* (window strategy, per-word thresholds, morphology scoring, aggressive mode) — reimplement cleanly, don't copy.
**Tests**: the ported spec + `Match.span`/`replacement` fields; allowlist suppression ("damage" never matches "damn").
**Demo**: pytest green over the ported v1 spec — the matcher provably behaves like the battle-tested one.

### Step 5: subtitles/ (io, select, mask)

**Objective**: `io.py` (pysubs2-only load/save; `SubtitleEntry` with `text` + `plaintext`), `select.py` (text-codec filter per R12, language + title-exclude + forced rules over `MediaInfo`; `TrackSelection` incl. `language_mismatch` flag and audio-track choice), `mask.py` (masked doc — asterisks-preserving-first-letter or `replacement`; masks re-injected into styled text; captions doc = masked entries only, `None` when empty).
**Tests**: unit — selection matrix over synthetic `MediaInfo` (bitmap exclusion, SDH exclusion, forced, mismatch detection); masking preserves timings/count/styling, byte-identical unmasked plaintext. Integration — extract-and-parse from the multi-subtitle fixture.
**Demo**: script masks the fixture SRT and prints before/after entries + the captions doc.

### Step 6: naming/

**Objective**: `plex.py` + `models.py` per design §4: `classify` (Arr hint > path/filename heuristics), `plan_names` implementing R4 (edition insertion, no-year fallback, **combine** rule, output≠source invariant) and R5 (clean-root config + derivation algorithm, shallow-path refusal), sidecar paths only when enabled, track titles.
**Tests**: the golden table (design §7 lists the required cases) as parametrized data — this is the Plex contract; keep it brutally readable.
**Demo**: `censorr inspect`-precursor snippet: feed paths, print planned names for a dozen golden cases.

### Step 7: audio/windows

**Objective**: `windows.py`: `MuteWindowProvider` protocol, `EntrySpanProvider` (entry span ± `buffer_s`, overlap-merge), `ExternalFileProvider` (`--mute-windows` JSON, merged). Providers are pure (R15 guardrails).
**Tests**: R2 cases — single-word entry gets full span + both buffers; merge of overlapping/adjacent windows; external merge; determinism.
**Demo**: pytest + snippet printing windows derived from the fixture SRT.

### Step 8: pipeline/ — context, runner, fingerprint; inspect + dry-run

**Objective**: `context.py` (`PipelineContext` per design §4), `stages.py` wiring Steps 3–7 into `probe → select_tracks → acquire_subtitles → detect → plan_windows → mask_subtitles → plan_names` with per-stage input validation and mode transitions (`clean`, `subtitles_only`, skip outcomes per R16), `fingerprint.py` (R10 hash, path-independent), `errors.py` (design §6 taxonomy), `runner.py` (sequential, stage markers in workdir, `on_progress`), and the first real CLI: `censorr inspect <file>` and `censorr process <file> --dry-run` (rich rendering in `cli/views.py`; exit codes per §6).
**Tests**: unit — runner stage sequencing/short-circuits on a stubbed context; fingerprint matrix; exit-code contract. Integration — `inspect` on fixtures: happy, clean, no-subs, language-mismatch each produce the right mode/outcome.
**Demo**: `censorr inspect "Test Movie (2024).mkv"` prints tracks, matches, windows, planned names; `--dry-run` shows the full plan. **The tool is now demoable end-to-end minus writing.**

### Step 9: media/ffmpeg — remux (first real output)

**Objective**: `ffmpeg.py` (`RemuxPlan` model + `remux()` per design §4: args-as-list, filtergraph → `workdir/mute.filter` + `-filter_complex_script`, single-pass copy-video/mute-encode-audio per R13 codec policy, masked + captions subs, dispositions/titles/language, `-map_metadata 0 -map_chapters 0`, `CENSORR_FINGERPRINT` metadata, `-progress pipe:1` parsing in `progress.py`, heartbeats env-suppressible), `audio_mode="copy"` path for clean/subtitles-only. Wire as the `remux` stage; `process` (without `--dry-run`) now produces a temp output in the workdir (publish comes in Step 11 — for this step the CLI reports the temp path).
**Tests**: integration — remux the movie fixture: probe output for track layout, dispositions, titles, fingerprint metadata, duration parity; RMS silence in a buffered window vs. audible control (decode via `-ss/-t`); eac3 5.1 fixture exercises codec preservation; captions track omitted on the clean fixture.
**Demo**: `censorr process "Test Movie (2024).mkv" --keep-intermediates` → playable clean MKV in the workdir; muted span audibly silent, masked captions display.

### Step 10: verify — symmetric QC

**Objective**: `subtitles/qc.py` + `audio/qc.py` producing `QCReport` per R14 (under-mute RMS per window; over-mute budgets: mute ratio, max window, matched-entry ratio; within-output control integrity; duration parity; over-mask: altered-words-map-to-matches, unmasked plaintext identical, ratios, per-word audit). `QCError` on violation unless `continue_on_*`. Wire as `verify` stage; report saved to workdir and summarized in CLI output.
**Tests**: unit — report math over synthetic measurements. Integration — hostile match-everything wordlist trips budgets; all-silent audio (mute window 0–duration) trips control integrity; happy path passes; QC skipped appropriately in clean/subtitles-only modes.
**Demo**: `censorr process` prints a QC summary table; a deliberately hostile wordlist run exits 4 with the QC report explaining why.

### Step 11: publish + degraded modes + skip

**Objective**: `publish` stage: atomic move (rename; copy+SHA256-verify+delete across filesystems — v1's `FinalDestinationManager` semantics), sidecar written only when enabled, superseded-output deletion from `job.deleted_files` (R10), job-record write, intermediate cleanup (R11 success path). Fingerprint skip-check before running (expected output exists → read tag → compare; `--force` bypass). Complete R16 end-to-end: zero-match TV stream-copy publish / movie skip; subtitles-only publish; no-subs skip.
**Tests**: integration — full `process` publishes to golden paths; re-run skips (`fingerprint_match`); `--force` re-runs; modified wordlist re-processes and replaces; upgrade-with-deletedFiles removes the old output; each R16 fixture lands its decided outcome; **no sidecar by default**, sidecar when opted in; failed QC leaves the library untouched.
**Demo**: the complete CLI story on a tmp media tree — process, re-run (skips), change wordlist (replaces), episode lands in derived clean root.

### Step 12: reprocess, reconcile, retention

**Objective**: `reprocess <root>` (walk; skip Censorr outputs via fingerprint tag / edition tag in name; skip Plex extras per R7; fingerprint-driven), `reconcile <clean_root>` (delete clean outputs whose source is gone; `--dry-run`), `retention.py` GC (failed-workdir TTL, record TTL) invoked by worker start + interval (worker exists next step; expose `censorr gc` for testing).
**Tests**: integration — tree with processed/unprocessed/extra/orphan files: reprocess touches exactly the right set; reconcile removes exactly orphans (dry-run prints, real run deletes); GC honors TTLs.
**Demo**: `censorr reprocess /tmp/library --dry-run` prints an honest worklist; `reconcile --dry-run` names the orphan.

### Step 13: queue/ + worker

**Objective**: `file_queue.py` (v1's design: atomic renames `incoming→processing→done|failed`, leases, bounded retries, stale recovery — plus R9 additions: same-source dedup on enqueue, lease renewal API), `service/worker.py` (claim loop; existence + fingerprint checks worker-side; `run_job` with `on_progress` → record progress + lease renewal; pre-publish source re-stat → `TransientError`; GC on start + interval), `censorr work` command. Job records per design §5, atomic writes.
**Tests**: unit — queue state machine incl. dedup, lease expiry/renewal, retry exhaustion (tmp dirs, no Docker). Integration — worker processes a fixture job end-to-end via the queue; mid-job source swap fails transient and succeeds on retry.
**Demo**: two terminals: manually drop a job JSON into `incoming/`, `censorr work` picks it up, record shows live progress, clean file lands.

### Step 14: service/ — FastAPI

**Objective**: `arr_models.py` (pydantic, `extra="ignore"`, per research/arr-webhook-schemas.md), `routes_webhooks.py` (`/webhook/radarr`, `/webhook/sonarr` per design §4: Test/Download/ignore, prefix-map-only path handling, preset precedence query > tag map > media type, secret via `?token=` or header, upgrade `deletedFiles` into the job), `routes_jobs.py` (`POST /jobs`, `GET /jobs/{id}`, `GET /jobs`, `/healthz`, `/status`), `app.py` (lifespan: config + queue init), `censorr serve` (uvicorn). Structured JSON logging (N2) across service + worker.
**Tests**: contract — captured payload fixtures for every branch (Test, Download movie/episode, upgrade, unknown event, unmapped path, bad token, tag-mapped preset); OpenAPI docs render.
**Demo**: `censorr serve` + curl a captured Radarr payload → 202 with job id; `censorr work` in another shell processes it; `GET /jobs/{id}` shows progress → done.

### Step 15: Docker + compose e2e + README

**Objective**: Build the existing `Dockerfile` against the now-real package (adjust only if the build reveals drift — e.g. wordlist packaging into the wheel); add the worker's clean-root startup check (N7); run the compose stack and drive one webhook job through it; write `README.md` (quick start: compose, Arr connection setup with real Webhook settings, CLI usage, config reference) and `CLAUDE.md` for the new codebase (build/test commands, architecture map).
**Tests**: `tests/integration/test_container_smoke.py` (`@pytest.mark.docker`): image builds; `serve` healthcheck passes; end-to-end webhook → clean file on a bind-mounted tmp tree.
**Demo**: `docker compose up -d`, curl the webhook, watch `docker compose logs work` process it, clean file appears on the host mount. **Ship it.**

---

## Cross-step rules

- After each step: `pytest && ruff check . && mypy censorr` green before commit.
- No step may leave dead code for a later step ("wired in Step N+2" is not allowed — if it isn't reachable, don't build it yet).
- When a design detail is ambiguous during implementation, check `idea-honing.md` for the decision history before guessing; if still ambiguous, ask Josh rather than inventing behavior (his standing instruction).
- v1 tests are spec for: matcher (Step 4), queue semantics (Step 13), exit codes (Step 8). Everything else: the design is the spec.
