# Tasks: Integrate Censorr Docker Image into NAS Ansible Deployment (Feature 002)

**Input**: Design documents from `/specs/002-integrate-existing-docker/`  
**Prerequisites**: spec.md, plan.md, research.md, data-model.md, quickstart.md, contracts/

Immutable ledger (Constitution v0.4.0). Append-only. Completed tasks marked with ✅ (suffix only). No rewrites.

## Execution Flow (reference)
See plan.md Phase 2 strategy: documentation/integration artifacts + future validation tooling.

## Phase 3.1: Baseline Documentation & Artifacts (Retroactive Documentation Tasks)
These tasks capture already-added artifacts for traceability.
- [x] T001 Create research decisions file `specs/002-integrate-existing-docker/research.md` ✅
- [x] T002 Create data model `data-model.md` documenting DeploymentConfig & related specs ✅
- [x] T003 Add JSON Schema `contracts/deployment-config.schema.json` ✅
- [x] T004 Add quickstart integration guide `quickstart.md` ✅
- [x] T005 Add Ansible integration directory `deploy/ansible/README.md` ✅
- [x] T006 Add example vars file `deploy/ansible/vars.example.yml` ✅
- [x] T007 Add compose service fragment `deploy/ansible/compose.censorr.yml` ✅

## Phase 3.2: Documentation Enhancements
- [x] T008 [P] Add env→CLI mapping table to `deploy/ansible/README.md` (CENSORR_VERBOSE → --verbose, etc.)
- [x] T009 [P] Add multi-arch & architecture support note to `deploy/ansible/README.md`
- [x] T010 [P] Add digest pin / rollback guidance section to `deploy/ansible/README.md`
- [x] T011 [P] Add explicit idempotency verification step (2nd run) to `quickstart.md`
- [x] T012 [P] Add enabled health check example (uncommented) to `vars.example.yml`
- [x] T013 [P] Add JSON Schema validation instructions (ajv/python jsonschema) to `deploy/ansible/README.md`
- [x] T014 [P] Add secrets handling + Ansible vault example to `deploy/ansible/README.md`
- [x] T015 [P] Add resource constraints documentation (cpu_shares, mem_limit) rationale to README
- [x] T016 [P] Add rollback risk & manual recovery playbook snippet to README
- [x] T017 [P] Add note on mounting config directory for Censorr config (if used) to README
- [x] T018 [P] Add note on recommended ownership & permissions for `/srv/censorr/work` to README
- [x] T019 [P] Add label extension examples (`censorr_labels`) to README & vars example
- [x] T020 [P] Add timezone injection description and edge cases to README
- [x] T021 [P] Add example enabling `censorr_force_pull` in quickstart update workflow
- [x] T022 [P] Add no-op performance expectation note (<10s) to README
- [x] T023 [P] Extend quickstart with disable scenario (`censorr_enabled: false`) output expectations

## Phase 3.2b: Build-from-Source (Private Repo) Additions
- [ ] T023.1 Add Dockerfile template capable of cloning private repo via BuildKit secret
- [ ] T023.2 Update `deploy/ansible/compose.censorr.yml` to support build section when `censorr_build_enabled: true`
- [ ] T023.3 Extend `vars.example.yml` with build-mode variables: `censorr_build_enabled`, `censorr_git_repo`, `censorr_git_ref`, `censorr_dockerfile`, and document `censorr_git_token` (vault)
- [ ] T023.4 Add README instructions for enabling BuildKit and passing secrets with Ansible (no_log) and how to run a build
- [ ] T023.5 Add validation script checks for mutually exclusive image vs build configuration

## Phase 3.2c: Media Mount Standardization
- [ ] T023.6 Update compose fragment to mount TV and Movies to /data/media/tv and /data/media/movies (container paths)
- [ ] T023.7 Extend vars with `censorr_tv_path_host` and `censorr_movies_path_host` and migrate examples
- [ ] T023.8 Update README with new internal paths and rationale

## Phase 3.3: Future Validation Tooling (Tests First)
NOTE: These tasks introduce executable code; follow strict TDD order.
- [x] T024 Create spec for validation script `specs/002-integrate-existing-docker/contracts/validation-script.md` describing expected CLI usage (`python scripts/validate_deployment.py --config censorr.yml`)
- [x] T025 [P] Contract test (failing) for validation script: `tests/contract/test_validate_deployment_config.py` (invalid: missing required volume → non-zero exit)
- [x] T026 [P] Contract test (failing) for validation script: invalid health spec (both http+command hypothetically) → error message
- [x] T027 [P] Contract test (failing) for validation script: invalid env key (lowercase) flagged
- [x] T028 Implement minimal validation script `scripts/validate_deployment.py` to satisfy tests (schema load + rules)
- [x] T029 [P] Integration test simulating docker inspect JSON (fixture) to detect mismatch label vs config → failure `tests/integration/test_validate_runtime_state.py`

