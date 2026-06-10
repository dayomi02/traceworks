import logging
import logging.config
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import (
    _errors,
    alerts,
    auth,
    dashboard,
    persons,
    projects,
    recommendations,
    reports,
    rfp,
    tasks,
    webhooks,
)
from app.config import get_settings

_STATIC_DIR = Path(__file__).parent.parent.parent / "demo"

logging.config.dictConfig({
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
        },
    },
    "loggers": {
        "app": {"level": "INFO", "handlers": ["console"], "propagate": False},
    },
    "root": {"level": "WARNING", "handlers": ["console"]},
})


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Startup hook (DB pools, Fuseki health check, etc.) — wire later.
    yield
    # Shutdown hook — release resources here.


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Traceworks API",
        version="0.1.0",
        description="Ontology-based AI project management system",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "env": settings.ENV}

    app.include_router(auth.router)
    app.include_router(dashboard.router)
    app.include_router(webhooks.router)
    app.include_router(projects.router)
    app.include_router(tasks.router)
    app.include_router(persons.router)
    app.include_router(recommendations.router)
    app.include_router(alerts.router)
    app.include_router(reports.router)
    app.include_router(rfp.router)

    _errors.install(app)

    # 데모 UI: http://localhost:8000/demo/
    if _STATIC_DIR.exists():
        app.mount(
            "/demo",
            StaticFiles(directory=_STATIC_DIR, html=True),
            name="demo",
        )

    return app


app = create_app()
