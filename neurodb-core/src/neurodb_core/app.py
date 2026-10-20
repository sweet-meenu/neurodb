from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from neurodb_core.container import AppContainer
from neurodb_core.controlplane.project_data import router as project_data_router
from neurodb_core.controlplane.router import router as control_router
from neurodb_core.dataplane.router import router as data_router

# Explicit path (not a bare load_dotenv()) so this finds neurodb-core/.env
# regardless of the process's working directory — matters since run.ps1,
# `uv run` from this directory, and `uv run` from elsewhere via --directory
# would otherwise all resolve a bare load_dotenv()'s cwd-relative search
# differently. A no-op if the file doesn't exist (e.g. CI, fresh clones).
load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def create_app(data_root: Path | str | None = None) -> FastAPI:
    root = Path(data_root or os.environ.get("NEURODB_DATA_ROOT", "./neurodb_data"))
    host = os.environ.get("NEURODB_HOST", "localhost:8000")
    cors_origins_raw = os.environ.get("NEURODB_CORS_ORIGINS", "*")
    cors_origins = [o.strip() for o in cors_origins_raw.split(",")] if cors_origins_raw != "*" else ["*"]

    app = FastAPI(title="NeuroDB", version="0.1.0", description="AI Knowledge Lake — Vector Database-as-a-Service")
    app.state.container = AppContainer(root, host=host)

    # Middleware order matters here. Starlette builds the stack as
    # [ServerErrorMiddleware] + user_middleware + [ExceptionMiddleware], with
    # add_middleware() *prepending* to user_middleware — so whichever of these
    # two is added last ends up outermost. A handler registered via
    # @app.exception_handler(Exception) gets special-cased into
    # ServerErrorMiddleware itself (see Starlette's build_middleware_stack),
    # which sits *outside* CORSMiddleware no matter what it returns — so that
    # approach can never carry CORS headers. Catching exceptions in a plain
    # middleware placed *inside* CORSMiddleware is what actually works: add it
    # first (so CORS, added second, ends up outer and wraps its responses).
    @app.middleware("http")
    async def catch_unhandled_exceptions(request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as exc:  # noqa: BLE001 - last-resort safety net, re-raising would skip CORS entirely
            return JSONResponse(status_code=500, content={"detail": f"Internal server error: {exc}"})

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        # No cookie-based session anywhere (session JWTs and project API keys are
        # sent as explicit headers, never auto-attached by the browser), so
        # credentialed CORS isn't needed — this lets allow_origins default to "*"
        # without the browser-enforced "credentials + wildcard origin" conflict,
        # which avoids origin-mismatch breakage (e.g. localhost vs 127.0.0.1, or
        # a dev server picking a different port) for a tool that only ever runs
        # locally/self-hosted anyway.
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(control_router, prefix="/api/control", tags=["control-plane"])
    app.include_router(
        project_data_router, prefix="/api/control/projects/{project_id}/data", tags=["dashboard-data"]
    )
    app.include_router(data_router, prefix="/api/data/v1", tags=["data-plane"])

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
