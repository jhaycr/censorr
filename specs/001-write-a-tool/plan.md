
# Implementation Plan: Presets via Config (Movies/TV) with In-Place Remux and Backup

**Branch**: `[###-feature-name]` | **Date**: [DATE] | **Spec**: [link]
**Input**: Feature specification from `/specs/[###-feature-name]/spec.md`

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
Add a config-driven presets system in `config/censorr.json` enabling `--preset movies` and `--preset tv` to run a full default pipeline:
subtitle_extract, subtitle_merge, subtitle_mask, audio_extract, audio_mute, audio_qc, subtitle_qc, video_remux.
Presets set defaults for: `--create-subtitle-sidecar` and `--profanity-list-file config/profanity_list.json`.
Extend profanity list format to allow per-word overrides (custom fuzzy threshold and variant strategy), enabling aggressive variant detection for families such as "fuck" without enumerating every variant. Maintain backward compatibility with string lists.
Language selection prefers non‑SDH/non‑CC tracks (by title/code/empty), merging same‑language Forced; falls back to SDH/CC when needed. Remux embeds muted audio as an additional track, preserves originals, and supports in-place replacement with optional `--backup`.
Introduce output modes: REMUX_ORIGINAL_VIDEO (in-place replace, optional backup) and REMUX_NEW_FILE (non-destructive new file). For movies, REMUX_NEW_FILE writes `{edition-Censorr}` in the same folder. For TV, REMUX_NEW_FILE writes using a configurable policy: `subfolder_tag` (e.g., `Show [Censorr]/Season …`) or `separate_root` (e.g., `TV/Censorr/Show/Season …`). Policies are configurable and reusable across shows via templates.

## Technical Context
**Language/Version**: Python 3.12  
**Primary Dependencies**: typer, pydantic, ffmpeg/ffprobe, pysubs2, rapidfuzz, PyYAML  
**Storage**: Filesystem (workdir, config)  
**Testing**: pytest (unit + integration + end-to-end on fixtures)  
**Target Platform**: Linux CLI and Docker container  
**Project Type**: Single project (CLI/lib)  
**Performance Goals**: End-to-end on sample within CI time; operations stream via ffmpeg  
**Constraints**: Deterministic outputs, idempotency, atomic replace when possible  
**Scale/Scope**: Single-file processing per invocation (batch optional later)

## Constitution Check
*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

[Gates determined based on constitution file]

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

**Structure Decision**: Option 1 (single project). Add presets to config model and CLI wiring; add E2E tests and small fixtures.

## Phase 0: Outline & Research
1. **Extract unknowns from Technical Context** above:
   - For each NEEDS CLARIFICATION → research task
   - For each dependency → best practices task
   - For each integration → patterns task

2. **Generate and dispatch research agents**:
   ```
   For each unknown in Technical Context:
     Task: "Research {unknown} for {feature context}"
   For each technology choice:
     Task: "Find best practices for {tech} in {domain}"
   ```

3. **Consolidate findings** in `research.md` using format:
   - Decision: [what was chosen]
   - Rationale: [why chosen]
   - Alternatives considered: [what else evaluated]

**Output**: research.md with all NEEDS CLARIFICATION resolved

