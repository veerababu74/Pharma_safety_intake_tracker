"""FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.auth.seed import seed_users
from app.core.config import get_settings
from app.core.container import get_container
from app.core.logging import get_logger, setup_logging
from app.db.session import db_manager
from app.middleware.audit_middleware import AuditLogMiddleware
from app.services.document_service import DocumentService


@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_logging()
    logger = get_logger("startup")
    settings = get_settings()
    weak_secrets = {
        "dev-secret-change-me-novacure-training",
        "change-me-in-production-use-long-random-string",
    }
    if settings.app_env.lower() not in {"development", "dev", "test", "local"}:
        if settings.secret_key in weak_secrets or len(settings.secret_key) < 24:
            raise RuntimeError(
                "Refusing to start: set a strong SECRET_KEY for non-development APP_ENV."
            )
    elif settings.secret_key in weak_secrets:
        logger.warning("weak_secret_key", hint="Change SECRET_KEY before any shared/production deploy")
    db_manager.init()
    seed_users()
    # warm providers
    get_container()
    DocumentService()._rebuild_bm25_index()
    logger.info(
        "app_started",
        env=settings.app_env,
        embedding=settings.embedding_provider,
        vector=settings.vector_store_provider,
        llm=settings.llm_provider,
        llm_roles=settings.llm_roles_summary(),
        tracing=settings.tracing_mode,
    )
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(AuditLogMiddleware)
    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()
if __name__ == "__main__":
    import uvicorn
    app=create_app()

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
