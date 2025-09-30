## Quickstart: Deploying Censorr via Ansible (Homelab Integration)

Goal: Add the Censorr container to an existing NAS infrastructure managed with the `jhaycr-local.docker_compose` role—without modifying the role itself.

### 1. Add Repository as Submodule (Recommended)
In your `nas-infra` repository root:
```
git submodule add https://github.com/<your-fork-or-source>/censorr_private external/censorr
git commit -m "Add censorr submodule"
```

To update later:
```
cd external/censorr
git fetch --all
git checkout <tag-or-branch>
cd ../..
git add external/censorr
git commit -m "Update censorr submodule to <ref>"
```

### 2. Copy Example Variables
From the submodule, copy the provided example (future path):
```
cp external/censorr/deploy/ansible/vars.example.yml group_vars/media/censorr.yml
```
Edit `group_vars/media/censorr.yml` to fit your environment (paths, image tag, volumes).

### 3. Compose Fragment
Copy (or merge) the service fragment into your central compose aggregation path used by the role, e.g.:
```
cp external/censorr/deploy/ansible/compose.censorr.yml compose/services/censorr.yml
```
Ensure your role's variable that enumerates compose service files includes this new file if required.

### 4. Minimum Required Variables
```
censorr_enabled: true
censorr_image_repo: ghcr.io/jhaycr/censorr
censorr_image_tag: v0.1.0
censorr_volumes:
  - { host: /mnt/media, container: /media, mode: ro }
  - { host: /srv/censorr/work, container: /app/workdir, mode: rw }
censorr_env:
  TZ: "UTC"
  CENSORR_VERBOSE: "true"
```

### 5. Optional Variables
```
censorr_force_pull: false
censorr_cpu_shares: 256
censorr_mem_limit: 512m
censorr_health:
  command: ["censorr", "--version"]
  interval_seconds: 30
  timeout_seconds: 5
  retries: 3
  start_period_seconds: 10
```

### 6. Run Playbook
```
ansible-playbook site.yml --limit media_host
```
Expected result: Censorr container created and running. Inspect:
```
docker ps | grep censorr
docker inspect censorr | jq '.[0].Config.Labels'
```

### 7. Updating Image
Change `censorr_image_tag` and re-run the playbook. Add `censorr_force_pull: true` if re-pulling same tag.

### 8. Disabling Service
Set `censorr_enabled: false` and re-run. Container removed; volumes remain.

### 9. Verification Checklist
- Container name matches expected
- Volumes mounted correctly (read-only media)
- Labels present (`org.censorr.service`)
- Health (if configured) shows healthy

### 10. Future Enhancements (Deferred)
- Automated validation script to assert running state matches config
- Optional Prometheus or reverse proxy labels
- Rollback helper documenting prior digest

### Safety Notes
- Never store secrets directly in repo; use Ansible vault.
- Use explicit tags (avoid mutable tags in production if reproducibility required).
