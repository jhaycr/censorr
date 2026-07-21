# A History of Censorr

How Censorr got built — four codebases across ten months, what each one was
reaching for, what worked, and what pushed the next attempt. Written 2026-07-20,
reconstructed from the git history and planning records of the sibling checkouts
`~/Code/Censorr1`, `~/Code/Censorr2`, and `~/Code/Censorr` (the current shipping
tree lives at `~/Code/censorr`).

The goal never changed: take a movie or episode, find profanity from its
subtitles, mute the matching audio spans and mask the subtitle text, and publish
a clean copy that Plex resolves correctly — driven directly by Sonarr/Radarr.
What changed, four times, was the architecture and the discipline used to get there.

## Timeline at a glance

| # | Checkout | Active | Tooling / author | Commits | Fate |
|---|----------|--------|------------------|--------:|------|
| 1 | `Censorr1` | Sep 14–20 2025 | SpecKit ("Specify template") | 5 | Abandoned after subtitle masking worked |
| 2 | `Censorr2` (v1) | Sep 20 – Dec 14 2025 | SpecKit → Kiro → governance gates | ~100 | Grew powerful but fragile; became the *reference* for the rewrite |
| 3 | `Censorr` (unnumbered) | Dec 15 2025 – Jan 4 2026 | GitHub Copilot, hand-driven | 15 | Clean-room retry; working end-to-end prototype, then stalled |
| 4 | `Censorr2/.sop` + `censorr` (v2) | Jul 15–20 2026 | **Claude Fable 5** (design + build), Sonnet 5 (QC), Opus 4.8 (polish) | 20+ | **Shipped** — the current tree |

The numbering is not chronological and the efforts overlap: #2 and #3 ran on
parallel tracks, and #4's *planning* lives inside the #2 checkout while its *code*
is a fresh tree. What follows is the story in the order it actually happened.

---

## Attempt 1 — `Censorr1`: the first cut (Sep 2025)

The first Censorr started from a SpecKit "Specify template" and framed the problem
in phases: **subtitles first, audio later**. Its README is explicit — "Clean
subtitles (first feature) and, in a separate phase, clean audio." It defined a
unified JSON word-list format, multiple masking modes (full / partial /
replacement), and debug affordances (`--subtitles-only`, `--dry-run`,
`--debug-persist`) that would survive into every later version.

**What worked**
- Subtitle masking got working end-to-end — the last commit is literally
  "Subtitle masking fixed" (Sep 20). The core insight that detection should be
  *subtitle-driven* (no audio transcription) was established here and never
  abandoned.
- The debug-first ergonomics (dry-run, subtitles-only, persist artifacts) proved
  their worth immediately and became permanent.

**What didn't**
- It never reached the audio-muting phase. Only five commits exist; the audio spec
  (`002-audio-muting`) stayed a stub.
- Structurally it was a thin `src/{cli,services,lib}` layout with no pipeline
  abstraction — fine for one feature, not a foundation.

It was set aside within a week, but its subtitle format and CLI conventions were
carried straight into the next attempt.

---

## Attempt 2 — `Censorr2` (v1): the workhorse that got heavy (Sep–Dec 2025)

`Censorr2` is where Censorr became a real tool. Over roughly a hundred commits it
grew every capability the product needed, and in doing so accumulated the
complexity that eventually justified a rewrite. This is the codebase later
generations refer to simply as **"v1."**

The build moved through three methodological phases, all visible in the log:

1. **SpecKit specs (Sep–Oct).** Formal `specs/00N-*` folders with plans,
   research, data models, and OpenAPI contracts. This produced the composable
   **operations pipeline** — `subtitle_extract → merge → mask → qc` and
   `audio_extract → mute → qc`, feeding `video_remux` — with a `Planner`,
   an `Executor`, and content-addressed `CacheManager`.
2. **Kiro steering (`.kiro/`).** A second spec system layered on for development
   principles, testing strategy, and conventions.
3. **Governance gates (Nov).** A `CONSTITUTION.md`, "Feature-Sized" PR caps
   (≤400 lines / ≤10 files), a `Dangerfile.js` enforcing a task ledger, and CI
   to match — an attempt to keep AI-assisted change small and traceable.

Feature-wise it went deep: per-word fuzzy thresholds with an aggressive-variant
mode and a false-positive allowlist (`damage` ≠ `damn`); length-based threshold
floors; preset-driven audio parameter parity (preserve original codec / channels /
sample-rate / bitrate); a filesystem-backed job queue with atomic claim, retries,
and crash recovery; a WSGI webhook + Gunicorn worker; and a split Docker build
(`Dockerfile.tool` with FFmpeg, `Dockerfile.web` without).

