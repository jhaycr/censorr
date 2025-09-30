# Censorr Ansible Integration Artifacts

These files support integrating the Censorr container into an external infrastructure-as-code repository (e.g., `nas-infra`) **without modifying existing Ansible roles**. Use as reference; copy into your infra repo where appropriate.

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

## Base Labels
```
org.censorr.service: censorr
org.censorr.version: <resolved image tag>
```
Extend with `censorr_labels` if needed.

## Health Check (Optional)
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

