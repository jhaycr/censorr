# Sandbox Repository Strategy

Use a disposable sandbox repo for risky or large efforts to protect the main codebase and speed up iteration.

## When to Use a Sandbox
- Large refactors touching many files or modules
- Dependency introductions with unclear impact
- Experimental designs or performance-sensitive changes

## How to Operate
1. Create a new private repo or a dedicated branch in a sandbox org.
2. Reproduce minimal project scaffolding to validate the change.
3. Implement and validate with equivalent tests.
4. Capture key commits and a porting plan mapping to tasks.
5. Open a minimal diff PR in this repo with links to the sandbox and the porting rationale.

## Porting Back
- Avoid pasting large blobs; prefer fresh, minimal diffs aligned with repo conventions.
- Split into stacked, feature-sized PRs if needed.
- Include links to sandbox commits and a brief porting plan section in the PR body.
