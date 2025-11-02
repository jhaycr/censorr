# Change Request Workflow (Spec → Plan → Tasks → Slices → PRs)

This workflow ensures changes are feature-sized, test-first, and traceable.

## Overview
1. Spec: Author `specs/NNN-feature/spec.md` using the spec-template; capture FR/NFR, scenarios, and edge cases.
2. Plan: Create `specs/NNN-feature/plan.md` from the plan-template; include Constitution Check and a slice plan.
3. Tasks: Generate `specs/NNN-feature/tasks.md` as an immutable ledger (append-only) mapping slices to task IDs.
4. Slices: Implement one slice per PR, keeping within size caps; reference task IDs in commits.
5. PR: Use the PR template; include slice scope, tests added, risk, and (if used) sandbox links.
6. Review: CI enforces gates (size caps, body sections). Review verifies tests, docs, FR traceability.
7. Merge: Only when all gates pass and reviewers approve.

## Roles & Gates
- Author: Drafts spec/plan; proposes slice plan; writes tests first.
- Reviewer: Verifies constitution gates, size caps, and test coverage; enforces task ledger rules.
- CI: Fails if size caps exceeded without justification or required PR sections missing.

## Slice Definition
A slice is the smallest reviewable unit that adds or changes a single behavior. Each slice must:
- Include tests (contract/integration/unit as relevant) and any required docs.
- Touch ≤ 10 files; ≤ +400 additions and ≤ -400 deletions.
- Reference task IDs in commits.

## Traceability
- Each FR-XXX in `spec.md` should be referenced by tests and, optionally, in code comments.
- Commits must reference task IDs (e.g., "Implements T012, T013").

## Sandbox (optional but encouraged for risky work)
- Build in a separate repo to validate large/risky changes.
- Port minimal diffs back, include sandbox link and porting notes in PR.

## Checklist Before Opening PR
- [ ] Tests fail before implementation (observable in history) and then pass.
- [ ] Spec/plan/docs updated accordingly.
- [ ] PR body filled with required sections.
- [ ] Size caps met or justification provided.
