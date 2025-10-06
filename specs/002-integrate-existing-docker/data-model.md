## Data Model: Censorr Deployment Integration

Scope: Conceptual (documentation-only). No runtime persistence added.

### 1. DeploymentConfig
Represents desired declarative state consumed by external Ansible role.

Fields:

Validation Rules:

### 2. VolumeMount
Fields:
- host_path (string)
- container_path (string)
- retries (int, default: 3)
- start_period_seconds (int, default: 10)
- memory_limit (string, optional)
- cpu_shares (int, optional)

  
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
