# Copilot Instructions for Feature-Sized Changes

Use these instructions when asking Copilot to implement a change:

## Goal
- Produce a minimal, feature-sized diff that implements a single behavior with tests and docs.

## Constraints
- Keep the PR ≤ 10 files changed and ≤ +400/-400 lines (excluding lockfiles/vendor). Split into stacked PRs otherwise.
- Write tests first (failing), then implement to make them pass, then update docs.
- Reference task IDs in commits (e.g., "Implements T012").
- Do not modify unrelated modules or repo settings; no secrets.
- Prefer composition over inheritance; follow the constitution.

## Deliverables
- Code changes, plus:
  - Tests (contract/integration/unit as appropriate)
  - Doc updates (quickstart/spec/README snippets)
  - Observability: structured logs or notes if relevant

## Prompts to Use
- "Implement slice: [brief scope]. Add failing tests in [paths], then minimal implementation in [paths], and docs in [paths]. Keep diff small and reference tasks [IDs]."
- "Refactor [module] mechanically using script [path]; isolate change to a dedicated PR and include the script." (mechanical)
- "Add GitHub Action to enforce PR size caps and required PR body sections."

## Non-Goals
- Avoid speculative abstractions or large rewrites.
- Do not introduce dependencies without a short justification.
