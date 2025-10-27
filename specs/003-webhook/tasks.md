# Tasks: Censorr Webhook Service (WSGI + Gunicorn)

Feature Dir: /home/josh/Code/Censorr2/specs/003-webhook  
Branch: 003-webhook

## Generation Context
- Based on: plan.md, research.md, data-model.md, contracts/openapi.yaml, quickstart.md
- Constraints: Minimal server (allowlist filter only), CLI owns business rules, bounded FIFO queue, counters since process start, Radarr/Sonarr only, no idempotency

## Ordering Rules
- Setup before everything
- Tests before implementation (TDD)
- Models before services
- Services before endpoints
- Core before integration
- Parallel [P] when different files

---

## TDD Plan and Tasks

T001 Setup project scaffolding [P]
- Create `src/webhook/wsgi_app.py` (stdlib WSGI) with stubs for /webhook, /healthz, /readyz, /status
- Create `src/webhook/__init__.py`
- Add `src/webhook/runner.py` Gunicorn entry hints (module:app)
- Ensure non-root runtime and stdout logging per spec-002

T002 Contract tests for POST /webhook [P]
- File: `tests/contract/test_webhook_post.py`
- Use OpenAPI to assert statuses: 202 accepted, 200 ignored (allowlist miss, unknown/missing preset), 400 failed (malformed/security)
- Include fixtures for Radarr/Sonarr media import payloads with 'censorr_profile' allowlisted

T003 Contract tests for GET /status [P]
- File: `tests/contract/test_status.py`
- Assert counters schema and queue_depth, since process start

T004 Contract tests for GET /healthz and /readyz [P]
- File: `tests/contract/test_health_ready.py`
- Assert 200 responses; /readyz depends on worker availability/config loaded

T005 Unit tests: allowlist filtering (server) [P]
- File: `tests/unit/test_allowlist.py`
- Cases: allowlist miss (ignored), allowlist hit (pass-through), empty allowlist (disabled), configurable list

T006 Unit tests: example payloads (Radarr/Sonarr) [P]
- File: `tests/unit/test_example_payloads.py`
- Use representative media import/completed download payloads
- Verify: allowlist behavior, pass-through invocation of CLI (mocked), response categorization

T007 Unit tests: CLI exit-code mapping [P]
- File: `tests/unit/test_exit_code_mapping.py`
- Map: 0→202 accepted; 2→200 ignored; 3→400 failed; 1→500 error

T008 Integration tests: Compose service basic flow
- File: `tests/integration/test_compose_flow.py`
- Spin up service container (if available) or skip gracefully
- POST webhook with valid allowlist+preset → expect accepted; check status counters increment

T009 Implement WSGI app shell
- File: `src/webhook/wsgi_app.py`
- Implement minimal routes: parse JSON; apply allowlist; call CLI (subprocess) with raw payload; map exit codes

T010 Implement status counters and health/readiness
- File: `src/webhook/wsgi_app.py`
- Maintain in-memory counters since process start; queue depth query via CLI status call; health endpoints

T011 Wire Gunicorn entrypoint
- File: `src/webhook/runner.py`
- Expose `app` for Gunicorn; document command in README/quickstart

T012 Docs polish [P]
- Update `specs/003-webhook/quickstart.md` with Gunicorn command examples and env for allowlist
- Add usage notes for enabling/disabling webhooks

T013 Observability polish [P]
- Ensure structured log fields for request_id, source, decision, status
- Confirm logs to stdout/stderr

T014 Security polish [P]
- Optional shared secret header validation path with graceful failure
- Oversized payload rejection path

T015 Task ledger and commit hygiene
- Ensure tasks are referenced in commits; no generated artifacts are committed; follow constitution v0.4.0

## Parallelization Hints
- T001, T002, T003, T004, T005, T006, T007 can start in parallel ([P]) as separate files
- Implementations (T009–T011) follow after tests are authored
- Polish tasks (T012–T014) can run in parallel after core implementation

