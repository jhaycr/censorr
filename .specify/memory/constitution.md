<!--
Sync Impact Report
- Version change: 0.2.0 → 0.3.0 (MINOR: added container deployability principle and constraints)
- Modified principles:
	* None (new principle added)
- Added sections:
	* XII. Container‑Deployable Deliverables
	* Additional container constraints in Security & Operational Constraints
- Removed sections: None
- Templates requiring updates:
	* ✅ .specify/templates/plan-template.md (footer updated to Constitution v0.3.0)
	* ✅ .specify/templates/spec-template.md (no changes required)
	* ✅ .specify/templates/tasks-template.md (no changes required)
	* ⚠ .specify/templates/commands/* (directory not present)
- Follow-up TODOs: None
-->

# Censorr Homelab Service Constitution

Guiding rules for a small script/webservice that orchestrates and observes containerized services in a self‑hosted homelab (Docker/Podman/Compose/K8s where applicable).

## Core Principles

### I. Library‑First, Toolable Units
Every feature begins as a small, self‑contained library or module with a clear purpose. Each library must be independently testable and documented. Applications (CLI/HTTP service) are thin layers that wire libraries together.

### II. CLI and Text I/O First (with Optional HTTP)
All capabilities are exposed via a CLI with text I/O: args/stdin → stdout; errors → stderr; exit codes are meaningful. JSON output is supported via --format=json; human‑readable otherwise. An HTTP interface may be added, but it must call the same library contracts as the CLI.

### III. Test‑First & Doc‑Driven are Non-Negotiable
Practice strict Red‑Green‑Refactor. Write failing contract/integration tests from user
scenarios before implementation. Commits must show tests preceding code that makes
them pass. No implementation without a failing test. Documentation is first‑class:
specs, quickstarts, and public contracts are authored or updated alongside tests.
No new feature is complete without docs that demonstrate usage and constraints.

### IV. Realistic Integration Testing
Prefer contract and integration tests that run against real container runtimes (Docker/Podman) or ephemeral test environments. Validate inter‑service communication, shared schemas, and idempotent operations (create/update/delete) including dry‑run behavior.

### V. Safety, Observability, Versioning, Simplicity
- Safety: Least‑privilege by default; non‑destructive by default; dry‑run required for mutating commands; explicit --force for destructive actions.
- Observability: Structured logs (JSON optional), stable fields, and audit trails for all container operations (who/what/when/target/result).
- Versioning: Semantic versioning MAJOR.MINOR.BUILD. BUILD increments on every change. Breaking changes require a migration plan and parallel tests.
- Simplicity: Prefer direct use of platform/runtime APIs. Avoid abstractions and patterns (Repository/UoW, custom wrappers) unless justified by tests and scale.

### VI. KISS (Keep It Simple, Stupid)
Prefer the simplest design that solves the problem. Default to straightforward flows
and obvious data structures. Additional layers or patterns require clear benefit
demonstrated by tests or scale.

### VII. Single Responsibility
Keep modules and operations small with one clear purpose. A change in one behavior
should require edits in one place. Complex pipelines are composed from small units.

### VIII. Composition Over Inheritance
Favor composing small components over building inheritance hierarchies. Wire behavior
via explicit interfaces/parameters to keep code paths easy to reason about and test.

### IX. Explicit Contracts
Define clear, typed (or well‑specified) contracts for inputs/outputs and expose a
minimal public surface. Internals are private by default; stability guarantees apply
only to documented contracts.

### X. Plugin‑First Extensibility
Design for extension via a registry and stable plugin API. New behaviors are added as
plugins without modifying core planner/executor logic. Backward compatibility rules
apply to the plugin API surface.

### XI. YAGNI & Documented Complexity
You Aren’t Gonna Need It: avoid speculative features. Any added abstraction must be
justified in the plan/spec and tracked in “Complexity Tracking” with rationale and
alternatives considered.

### XII. Container‑Deployable Deliverables
All solutions MUST be straightforward to deploy as containers (Docker/Podman):
- Provide a working Dockerfile (Podman compatible) that builds a minimal, non‑root image.
- Define a sensible ENTRYPOINT/CMD for the CLI, emitting logs to stdout/stderr.
- Support configuration via flags and environment variables (env never required when a flag exists).
- Include a HEALTHCHECK when applicable for long‑running modes; short‑lived CLI remains simple.
- Document required volumes (e.g., media, workdir) and example Compose/Podman run invocations.
- Ensure images are reproducible: pinned bases, deterministic builds; provide SBOM or dependency manifest.
- Prefer multi‑arch builds (amd64, arm64) or document supported arches.
- Security: run as non‑root, least privileges; no secrets baked into images.

## Security & Operational Constraints

- Runtime scope: Support Docker or Podman first; Compose/K8s support is additive and must not break the CLI contract.
- Permissions: Run as non‑root where possible; require only the minimal socket/permissions needed; allow explicit context selection (e.g., DOCKER_HOST, kubeconfig).
- Idempotency: All operations must be repeatable and converge to desired state. Provide --dry-run on mutating commands and surface planned actions before executing.
- Configuration: Single source of truth via config file (YAML/TOML) and/or flags. Environment variables allowed but never required when a flag exists.
- Failure modes: Timeouts for remote calls; retries with backoff for transient errors; clear, actionable error messages; no silent fallback behavior.
- Backups and reversibility: Changes to persistent data must document backup/restore steps in quickstart/docs; destructive actions require confirmation.
- Container images: Build minimal, non‑root images with pinned bases; publish or document build steps; provide Compose/Podman examples and healthcheck guidance where relevant; log to stdout/stderr only.

## Development Workflow & Quality Gates

- Workflow: Spec → Plan → Tasks → Tests → Implementation → Validation, following the provided templates in `.specify/templates/`.
- Tests: Order is Contract → Integration → E2E → Unit. Use real dependencies where feasible (e.g., local Docker socket). Mocks allowed only to isolate failure modes.
- Documentation: Each library includes `llms.txt` or equivalent minimal docs describing inputs/outputs and examples. CLI includes `--help`, `--version`, and `--format` flags. Docs are updated in the same PR as the feature and validated during review.
- Build & Lint: Code must compile and lint cleanly. Pre‑commit hooks encouraged. CI must run tests and validate constitution checks where applicable.
- Observability: Ensure structured logging fields and correlation IDs are present in both CLI and HTTP paths.
- Versioning gate: Assign a version at merge; increment BUILD for any change; document breaking changes and provide migration notes.

## Governance

This constitution supersedes other practices for this repository. Amendments require:
1) Documentation of the proposed change and rationale,
2) Updates to affected templates per `constitution_update_checklist.md`,
3) A migration/testing plan for any breaking changes,
4) Version bump and amendment date update below.

All reviews must verify compliance with the Core Principles and Quality Gates. Complexity must be justified in the plan/spec. Deviations are recorded in "Complexity Tracking" within plans.

**Version**: 0.3.0 | **Ratified**: 2025-09-14 | **Last Amended**: 2025-09-21