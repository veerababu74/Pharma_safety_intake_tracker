from fastapi import APIRouter, Depends

from app.auth.deps import require_permission
from app.core.config import get_settings
from app.db.models.core import User

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/providers")
def providers(user: User = Depends(require_permission("rag:view"))):
    s = get_settings()
    return {
        "embedding_provider": s.embedding_provider,
        "embedding_model_name": s.embedding_model_name,
        "vector_store_provider": s.vector_store_provider,
        "llm_provider": s.llm_provider,
        "llm_model_name": s.llm_model_name,
        "llm_roles": s.llm_roles_summary(),
        "storage_provider": s.storage_provider,
        "tracing_mode": s.tracing_mode,
    }
