import os
import shutil
import socket
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from censorr.config.load import load_config
from censorr.config.schema import ResolvedConfig
from censorr.naming.plex import classify
from censorr.pipeline import library, retention
from censorr.pipeline.context import PipelineContext
from censorr.pipeline.errors import CensorrError, JobValidationError, QCError, TransientError
from censorr.pipeline.fingerprint import check_skip, resolve_wordlist
from censorr.pipeline.job import Job, JobErrorInfo, JobRecord, JobResult, JobStatus
from censorr.pipeline.runner import STAGE_SEQUENCE, Stage, run_pipeline
from censorr.pipeline.stages import stats_from_context
from censorr.queue.file_queue import ClaimedJob, FileJobQueue
from censorr.service.logging import log_event

GC_INTERVAL_S = 3600.0

# Fraction of STAGE_SEQUENCE completed per stage, for coarse progress.
_STAGE_COUNT = len(STAGE_SEQUENCE)


def _write_record_atomic(cfg: ResolvedConfig, record: JobRecord) -> None:
    records_dir = cfg.service.queue_path / "records"
    records_dir.mkdir(parents=True, exist_ok=True)
    path = records_dir / f"{record.job.id}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(record.model_dump_json(indent=2))
    os.replace(tmp, path)


def _source_stability_stage(initial_size: int, initial_mtime: float) -> Stage:
    """R9: re-stat the source right before publish; if an Arr upgrade landed
    mid-job (size/mtime changed), fail transient so the retry sees the new
    file instead of publishing an output built from the replaced one."""

    def stage(ctx: PipelineContext, workdir: Path) -> PipelineContext:
        if ctx.outcome is not None:
            return ctx
        stat = ctx.job.source.stat()
        if (stat.st_size, stat.st_mtime) != (initial_size, initial_mtime):
            raise TransientError(f"source changed mid-job: {ctx.job.source}")
        return ctx

    return stage


