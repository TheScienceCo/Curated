"""FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import dashboard, decisions, jobs, profile, resumes
from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import configure_logging, get_logger
from app.db.session import create_all, init_engine
from app.llm.factory import get_provider

configure_logging(settings.log_level)
logger = get_logger(__name__)

DESCRIPTION = """\
Ingests recruiter messages and job descriptions, extracts structured data,
scores each opportunity against a configurable candidate profile across seven
transparent dimensions, identifies missing information, and drafts a reply for
**human approval**.

Nothing is ever sent automatically. Every outbound message requires an explicit
human action outside this system.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_engine()
    create_all()
    provider = get_provider()
    logger.info(
        "Job Intelligence Agent starting (env=%s, llm=%s, available=%s)",
        settings.app_env,
        provider.name,
        provider.available,
    )
    if settings.seed_on_startup:
        try:
            from app.db.seed import seed_if_empty

            seed_if_empty()
        except Exception as exc:  # noqa: BLE001 - seeding must never block startup
            logger.warning("Seeding skipped: %s", exc)
    yield
    logger.info("Job Intelligence Agent shutting down")


app = FastAPI(
    title="Job Intelligence Agent",
    description=DESCRIPTION,
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    logger.warning("%s on %s: %s", exc.code, request.url.path, exc.message)
    return JSONResponse(status_code=exc.status_code, content=exc.to_payload())


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "Request body failed validation.",
                "details": {"errors": exc.errors()},
            }
        },
    )


@app.get("/health", tags=["meta"])
def health() -> dict:
    """Liveness plus a view of how the system is configured."""
    provider = get_provider()
    return {
        "status": "ok",
        "version": app.version,
        "environment": settings.app_env,
        "llm_provider": provider.name,
        "llm_available": provider.available,
        "embeddings_enabled": settings.embeddings_enabled,
        "extraction_mode": "llm+rules" if provider.available else "rules-only (deterministic)",
    }


app.include_router(profile.router)
app.include_router(resumes.router)
app.include_router(jobs.router)
app.include_router(decisions.router)
app.include_router(dashboard.router)
