from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from censorr.service.ui import UI_HTML

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
@router.get("/ui", response_class=HTMLResponse)
def ui_page() -> str:
    return UI_HTML