class Worker:
    def __init__(
        self,
        cfg: ResolvedConfig,
        *,
        worker_id: str | None = None,
        config_path: Path | None = None,
        on_stage: Callable[[str, PipelineContext], None] | None = None,
    ) -> None:
        # on_stage: test-only failure-injection hook, called after each
        # completed pipeline stage (testing philosophy: mock only for
        # failure injection -- e.g. swapping the source file mid-job).
        self.cfg = cfg
        self.worker_id = worker_id or f"{socket.gethostname()}-{os.getpid()}"
        self._config_path = config_path
        self._on_stage = on_stage
        self.queue = FileJobQueue(
            cfg.service.queue_path,
            max_retries=cfg.service.max_retries,
            lease_seconds=cfg.service.lease_seconds,
        )
        self._last_gc = 0.0

    def _cfg_for_job(self, job: Job) -> ResolvedConfig:
        """Re-resolve config per job: the preset overlay lands here (R8 --
        the API only decides the preset *name*), and re-reading the file
        means UI/config edits apply from the next job onward without a
        worker restart. Programmatic use (no config_path, no preset --
        i.e. tests) keeps the constructor's cfg snapshot. An unknown
        preset is a deterministic bad-payload error."""
        if self._config_path is None and not job.preset:
            return self.cfg
        try:
            return load_config(config_path=self._config_path, preset=job.preset)
        except KeyError as exc:
            raise JobValidationError(f"unknown preset: {job.preset!r}") from exc

    def _maybe_gc(self) -> None:
        now = time.monotonic()
        if now - self._last_gc >= GC_INTERVAL_S or self._last_gc == 0.0:
            retention.sweep(self.cfg)
            self.queue.recover_stale()
            self._last_gc = now

    def _record(
        self,
        job: Job,
        status: JobStatus,
        *,
        result: JobResult | None = None,
        stage: str | None = None,
        progress: float = 0.0,
        error: JobErrorInfo | None = None,
        created_at: datetime | None = None,
    ) -> None:
        now = datetime.now(UTC)
        record = JobRecord(
            job=job,
            status=status,
            result=result,
            stage=stage,
            progress=progress,
            error=error,
            created_at=created_at or now,
            started_at=now if status != JobStatus.QUEUED else None,
            finished_at=now if status in (JobStatus.DONE, JobStatus.FAILED) else None,
        )
        _write_record_atomic(self.cfg, record)

    def _complete_without_running(self, claimed: ClaimedJob, status: str, reason: str) -> None:
        self.queue.complete(claimed, {"status": status, "reason": reason})
        self._record(
            claimed.entry.job,
            JobStatus.DONE,
            result=JobResult(status=status, reason=reason, mode="none"),
        )

    def _expand_backfill(self, claimed: ClaimedJob, job_cfg: ResolvedConfig) -> None:
        """A directory job is a backfill request: walk it worker-side (the
        API has no media mounts, R8), skip Censorr outputs/extras and
        fingerprint-fresh files (unless force), and enqueue one child job
        per remaining source. Same-source dedup makes resubmission safe."""
        job = claimed.entry.job
        wordlist = resolve_wordlist(job_cfg)
        queued = 0
        fresh = 0
        for candidate in library.find_backfill_candidates(job.source, job_cfg):
            if not job.force:
                media_type = classify(candidate, None)
                skip, _plan = check_skip(candidate, media_type, cfg=job_cfg, wordlist=wordlist)
                if skip:
                    fresh += 1
                    continue
            child = Job(
                id=str(uuid.uuid4()),
                source=candidate,
                preset=job.preset,
                force=job.force,
                submitted_by=f"backfill:{job.id[:8]}",
            )
            self.queue.enqueue(child)
            queued += 1
        reason = f"backfill: {queued} queued, {fresh} already clean"
        self.queue.complete(claimed, {"status": "ok", "reason": reason})
        self._record(
            job,
            JobStatus.DONE,
            result=JobResult(status="ok", reason=reason, mode="backfill"),
        )
        log_event("backfill_expanded", job_id=job.id, root=str(job.source), queued=queued)

    def _precheck(self, claimed: ClaimedJob, job_cfg: ResolvedConfig) -> bool:
        """Worker-side existence + fingerprint checks (R9/R10). Returns True
        when the job was already completed without running the pipeline."""
        job = claimed.entry.job
        if job.source.is_dir():
            self._expand_backfill(claimed, job_cfg)
            return True
        if not job.source.is_file():
            self._complete_without_running(claimed, "ignored", "missing_source")
            return True
        if not job.force:
            wordlist = resolve_wordlist(job_cfg)
            media_type = classify(job.source, job.media_type_hint)
            skip, _plan = check_skip(job.source, media_type, cfg=job_cfg, wordlist=wordlist)
            if skip:
                self._complete_without_running(claimed, "skipped", "fingerprint_match")
                return True
        return False

    def _process(self, claimed: ClaimedJob) -> None:
        job = claimed.entry.job
        try:
            job_cfg = self._cfg_for_job(job)
        except JobValidationError as exc:
            error = JobErrorInfo(kind=type(exc).__name__, message=str(exc))
            self.queue.fail(
                claimed, {"kind": error.kind, "message": error.message}, retryable=False
            )
            self._record(job, JobStatus.FAILED, error=error)
            return
        if self._precheck(claimed, job_cfg):
            return

        stat = job.source.stat()
        stages: list[tuple[str, Stage]] = []
        for name, stage_fn in STAGE_SEQUENCE:
            if name == "publish":
                stages.append(
                    ("source_stability", _source_stability_stage(stat.st_size, stat.st_mtime))
                )
            stages.append((name, stage_fn))

        workdir = retention.workdir_root(self.cfg) / job.id
        stages_done = 0

        def on_progress(stage_name: str, ctx: PipelineContext) -> None:
            nonlocal stages_done
            stages_done += 1
            self.queue.renew_lease(claimed)
            self._record(
                job, JobStatus.RUNNING, stage=stage_name, progress=stages_done / _STAGE_COUNT
            )
            if self._on_stage is not None:
                self._on_stage(stage_name, ctx)

        ctx = PipelineContext(job=job, cfg=job_cfg)
        try:
            ctx = run_pipeline(ctx, workdir, on_progress=on_progress, stage_sequence=stages)
        except CensorrError as exc:
            retryable = not isinstance(exc, (JobValidationError, QCError))
            error = JobErrorInfo(kind=type(exc).__name__, message=str(exc))
            self.queue.fail(
                claimed, {"kind": error.kind, "message": error.message}, retryable=retryable
            )
            self._record(job, JobStatus.FAILED, error=error)
            # QCError keeps the workdir for inspection (R11); GC sweeps it later.
            if not isinstance(exc, QCError):
                shutil.rmtree(workdir, ignore_errors=True)
            return

        if ctx.outcome is not None:
            self.queue.complete(claimed, {"status": "skipped", "reason": ctx.outcome})
            self._record(
                job,
                JobStatus.DONE,
                result=JobResult(status="skipped", reason=ctx.outcome, mode=ctx.mode),
                progress=1.0,
            )
        else:
            outputs = [ctx.naming_plan.video_path] if ctx.naming_plan else []
            self.queue.complete(claimed, {"status": "ok"})
            self._record(
                job,
                JobStatus.DONE,
                result=JobResult(
                    status="ok", mode=ctx.mode, outputs=outputs, stats=stats_from_context(ctx)
                ),
                progress=1.0,
            )
        shutil.rmtree(workdir, ignore_errors=True)

    def run_once(self) -> bool:
        """Claim and process at most one job. Returns True if one was claimed."""
        self._maybe_gc()
        claimed = self.queue.claim(self.worker_id)
        if claimed is None:
            return False
        self._process(claimed)
        return True

    def run_forever(self, *, poll_interval_s: float = 5.0) -> None:
        while True:
            if not self.run_once():
                time.sleep(poll_interval_s)
