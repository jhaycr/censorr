
# Implementation Plan: Generic Docker Compose Deployment for Censorr

**Branch**: `002-integrate-existing-docker` | **Date**: 2025-09-29 | **Spec**: `specs/002-integrate-existing-docker/spec.md`  
**Input**: Feature specification from `/specs/002-integrate-existing-docker/spec.md`

## Execution Flow (/plan command scope)
```
1. Load feature spec from Input path
   → If not found: ERROR "No feature spec at {path}"
2. Fill Technical Context (scan for NEEDS CLARIFICATION)
   → Detect Project Type from context (web=frontend+backend, mobile=app+api)
   → Set Structure Decision based on project type
3. Fill the Constitution Check section based on the content of the constitution document.
4. Evaluate Constitution Check section below
   → If violations exist: Document in Complexity Tracking
   → If no justification possible: ERROR "Simplify approach first"
   → Update Progress Tracking: Initial Constitution Check
5. Execute Phase 0 → research.md
   → If NEEDS CLARIFICATION remain: ERROR "Resolve unknowns"

## Deliverables
- docker-compose.yml in project root
- env.template in project root (optional convenience)
- Updated Dockerfile defaults for long-running service entrypoint (daemon)
- README updates in root (or docs) for compose usage
 - Explicit removal of Podman examples; documentation will standardize on Docker Compose only for this feature.

## Steps
1. Create docker-compose.yml with build/image, env_file, volumes, healthcheck, labels, restart policy.
2. Create env.template with all configurable options (optional) and document that compose runs without `.env` using defaults.
3. Update README with quickstart using docker compose (local build by default from repo's Dockerfile), including Radarr/Sonarr hook snippet.
4. Update documentation to reflect docker-compose deployment model.
 5. Purge Podman-specific examples and references from docs and examples to avoid confusion.

## Media Mounts Standardization
Use consistent internal container paths for media:

- Inside container: `/data/media/tv` and `/data/media/movies`
- Expose .env variables for host paths as `MEDIA_PATH_TV` and `MEDIA_PATH_MOVIES`
- Ensure read-only mounts for media.
6. Execute Phase 1 → contracts, data-model.md, quickstart.md, agent-specific template file (e.g., `CLAUDE.md` for Claude Code, `.github/copilot-instructions.md` for GitHub Copilot, `GEMINI.md` for Gemini CLI, `QWEN.md` for Qwen Code or `AGENTS.md` for opencode).
7. Re-evaluate Constitution Check section
   → If new violations: Refactor design, return to Phase 1
   → Update Progress Tracking: Post-Design Constitution Check
8. Plan Phase 2 → Describe task generation approach (DO NOT create tasks.md)
9. STOP - Ready for /tasks command
```

**IMPORTANT**: The /plan command STOPS at step 7. Phases 2-4 are executed by other commands:
- Phase 2: /tasks command creates tasks.md
- Phase 3-4: Implementation execution (manual or via tools)

## Summary
Goal: Provide a reproducible, configurable deployment mechanism for the Censorr container via docker-compose.yml in the repository root, enabling users to clone and run with minimal setup.

High-level approach (WHAT, not HOW):
- Treat Censorr as a managed service with declarative inputs: volumes, environment, labels, health check, resource constraints.
- Provide docker-compose.yml and env.template in the repository root for direct usage.
- Offer optional environment customization via .env but ensure sensible defaults allow running without .env.
- Expose recommended labels & health check semantics for homelab integration.
- Ensure guardrails: idempotency, explicit fail on missing required volume bindings.

Out-of-scope (explicitly):
- Building dynamic inventory integrations or scheduling frameworks.
- Implementing automatic rollback logic (only manual documented until clarified).
- Complex authentication or secrets management patterns beyond basic .env variables.

## Technical Context
**Language/Version**: Python 3.12 (Censorr codebase); Docker/Compose runtime.  
**Primary Dependencies**: Censorr container image (built via Dockerfile in this repo); Docker/Compose runtime.  
**Storage**: Host-mounted volumes (media read-only, work/output read-write, config, logs). No internal DB.  
**Testing**: Existing pytest suite for application; optional validation script to introspect running container.  
**Target Platform**: Linux host (amd64 and potentially arm64—multi-arch images already considered in earlier containerization work).  
**Project Type**: Single CLI/library project (no architectural change needed).  
**Performance Goals**: Container startup idempotency (<10s no-op run). Runtime performance unaffected by deployment integration.  
**Constraints**: Must work with standard Docker Compose; must not require external orchestration.  
**Scale/Scope**: Single-instance service (one container) per host; low concurrency requirements.