## Phase 1: Design & Contracts
1. Extend Config model to include `presets` map: name → { operations[], flags, selector config, output policies, backup(bool) }.
2. Define default presets `movies` and `tv` with the specified pipeline and flags. Add language selection policy description.
3. Update selector schema documentation to express the non‑SDH preference and forced merge behavior (configurable patterns).
4. Profanity list contract: define a structured profanity entry object with fields `word`, optional `fuzzy_threshold`, optional `variant_strategy: default|aggressive`; specify global defaults and inheritance. Document backward compatibility with plain strings.
5. Add CLI contract for `--preset` and `--backup` flags; precedence: CLI > preset > config defaults.
5. Output Mode contract: define enum `output_mode` with `REMUX_ORIGINAL_VIDEO` and `REMUX_NEW_FILE`; define destination policy contract with `policy: subfolder_tag|separate_root`, `{tag}`, `{root}`, and a templated path schema supporting `{library_root}`, `{collection}{tag}`, `{season}`, `{episode}` tokens. Specify idempotency and conflict resolution policies.
6. Implementation milestone: Model changes — update Config presets to include `output_mode` and `destination_policy` (schema, validation, docs).
7. Implementation milestone: CLI flags and resolution — add flags (`--output-mode`, `--dest-policy`, `--dest-policy-tag`, `--dest-separate-root`) and enforce precedence CLI > preset > config.
8. Implementation milestone: Profanity config ingestion — update config/profanity list loader to accept string or object entries; normalize into an internal term model with effective thresholds and strategies; unit tests for parsing and inheritance.
9. Implementation milestone: Matcher wiring — update the fuzzy matcher to accept an effective threshold per term and a variant strategy; add an aggressive variant pathway that expands candidate windows (e.g., morphological/compounded forms) while preserving boundary semantics; tests for detection of variants like "fuckable" without explicit enumeration.
8. Implementation milestone: Path builders & conflicts — implement same-folder new-name builder (movie edition) and generic destination builders (subfolder_tag, separate_root), with conflict handling (reuse/overwrite/fail/suffix) and idempotency.
*Prerequisites: research.md complete*

1. **Extract entities from feature spec** → `data-model.md`:
   - Entity name, fields, relationships
   - Validation rules from requirements
   - State transitions if applicable

2. **Generate API contracts** from functional requirements:
   - For each user action → endpoint
   - Use standard REST/GraphQL patterns
   - Output OpenAPI/GraphQL schema to `/contracts/`

3. **Generate contract tests** from contracts:
   - One test file per endpoint
   - Assert request/response schemas
   - Tests must fail (no implementation yet)

4. **Extract test scenarios** from user stories:
   - Each story → integration test scenario
   - Quickstart test = story validation steps

5. **Update agent file incrementally** (O(1) operation):
   - Run `.specify/scripts/bash/update-agent-context.sh copilot` for your AI assistant
   - If exists: Add only NEW tech from current plan
   - Preserve manual additions between markers
   - Update recent changes (keep last 3)
   - Keep under 150 lines for token efficiency
   - Output to repository root

**Output**: data-model.md, /contracts/*, failing tests, quickstart.md, agent-specific file

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

**Estimated Output**: 14-20 tasks (model, CLI, ops integration, output mode + TV policy, idempotency, tests, docs)

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
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |


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
- [ ] Initial Constitution Check: PASS
- [ ] Post-Design Constitution Check: PASS
- [ ] All NEEDS CLARIFICATION resolved
- [ ] Complexity deviations documented

## Phase 5: Operation Names & Observability Enhancement
*Added 2025-01-27*

### Task 67: Update Operation Names to Noun-Verb Convention
**Context**: Following constitutional naming standards, operation names should use noun-verb pattern for better readability and consistency.

**Changes Required**:
- `mask_subtitles` → `sub_mask` (subtitle masking operation)
- `mute_audio` → `audio_mute` (audio muting operation)  
- `extract_subtitles` → `sub_extract` (subtitle extraction operation)
- `remux` → `video_remux` (video remuxing operation)

**Files to Update**:
- CLI command names and help text
- Operation registry and routing
- Logging messages and audit entries
- Documentation and user-facing strings
- Test fixtures and validation

**Validation**: Ensure backward compatibility through deprecation warnings for old names

### Task 68: Universal Timestamp Integration
**Context**: Extend timestamp logging beyond FFmpeg operations to provide comprehensive observability across all pipeline stages.

**Enhancement Scope**:
- Add timestamps to all operation start/completion events
- Include timing data in progress reporting
- Extend audit trail with operation duration metrics
- Add timestamp formatting consistency across all outputs

**Files to Update**:
- Core operation base classes
- Progress reporting utilities
- Audit logging system
- CLI output formatting
- Operation completion summaries

**Validation**: Verify timestamp presence in all operation types (extract, mask, mute, remux)

---
*Based on Constitution v0.3.0 - See `.specify/memory/constitution.md`*
