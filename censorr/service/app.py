from pathlib import Path

from fastapi import FastAPI

from censorr import __version__
from censorr.config.schema import ResolvedConfig
from censorr.queue.file_queue import FileJobQueue
from censorr.service.routes_browse import router as browse_router
from censorr.service.routes_jobs import router as jobs_router
from censorr.service.routes_ui import router as ui_router
from censorr.service.routes_webhooks import router as webhooks_router


def create_app(cfg: ResolvedConfig, config_path: Path | None = None) -> FastAPI:
    """API container: config + queue init; sources mounted read-only for
    the UI's path browser (Q19) but never written -- clean roots and all
    media writes belong to the worker alone, and FFmpeg never runs here
    (R8); file existence is the worker's check. `config_path` enables the
    UI's config editor; None disables it."""
    app = FastAPI(title="censorr", version=__version__)
    app.state.cfg = cfg
    app.state.config_path = config_path
    app.state.queue = FileJobQueue(
        cfg.service.queue_path,
        max_retries=cfg.service.max_retries,
        lease_seconds=cfg.service.lease_seconds,
    )
    app.include_router(webhooks_router)
    app.include_router(jobs_router)
    app.include_router(browse_router)
    app.include_router(ui_router)
    return app