**What worked** (and was deliberately carried into v2)
- **Subtitle-driven fuzzy detection.** The `FuzzyMatcher` (~450 lines, rapidfuzz)
  was the most battle-tested logic in the repo — per-word thresholds, aggressive
  mode, allowlist suppression — and its unit tests became the executable spec for
  the rewrite's matcher.
- **Output verification (QC).** Re-scanning the masked output for residual
  profanity, and RMS-comparing muted windows against neighboring control audio, is
  a genuinely good idea that few comparable tools do. Kept as a first-class concern.
- **The FFmpeg adapter shape.** Args-as-list (never a shell), `ffprobe` → typed
  `MediaInfo`/`TrackInfo`, heartbeat logging for long runs. Ported almost verbatim.
- **Subtitle selection** (language + title include/exclude, SDH/HI/CC excluded by
  default so the mask source is clean dialogue), dry-run everywhere, and a clean
  exit-code contract (0 ok / 2 ignored / 3 permanent / else transient).
- **Lean, correct dependencies:** typer, pydantic v2, rapidfuzz, pysubs2, rich.

**What didn't** (the diagnosis that drove the rewrite — see
`Censorr2/.sop/planning/research/existing-code-pipeline.md`)
- **The `Planner` was dead weight.** `plan()` had TODOs for dependency resolution;
  presets bypassed it entirely with explicit op lists. It even had copy-pasted code
  *inside a docstring*. A pipeline is just an ordered list of stages — the
  abstraction earned nothing.
- **Artifact routing by side-channels.** The executor special-cased ops by name;
  `video_remux` globbed the filesystem to *find* the muted audio; track identity
  was inferred from path substrings. Whole classes of bugs came from metadata lost
  between the cache and the executor.
- **A ~480-line `process()`** of manual four-layer flag precedence
  (CLI > preset > config > default) as ad-hoc `if` cascades, with sentinel-value
  bugs like `output != "./output"` to detect "did the user set this?"
- **A 30-field `OperationFlags` god object** passed to every op, mutated through
  `flags.__dict__["_applied_audio_encode"]` side-channels.
- **Caching over-engineered for the real need.** Content-addressed per-op manifests
  with type-inference-from-file-extension, when the actual requirement was just
  "resume a failed run" and "skip if already processed."
- **Governance friction.** The 400-line PR gates were designed for incremental
  change and actively fought any ground-up work — a signal that the process had
  outgrown its usefulness for this project.

`Censorr2` was never deleted. It was too valuable as a working reference and a test
oracle — which is exactly the role it plays today.

---

## A parallel track — `Censorr` (unnumbered): the clean-room retry (Dec 2025 – Jan 2026)

While `Censorr2` sat heavy, a *second* effort started fresh on Dec 15 2025 —
"Initial commit; prototype working end-to-end" — built with GitHub Copilot and
committed entirely by hand. This is the unnumbered `~/Code/Censorr` checkout, and
it ran in parallel with (not after) the dormant `Censorr2`.

It was a deliberate simplification: a single `src/censorr` package with
`cli / commands / worker / api`, a `RunPipeline` reused by both CLI and worker
paths, and a modern stack (FastAPI + typer + rapidfuzz + pysubs2). The
`WORKER_IMPLEMENTATION_PLAN.md` states the philosophy plainly — "in-memory only,
no SQL persistence," webhook-driven submission, containerized. Over three weeks it
added subtitle QC, a fuzzy-matcher retune, an abstracted job queue, worker/job
control commands, and Radarr/Sonarr webhook support.

**What worked**
- It reached a working end-to-end prototype *fast*, and proved a much smaller
  architecture could do the core job — validating the instinct that v1 was
  over-built.
- The CLI/worker-share-one-pipeline idea (later a hard rule in v2: the worker and
  the CLI run the *exact same* stage sequence) was demonstrated here.

**What didn't**
- In-memory queue only — no crash safety or restart durability, so not truly
  deployable as a service.
- It stalled in early January (last commit Jan 4) before hardening into something
  production-ready, and its AI-assistance was Copilot-generated without the
  design-first paper trail that the eventual rewrite insisted on.

Its real contribution was evidence: *small works.* That lesson went directly into
the rewrite's scope.

---

## Attempt 4 — the Fable rewrite (v2): design-first, and it shipped (Jul 2026)

