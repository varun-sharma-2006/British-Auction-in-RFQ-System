import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import auth
from app.api.routes import authed, router, ws_router
from app.config import get_settings
from app.errors import DomainError
from app.services.closer import run_closer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    stop = asyncio.Event()
    task = asyncio.create_task(run_closer(settings.closer_interval_seconds, stop)) if settings.run_closer else None
    yield
    stop.set()
    if task:
        await task


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
app.include_router(router)
app.include_router(authed)
app.include_router(ws_router)
