---
inclusion: always
---

# Censorr Development Principles

This steering document defines the core development principles for the Censorr project. These principles guide all implementation decisions and code reviews.

## Core Architecture Principles

### Library-First Design
Every feature begins as a small, self-contained library or module with a clear purpose. Each library must be independently testable and documented. Applications (CLI/HTTP service) are thin layers that wire libraries together.

**When implementing:**
- Start with library code in `src/lib/` or `src/services/`
- Make libraries independently testable
- Keep CLI/HTTP layers thin - they should only wire libraries together
- Document each library's purpose and contracts

### CLI and Text I/O First
All capabilities are exposed via a CLI with text I/O: args/stdin → stdout; errors → stderr; exit codes are meaningful. JSON output is supported via `--format=json`; human-readable otherwise.

**When implementing:**
- CLI is the primary interface
- HTTP interfaces must call the same library contracts as CLI
- Support both human-readable and JSON output
- Use meaningful exit codes (0=success, 1=error, 2=ignored, 3=validation failure)

### Test-First Development
Practice strict Red-Green-Refactor. Write failing contract/integration tests from user scenarios before implementation.

**When implementing:**
- Write tests BEFORE implementation
- Commits must show tests preceding code
- No implementation without a failing test
- Test order: Contract → Integration → E2E → Unit
- Prefer real dependencies (e.g., Docker) over mocks

### Composition Over Inheritance
Favor composing small components over building inheritance hierarchies. Wire behavior via explicit interfaces/parameters.

**When implementing:**
- Compose small, focused components
- Use explicit interfaces and parameters
- Avoid deep inheritance hierarchies
- Keep code paths easy to reason about

## Code Quality Principles

### Single Responsibility
Keep modules and operations small with one clear purpose. A change in one behavior should require edits in one place.

**When implementing:**
- One module = one clear purpose
- Complex pipelines are composed from small units
- Changes should be localized to one place

### KISS (Keep It Simple, Stupid)
Prefer the simplest design that solves the problem. Default to straightforward flows and obvious data structures.

**When implementing:**
- Choose the simplest solution that works
- Avoid premature abstraction
- Use obvious data structures
- Additional complexity requires justification

### YAGNI (You Aren't Gonna Need It)
Avoid speculative features. Any added abstraction must be justified in the plan/spec.

**When implementing:**
- Don't build features you don't need yet
- Justify any abstraction in design documents
- Track complexity decisions in "Complexity Tracking"
- Document alternatives considered

### Explicit Contracts
Define clear, typed contracts for inputs/outputs and expose a minimal public surface. Internals are private by default.

**When implementing:**
- Document all public interfaces
- Keep public surface minimal
- Make internals private by default
- Stability guarantees apply only to documented contracts

## Safety and Operations

### Safety First
- Least-privilege by default
- Non-destructive by default
- Dry-run required for mutating commands
- Explicit `--force` for destructive actions

### Idempotency
All operations must be repeatable and converge to desired state.

**When implementing:**
- Operations should be safe to re-run
- Provide `--dry-run` for mutating commands
- Surface planned actions before executing
- Ensure convergence to desired state

### Observability
Structured logs (JSON optional), stable fields, and audit trails for all operations.

**When implementing:**
- Use structured logging with stable fields
- Include correlation IDs
- Provide audit trails (who/what/when/target/result)
- Log to stdout/stderr only (container-friendly)

## Container Deployment

All solutions must be straightforward to deploy as containers:

**When implementing:**
- Provide working Dockerfile (minimal, non-root)
- Define sensible ENTRYPOINT/CMD
- Support configuration via flags and environment variables
- Include HEALTHCHECK for long-running services
- Document required volumes
- Run as non-root user
- No secrets baked into images
- Prefer multi-arch builds (amd64, arm64)

## Version Control and Task Management

### Immutable Task Ledger
`tasks.md` is an append-only historical ledger.

**Rules:**
- Never delete, renumber, or repurpose existing tasks
- Mark completion by appending ✅ only
- Create new tasks for corrections/omissions
- Task IDs are never reused
- Commits must reference completed task IDs

### Commit Traceability
Every feature/fix/refactor must be traceable.

**Rules:**
- Commits must include: tests (failing first), implementation, docs
- Reference task IDs in commit messages
- No generated/transient artifacts in commits
- Update `.gitignore` when adding new artifact types

## Change Size and Review

### PR Size Limits
Keep changes small and reviewable:

**Limits:**
- ≤ 400 additions and ≤ 400 deletions (excluding lockfiles)
- ≤ 10 files changed (unless mechanical refactor)
- Single behavior slice per PR
- Large efforts split into stacked PRs

**Exemptions:**
- Require "Oversized Change Justification" in PR body
- Need maintainer approval

### Sandbox Validation
For risky/large changes:

**Process:**
- Implement and validate in disposable sandbox first
- Link to sandbox repo/commit in PR
- Port minimal slice with equivalent tests
- Avoid copy-pasting large blobs

## Documentation Requirements

### Required Documentation
- Each library includes minimal docs describing inputs/outputs
- CLI includes `--help`, `--version`, `--format` flags
- Docs updated in same PR as feature
- Quickstart guides for new features

### Documentation Types
- Specs: Requirements and design
- Quickstarts: Getting started guides
- Contracts: API/interface definitions
- README: Project overview and setup

## Workflow Summary

1. **Spec** → Define requirements with user stories
2. **Plan** → Design architecture and approach
3. **Tasks** → Break down into implementation tasks
4. **Tests** → Write failing tests first
5. **Implementation** → Make tests pass
6. **Validation** → Verify against requirements

---

**Version:** 0.5.0 | **Last Updated:** 2025-11-02
