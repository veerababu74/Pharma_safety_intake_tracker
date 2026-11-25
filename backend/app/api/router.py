from fastapi import APIRouter

from app.api.routes import agent, audit, auth, observability, rag, reports, system

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(auth.router)
api_router.include_router(reports.router)
api_router.include_router(rag.router)
api_router.include_router(agent.router)
api_router.include_router(observability.router)
api_router.include_router(audit.router)
