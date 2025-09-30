## Research: Censorr Ansible Integration (Feature 002)

Date: 2025-09-29  
Scope: Resolve deployment/integration ambiguities before producing artifacts.

### Decision Log Format
Each entry includes: Decision, Rationale, Alternatives Considered, Open Risks.

---
### 1. Image Tag Strategy
Decision: Fail fast if specified tag not found; do not auto-fallback.  
Rationale: Prevents drift; explicitness preferred for reproducibility.  
Alternatives: Auto-fallback to `latest` (rejected: hides errors), dual variable (tag + fallback) (rejected: adds complexity).  
Open Risks: If registry transient failure occurs, playbook fails; mitigation via retry at Ansible layer.

### 2. Rollback Handling
Decision: Manual rollback via changing `censorr_image_tag` to previous known good version.  
Rationale: Simplicity; avoids speculative automation before health semantics stabilized.  
Alternatives: Automatic previous digest retention & revert (rejected: state management overhead).  
Open Risks: Operator must remember prior tag; mitigation: suggest logging last deployed digest in future validation script (future task).

### 3. Label Conventions
Decision: Provide neutral labels only:
```
labels:
  org.censorr.service: "censorr"
  org.censorr.version: "<resolved image tag>"
```
Rationale: Avoid coupling to Traefik/Prometheus specifics prematurely.  
Alternatives: Add Traefik routing labels (rejected until requirement emerges).  
Open Risks: Users may need additional labels; addressed by allowing map extension.

### 4. Resource Constraints Variables
Decision: Support optional `censorr_mem_limit` (string e.g. "512m") and `censorr_cpu_shares` (int).  
Rationale: Common Compose semantics; minimal surface.  
Alternatives: Add reservations/limits pair (rejected for simplicity).  
Open Risks: Advanced resource governance not covered.

### 5. Force Pull Mechanism
Decision: Boolean var `censorr_force_pull` triggers image pull even if tag unchanged.  
Rationale: Enables digest refresh for mutable tags (e.g. `latest`).  
Alternatives: Always pull (wastes bandwidth), never pull (stale images).  
Open Risks: If registry rate-limits; doc note to disable when unnecessary.

### 6. Health Check Form
Decision: Provide optional command health check using `censorr --version`; skip if disabled.  
Rationale: Simple, low-cost; no background server to probe.  
Alternatives: HTTP endpoint (not available), deep functional test (too heavy).  
Open Risks: Command may exit quickly—Compose marks healthy almost immediately (acceptable).

### 7. Secrets Handling Pattern
Decision: Document pattern: environment map supports values or references; recommend Ansible vault for secrets (user defines separate vars).  
Rationale: Keep this repo agnostic of secret storage.  
Alternatives: Provide template expecting `_FILE` usage (rejected pending need).  
Open Risks: Misconfiguration could leak secrets in logs—warn in README.

### 8. Consumption Path (Integration Mechanism)
Decision: Recommend git submodule under `nas-infra/roles/_external/censorr-deploy` (example) pointing to this repo; operator copies/links compose fragment and vars example into group_vars.  
Rationale: Version pinning + easy updates.  
Alternatives: Raw file copy (loses update traceability), Ansible Galaxy role (overkill), remote include (fragile).  
Open Risks: Submodule management complexity; mitigated with documented update steps.

### 9. No-Op Deployment Time Goal
Decision: Aim <10s; warn if >15s (future validation script could measure).  
Rationale: Provides expectation without enforcing now.  
Alternatives: Strict failure threshold (premature).  
Open Risks: Variability due to host load.

### 10. Validation Script (Future)
Decision: Defer implementation; create tasks for a Python script to parse compose config & running container state (docker inspect) verifying label/image/tag alignment.  
Rationale: Keeps current scope minimal; provides path to automation later.  
Alternatives: Immediate implementation (adds complexity before stability).  
Open Risks: Drift detection unavailable until implemented.

---
### Open Clarifications (Deferred)
- Need for automatic rollback logic? → Deferred until health instability observed.
- Additional label ecosystems (Traefik, metrics) requested? → Await explicit requirement.
- Secret injection via `_FILE` convention needed? → Await usage feedback.

---
### Summary
All major unknowns resolved with conservative, minimal decisions emphasizing explicit configuration, idempotency, and extendability. Deferred items are explicitly noted and will surface as follow-up tasks if prioritized.