In mid-July 2026 Josh returned to the problem with a different method entirely:
**Prompt-Driven Development (PDD)**, executed by **Claude Fable 5**. PDD came from
the [Strands Agents `agent-sop` toolkit](https://github.com/strands-agents/agent-sop)
(Amazon) — the `pdd` SOP ("Prompt-Driven Development"), invoked in the Fable 5
workflow as the `/pdd` skill in Claude Code. Its fingerprint is unmistakable: the
SOP scaffolds `rough-idea.md → idea-honing.md → research/ → design/ →
implementation/`, which is exactly the `.sop/planning/` layout that appeared in the
`Censorr2` checkout. Rather than start coding, Fable first produced a full planning
paper trail there (`.sop/planning/`, Jul 15–16): a rough-idea brief, an 18-question
idea-honing Q&A, research notes (dependency audit, base-image analysis, Arr webhook
schemas, Plex naming rules, and a frank `existing-code-*` autopsy of v1),
adversarial design reviews, a detailed design with numbered requirements
(R1–R16 / N1–N7), and a 15-step TDD implementation plan.

The idea-honing explicitly chose a **clean-slate sibling repo** over reworking v1
in place — "v1 stays runnable and diffable for reference; no risk of the agent
borrowing v1 code paths" — which is why the v2 code became a separate tree.

Then, Jul 17–19, Fable 5 (with Sonnet 5 taking the symmetric-QC stage) implemented
it against that plan, one reviewed step at a time. The Opus 4.8 session on Jul 20
did the finish work: shipped a single-page web UI (job history, ad-hoc/backfill
submission, in-browser config editing, a read-only path browser), removed the dead
SpecKit/Kiro/governance scaffolding the rewrite no longer used, and got CI green.

**What the rewrite kept from the lessons above**
- Subtitle-driven fuzzy detection with the ported matcher semantics and v1's tests
  as the spec; output QC as a first-class, *symmetric* check (under- **and**
  over-mute/mask budgets); the args-as-list FFmpeg discipline; the exit-code
  contract; dry-run everywhere.

**What it fixed by design**
- **No planner, no cache-as-truth.** A pipeline is a fixed ordered list of stages
  (`probe → select_tracks → acquire_subtitles → detect → plan_windows →
  mask_subtitles → plan_names → remux → verify → publish`); the CLI and worker run
  the *same* sequence.
- **Typed `PipelineContext` passed stage-to-stage** — no filesystem archaeology,
  no name-based dispatch, no path-substring track identity (the chief v1 bug class).
- **Precedence resolved once, generically**, in a config module — no 480-line flag
  cascade, no sentinel bugs.
- **The output file *is* the idempotency store** — a content fingerprint embedded
  as MKV metadata, read back on skip-checks. No separate cache to corrupt.
- **Originals are never touched**; clean copies publish to a separate `*-clean`
  root, and the code refuses to write a path equal to its source.
- **Degraded modes are visible outcomes**, never silent proceeds.

This is the version that ships today at `~/Code/censorr` (public repo
`jhaycr/censorr`), running as the compose stack described in the README.

---

## What the whole arc taught

- **Detection strategy was right from day one.** Subtitle-driven fuzzy matching —
  cheap, deterministic, no ML dependency — survived all four attempts unchanged in
  concept. The matcher and its allowlist were the crown jewels; everything else was
  plumbing.
- **The plumbing is where it went wrong, twice.** v1's abstractions (planner,
  content-addressed cache, god-object flags, side-channel artifact routing) each
  looked reasonable and each became a bug farm. The rewrite's north star was
  *typed data flowing through fixed stages* — boring, and correct.
- **Small wins.** The Copilot prototype proved a fraction of v1's surface area
  could do the job; the rewrite deliberately scoped to that.
- **Process has to match the task.** SpecKit and the 400-line governance gates fit
  incremental feature work and fought a ground-up rebuild. PDD — design and
  interrogate *first*, then implement against a plan with fresh context — fit the
  rebuild exactly, and it's the method that finally shipped.
- **Keep the old versions runnable.** `Censorr2` earned its keep as a reference and
  test oracle long after its code stopped being the product. That's why it was
  detached into a standalone checkout rather than deleted.

---

*Sources: git logs and READMEs of `Censorr1`, `Censorr2`, `Censorr`, and `censorr`;
`Censorr2/.sop/planning/` (rough-idea, idea-honing, research, design, implementation
plan). Model attribution is from commit `Co-Authored-By` trailers. The PDD
methodology is the `pdd` SOP from the Strands Agents `agent-sop` toolkit
(https://github.com/strands-agents/agent-sop), run as the `/pdd` skill.*
