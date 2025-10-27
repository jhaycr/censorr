
# Implementation Plan: Webhook-triggered processing via 'censorr_preset'

**Branch**: `003-webhook` | **Date**: 2025-10-26 | **Spec**: `/home/josh/Code/Censorr2/specs/003-webhook/spec.md`  
**Input**: Feature specification from `/home/josh/Code/Censorr2/specs/003-webhook/spec.md`

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
Implement a lightweight Python Flask HTTP service running inside the Docker container defined in spec-002. The service handles Radarr and Sonarr webhooks, only processes events that include the fixed tag key `censorr_preset`, maps its value to a preset in `censorr.json`, enqueues a processing job, and triggers the existing CLI pipeline asynchronously. The system explicitly does not implement idempotency for duplicate deliveries, fails gracefully and logs errors, maintains basic counters since process start, exposes health/readiness and status endpoints, and uses a bounded best-effort FIFO queue to preserve responsiveness under load.

## Technical Context
**Language/Version**: Python 3.12  
**Primary Dependencies**: Flask (HTTP server), Typer (existing CLI), standard library queue/threading; optional Gunicorn for production serving under Docker  
**Storage**: None (in-memory queue and counters; persistent media via mounted volumes)  
**Testing**: pytest (contract, integration, unit)  
**Target Platform**: Linux (Docker, Compose), non-root container  
**Project Type**: single (backend service within existing repository)  
**Performance Goals**: Accept POST within ~100ms under no-load; maintain availability during bursts via queueing  
**Constraints**: Bounded queue to prevent resource exhaustion; logs to stdout/stderr; structured logs; health/readiness endpoints; no idempotency for duplicate deliveries by design  
**Scale/Scope**: Homelab scale; tens to low hundreds of webhook events/day; burst handling via queue

## Constitution Check
*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- Library‑First (I): Webhook validation, preset resolution, CLI invocation, and queue worker are isolated as small modules callable from both CLI and HTTP paths.
- CLI and Text I/O First (II): HTTP handler uses the same internal callable used by the CLI entrypoint; logs and statuses are emitted to stdout/stderr.
- Test‑First (III): Plan enumerates contract tests for endpoints and integration tests with Docker; docs (quickstart) generated alongside.
- Realistic Integration (IV): Integration tests will target the Docker Compose service from spec‑002.
- Safety/Observability/Versioning/Simplicity (V/VI): Structured logs with stable fields; simple FIFO queue; versioning deferred to merge; minimal design.
- Non‑Root Container Deliverable (XII): Flask service runs as non‑root; healthcheck endpoint provided; volumes for media honored.

Potential deviation: Constitution’s “Idempotency” principle (Security & Operational Constraints) is relaxed specifically for duplicate webhook deliveries per spec‑003 FR‑007. Justification: duplicates are considered distinct notifications; avoiding idempotency simplifies the service and defers deduplication to upstream systems. Core CLI operations remain convergent/idempotent regarding media outputs.

Initial Constitution Check: PASS (with documented deviation)

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

**Structure Decision**: Option 1 (Single project). Add `src/webhook/` for HTTP service and queue worker; reuse existing `src/cli` and libraries.

## Phase 0: Outline & Research
Key questions and decisions are consolidated in `research.md`:
- Flask within Docker Compose (spec‑002) vs. alternative frameworks → choose Flask for simplicity and fit.
- Production serving: run under Gunicorn in container vs Flask dev server → choose Gunicorn for robustness under compose; single worker/thread adequate for queueing model.
- Queue strategy: in‑process bounded `queue.Queue` with best‑effort FIFO; capacity default 100; overflow policy is reject and log.
- Endpoint surface: POST `/webhook` (source autodetect), or split `/webhook/radarr` and `/webhook/sonarr`; choose single `/webhook` with source field detection.
- Counters semantics: in‑memory since process start.
- Health and readiness: `/healthz` (liveness) and `/readyz` (queue worker up; config loaded).
- Security posture: shared secret header optional; if invalid/missing → fail gracefully and log (no 500s); no IP allowlist in this feature.

Output: `/home/josh/Code/Censorr2/specs/003-webhook/research.md`

## Phase 1: Design & Contracts
Prerequisite met: `research.md` created.

1) Data model (`data-model.md`):
- WebhookEvent: source (radarr|sonarr), eventType, tags, mediaPaths, receivedAt.
- ProcessingJob: id, preset, mediaPath, enqueuedAt, startedAt, finishedAt, status (queued|running|succeeded|failed), error.
- Counters: processed, ignored, failed, queued (since process start).

2) API Contracts (`contracts/openapi.yaml`):
- POST /webhook → 202 accepted on qualifying event; 200 ignored; 400 failed (malformed/oversized, security), body: {status, reason}.
- GET /status → 200 with counters and queue depth.
- GET /healthz → 200 when process alive.
- GET /readyz → 200 when queue worker running and config loaded.

3) Contract tests (to be generated in /tasks phase):
- Schema and status code assertions per endpoint.

4) Quickstart (`quickstart.md`):
- Compose integration (spec‑002): service runs non‑root, logs to stdout, exposes ports, healthcheck hitting `/healthz`.
- Example curl for qualifying webhook payload with `censorr_preset`.

Outputs: `/home/josh/Code/Censorr2/specs/003-webhook/data-model.md`, `/home/josh/Code/Censorr2/specs/003-webhook/contracts/openapi.yaml`, `/home/josh/Code/Censorr2/specs/003-webhook/quickstart.md`

## Phase 2: Task Planning Approach
*This section describes what the /tasks command will do - DO NOT execute during /plan*

**Task Generation Strategy**:
- Load `.specify/templates/tasks-template.md` as base
- Generate tasks from Phase 1 design docs (contracts, data model, quickstart)
- Each contract → contract test task [P]
- Each entity → model creation task [P] 
- Each user story → integration test task
- Implementation tasks to make tests pass

**Ordering Strategy**:
- TDD order: Tests before implementation 
- Dependency order: Models before services before UI
- Mark [P] for parallel execution (independent files)

**Estimated Output**: 25-30 numbered, ordered tasks in tasks.md

**IMPORTANT**: This phase is executed by the /tasks command, NOT by /plan

## Phase 3+: Future Implementation
*These phases are beyond the scope of the /plan command*

**Phase 3**: Task execution (/tasks command creates tasks.md)  
**Phase 4**: Implementation (execute tasks.md following constitutional principles)  
**Phase 5**: Validation (run tests, execute quickstart.md, performance validation)

## Complexity Tracking
*Fill ONLY if Constitution Check has violations that must be justified*

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Webhook idempotency relaxed | Spec‑003 mandates no idempotency for duplicate deliveries | Upstream systems (Radarr/Sonarr) can dedupe; adding dedupe here increases complexity and state management |


## Progress Tracking
*This checklist is updated during execution flow*

**Phase Status**:
- [x] Phase 0: Research complete (/plan command)
- [x] Phase 1: Design complete (/plan command)
- [ ] Phase 2: Task planning complete (/plan command - describe approach only)
- [ ] Phase 3: Tasks generated (/tasks command)
- [ ] Phase 4: Implementation complete
- [ ] Phase 5: Validation passed

**Gate Status**:
- [x] Initial Constitution Check: PASS
- [x] Post-Design Constitution Check: PASS
- [x] All NEEDS CLARIFICATION resolved
- [x] Complexity deviations documented

---
*Based on Constitution v0.4.0 - See `.specify/memory/constitution.md`*
