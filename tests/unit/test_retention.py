import os
import time
from pathlib import Path

from censorr.config.schema import ResolvedConfig
from censorr.pipeline.retention import SECONDS_PER_DAY, sweep


def cfg_for(tmp_path: Path) -> ResolvedConfig:
    return ResolvedConfig(service={"queue_path": str(tmp_path / "queue")})


def age(path: Path, days: float) -> None:
    stamp = time.time() - days * SECONDS_PER_DAY
    os.utime(path, (stamp, stamp))


def test_expired_workdir_removed_fresh_kept(tmp_path: Path) -> None:
    cfg = cfg_for(tmp_path)
    workdirs = cfg.service.queue_path / "workdirs"
    old = workdirs / "old-job"
    fresh = workdirs / "fresh-job"
    old.mkdir(parents=True)
    fresh.mkdir(parents=True)
    (old / "output.mkv").write_bytes(b"x")
    age(old, days=8)  # past the 7-day default

    result = sweep(cfg)

    assert not old.exists()
    assert fresh.exists()
    assert result.removed_workdirs == [old]


def test_expired_record_removed_fresh_kept(tmp_path: Path) -> None:
    cfg = cfg_for(tmp_path)
    records = cfg.service.queue_path / "records"
    records.mkdir(parents=True)
    old = records / "old.json"
    fresh = records / "fresh.json"
    old.write_text("{}")
    fresh.write_text("{}")
    age(old, days=31)  # past the 30-day default

    result = sweep(cfg)

    assert not old.exists()
    assert fresh.exists()
    assert result.removed_records == [old]


def test_custom_ttls_honored(tmp_path: Path) -> None:
    cfg = ResolvedConfig(
        service={"queue_path": str(tmp_path / "queue"), "failed_ttl_days": 1, "record_ttl_days": 2}
    )
    workdir = cfg.service.queue_path / "workdirs" / "job"
    workdir.mkdir(parents=True)
    record = cfg.service.queue_path / "records" / "job.json"
    record.parent.mkdir(parents=True)
    record.write_text("{}")
    age(workdir, days=1.5)
    age(record, days=1.5)

    result = sweep(cfg)

    assert not workdir.exists()  # 1.5 > 1 day TTL
    assert record.exists()  # 1.5 < 2 day TTL
    assert result.removed_workdirs == [workdir]
    assert result.removed_records == []


def test_missing_queue_dirs_are_fine(tmp_path: Path) -> None:
    result = sweep(cfg_for(tmp_path))

    assert result.removed_workdirs == []
    assert result.removed_records == []
