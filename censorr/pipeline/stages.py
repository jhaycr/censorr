import errno
import hashlib
import os
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from censorr.audio import qc as audio_qc
from censorr.audio.windows import AudioSettings, EntrySpanProvider
from censorr.config.schema import ResolvedConfig
from censorr.detect.matcher import Matcher
from censorr.media.ffmpeg import RemuxPlan, extract_subtitle_stream, resolve_audio_codec
from censorr.media.ffmpeg import remux as ffmpeg_remux
from censorr.media.probe import probe as probe_media
from censorr.naming.models import MediaType
from censorr.naming.plex import classify, plan_names
from censorr.pipeline.context import PipelineContext, QCReport
from censorr.pipeline.errors import JobValidationError, QCError, TransientError
from censorr.pipeline.fingerprint import fingerprint_for_source, resolve_wordlist
from censorr.pipeline.job import JobRecord, JobResult, JobStats, JobStatus
from censorr.subtitles import qc as subtitle_qc
from censorr.subtitles.io import load as load_subtitle_doc
from censorr.subtitles.io import save as save_subtitle_doc
from censorr.subtitles.mask import mask_entries
from censorr.subtitles.select import select_tracks

DURATION_PARITY_TOLERANCE_S = 2.0


def probe(ctx: PipelineContext, workdir: Path) -> PipelineContext:
    media_info = probe_media(ctx.job.source)
    return ctx.model_copy(update={"media_info": media_info})


def select_tracks_stage(ctx: PipelineContext, workdir: Path) -> PipelineContext:
    assert ctx.media_info is not None, "select_tracks requires media_info from probe"
    selection = select_tracks(
        ctx.media_info,
        language=ctx.cfg.subtitles.language,
        exclude_titles=ctx.cfg.subtitles.exclude_titles,
    )
    if not selection.language_mismatch:
        return ctx.model_copy(update={"selection": selection})
    if ctx.cfg.subtitles.allow_language_mismatch:
        return ctx.model_copy(update={"selection": selection, "mode": "subtitles_only"})
    return ctx.model_copy(update={"selection": selection, "outcome": "language_mismatch"})


def _find_sidecar(source: Path, language: str) -> Path | None:
    for candidate in (source.with_suffix(f".{language}.srt"), source.with_suffix(".srt")):
        if candidate.is_file():
            return candidate
    return None


def acquire_subtitles(ctx: PipelineContext, workdir: Path) -> PipelineContext:
    if ctx.outcome is not None:
        return ctx
    assert ctx.selection is not None, "acquire_subtitles requires a selection"

    if ctx.selection.subtitle_stream is not None:
        extracted = extract_subtitle_stream(ctx.job.source, ctx.selection.subtitle_stream, workdir)
        doc = load_subtitle_doc(extracted)
        return ctx.model_copy(update={"subtitle_doc": doc})

    sidecar = _find_sidecar(ctx.job.source, ctx.selection.subtitle_lang)
    if sidecar is not None:
        return ctx.model_copy(update={"subtitle_doc": load_subtitle_doc(sidecar)})

    if ctx.cfg.behavior.fail_on_no_subtitles:
        raise JobValidationError(f"no usable text subtitles found for {ctx.job.source}")
    return ctx.model_copy(update={"outcome": "no_text_subtitles"})


def detect(ctx: PipelineContext, workdir: Path) -> PipelineContext:
    if ctx.outcome is not None:
        return ctx
    assert ctx.subtitle_doc is not None, "detect requires a subtitle_doc from acquire_subtitles"

    wordlist = resolve_wordlist(ctx.cfg)
    matcher = Matcher(wordlist, similarity_threshold=ctx.cfg.detect.fuzzy_threshold)

    matches = {
        entry.index: found
        for entry in ctx.subtitle_doc.entries
        if (found := matcher.find_matches(entry.plaintext))
    }

    if matches or ctx.mode != "full":
        return ctx.model_copy(update={"matches": matches, "mode": ctx.mode})

    # R16 zero-match handling: TV publishes a stream-copy remux into the
    # clean root (library stays complete); movies skip by default (no
    # pointless full-size edition duplicate).
    media_type = classify(ctx.job.source, ctx.job.media_type_hint)
    policy = (
        ctx.cfg.behavior.on_clean_movie
        if media_type == MediaType.MOVIE
        else ctx.cfg.behavior.on_clean_tv
    )
    if policy == "skip":
        return ctx.model_copy(
            update={"matches": matches, "mode": "clean", "outcome": "skipped_clean"}
        )
    return ctx.model_copy(update={"matches": matches, "mode": "clean"})