## Phase 3.3b: Validation Updates for Build Mode
- [ ] T029.1 Contract test: invalid when both image and build enabled
- [ ] T029.2 Contract test: invalid when build enabled but git repo/ref missing
- [x] T030 Extend validator to accept optional runtime JSON via flag and validate (makes earlier integration test pass)

## Phase 3.4: Observability & Health Documentation
- [x] T031 [P] Add health troubleshooting matrix to `deploy/ansible/README.md` (symptom → probable cause)
- [x] T032 [P] Add suggestion to export image digest after deployment (future automation) to README

## Phase 3.5: Polish & Risk
- [x] T033 [P] Add future enhancements section enumerating deferred features (auto rollback, Prometheus labels, digest pin helper)
- [x] T034 [P] Cross-reference FR requirements → tasks mapping table appended to `plan.md`
- [x] T035 [P] Add CONTRIBUTING snippet for updating integration artifacts & task ledger rules to `deploy/ansible/README.md`

## Phase 3.6: Deferred / Clarification Tasks
- [x] T036 Clarify need for automatic rollback mechanism (stakeholder decision) → CLARIFIED: Manual rollback only, automatic rollback deferred to future release
- [x] T037 Clarify monitoring/label ecosystem requirements (Traefik, Prometheus, etc.) → CLARIFIED: Basic Docker labels provided, extended monitoring integration deferred
- [x] T038 Clarify acceptable max no-op deploy time threshold (confirm 10s/15s values) → CLARIFIED: 15s threshold acceptable for homelab environments  
- [x] T039 Clarify whether secrets `_FILE` injection pattern needed → CLARIFIED: Standard Docker secrets adequate, `_FILE` pattern not required initially

## Dependencies
- T024 precedes T025–T028; T028 unblocks T029 & T030.
- Documentation enhancement tasks (T008–T023) independent and parallel.
- Validation tooling isolated; does not block docs.
- Clarification tasks (T036–T039) may influence future extensions but not current tasks.

## Parallel Execution Examples
Example batch 1 (docs): T008, T009, T010, T011 can run concurrently.  
Example batch 2 (validator tests): T025, T026, T027 in parallel after T024; then implement T028.  
Example batch 3 (post-validator): T029 & T030 after T028.

## FR Mapping Summary
| FR | Tasks |
|----|-------|
| FR-001 enable flag | vars.example (T006), README docs (T008, T016) |
| FR-002 image repo/tag | T006, T008, T010 |
| FR-003 volumes | T006, T011, validator tests T025 |
| FR-004 env overrides | T008, T014, validator T027 |
| FR-005 restart policy | compose fragment (T007) + README T008 |
| FR-006 health check | T012, T031 |
| FR-007 labels | T019, T032 |
| FR-008 uid/gid | T018 |
| FR-009 image update | T021, T010 |
| FR-010 persistence | T011, T018 |
| FR-011 missing volumes fail | validator T025 |
| FR-012 disable deployment | T023 |
| FR-013 rollback manual | T010, T021 (auto rollback deferred: T036) |
| FR-014 log retention | T015 (extend with log volume guidance) |
| FR-015 mutually exclusive health forms | validator T026 |
| FR-016 deterministic container name | T007 docs, validator runtime later T029 |
| FR-017 resource constraints | T015 |
| FR-018 example vars file | T006 (done) |
| FR-019 update channel/tag pattern | Clarification T036/T038 (deferred) |
| FR-020 idempotency | T011 (2nd run), validator future extension |
| FR-021 manual force pull | T021 |
| FR-022 timezone env | T020 |
| FR-023 security (non-root/secrets) | T014, T018 |
| FR-024 secret handling (no log) | T014 + future validator update |
| FR-025 no secret leakage | T014 (doc) + potential validator enhancement |
| FR-026 concurrency/jobs env | T008 (mapping) |
| FR-027 safe disable (volumes intact) | T023 |
| FR-028 schedule out-of-scope | Plan doc (no task) |
| FR-029 structured logging volume | T015 + README log example |
| FR-030 summary output (play) | Out of scope (external role) – note in README (T010) |

## Validation Checklist
- Retroactive tasks documented for existing artifacts.
- Tests scheduled before implementation for new validation code (T024→T025..T028).
- Parallel tags only on independent files.
- FR mapping present.
- Clarification tasks enumerated.
