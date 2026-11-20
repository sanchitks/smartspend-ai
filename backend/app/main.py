"""SmartSpend AI API."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.ai.providers import get_provider
from app.api import ai, analytics, auth, planning, records
from app.core import errors
from app.core.config import get_settings
from app.core.security import RequestContextMiddleware, configure_logging
from app.database import SessionLocal, engine
from app.services.categories import seed_defaults

settings = get_settings()
configure_logging(settings.log_level)
log = logging.getLogger("smartspend")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.check()
    if engine.dialect.name == "sqlite":
        # Local quick-start: create the schema directly. PostgreSQL deployments run `alembic upgrade head`.
        from app.database import Base

        Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_defaults(db)
    p = get_provider()
    log.info("started", extra={"provider": p.name, "model": p.model})
    yield


app = FastAPI(
    title="SmartSpend AI API",
    version="1.0.0",
    description="Personal finance and budgeting assistant. General budgeting help, not regulated financial advice.",
    lifespan=lifespan,
    openapi_url="/api/v1/openapi.json",
    docs_url="/docs",
    redoc_url=None,
)
errors.install(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,  # bearer tokens, no cookies
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID", "Retry-After", "Content-Disposition"],
    max_age=600,
)
app.add_middleware(RequestContextMiddleware)

for module in (auth, records, planning, analytics, ai):
    app.include_router(module.router, prefix="/api/v1")


@app.get("/api/v1/health", tags=["health"])
def health():
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
    p = get_provider()
    return {"status": "ok", "ai_provider": p.name, "ai_live": p.is_live}
