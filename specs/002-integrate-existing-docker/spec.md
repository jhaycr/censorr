# Feature Specification: Provide Generic Docker Compose Deployment for Censorr

**Feature Branch**: `002-integrate-existing-docker`  
**Created**: 2025-09-29  
**Status**: Draft  
**Input**: User description: "Provide a simple, generic docker-compose setup (docker-compose.yml + env.template) in the repo with the Dockerfile so users can deploy and run Censorr as a long-running service without Ansible."

## Execution Flow (main)
```
1. Parse user description from Input
2. Extract key concepts: integration with existing Ansible role (docker_compose), deployment of censorr container, configuration (env, volumes), update management, health/monitoring hooks.
3. Ambiguities identified and marked.
4. Define user scenarios (administrative workflows + runtime expectations).
5. Generate functional requirements (deployment, config management, lifecycle, observability, security, update strategy, rollback capability).
6. Identify key entities: DeploymentConfig, RuntimeContainerState, MonitoringSignal.
7. Review checklist — ambiguities remain (clarification markers retained) → spec remains Draft.
8. Output specification for planning phase.
```

---

## ⚡ Quick Guidelines
- Focus on WHAT: Provide a managed, reproducible deployment of the Censorr tool via a generic docker-compose setup.
- Avoid HOW: No low-level implementation (no playbook YAML specifics, no handler code, no docker-compose syntax details here).
- Audience: Home-lab / infra maintainer who operates an automated NAS stack.

---

## User Scenarios & Testing *(mandatory)*

### Primary User Story
As a homelab operator, I want a simple docker-compose.yml and an env.template in the project so I can `docker compose up -d` and get a long-running Censorr service, then trigger processing jobs on demand or via Radarr/Sonarr hooks.

### Acceptance Scenarios
1. **Given** a fresh host without the Censorr container present, **When** I run `docker compose up -d` using the provided docker-compose.yml and .env file, **Then** a Censorr container is built (if needed) and started with the configured environment, volumes, restart policy, and labels.
2. **Given** an existing running Censorr container, **When** I update the image tag or rebuild via Compose and run `docker compose up -d` again, **Then** the container is recreated using the new image and persistent volumes remain intact.
3. **Given** invalid configuration values in the .env (e.g., missing required volume mapping), **When** `docker compose up` runs, **Then** the run fails with a clear error referencing the missing or invalid variable name.
4. **Given** monitoring/label integrations (e.g., Traefik / auto-discovery / health label expectations), **When** the container is deployed, **Then** the configured labels are applied and discoverable via `docker inspect`.
5. **Given** a desire to stop the service temporarily, **When** I run `docker compose stop` (or `down`), **Then** the container is stopped (removed if `down`) without deleting persistent data volumes.
6. **Given** a corrupted or failing container (non-zero restart loop), **When** I run `docker compose up -d --pull always --build`, **Then** the deployment enforces the desired healthy state (rebuild, recreate) unless explicitly pinned to an image digest.
7. **Given** log retention settings are configured via environment or volume mapping, **When** the container runs for multiple days, **Then** logs persist according to retention policy (externalized if volume configured) and are not lost on restart.
8. **Given** a health check configuration (interval, retries) is defined in vars, **When** the container starts, **Then** the health status transitions from starting to healthy within the expected grace period assuming the tool is functional.
9. [Removed] Build-from-private-repo via BuildKit secrets is out of scope for this feature.
10. **Given** no `.env` file is present, **When** I run `docker compose up -d` with the provided docker-compose.yml, **Then** the service starts using documented sensible defaults, or fails clearly if required host paths do not exist.
10. **Given** the NAS stores media at separate roots for TV and Movies, **When** I deploy Censorr, **Then** the container has read access to TV at `/data/media/tv` and Movies at `/data/media/movies` inside the container via bind mounts.

11. [Removed] Podman examples are not provided; this feature standardizes on Docker Compose commands only.

### Edge Cases
- What happens when the specified image tag does not exist? → Deployment should fail clearly; no partial container left running. [NEEDS CLARIFICATION: Should there be an optional fallback to `latest`?]
- How does the system handle a downgrade (image tag changes from higher to lower semantic version)? → Should allow and document; require explicit rollback variable? [NEEDS CLARIFICATION]
- Behaviour when volumes already mounted by another container name? → Should fail fast with explicit conflict message.
- If the service is disabled but container still running manually started by user? → Role should stop/remove it to enforce declarative state. [Confirm desired enforcement strictness] [NEEDS CLARIFICATION]
- Handling of breaking config changes (removed env var) — warn vs fail? [NEEDS CLARIFICATION]

---

## Requirements *(mandatory)*

