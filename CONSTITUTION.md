# Project Constitution

This document codifies non-functional guardrails, development principles, and process conventions that govern contributions to the project.

## 1. Core Engineering Principles
1. KISS (Keep It Simple & Specific): Prefer the simplest design that meets current *documented* requirements. Additional abstraction requires justification in the spec/plan (Complexity Tracking).
2. Single Responsibility: Each module, operation, and adapter does one thing. If a file needs a second high-level purpose, split it.
3. Composition over Inheritance: Favor explicit wiring, small helpers, and dependency injection for test seams instead of deep hierarchies.
4. Explicit Contracts: Public-facing types (Artifacts, Selectors, Operations) are versioned, documented, and stable. Avoid leaking internal helpers.
5. Plugin-Friendly: New operations should register; core planner/executor should remain closed to modification for extensions.
6. YAGNI Enforcement: No speculative features without a requirement ID. If in doubt, add a [NEEDS CLARIFICATION] marker to the spec instead of guessing.
7. Test-First & Doc-Driven: No implementation PR merges without corresponding tests and spec/docs updates. Failing or missing tests block merges.
8. Observability & Auditability: Every non-trivial transformation emits structured logs (timestamps, context, decisions). Heartbeats required for long-running FFmpeg tasks (see FR-064).
9. Idempotency & Determinism: Re-running with unchanged inputs yields identical outputs (paths, checksums, logs excluding timestamps). Edition tagging & sidecar naming must be idempotent.
10. Minimal External Surface: Keep the CLI and Operation API small; everything else is internal. Avoid premature layering.

## 2. Requirements Discipline
- Every feature maps to an FR-XXX identifier in the spec. Code comments MAY reference FR IDs for traceability.
- New functionality without a spec addition is prohibited. Update the spec first, then implement.
- Ambiguities must be captured as `[NEEDS CLARIFICATION: question]` in the spec until resolved.

## 3. Logging & Heartbeat Standards
- All user-visible progress lines MUST be timestamped (UTC, ISO-8601, no local timezone ambiguity).
- Heartbeat lines (FR-064) MUST include token `HEARTBEAT`, elapsed time, and concise context. Format example:
  `2025-09-27T12:34:56Z HEARTBEAT elapsed=48s context="remuxing movie output"`
- Heartbeats are interval-based only—no tight loops. Stop immediately when process exits.
- Disable Toggle: Setting env var `CENSORR_NO_HEARTBEAT=1` MUST suppress heartbeat emission for deterministic tests.
- Legacy verbose phrases required by tests must be preserved until tests are updated; deprecation requires a test change PR.

## 4. Git Commit Message Convention
Every non-trivial commit (feature, refactor, behavior change) SHOULD follow this structured format:

```
<Concise imperative summary>

Optional rationale paragraph (WHY, not HOW) – especially for architectural or performance changes.

Key changes:
- Bullet 1 (focus on externally visible behavior or contract impact)
- Bullet 2
- Bullet 3

Observability (when applicable):
- New logs / metrics / heartbeat impacts

Spec alignment:
- FR-0XX, FR-0YY
```

Guidelines:
- Wrap lines at ~100 chars for readability.
- Use present tense imperative ("Add", "Fix", "Refactor").
- Do not include issue numbers unless cross-referenced in spec or tracker.
- If reverting: `Revert: <original summary>` with rationale.
- Squash small fix-ups into the original feature commit before merge.

## 5. Pull Request Expectations
- Checklist referencing affected FR IDs.
- Evidence of tests: list new/updated test modules.
- Spec diff summary (quote only the added/changed FR sections, not whole spec).
- Risk assessment (runtime, API, migration, perf) with mitigation notes.

## 6. Test & Quality Gates
- Unit tests: fast, isolated, no network.
- Integration tests: minimal fixtures, assert critical end-to-end behavior.
- No flaky tests tolerated; flakiness requires immediate quarantine + fix plan.
- Lint/type checks MUST pass (where configured) prior to merge.

## 7. Media & Fixture Handling
- Keep binary fixtures tiny and documented. Larger generated artifacts should be created on-the-fly in tests when possible.
- Do not commit proprietary or licensed media.

## 8. Backward Compatibility
- Changes to public contracts (CLI flags, artifact metadata fields, operation names) require a spec update and migration notes.
- Deprecations: announce in CHANGELOG and retain behavior behind a flag or shim until the next minor release.

## 9. Security & Safety
- Never execute unvalidated external input through shell interpolation—always pass args as lists.
- Validate file paths exist and are inside allowed work contexts when writing outputs.

## 10. Governance & Amendments
- Amendments to this constitution require a spec update referencing a new FR or NFR if materially affecting behavior.
- Editorial changes (typos, formatting) may be committed directly with a short conventional commit message.

---
Last updated: 2025-11-02 (Add Feature-Sized PR gates & Sandbox validation; align with .specify/memory/constitution.md v0.5.0)

---

## 11. Feature-Sized AI Change Requests & Sandbox Validation

To keep changes reviewable and safe when using AI agents and automation:

- PR Size Caps:
  - Lines changed caps: ≤ 400 additions and ≤ 400 deletions total, excluding lockfiles and vendored dirs. If exceeded, split into stacked PRs.
  - File count cap: ≤ 10 files changed, unless a mechanical refactor; mechanical refactors MUST include the exact script used and be isolated in their own PR.
  - Exemptions require an “Oversized Change Justification” section in the PR body and maintainer approval.

- Single-Slice Scope:
  - Each PR MUST implement a single behavior slice (feature, fix, or refactor) with its tests and docs. The slice MUST be independently verifiable by CI.

- Stacked PRs:
  - Large efforts MUST be split into a series of small, stacked PRs, each based on the previous. Use branch names like `feature/NNN-topic/part-k-of-n`. Keep each PR green.

- Sandbox First for Risky/Large Work:
  - For broad or risky changes, first implement and validate in a disposable sandbox repository (no secrets; private if needed). The ported PR MUST:
    - Link to sandbox repo/commit(s) and describe the “porting plan” mapping to tasks.
    - Port only the minimal slice with equivalent tests reproduced in this repo.
    - Avoid copy‑pasting large blobs; prefer fresh, minimal diffs aligned to local conventions.

- Dependency Hygiene:
  - Introducing a new dependency requires a short justification (purpose, size impact). Prefer separate, dedicated “deps: add X” PRs. Lockfile diffs MAY be excluded from line caps if isolated.

- AI Agent Constraints:
  - AI agents MUST NOT alter CI/CD secrets, repository settings, or unrelated modules. Avoid repo‑wide pattern rewrites unless justified as mechanical with a provided script.

- Review Gates (enforced by CI or reviewers):
  - PR body MUST include: slice scope, acceptance tests added, risk notes, sandbox link (if used), size stats.
  - Commits MUST reference completed task IDs; no prohibited artifacts; size/file caps respected or justified.
