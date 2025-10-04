# Validation Script Contract

## Purpose
Validate Censorr deployment configuration and runtime state.

## Command Line Interface
```bash
python scripts/validate_deployment.py --config path/to/censorr.yml [--runtime-check]
```

## Parameters
- `--config`: Path to YAML configuration file (required)
- `--runtime-check`: Also validate running container state (optional)

## Exit Codes
- `0`: Configuration valid
- `1`: Configuration invalid  
- `2`: Runtime state mismatch (if --runtime-check enabled)
- `3`: Script error (file not found, etc.)

## Validation Rules

### Configuration Validation
1. Required fields present (`enabled`, `image_repo`, `image_tag`, `volumes`)
2. Volume mappings include required media (ro) and work (rw) volumes
3. Environment variable keys follow `CENSORR_*` pattern (uppercase, underscores)
4. Health check spec valid (command array, positive intervals)
5. Resource constraints valid (memory parseable, cpu_shares > 0)
6. No mutually exclusive health configurations
7. Label keys/values are strings

### Runtime Validation (Optional)
1. Container exists and matches expected name
2. Image digest matches expected repository:tag
3. Volume mounts match configuration
4. Environment variables match configuration  
5. Labels match expected base + user labels
6. Health status is healthy (if health check configured)

## Output Format
```json
{
  "valid": true,
  "errors": [],
  "warnings": ["Non-critical issues"],
  "runtime_checks": {
    "container_running": true,
    "image_match": true,
    "volumes_match": true
  }
}
```

## Error Examples
```json
{
  "valid": false,
  "errors": [
    "Missing required volume: media mount with mode 'ro'",
    "Invalid environment key 'censorr_verbose': must be uppercase"
  ]
}
```