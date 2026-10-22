"""FixFlow API entry point:  uvicorn app.main:app --reload"""
import logging
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from .config import settings
from .database import engine
from .routers import (
    admin, analytics, assets, auth, catalog, locations, notifications, predictions, reports, sla, technicians,
    users,
)
from .routers import requests as requests_router
from .scheduler import start_scheduler, stop_scheduler


def _configure_logging() -> None:
    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        fh = RotatingFileHandler(settings.LOG_DIR / "fixflow.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
    if not any(type(h) is logging.StreamHandler for h in root.handlers):
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(sh)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)


_configure_logging()
log = logging.getLogger("fixflow")


@asynccontextmanager
async def lifespan(_: FastAPI):
    log.info("FixFlow API starting")
    if settings.SCHEDULER_ENABLED:
        start_scheduler()
    yield
    stop_scheduler()
    log.info("FixFlow API stopped")


app = FastAPI(
    title="FixFlow API",
    description="Intelligent maintenance management & failure prediction",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


@app.exception_handler(IntegrityError)
async def integrity_error_handler(_: Request, exc: IntegrityError):
    log.warning("Integrity error: %s", exc.orig)
    return JSONResponse(status_code=409, content={"detail": "That conflicts with existing data (duplicate or "
                                                            "still referenced). Check the values and try again."})


@app.exception_handler(Exception)
async def unhandled_error_handler(_: Request, exc: Exception):
    log.exception("Unhandled error")
    return JSONResponse(status_code=500, content={"detail": "Something went wrong on the server. "
                                                            "The error has been logged."})


for r in (auth, users, locations, catalog, assets, requests_router, technicians, sla, analytics, reports,
          predictions, notifications, admin):
    app.include_router(r.router)

app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")


@app.get("/api/health", tags=["System"])
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "database": db_ok}
