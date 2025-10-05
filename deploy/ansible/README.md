# Censorr Ansible Integration Artifacts### Health Check Configuration

Censorr containers can include health checks to monitor application status:

```yaml
# Deploy with health check enabled
censorr_health_check_enabled: true
censorr_health_check_interval: "30s"
censorr_health_check_timeout: "10s"
censorr_health_check_retries: 3
```

### Troubleshooting Health Issues

Common health check problems and their solutions:

| Symptom | Probable Cause | Solution |
|---------|---------------|----------|
| Health check "starting" → "unhealthy" | Application startup slow | Increase `censorr_health_check_timeout` or `censorr_health_check_retries` |
| Immediate "unhealthy" status | Wrong health endpoint configured | Verify `censorr_health_check_test` matches application endpoint |
| Intermittent health failures | Resource contention | Check CPU/memory limits, increase `censorr_health_check_interval` |
| Health check never runs | Docker daemon issues | Restart Docker daemon, check container logs |
| "starting" status persists | Application never ready | Check application logs, verify all dependencies available |
| Health failures after deploy | Configuration mismatch | Compare deployed vs expected environment variables |iles support integrating the Censorr container into an external infrastructure-as-code repository (e.g., `nas-infra`) **without modifying existing Ansible roles**. Use as reference; copy into your infra repo where appropriate.

## Files
- `vars.example.yml` – Suggested variable structure for group_vars/host_vars.
- `compose.censorr.yml` – Example Docker Compose service fragment to merge into your aggregated compose configuration consumed by `jhaycr-local.docker_compose` role.

## Recommended Consumption Pattern
1. Add this repository as a git submodule:
   ```
   git submodule add https://github.com/<source>/censorr_private external/censorr
   ```
2. Copy/update example vars and compose fragment into your infra repo paths.
3. Adjust volume paths, UID/GID, and image tag.
4. Re-run your Ansible play targeting the relevant host group.

## Variables Overview
| Variable | Purpose | Required | Default |
|----------|---------|----------|---------|
| censorr_enabled | Toggle deployment | No | true |
| censorr_image_repo | Image repository | Yes | ghcr.io/jhaycr/censorr |
| censorr_image_tag | Image tag | Yes | (none) |
| censorr_force_pull | Force repull even if tag unchanged | No | false |
| censorr_volumes | List of volume mappings | Yes | (none) |
| censorr_env | Environment map | No | {} |
| censorr_labels | Additional labels | No | {} |
| censorr_health | Health spec map | No | null |
| censorr_cpu_shares | CPU shares | No | null |
| censorr_mem_limit | Memory limit | No | null |
| censorr_timezone | Inject TZ env | No | null |

### Media Mounts (Standardized Internal Paths)

- Inside container, media paths are standardized:
  - TV: `/data/media/tv`
  - Movies: `/data/media/movies`
- Configure host paths via:
  - `censorr_tv_path_host` (default: `/mnt/media/tv`)
  - `censorr_movies_path_host` (default: `/mnt/media/movies`)
- The example volumes in `vars.example.yml` bind these host paths read-only to the standardized internal paths.

Migration note: if you previously mounted all media at `/media`, update your workflows or add compatibility bind mounts if needed.

## Base Labels
```
org.censorr.service: censorr
org.censorr.version: <resolved image tag>
```
Extend with `censorr_labels` if needed.

## Build from Private Git Repo (Optional)

If you cannot or prefer not to pull a prebuilt image, you can build from the private Censorr Git repo using Docker BuildKit secrets for Git tokens.

1) Enable Build Mode in vars:

```yaml
censorr_build_enabled: true
censorr_git_repo: https://github.com/jhaycr/censorr_private.git
censorr_git_ref: main   # or tag/commit
censorr_dockerfile: Dockerfile
```

2) Provide Git token securely via Ansible Vault and BuildKit secret:

- Store token in vault (e.g., `vault_censorr_git_token`).
- In your role/tasks, render it to a temp file with `no_log: true` and pass to build as secret env/file.
- Example BuildKit secret mapping (conceptual): `--secret id=git_token,src={{ censorr_git_token_file }}`

3) Compose fragment:

- When `censorr_build_enabled: true`, switch from `image:` to a `build:` block with `context`, `dockerfile`, and BuildKit `secrets`.
- Ensure BuildKit is enabled on the target host (DOCKER_BUILDKIT=1).

Security: The Git token must not appear in logs or image layers. Use BuildKit secrets and `no_log` on Ansible tasks.

## Post-Deployment Operations

### Export Image Digest (Automation Readiness)

After successful deployment, capture the deployed image digest for future automation:

```bash
# Export actual deployed image digest
docker inspect censorr --format='{{.Image}}' > censorr-deployed-digest.txt

# Alternative: Get digest from registry
docker image inspect censorr:latest --format='{{index .RepoDigests 0}}' >> deployment-log.txt
```

## Future Enhancements

The following features are planned for future releases:

### Deferred Features
- **Automatic Rollback**: Automated rollback based on health check failures
- **Prometheus Integration**: Extended container labels for metrics collection  
- **Digest Pin Helper**: Utility script to automatically pin to latest stable digest
- **Multi-Environment Support**: Environment-specific configuration templates
- **Backup Integration**: Automated volume backup before deployments

### Monitoring Extensions
- **Traefik Label Automation**: Dynamic service discovery configuration
- **Log Aggregation**: Structured logging with centralized collection
- **Performance Metrics**: Container resource usage tracking

## Contributing to Integration Artifacts

### Updating Deployment Configuration

When modifying integration artifacts, follow these rules:

1. **Task Ledger Updates**: Any changes to deployment behavior must be tracked in `/specs/002-integrate-existing-docker/tasks.md`
2. **Documentation Sync**: Keep `README.md` examples aligned with `vars.example.yml` defaults
3. **Validation Script**: Update `/scripts/validate_deployment.py` schema when adding new configuration options
4. **Contract Tests**: Add test cases in `/tests/contract/` for new validation scenarios

### Testing Integration Changes

Before submitting changes:

```bash
# Validate example configuration
python3 scripts/validate_deployment.py deploy/ansible/vars.example.yml

# Run contract tests  
python3 -m pytest tests/contract/test_validate_deployment_config.py -v

# Test actual deployment (if possible)
python3 scripts/validate_deployment.py /path/to/your/config.yml --runtime-check
```

### Integration Artifact Paths

- Configuration: `deploy/ansible/vars.example.yml`
- Documentation: `deploy/ansible/README.md`  
- Validation: `scripts/validate_deployment.py`
- Tests: `tests/contract/test_validate_deployment_config.py`
- Planning: `specs/002-integrate-existing-docker/`

These enhancements will be considered based on user feedback and ecosystem maturity.
```yaml
censorr_health:
  command: ["censorr", "--version"]
  interval_seconds: 30
  timeout_seconds: 5
  retries: 3
  start_period_seconds: 10
```

## Security Notes
- Run as non-root by setting UID/GID if image supports it.
- Never commit secrets; use Ansible vault for sensitive values in `censorr_env`.

## Rollback
Change `censorr_image_tag` back to prior version. (Future enhancement: store last digest artifact.)

## Future Enhancements (Deferred)
- Automated validation script
- Advanced label ecosystem (Traefik/Prometheus)
- Digest pin + rollback helper

