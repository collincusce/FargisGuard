"""Read-only moderation dashboard (FastAPI), served in-process by uvicorn.

Fail-closed by construction (gameplan D3): ``create_app`` refuses an empty
token, every data route requires ``Authorization: Bearer <token>``, and the
default bind is loopback. With no token configured the dashboard simply is not
started. Rows are dicts, read through per-call connections (H-04, H-08).
"""

import asyncio
import logging
import secrets
from collections.abc import Callable

from fastapi import Depends, FastAPI, HTTPException, Request

from database import connect

log = logging.getLogger(__name__)


def create_app(token: str) -> FastAPI:
    if not token:
        raise ValueError("dashboard token is required; refusing to build an unauthenticated app")

    app = FastAPI(title="FargisGuard dashboard", docs_url=None, redoc_url=None)

    def require_token(request: Request) -> None:
        scheme, _, value = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not secrets.compare_digest(value.strip(), token):
            raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Bearer"})

    auth = [Depends(require_token)]

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/infractions", dependencies=auth)
    def infractions() -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                "SELECT user_id, guild_id, count FROM warnings ORDER BY count DESC, user_id"
            ).fetchall()
        return [dict(r) for r in rows]

    @app.get("/appeals", dependencies=auth)
    def appeals() -> list[dict]:
        with connect() as conn:
            rows = conn.execute("SELECT * FROM appeals ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    @app.get("/pending", dependencies=auth)
    def pending() -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                "SELECT * FROM pending_actions WHERE status='pending' ORDER BY id"
            ).fetchall()
        return [dict(r) for r in rows]

    return app


def _uvicorn_server(app: FastAPI, host: str, port: int):
    import uvicorn

    return uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="info"))


def start_dashboard(
    *,
    token: str,
    host: str,
    port: int,
    server_factory: Callable = _uvicorn_server,
) -> asyncio.Task | None:
    """Start the dashboard on the running loop, or return None when no token is set."""
    if not token:
        log.warning("DASHBOARD_TOKEN is not set; the dashboard will not be started")
        return None
    server = server_factory(create_app(token), host, port)
    log.info("dashboard listening on %s:%s", host, port)
    return asyncio.get_running_loop().create_task(server.serve(), name="fargisguard-dashboard")