def plan_windows(ctx: PipelineContext, workdir: Path) -> PipelineContext:
    if ctx.outcome is not None or ctx.mode in ("clean", "subtitles_only"):
        return ctx
    assert ctx.subtitle_doc is not None, "plan_windows requires a subtitle_doc"

    settings = AudioSettings(buffer_s=ctx.cfg.detect.buffer_s)
    windows = EntrySpanProvider().windows(
        ctx.subtitle_doc.entries, ctx.matches, ctx.job.source, settings
    )
    return ctx.model_copy(update={"windows": windows})


def mask_subtitles_stage(ctx: PipelineContext, workdir: Path) -> PipelineContext:
    if ctx.outcome is not None or ctx.subtitle_doc is None:
        return ctx
    masked_doc, captions_doc = mask_entries(ctx.subtitle_doc, ctx.matches)
    if ctx.mode == "subtitles_only":
        # R16: muting windows derived from a translation against foreign
        # speech would be nonsense -- never show a mute caption here.
        captions_doc = None
    return ctx.model_copy(update={"masked_doc": masked_doc, "captions_doc": captions_doc})


def plan_names_stage(ctx: PipelineContext, workdir: Path) -> PipelineContext:
    if ctx.outcome is not None:
        return ctx
    media_type = classify(ctx.job.source, ctx.job.media_type_hint)
    naming_plan = plan_names(
        ctx.job.source, media_type, ctx.cfg.naming, language=ctx.cfg.subtitles.language
    )
    return ctx.model_copy(update={"naming_plan": naming_plan})


def remux_stage(ctx: PipelineContext, workdir: Path) -> PipelineContext:
    if ctx.outcome is not None:
        return ctx
    assert ctx.media_info is not None, "remux requires media_info from probe"
    assert ctx.selection is not None, "remux requires a selection"
    assert ctx.masked_doc is not None, "remux requires a masked_doc"
    assert ctx.naming_plan is not None, "remux requires a naming_plan"

    masked_sub_path = workdir / "masked.srt"
    save_subtitle_doc(ctx.masked_doc, masked_sub_path)

    captions_sub_path: Path | None = None
    if ctx.captions_doc is not None:
        captions_sub_path = workdir / "captions.srt"
        save_subtitle_doc(ctx.captions_doc, captions_sub_path)

    video_stream = ctx.media_info.video_streams()[0].index
    audio_info = next(
        s for s in ctx.media_info.audio_streams() if s.index == ctx.selection.audio_stream
    )

    audio_mode: Literal["mute_encode", "copy"] = (
        "copy" if ctx.mode in ("clean", "subtitles_only") else "mute_encode"
    )
    audio_codec = audio_bitrate = None
    if audio_mode == "mute_encode":
        audio_codec, audio_bitrate = resolve_audio_codec(
            audio_info.codec_name,
            audio_info.channels or 2,
            ctx.cfg.audio,
            source_bitrate=audio_info.bit_rate,
        )

    wordlist = resolve_wordlist(ctx.cfg)
    fingerprint = fingerprint_for_source(ctx.job.source, cfg=ctx.cfg, wordlist=wordlist)

    plan = RemuxPlan(
        source=ctx.job.source,
        temp_output=workdir / "output.mkv",
        video_stream=video_stream,
        audio_stream=ctx.selection.audio_stream,
        audio_mode=audio_mode,
        audio_codec=audio_codec,
        audio_bitrate=audio_bitrate,
        windows=ctx.windows,
        masked_sub=masked_sub_path,
        captions_sub=captions_sub_path,
        stream_titles=ctx.naming_plan.track_titles,
        language=ctx.selection.subtitle_lang or ctx.cfg.subtitles.language,
        fingerprint=fingerprint,
    )
    temp_output = ffmpeg_remux(plan)
    return ctx.model_copy(update={"temp_output": temp_output})


