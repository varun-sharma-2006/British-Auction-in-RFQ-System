import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from app.api import auth
from app.api import availability as availability_api
from app.api.routes import authed, router, ws_router
from app.config import get_settings
from app.db import SessionLocal
from app.errors import DomainError
from app.realtime import relay_from_redis
from app.services import availability
from app.services.closer import run_closer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
settings = get_settings()
log = logging.getLogger("app")


async def refresh_bloom_filters(stop: asyncio.Event) -> None:
    """Rebuild the availability Bloom filters from the database now and every few minutes."""
    def rebuild():
        with SessionLocal() as db:
            return availability.rebuild_all(db)

    while not stop.is_set():
        try:
            log.info("Bloom filters rebuilt: %s", await run_in_threadpool(rebuild))
        except Exception:
            log.exception("Bloom filter rebuild failed (checks fall back to the database)")
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=settings.bloom_rebuild_seconds)


@asynccontextmanager
async def lifespan(_: FastAPI):
    stop = asyncio.Event()
    tasks = [asyncio.create_task(refresh_bloom_filters(stop))]
    if settings.run_closer:
        tasks.append(asyncio.create_task(run_closer(settings.closer_interval_seconds, stop)))
    if settings.redis_url:
        tasks.append(asyncio.create_task(relay_from_redis(stop)))
    yield
    stop.set()
    await asyncio.gather(*tasks)


app = FastAPI(
    title="British Auction RFQ API",
    version="1.0.0",
    description="RFQ system with British-auction bidding: automatic time extensions, "
                "forced close and a full activity log.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware, allow_origins=settings.cors_origin_list, allow_methods=["*"], allow_headers=["*"],
)


@app.exception_handler(DomainError)
async def domain_error_handler(_: Request, exc: DomainError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError):
    # Flatten pydantic's errors into readable sentences the UI can show as-is.
    messages = []
    for err in exc.errors():
        field = ".".join(str(p) for p in err["loc"] if p != "body")
        msg = err["msg"].removeprefix("Value error, ")
        messages.append(f"{field}: {msg}" if field and err["type"] != "value_error" else msg)
    fields = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": "; ".join(messages), "errors": fields})


app.include_router(auth.router)
app.include_router(availability_api.router)
app.include_router(router)
app.include_router(authed)
app.include_router(ws_router)


def mount_frontend(dist: Path) -> None:
    """Serve the built React app: real files when they exist, index.html for client-side routes."""
    root = dist.resolve()
    app.mount("/assets", StaticFiles(directory=root / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith(("api/", "ws")):
            raise HTTPException(404)
        candidate = (root / path).resolve()
        if path and candidate.is_file() and root in candidate.parents:   # no path traversal out of dist
            return FileResponse(candidate)
        return FileResponse(root / "index.html")


if settings.frontend_dist and (Path(settings.frontend_dist) / "index.html").exists():
    mount_frontend(Path(settings.frontend_dist))
