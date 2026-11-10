from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text

from app.core.config import settings
from app.core.db import SessionLocal, engine, init_db
from app.models import Job
from app.routers import auth, discovery, insights, jobs, profile, resumes, tracking
from app.schemas import HealthOut

logging.basicConfig(
    level=logging.INFO if not settings.debug else logging.DEBUG,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info(
        "Started %s | db=%s | embeddings=%s | llm=%s | tasks=%s",
        settings.app_name,
        "postgresql" if not settings.is_sqlite else "sqlite",
        _embedding_backend(),
        _llm_provider(),
        _task_backend(),
    )
    yield
    from app.services import tasks

    tasks.shutdown()


app = FastAPI(
    title="JobMatch API",
    description=(
        "Resume-to-job matching with a hybrid engine: deterministic weighted "
        "scoring, embedding-based semantic similarity, and LLM-assisted "
        "extraction and explanation."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def add_timing_and_security_headers(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Response-Time-ms"] = f"{(time.perf_counter() - started) * 1000:.1f}"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    """Flatten FastAPI's validation errors into the app's error envelope."""
    fields: dict[str, str] = {}
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"] if part != "body")
        fields[location or "body"] = error["msg"]
    return JSONResponse(
        status_code=422,
        content={
            "detail": {
                "code": "validation_error",
                "message": "Some fields need attention.",
                "fields": fields,
            }
        },
    )


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "detail": {
                "code": "internal_error",
                "message": "Something went wrong on our side. Please try again.",
                "fields": {},
            }
        },
    )


for module in (auth, resumes, profile, discovery, jobs, tracking, insights):
    app.include_router(module.router, prefix=API_PREFIX)


def _embedding_backend() -> str:
    from app.services.matching.embeddings import active_backend

    return active_backend()


def _llm_provider() -> str:
    from app.services import llm

    return llm.provider_name()


def _task_backend() -> str:
    from app.services import tasks

    return tasks.backend_name()


@app.get(f"{API_PREFIX}/health", response_model=HealthOut, tags=["meta"])
def health() -> HealthOut:
    from app.services.sources.registry import all_sources

    database = "ok"
    jobs_indexed = 0
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
            jobs_indexed = int(
                db.scalar(select(func.count(Job.id)).where(Job.is_active.is_(True))) or 0
            )
    except Exception as exc:
        database = f"error: {type(exc).__name__}"

    sources = all_sources()
    return HealthOut(
        status="ok" if database == "ok" else "degraded",
        database=database,
        embedding_backend=_embedding_backend(),
        llm_provider=_llm_provider(),
        task_backend=_task_backend(),
        sources_live=[s.key for s in sources if s.availability().available],
        sources_unavailable=[s.key for s in sources if not s.availability().available],
        jobs_indexed=jobs_indexed,
    )


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {
        "name": settings.app_name,
        "docs": "/docs",
        "health": f"{API_PREFIX}/health",
    }