def verify_stage(ctx: PipelineContext, workdir: Path) -> PipelineContext:
    """R14 symmetric QC: guards against under- *and* over-censoring.
    Audio QC is skipped in clean/subtitles_only modes (nothing was muted).
    Raises QCError unless the matching continue_on_* flag bypasses it.
    """
    if ctx.outcome is not None:
        return ctx
    assert ctx.temp_output is not None, "verify requires a temp_output from remux"
    assert ctx.subtitle_doc is not None, "verify requires a subtitle_doc"
    assert ctx.masked_doc is not None, "verify requires a masked_doc"
    assert ctx.media_info is not None, "verify requires media_info"

    wordlist = resolve_wordlist(ctx.cfg)
    matcher = Matcher(wordlist, similarity_threshold=ctx.cfg.detect.fuzzy_threshold)
    sub_result = subtitle_qc.audit(ctx.subtitle_doc, ctx.masked_doc, ctx.matches, matcher)

    total_entries = len(ctx.subtitle_doc.entries)
    matched_entry_ratio = len(ctx.matches) / total_entries if total_entries else 0.0

    warnings: list[str] = []
    if matched_entry_ratio > ctx.cfg.qc.warn_matched_entry_ratio:
        warnings.append(
            f"matched-entry ratio {matched_entry_ratio:.2%} exceeds warn threshold "
            f"{ctx.cfg.qc.warn_matched_entry_ratio:.2%}"
        )
    if sub_result.masked_entry_ratio > ctx.cfg.qc.warn_masked_entry_ratio:
        warnings.append(
            f"masked-entry ratio {sub_result.masked_entry_ratio:.2%} exceeds warn threshold "
            f"{ctx.cfg.qc.warn_masked_entry_ratio:.2%}"
        )

    audio_result: audio_qc.AudioQCResult | None = None
    if ctx.mode == "full":
        audio_result = audio_qc.audit(
            ctx.temp_output,
            ctx.windows,
            ctx.media_info.duration_s,
            audio_min_drop_db=ctx.cfg.qc.audio_min_drop_db,
            max_mute_ratio=ctx.cfg.qc.max_mute_ratio,
            max_window_s=ctx.cfg.qc.max_window_s,
        )

    output_duration = probe_media(ctx.temp_output).duration_s
    duration_delta_s = abs(output_duration - ctx.media_info.duration_s)
    duration_violation = duration_delta_s > DURATION_PARITY_TOLERANCE_S

    subtitle_hard_fail = (
        bool(sub_result.violations) and not ctx.cfg.qc.continue_on_subtitle_qc_fail
    )
    audio_hard_fail = (
        bool(audio_result and audio_result.violations) and not ctx.cfg.qc.continue_on_audio_qc_fail
    )
    passed = not (subtitle_hard_fail or audio_hard_fail or duration_violation)

    all_messages = list(warnings)
    all_messages += sub_result.violations
    if audio_result is not None:
        all_messages += audio_result.violations
    if duration_violation:
        all_messages.append(
            f"output duration diverged from source by {duration_delta_s:.2f}s "
            f"(tolerance {DURATION_PARITY_TOLERANCE_S:.2f}s)"
        )

    report = QCReport(
        subtitle_residuals=sub_result.residual_matches,
        audio_windows=audio_result.window_measurements if audio_result else [],
        mute_ratio=audio_result.mute_ratio if audio_result else 0.0,
        max_window_s=audio_result.max_window_s if audio_result else 0.0,
        matched_entry_ratio=matched_entry_ratio,
        masked_entry_ratio=sub_result.masked_entry_ratio,
        masked_words=sub_result.masked_words,
        control_audio_ok=audio_result.control_audio_ok if audio_result else True,
        duration_delta_s=duration_delta_s,
        unmasked_text_identical=sub_result.unmasked_text_identical,
        passed=passed,
        warnings=all_messages,
    )
    (workdir / "qc_report.json").write_text(report.model_dump_json(indent=2))

    if not passed:
        reason = "; ".join(all_messages) or "see qc_report.json"
        raise QCError(f"QC failed for {ctx.job.source}: {reason}")

    return ctx.model_copy(update={"qc_report": report})


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_move(source: Path, dest: Path) -> None:
    """Rename when possible (atomic, same filesystem); otherwise
    copy+SHA256-verify+delete (v1's FinalDestinationManager semantics).
    Any I/O failure in the copy path is transient (destination filesystem
    hiccup -- e.g. a network mount) and must never surface as a raw
    traceback: the queue retries transients."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(source, dest)
        return
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise TransientError(f"failed to move {source} to {dest}: {exc}") from exc

    tmp_dest = dest.with_name(dest.name + ".part")
    try:
        shutil.copy2(source, tmp_dest)
        if _sha256(tmp_dest) != _sha256(source):
            raise TransientError(f"checksum mismatch copying {source} to {dest}")
        os.replace(tmp_dest, dest)
    except OSError as exc:
        raise TransientError(f"failed to copy {source} to {dest}: {exc}") from exc
    finally:
        tmp_dest.unlink(missing_ok=True)
    source.unlink()


def _delete_superseded_outputs(ctx: PipelineContext) -> list[Path]:
    """R10: an Arr upgrade's deletedFiles[] are run through plan_names to
    delete the superseded clean outputs during publish."""
    deleted: list[Path] = []
    if not ctx.job.deleted_files:
        return deleted
    media_type = classify(ctx.job.source, ctx.job.media_type_hint)
    for deleted_source in ctx.job.deleted_files:
        plan = plan_names(
            deleted_source, media_type, ctx.cfg.naming, language=ctx.cfg.subtitles.language
        )
        for path in (plan.video_path, *plan.sidecar_paths):
            if path.is_file():
                path.unlink()
                deleted.append(path)
    return deleted


def _write_job_record(cfg: ResolvedConfig, record: JobRecord) -> None:
    """Best-effort: service.queue_path defaults to the container path
    (/app/queue) and won't exist on a bare host. The job record is a
    status-tracking convenience for the service/worker (Steps 13-14);
    it must never block a plain CLI publish, which promises zero-config
    operation.
    """
    try:
        records_dir = cfg.service.queue_path / "records"
        records_dir.mkdir(parents=True, exist_ok=True)
        (records_dir / f"{record.job.id}.json").write_text(record.model_dump_json(indent=2))
    except OSError as exc:
        print(f"warning: could not write job record: {exc}", file=sys.stderr)


def stats_from_context(ctx: PipelineContext) -> JobStats:
    """Censoring summary for records/CLI/UI: counts and ratios only, never
    the matched words (they live nowhere but the masked output itself)."""
    muted_seconds = sum(w.end_s - w.start_s for w in ctx.windows)
    return JobStats(
        entries_censored=len(ctx.matches),
        total_matches=sum(len(m) for m in ctx.matches.values()),
        mute_windows=len(ctx.windows),
        muted_seconds=round(muted_seconds, 2),
        mute_ratio=ctx.qc_report.mute_ratio if ctx.qc_report else 0.0,
        masked_entry_ratio=ctx.qc_report.masked_entry_ratio if ctx.qc_report else 0.0,
    )


def publish_stage(ctx: PipelineContext, workdir: Path) -> PipelineContext:
    """Atomic move temp -> final; delete superseded outputs; write the
    sidecar only when enabled (R6); write the job record. Publish is the
    last step -- a failed job never leaves partial files in the library.
    """
    if ctx.outcome is not None:
        return ctx
    assert ctx.temp_output is not None, "publish requires a temp_output from remux"
    assert ctx.naming_plan is not None, "publish requires a naming_plan"

    _delete_superseded_outputs(ctx)

    _atomic_move(ctx.temp_output, ctx.naming_plan.video_path)

    outputs = [ctx.naming_plan.video_path]
    if ctx.cfg.naming.write_sidecar and ctx.masked_doc is not None:
        for sidecar_path in ctx.naming_plan.sidecar_paths:
            save_subtitle_doc(ctx.masked_doc, sidecar_path)
            outputs.append(sidecar_path)

    wordlist = resolve_wordlist(ctx.cfg)
    fingerprint = fingerprint_for_source(ctx.job.source, cfg=ctx.cfg, wordlist=wordlist)
    now = datetime.now(UTC)
    record = JobRecord(
        job=ctx.job,
        status=JobStatus.DONE,
        result=JobResult(
            status="ok", mode=ctx.mode, outputs=outputs, stats=stats_from_context(ctx)
        ),
        stage="publish",
        progress=1.0,
        fingerprint=fingerprint,
        created_at=now,
        started_at=now,
        finished_at=now,
    )
    _write_job_record(ctx.cfg, record)

    return ctx
