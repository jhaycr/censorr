## Data Model: Censorr Deployment Integration

Scope: Conceptual (documentation-only). No runtime persistence added.

### 1. DeploymentConfig
Represents desired declarative state consumed by external Ansible role.

Fields:
- enabled (bool, default: true)
- image_repo (string, e.g., `ghcr.io/jhaycr/censorr`)
- image_tag (string, semver or channel, e.g., `v0.1.0` or `latest`)
- force_pull (bool, default: false)
- container_name (string, default: `censorr`)
- user_id (int|null) / group_id (int|null) – optional runtime UID/GID mapping
- volumes (list of VolumeMount)
- env (map<string,string>) – non-secret values
- labels (map<string,string>) – includes base labels + user extension
- health (HealthSpec|null)
- resources (ResourceSpec|null)
- log_volume_enabled (bool, default: false)
- timezone (string|null) – injected as `TZ` env var if provided

Validation Rules:
- image_repo and image_tag required if enabled.
- volumes must include at minimum: media (ro), work/output (rw).
- If health present: must have either command defined (only) → HTTP not supported now.
- resources.memory_limit if present must be parseable by Docker (e.g., `512m`, `1g`).

### 2. VolumeMount
Fields:
- host_path (string)
- container_path (string)
- mode (enum: `ro`|`rw`)

Constraints:
- No duplicate container_path entries.
- media volume must be `ro`.

### 3. HealthSpec
Fields:
- command (list[string]) – e.g., `["censorr", "--version"]`
- interval_seconds (int, default: 30)
- timeout_seconds (int, default: 5)
- retries (int, default: 3)
- start_period_seconds (int, default: 10)

### 4. ResourceSpec
Fields:
- memory_limit (string, optional)
- cpu_shares (int, optional)

Constraints:
- cpu_shares > 0 if provided.

### 5. DerivedRuntimeState (Conceptual)
Not configured directly—represents observed state from `docker inspect` (future validation usage).
Fields: image_digest, running (bool), health_status, restart_count, label_set.

### Relationships
- DeploymentConfig has many VolumeMount entries.
- DeploymentConfig optionally has one HealthSpec.
- DeploymentConfig optionally has one ResourceSpec.

### State Transitions (Declarative)
- enabled true → container should exist & be running.
- enabled false → container should be absent (volumes intact).
- image_tag change → triggers re-creation.
- force_pull true with unchanged tag → triggers image refresh.

### Notes
This model will inform JSON Schema + example variable file; no Python classes needed now.