### Functional Requirements
- **FR-001**: Provide docker-compose.yml with sensible defaults colocated with the Dockerfile; provide an env.template as an optional convenience for customization.
- **FR-002**: Allow specifying the Docker image/tag via .env and support local build via Compose (build: .).
- **FR-003**: Support configuring mapped volumes for: media input (read), work/output, configuration; media MUST be available inside the container at `/data/media/tv` and `/data/media/movies` (bind mounts), with host paths configurable via .env.
- **FR-004**: Allow specifying environment variables via .env (uppercase keys with underscores).
- **FR-005**: Apply a restart policy (default: unless-stopped) in compose.
- **FR-006**: Support optional health check in compose (CMD or HTTP), configurable via .env.
- **FR-007**: Attach user-defined labels from compose.
- **FR-008**: Optionally run as non-root with configurable UID/GID via .env, ensuring volume permissions.
- **FR-009**: Rebuild/recreate idempotently using `docker compose up -d --build`.
- **FR-010**: Preserve persistent data via volumes across redeploys.
- **FR-011**: Fail with a clear message if required volumes are missing (documented, plus runtime validation where possible).
- **FR-012**: Document how to stop/remove the service via Compose (`stop`/`down`) without deleting persistent volumes.
- **FR-013**: Document manual rollback by pinning image tag or digest in .env.
- **FR-014**: Provide log strategy guidance (Docker logging driver vs bind-mounted logs directory).
- **FR-015**: Validate that mutually exclusive health parameters are not set simultaneously.
- **FR-016**: Provide a deterministic default container name (e.g., `censorr`) configurable via .env.
- **FR-017**: Support optional resource constraints (memory, CPU) via compose fields.
- **FR-018**: Provide an env.template (optional) documenting all supported .env options.
- **FR-019a**: The docker-compose.yml MUST run without a `.env` file by relying on reasonable default values (documented), assuming the default host paths exist.
- **FR-019**: Allow specifying update channel/tag pattern via .env if published.
- **FR-020**: Ensure idempotent re-runs with no changes when configuration is unchanged.
- **FR-021**: Provide a documented way to refresh images (pull/build) without tag change.
- **FR-022**: Support optional timezone injection via TZ environment variable.
- **FR-023**: Document security recommendations: non-root user, volume permissions, secrets handling via .env or compose secrets.
- **FR-024**: Documentation and examples MUST use Docker Compose exclusively; Podman commands/examples are out of scope for this feature.

### Non-Functional / Operational Requirements
- **NFR-001**: Deployment MUST be idempotent (zero changes on second run with identical inputs).
- **NFR-002**: Failures MUST surface within a single Ansible run (no silent partial state).
- **NFR-003**: Secrets MUST NOT be written to disk in plaintext outside Ansible vault-managed files.
- **NFR-004**: Average deployment execution time SHOULD remain under 10s when no changes needed. [NEEDS CLARIFICATION: Acceptable upper bound?]
- **NFR-005**: Health check failure SHOULD produce actionable remediation guidance in message text.
- **NFR-006**: Documentation MUST be sufficient for a new operator to replicate deployment using only example vars file + README snippet.
- **NFR-007**: Build mode MUST NOT leak Git tokens in build cache, image layers, or logs; tokens MUST be provided via BuildKit secrets and marked no_log in Ansible.
 - Note: Podman-specific guidance is intentionally excluded to reduce surface area and confusion; Docker Compose is the canonical path for this feature.

### Key Entities
- **DeploymentConfig**: Declarative configuration defined in Ansible vars (image, tag, volumes, env, health, restart policy, enabled flag, resources, labels).
- **RuntimeContainerState**: Observed post-deploy state (running/stopped, image digest, health status, restart count, created timestamp).
- **MonitoringSignal**: Derived health/label metadata passed to external systems (discovery, metrics collector). (Conceptual only; no implementation defined here.)

---

## Review & Acceptance Checklist

### Content Quality
- [ ] No implementation details (languages, frameworks, APIs) — (PASS: kept abstract; docker-compose YAML not specified)
- [ ] Focused on user value and business needs — (PASS)
- [ ] Written for non-technical stakeholders — (PARTIAL: infrastructure emphasis; acceptable for ops audience)
- [ ] All mandatory sections completed — (PASS)

### Requirement Completeness
- [ ] No [NEEDS CLARIFICATION] markers remain — (FAIL: clarifications outstanding)
- [ ] Requirements are testable and unambiguous — (PARTIAL: ambiguous ones flagged)
- [ ] Success criteria are measurable — (PARTIAL: some NFR thresholds need confirmation)
- [ ] Scope is clearly bounded — (PASS; explicit out-of-scope scheduling implementation)
- [ ] Dependencies and assumptions identified — (PARTIAL: external monitoring expectations need naming) [NEEDS CLARIFICATION: Which monitoring stack?]

---

## Execution Status

- [x] User description parsed
- [x] Key concepts extracted
- [x] Ambiguities marked
- [x] User scenarios defined
- [x] Requirements generated
- [x] Entities identified
- [ ] Review checklist passed (pending clarifications)

---

