
# Implementation Plan: Plex/Arr Clean Censor Tool

**Branch**: `001-write-a-tool` | **Date**: 2025-09-25 | **Spec**: ./spec.md
**Input**: Feature specification at `/home/josh/Code/Censorr2/specs/001-write-a-tool/spec.md`

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
Deliver a CLI-first censorship pipeline for Plex/Radarr/Sonarr ecosystems: extract or accept provided subtitles/audio, merge/mask profanities (full/partial policies with fuzzy matching + allow-list), derive mute windows, produce muted audio, and remux with prioritized cleaned artifacts. Provide sidecar subtitle export, standardized naming (`<base>.<lang>.censorr.srt`), Plex movie edition tagging (`{edition-Censorr}`), audio codec parity, ephemeral intermediate cleanup, and optional final destination relocation for finished outputs. Selection logic is driven by structured selectors (config JSON/YAML) rather than ad-hoc CLI exclusion flags—SDH/HI exclusion is expressed via ordered priorities or explicit excludes. A manifest (checksums + params) aids debugging and optional future skip optimization; QC (subtitle + audio) with override flags and observability (structured logs, audit, reports) are core. Containerization (Docker/Podman) and minimal dependencies ensure homelab deployability.

## Technical Context
**Language/Version**: Python 3.11+  
**Primary Dependencies**: FFmpeg (external), RapidFuzz (fuzzy matching), pysubs2 (subtitle parsing), typer (CLI), pydantic (validation), PyYAML/JSON (config), pytest  
**Storage**: Filesystem working directory (deterministic layout + manifest.json for debugging); optional final destination path for remux outputs  
**Testing**: pytest (unit, contract, integration, container smoke); ffprobe-based parity assertions  
**Target Platform**: Linux homelab (Plex/Radarr/Sonarr integration), container-friendly (Docker/Podman)  
**Project Type**: Single project (library + CLI)  
**Performance Goals**: Linear passes, avoid full re-encode by default; handle feature-length media (< real-time where feasible), parallelizable independent ops  
**Constraints**: Preserve codecs (audio parity) unless user requests re-encode; limit memory (streaming where possible); reproducible outputs on repeat runs (skip optimization optional)  
**Scale/Scope**: Single-node pipeline; invoked per media item; selections driven by structured selectors; no service daemon required  
**Additional Addenda**: Naming strategy (FR-054/055) & operational addenda (FR-056..059) integrated post initial design.

## Constitution Check
KISS: Core kept minimal (Artifacts, Operations, Planner, Executor) – PASS
Single Responsibility: Each operation discrete (extract, merge, mask, mute, quality check, remux, export) – PASS
Composition Over Inheritance: Registry + simple composition; no inheritance chains – PASS
Explicit Contracts: Artifacts, selectors, operations documented in spec & data model – PASS
Plugin-First: Registry allows adding new operations without planner changes – PASS
YAGNI: No HTTP server or DB; features only for current pipeline & naming – PASS
Container Deployable: Docker/Podman deliverables defined (non-root image, entrypoint) – PASS
Observability: Structured logs, QC reports, audio parity validation – PASS
Idempotency/Dry-Run: Manifest present (debug); skip optional – PASS
Complexity Tracking: No unjustified complexity added (naming & cleanup logic scoped) – PASS

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

**Structure Decision**: Option 1 (Single project) – appropriate for CLI pipeline.

## Phase 0: Outline & Research (Completed)
Research captured FFmpeg strategies (copy vs re-encode, mute filters), fuzzy matching thresholds, subtitle normalization, Arr integration triggers, manifest usage (debug vs optimization), and naming/edition follow-up. Unknowns resolved; no outstanding NEEDS CLARIFICATION.

## Phase 1: Design & Contracts (Completed)
Artifacts: `data-model.md` (Artifact, Selector, Operation, MuteWindow, AuditLogEntry, ManifestEntry), contracts directory (selector schema & examples), quickstart updated with naming/edition examples.
Selector model extended (title filters, exclude SDH flag originally; now guided by structured selector ordering philosophy – CLI exclusion flags avoided going forward).

## Phase 2: Task Planning Approach (Documented)
Existing `tasks.md` enumerates base + incremental tasks (QC, subtitle filtering, naming FR‑054/055, parity/cleanup/move/selector precedence FR‑056..059). Additional generation not required; future tasks appended rather than regenerated to preserve history.

## Phase 3+: Future Implementation
*These phases are beyond the scope of the /plan command*

**Phase 3**: Task execution (/tasks command creates tasks.md)  
**Phase 4**: Implementation (execute tasks.md following constitutional principles)  
**Phase 5**: Validation (run tests, execute quickstart.md, performance validation)

## Complexity Tracking
No violations. Added naming/edition + cleanup logic minimally; avoided broader abstraction layers.


## Progress Tracking
**Phase Status**:
- [x] Phase 0: Research complete (/plan)
- [x] Phase 1: Design complete (/plan)
- [x] Phase 2: Task planning documented
- [ ] Phase 3: Tasks generated / extended (ongoing updates)
- [ ] Phase 4: Implementation complete
- [ ] Phase 5: Validation passed

**Gate Status**:
- [x] Initial Constitution Check: PASS
- [x] Post-Design Constitution Check: PASS
- [x] All NEEDS CLARIFICATION resolved
- [x] Complexity deviations documented (none needed)

---
*Based on Constitution v0.3.0 - See `.specify/memory/constitution.md`*
