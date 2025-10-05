# Feature Specification: Integrate Censorr Docker Image into NAS Ansible Deployment

**Feature Branch**: `002-integrate-existing-docker`  
**Created**: 2025-09-29  
**Status**: Draft  
**Input**: User description: "Integrate existing Docker image into NAS Ansible setup (roles/jhaycr-local.docker_compose) to deploy and manage censorr container with configurable environment, volumes, updates, and health/monitoring hooks"

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
- Focus on WHAT: Provide a managed, reproducible deployment of the Censorr tool via existing NAS Ansible automation.
- Avoid HOW: No low-level implementation (no playbook YAML specifics, no handler code, no docker-compose syntax details here).
- Audience: Home-lab / infra maintainer who operates an automated NAS stack.

---

## User Scenarios & Testing *(mandatory)*

### Primary User Story
As a NAS administrator maintaining infrastructure-as-code via Ansible, I want the Censorr media processing tool deployed and managed as a Docker service using my existing `jhaycr-local.docker_compose` Ansible role so that it can run jobs reliably with consistent configuration, logs, updates, and monitoring integration.

### Acceptance Scenarios
1. **Given** a fresh NAS host without the Censorr container present, **When** I apply the Ansible playbook including the censorr role vars, **Then** a Censorr container is created and started with the configured image tag, volumes, environment variables, restart policy, and labels.
2. **Given** an existing running Censorr container at image tag N, **When** the desired image tag is updated in Ansible vars and the playbook is re-run, **Then** the container is recreated using the new image and previous persistent volumes remain intact.
3. **Given** invalid configuration variables (e.g., missing required volume mapping), **When** the playbook runs, **Then** the run fails with a clear error referencing the missing or invalid variable name.
4. **Given** monitoring/label integrations (e.g., Traefik / auto-discovery / health label expectations), **When** the container is deployed, **Then** the configured labels are applied and discoverable via `docker inspect`.
5. **Given** a desire to disable the service temporarily, **When** I set an enabled flag to false in vars and re-run the playbook, **Then** the container is stopped and removed without deleting persistent data volumes.
6. **Given** a corrupted or failing container (non-zero restart loop), **When** I re-run the playbook, **Then** the idempotent deployment enforces the desired healthy state (pull latest image, recreate) unless an explicit rollback pin is configured.
7. **Given** log retention settings are configured via environment or volume mapping, **When** the container runs for multiple days, **Then** logs persist according to retention policy (externalized if volume configured) and are not lost on restart.
8. **Given** a health check configuration (interval, retries) is defined in vars, **When** the container starts, **Then** the health status transitions from starting to healthy within the expected grace period assuming the tool is functional.
9. **Given** the Censorr source is hosted in a private Git repository, **When** I enable a build-from-source mode and provide a Git access token via BuildKit secret in Ansible, **Then** the Docker image is built via a Dockerfile that clones the repo using the secret (not written to layers/logs) and the resulting container deploys successfully.

### Edge Cases
- What happens when the specified image tag does not exist? → Deployment should fail clearly; no partial container left running. [NEEDS CLARIFICATION: Should there be an optional fallback to `latest`?]
- How does the system handle a downgrade (image tag changes from higher to lower semantic version)? → Should allow and document; require explicit rollback variable? [NEEDS CLARIFICATION]
- Behaviour when volumes already mounted by another container name? → Should fail fast with explicit conflict message.
- If the service is disabled but container still running manually started by user? → Role should stop/remove it to enforce declarative state. [Confirm desired enforcement strictness] [NEEDS CLARIFICATION]
- Handling of breaking config changes (removed env var) — warn vs fail? [NEEDS CLARIFICATION]

---

## Requirements *(mandatory)*