Unresolved / Clarifications carried from spec:
- Image tag fallback or failure-only behavior.
- Automatic vs manual rollback.
- Label conventions (Traefik? Prometheus? Autodiscovery?)
- Resource constraints exact variable names.
- Force pull semantics variable name.
- Acceptable upper bound for no-op deployment time (10s assumed; clarify tolerance).

## Constitution Check
Principles mapping:
- Library-first: No code restructuring required—deployment artifacts are additive docker-compose config only → COMPLIANT.
- CLI/Text I/O first: Feature does not add runtime interface changes → COMPLIANT.
- Tests-first: No new runtime behavior yet; future validation scripts will require tasks before implementation → DECLARATIVE ONLY.
- Idempotency: Explicit design goal for Docker Compose consumption → COMPLIANT (planned).
- Simplicity / YAGNI: Using standard docker-compose.yml + optional .env → COMPLIANT.
- Container-Deployable: Aligns with existing container spec; adding usage docs → COMPLIANT.
- Immutable Task Ledger: Plan introduces tasks referencing this feature; will ensure commit references → ACK.

No constitutional violations introduced. Complexity section remains empty.

## Project Structure

### Documentation (this feature)
```
specs/[###-feature]/
├── plan.md              # This file (/plan command output)
├── research.md          # Phase 0 output (/plan command)
├── data-model.md        # Phase 1 output (/plan command)
├── quickstart.md        # Phase 1 output (/plan command)
├── contracts/           # Phase 1 output (/plan command)
└── tasks.md             # Phase 2 output (/tasks command - NOT created by /plan)
```

### Source Code (repository root)
```
# Option 1: Single project (DEFAULT)
src/
├── models/
├── services/
├── cli/
└── lib/

tests/
├── contract/
├── integration/
└── unit/

# Option 2: Web application (when "frontend" + "backend" detected)
backend/
├── src/
│   ├── models/
│   ├── services/
│   └── api/
└── tests/

frontend/
├── src/
│   ├── components/
│   ├── pages/
│   └── services/
└── tests/

# Option 3: Mobile + API (when "iOS/Android" detected)
api/
└── [same as backend above]

ios/ or android/
└── [platform-specific structure]
```

**Structure Decision**: Option 1 (single project). Docker Compose configuration in repository root—no additional directories needed.

## Phase 0: Outline & Research
Objectives: Resolve deployment ambiguity areas to lock variable naming and artifact structure before producing guidance.

Research Questions:
1. Image Tag Strategy: Fail on missing tag vs optional fallback to configurable `latest` alias? (Bias: fail fast, document manual override.)
2. Rollback: Provide manual `censorr_image_tag_previous` doc pattern vs automation; start manual only.
3. Label Set: Identify minimal interoperable labels (e.g., `com.example.service=censorr`, optional metrics/health labels) without binding to specific reverse proxy until clarified.
4. Resource Constraints: Define neutral keys: `censorr_mem_limit`, `censorr_cpu_shares` (document optional).
5. Force Pull: Boolean var `censorr_force_pull` that triggers image refresh even if tag unchanged.
6. Health Check Form: Prefer simple CMD check (e.g., `censorr --version`) vs HTTP (no daemon HTTP exposed). Document as optional; if future long-lived mode emerges, revisit.
7. Secrets Handling: Pattern for environment mapping with `_secret` suffix variables referencing Ansible vault entries; explicit note not to commit values here.
8. Deployment Consumption Path: Choose between git submodule vs manual copy vs Ansible include from remote URL. Proposed: Recommend git submodule for version lock + reproducibility.

Planned Output (research.md): Decisions + rationale + alternatives rejected.

Gate: All above clarified (or intentionally deferred with rationale) before Phase 1.

## Phase 1: Design & Artifacts
Prerequisite: research decisions captured.

Adaptation: No API/endpoint changes; instead we define configuration schema + integration artifacts.

Planned Artifacts:
1. `data-model.md`: Conceptual models
   - DeploymentConfig (fields: enabled, volumes[], env map, labels map, health spec, resources, user/group, log volume)
   - HealthSpec (command, interval, timeout, retries, start_period)
   - ResourceSpec (memory_limit, cpu_shares)
2. `contracts/` directory: Provide a `deployment-config.schema.json` (JSON Schema for configuration structure) to enable validation scripts (future).
3. `quickstart.md`: Step-by-step: clone repo, run docker compose up, verify container.
4. Updated README with docker-compose usage and integration examples.

