from fastapi import FastAPI

from censorr import __version__
from censorr.config.schema import ResolvedConfig
from censorr.queue.file_queue import FileJobQueue
from censorr.service.routes_jobs import router as jobs_router
from censorr.service.routes_webhooks import router as webhooks_router


def create_app(cfg: ResolvedConfig) -> FastAPI:
    """API container: config + queue init only -- it mounts no media and
    never touches FFmpeg (R8); file existence is the worker's check."""
    app = FastAPI(title="censorr", version=__version__)
    app.state.cfg = cfg
    app.state.queue = FileJobQueue(
        cfg.service.queue_path,
        max_retries=cfg.service.max_retries,
        lease_seconds=cfg.service.lease_seconds,
    )
    app.include_router(webhooks_router)
    app.include_router(jobs_router)
    return app