### Functional Requirements
- **FR-001**: System MUST define a declarative variable structure for enabling/disabling the Censorr deployment.
- **FR-002**: System MUST allow specifying the Docker image (registry, repository, tag) for Censorr.
- **FR-003**: System MUST support configuring mapped volumes for: media input (read), work/output, configuration, and optional logs directory.
- **FR-004**: System MUST allow specifying environment variables (key-value map) including override and remove semantics. [NEEDS CLARIFICATION: Is remove semantic required or just override?]
- **FR-005**: System MUST apply a restart policy (default: unless-stopped) configurable via variable.
- **FR-006**: System MUST support optional health check definition (command or HTTP endpoint, interval, timeout, retries, start period).
- **FR-007**: System MUST attach user-defined labels (for service discovery / monitoring / backup classification).
- **FR-008**: System MUST optionally pin container user/group IDs (uid/gid) for NAS permission alignment.
- **FR-009**: System MUST pull updated image when tag changes and recreate container idempotently.
- **FR-010**: System MUST preserve persistent data across redeploys via volumes.
- **FR-011**: System MUST fail with a clear message if required volumes are missing in variables.
- **FR-012**: System MUST allow disabling deployment (flag) which removes/stops container but does not delete persistent volumes.
- **FR-013**: System MUST optionally support a rollback mechanism by pinning a previous image tag if health check fails on update. [NEEDS CLARIFICATION: Automatic rollback vs manual pin?]
- **FR-014**: System MUST expose a variable to control log retention strategy (volume vs default Docker logging driver explanation in docs).
- **FR-015**: System MUST validate that mutually exclusive parameters (e.g., both health command and HTTP check) are not set simultaneously; fail clearly.
- **FR-016**: System MUST generate deterministic container name (e.g., `censorr`) unless overridden.
- **FR-017**: System MUST support optional resource constraints (CPU shares/limits, memory limit) via variables. [NEEDS CLARIFICATION: Which exact knobs needed?]
- **FR-018**: System MUST provide a documented example vars file referencing all supported options.
- **FR-019**: System MUST allow specifying update channel or tag pattern (e.g., stable vs edge) if the image repository publishes variants. [NEEDS CLARIFICATION]
- **FR-020**: System MUST ensure idempotent re-runs produce no changes when configuration is unchanged.
- **FR-021**: System MUST provide a way to trigger manual image refresh (force pull) without tag change (e.g., boolean var). [NEEDS CLARIFICATION]
- **FR-022**: System MUST support optional timezone/environment locale variable injection.
- **FR-023**: System MUST document security recommendations: non-root user run, volume permission alignment, secret handling.
- **FR-024**: System MUST allow secret values (e.g., API keys) to be sourced from Ansible vault/inventory variables without logging their content.
- **FR-025**: System MUST not expose secrets in Ansible output (no_log for sensitive tasks).
- **FR-026**: System MUST allow configuration of concurrency (e.g., jobs env var) for the tool via environment variable mapping.
- **FR-027**: System MUST ensure container removal on disable does not break dependent external mounts referencing the same paths.
- **FR-028**: System MUST support optional schedule integration (e.g., systemd timer / cron outside scope) documented as out-of-scope for this role (clarify boundaries).
- **FR-029**: System MUST allow enabling structured logging volume (if tool supports) via variable.
- **FR-030**: System MUST produce a summary output at end of play: deployed image tag, container name, health status (if health check defined).
- **FR-031**: System MUST support an alternative "build mode" that builds a Docker image from a Dockerfile which clones the private Censorr Git repository, using BuildKit secrets for Git credentials.
- **FR-032**: System MUST provide variables for Git repository URL and ref (branch/tag/commit) and a secure way to inject the Git token to the build (via Ansible vault → BuildKit secret), without persisting the secret in image layers or logs.

### Non-Functional / Operational Requirements
- **NFR-001**: Deployment MUST be idempotent (zero changes on second run with identical inputs).
- **NFR-002**: Failures MUST surface within a single Ansible run (no silent partial state).
- **NFR-003**: Secrets MUST NOT be written to disk in plaintext outside Ansible vault-managed files.
- **NFR-004**: Average deployment execution time SHOULD remain under 10s when no changes needed. [NEEDS CLARIFICATION: Acceptable upper bound?]
- **NFR-005**: Health check failure SHOULD produce actionable remediation guidance in message text.
- **NFR-006**: Documentation MUST be sufficient for a new operator to replicate deployment using only example vars file + README snippet.
- **NFR-007**: Build mode MUST NOT leak Git tokens in build cache, image layers, or logs; tokens MUST be provided via BuildKit secrets and marked no_log in Ansible.

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

