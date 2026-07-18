from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, Query, Request

from censorr.config.schema import ResolvedConfig
from censorr.naming.models import MediaTypeHint
from censorr.pipeline.job import Job
from censorr.queue.file_queue import FileJobQueue
from censorr.service.arr_models import RadarrWebhookPayload, SonarrWebhookPayload
from censorr.service.logging import log_event

router = APIRouter()


def _check_secret(cfg: ResolvedConfig, token: str | None, header_secret: str | None) -> None:
    """Shared secret accepted via ?token= (native-Arr-compatible) or the
    X-Webhook-Secret header. Only enforced when configured."""
    if not cfg.service.secret:
        return
    if token == cfg.service.secret or header_secret == cfg.service.secret:
        return
    raise HTTPException(status_code=403, detail="bad token")


def map_path(cfg: ResolvedConfig, path: str) -> str | None:
    """Prefix-map an Arr-reported path into the worker's view (pure string
    logic -- the API has no media mounts). An empty map passes paths
    through unchanged (zero-config); a non-empty map requires a matching
    prefix, else None (-> ignored/unmapped_path). Longest prefix wins."""
    if not cfg.service.path_map:
        return path
    best: tuple[str, str] | None = None
    for prefix, replacement in cfg.service.path_map.items():
        if path.startswith(prefix) and (best is None or len(prefix) > len(best[0])):
            best = (prefix, replacement)
    if best is None:
        return None
    return best[1] + path[len(best[0]) :]


def tag_gate_passes(cfg: ResolvedConfig, tags: list[str]) -> bool:
    """Q18: only Arr items carrying one of service.require_tags produce
    censored versions (default ["censorr"]). Empty require_tags disables
    gating. CLI and POST /jobs are never gated."""
    if not cfg.service.require_tags:
        return True
    return any(tag in cfg.service.require_tags for tag in tags)


def resolve_preset(
    cfg: ResolvedConfig, query_preset: str | None, tags: list[str], media_default: str
) -> str | None:
    """Preset precedence (R8): query param > Arr tag mapping > media-type
    default. The media-type default only applies when that preset is
    actually defined in config."""
    if query_preset:
        return query_preset
    for tag in tags:
        if tag in cfg.arr_tag_presets:
            return cfg.arr_tag_presets[tag]
    if media_default in cfg.preset_names:
        return media_default
    return None


def _enqueue(
    request: Request,
    *,
    source: str,
    preset: str | None,
    hint: MediaTypeHint,
    is_upgrade: bool,
    deleted_files: list[str],
    submitted_by: str,
) -> dict[str, str]:
    cfg: ResolvedConfig = request.app.state.cfg
    queue: FileJobQueue = request.app.state.queue

    mapped = map_path(cfg, source)
    if mapped is None:
        log_event("webhook_ignored", reason="unmapped_path", path=source)
        return {"status": "ignored", "reason": "unmapped_path"}

    mapped_deleted = [m for f in deleted_files if (m := map_path(cfg, f)) is not None]
    job = Job(
        id=str(uuid4()),
        source=Path(mapped),
        preset=preset,
        media_type_hint=hint,
        is_upgrade=is_upgrade,
        deleted_files=[Path(p) for p in mapped_deleted],
        submitted_by=submitted_by,
    )
    job_id = queue.enqueue(job)
    log_event("job_enqueued", job_id=job_id, source=mapped, preset=preset, upgrade=is_upgrade)
    return {"status": "queued", "job_id": job_id}


@router.post("/webhook/radarr", status_code=202)
def radarr_webhook(
    payload: RadarrWebhookPayload,
    request: Request,
    preset: str | None = Query(default=None),
    token: str | None = Query(default=None),
    x_webhook_secret: str | None = Header(default=None),
) -> dict[str, str]:
    cfg: ResolvedConfig = request.app.state.cfg
    _check_secret(cfg, token, x_webhook_secret)

    if payload.event_type == "Test":
        return {"status": "ok"}
    if payload.event_type != "Download":
        return {"status": "ignored", "reason": "unhandled_event"}
    if payload.movie_file is None or not payload.movie_file.path:
        return {"status": "ignored", "reason": "missing_path"}

    movie_tags = payload.movie.tags if payload.movie else []
    if not tag_gate_passes(cfg, movie_tags):
        log_event("webhook_ignored", reason="not_tagged", path=payload.movie_file.path)
        return {"status": "ignored", "reason": "not_tagged"}

    resolved = resolve_preset(cfg, preset, movie_tags, media_default="movies")
    return _enqueue(
        request,
        source=payload.movie_file.path,
        preset=resolved,
        hint=MediaTypeHint.MOVIE,
        is_upgrade=payload.is_upgrade,
        deleted_files=[f.path for f in payload.deleted_files if f.path],
        submitted_by="webhook:radarr",
    )


@router.post("/webhook/sonarr", status_code=202)
def sonarr_webhook(
    payload: SonarrWebhookPayload,
    request: Request,
    preset: str | None = Query(default=None),
    token: str | None = Query(default=None),
    x_webhook_secret: str | None = Header(default=None),
) -> dict[str, str]:
    cfg: ResolvedConfig = request.app.state.cfg
    _check_secret(cfg, token, x_webhook_secret)

    if payload.event_type == "Test":
        return {"status": "ok"}
    if payload.event_type != "Download":
        return {"status": "ignored", "reason": "unhandled_event"}
    if payload.episode_file is None or not payload.episode_file.path:
        return {"status": "ignored", "reason": "missing_path"}

    series_tags = payload.series.tags if payload.series else []
    if not tag_gate_passes(cfg, series_tags):
        log_event("webhook_ignored", reason="not_tagged", path=payload.episode_file.path)
        return {"status": "ignored", "reason": "not_tagged"}

    resolved = resolve_preset(cfg, preset, series_tags, media_default="tv")
    return _enqueue(
        request,
        source=payload.episode_file.path,
        preset=resolved,
        hint=MediaTypeHint.EPISODE,
        is_upgrade=payload.is_upgrade,
        deleted_files=[f.path for f in payload.deleted_files if f.path],
        submitted_by="webhook:sonarr",
    )
