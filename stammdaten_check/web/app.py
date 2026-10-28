"""Web API and dashboard.

Start with:  stammdaten-check serve
API docs:    http://localhost:8000/docs
"""
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .models import ERRORS
from .routes import router
from .store import BadInput, NotFound, Store

STATIC = Path(__file__).parent / "static"


def _error(status, code):
    async def handler(_: Request, e: Exception):
        return JSONResponse(status_code=status, content={"error": {"code": code, "message": str(e)}})
    return handler


def create_app(home=None, api_key=None):
    app = FastAPI(
        title="stammdaten-check",
        version="0.3.0",
        description="Master data readiness checks for an SAP ECC to S/4HANA move. "
                    "Upload table extracts, work through the findings, check single partners.",
        contact={"name": "Abdallah Aneed", "url": "https://github.com/abdallahaneed/stammdaten-check"},
        license_info={"name": "MIT"},
        servers=[{"url": "http://localhost:8000", "description": "local"}],
        responses=ERRORS,
    )
    app.state.store = Store(home or os.environ.get("STAMMDATEN_HOME", "var"))
    app.state.api_key = api_key if api_key is not None else os.environ.get("STAMMDATEN_API_KEY", "")

    app.add_exception_handler(NotFound, _error(404, "not_found"))
    app.add_exception_handler(BadInput, _error(422, "invalid_input"))
    app.add_exception_handler(PermissionError, _error(401, "unauthorized"))

    app.include_router(router)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html")

    return app
