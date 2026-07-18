import shutil
import time
from pathlib import Path

from pydantic import BaseModel

from censorr.config.schema import ResolvedConfig

SECONDS_PER_DAY = 86400.0


class GCResult(BaseModel):
    removed_workdirs: list[Path] = []
    removed_records: list[Path] = []


def workdir_root(cfg: ResolvedConfig) -> Path:
    return cfg.service.queue_path / "workdirs"


def records_root(cfg: ResolvedConfig) -> Path:
    return cfg.service.queue_path / "records"


def sweep(cfg: ResolvedConfig, *, now: float | None = None) -> GCResult:
    """R11 retention GC: failed workdirs kept failed_ttl_days, job records
    kept record_ttl_days (safe -- idempotency lives in output metadata, not
    records). Ages are judged by mtime. Called at worker start + interval
    (Step 13) and exposed as `censorr gc` for testing.
    """
    now = now if now is not None else time.time()
    result = GCResult()

    workdirs = workdir_root(cfg)
    if workdirs.is_dir():
        cutoff = now - cfg.service.failed_ttl_days * SECONDS_PER_DAY
        for path in sorted(workdirs.iterdir()):
            if path.is_dir() and path.stat().st_mtime < cutoff:
                shutil.rmtree(path, ignore_errors=True)
                result.removed_workdirs.append(path)

    records = records_root(cfg)
    if records.is_dir():
        cutoff = now - cfg.service.record_ttl_days * SECONDS_PER_DAY
        for path in sorted(records.glob("*.json")):
            if path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
                result.removed_records.append(path)

    return result