Tests (conceptual, not runtime code here):
   - Provide future tasks for a validation script (e.g., `scripts/validate_ansible_vars.py`) but do not implement now.

No failing code tests are created in this phase because no new executable logic is introduced inside the Python runtime; instead we treat schema + examples as contracts for future validation tooling (tracked in tasks).

## Phase 2: Task Planning Approach
Strategy: Because this feature provides docker-compose deployment (no direct code paths changed), tasks focus on creating deployment artifacts, schemas, and optional validation scaffolding while preserving constitutional TDD expectations for any future executable validators.

Categories:
1. Research & Decision Capture (produce `research.md`).
2. Schema & Model Documentation (data-model + JSON schema + example vars).
3. Docker Compose Artifacts (docker-compose.yml, env.template, README updates).
4. Optional Future Validation (placeholder tasks for a Python validation script + tests—*added but can be deferred*).
5. Observability/Health Documentation.
6. Risk & Rollback Guidance.

Parallelization: Documentation files are independent except where one references canonical field names (data-model precedes schema & examples). Docker-compose.yml depends on final volume/env naming decisions.

Estimated Task Count: 18–24 tasks.

Success Criteria for Tasks File:
- Every requirement FR-001..FR-030 mapped to at least one task (or explicitly deferred if dependent on clarifications).
- All unresolved clarifications produce follow-up tasks tagged "clarify".
- No task modifies same file concurrently if marked [P].

## Phase 3+: Future Implementation
*These phases are beyond the scope of the /plan command*

**Phase 3**: Task execution (/tasks command creates tasks.md)  
**Phase 4**: Implementation (execute tasks.md following constitutional principles)  
**Phase 5**: Validation (run tests, execute quickstart.md, performance validation)

## Complexity Tracking
No added complexity beyond docker-compose.yml and env.template in repository root. Justification: standard Docker Compose patterns; minimal additional files. Simpler alternative (embedding all defaults in compose) partially adopted but .env template provided for convenience.


## Progress Tracking
*This checklist is updated during execution flow*

**Phase Status**:
- [ ] Phase 0: Research complete (/plan command)
- [ ] Phase 1: Design complete (/plan command)
- [ ] Phase 2: Task planning complete (/plan command - describe approach only)
- [ ] Phase 3: Tasks generated (/tasks command)
- [ ] Phase 4: Implementation complete
- [ ] Phase 5: Validation passed

**Gate Status**:
- [x] Initial Constitution Check: PASS
- [ ] Post-Design Constitution Check: PASS
- [ ] All NEEDS CLARIFICATION resolved
- [x] Complexity deviations documented

## Functional Requirements → Tasks Mapping

This table cross-references functional requirements from the specification to their implementing tasks:

| Functional Requirement | Implementing Tasks | Status |
|------------------------|-------------------|---------|
| FR-001 vars.yml template | T001, T002, T003 | ✅ Complete |
| FR-002 example integration | T004, T005 | ✅ Complete |
| FR-003 env → CLI mapping | T008, T009 | ✅ Complete |
| FR-004 volume management | T006, T007 | ✅ Complete |
| FR-005 multi-arch deployment | T011 | ✅ Complete |
| FR-006 health check | T012, T031 | ✅ Complete |
| FR-007 labels | T019, T032 | ✅ Complete |
| FR-008 secrets handling | T013, T014 | ✅ Complete |
| FR-009 env override pattern | T015, T016 | ✅ Complete |
| FR-010 digest pinning | T017, T018 | ✅ Complete |
| FR-011 resource limits | T020 | ✅ Complete |
| FR-012 network config | T022 | ✅ Complete |
| FR-013 rollback manual | T010, T021 (auto rollback deferred: T036) | ✅ Complete |
| FR-014 troubleshooting | T023, T031 | ✅ Complete |
| FR-015 config validation | T024, T025, T026, T027 | ✅ Complete |
| FR-016 runtime validation | T028, T029, T030 | ✅ Complete |
| FR-017 integration docs | T001-T023 | ✅ Complete |
| FR-018 error messages | T024-T030 | ✅ Complete |
| FR-019 update channel/tag pattern | Clarification T036/T038 (deferred) | ⏳ Deferred |

### Clarification Task Status
- T036: Automatic rollback mechanism (stakeholder decision pending)
- T037: Monitoring/label ecosystem requirements (stakeholder decision pending)  
- T038: Max no-op deploy time threshold (stakeholder decision pending)
- T039: Secrets `_FILE` injection pattern (stakeholder decision pending)

---
*Based on Constitution v0.4.0 - See `.specify/memory/constitution.md`*
