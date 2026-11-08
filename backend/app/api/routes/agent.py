"""LangGraph agent + per-user chat sessions + HITL resume APIs."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.deps import require_permission
from app.db.models.core import User
from app.modules.agents.graph import LangGraphAgentService
from app.modules.agents.tool_backend import (
    set_runtime_tool_backend,
    tool_backend_status,
)
from app.services.chat_service import ChatHistoryService

router = APIRouter(prefix="/agent", tags=["agent"])
chat_svc = ChatHistoryService()
agent_svc = LangGraphAgentService()


class CreateSessionRequest(BaseModel):
    title: str | None = None


class RenameSessionRequest(BaseModel):
    title: str


class AgentChatRequest(BaseModel):
    session_id: str
    message: str
    tool_args: dict[str, Any] | None = Field(default=None)


class HitlResolveRequest(BaseModel):
    approved: bool
    note: str | None = None


class AgentToolBackendRequest(BaseModel):
    tool_backend: Literal["local", "mcp"]


@router.get("/config")
def get_agent_config(user: User = Depends(require_permission("agent:chat"))):
    """Current tool backend: local tools.py vs FastMCP (mcp_server)."""
    return tool_backend_status()


@router.put("/config")
def put_agent_config(
    payload: AgentToolBackendRequest,
    user: User = Depends(require_permission("agent:chat")),
):
    """Runtime override for which tool layer the LangGraph agent uses."""
    try:
        set_runtime_tool_backend(payload.tool_backend)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return tool_backend_status()


@router.post("/sessions")
def create_session(
    payload: CreateSessionRequest,
    user: User = Depends(require_permission("agent:chat")),
):
    return chat_svc.create_session(user.username, title=payload.title, session_kind="agent")


@router.get("/sessions")
def list_sessions(user: User = Depends(require_permission("agent:chat"))):
    return chat_svc.list_sessions(user.username, session_kind="agent")


@router.get("/sessions/{session_id}")
def get_session(session_id: str, user: User = Depends(require_permission("agent:chat"))):
    try:
        return chat_svc.get_session(session_id, username=user.username)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc


@router.patch("/sessions/{session_id}")
def rename_session(
    session_id: str,
    payload: RenameSessionRequest,
    user: User = Depends(require_permission("agent:chat")),
):
    try:
        return chat_svc.rename_session(session_id, user.username, payload.title)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, user: User = Depends(require_permission("agent:chat"))):
    try:
        chat_svc.soft_delete_session(session_id, user.username)
        return {"ok": True}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc


@router.get("/sessions/{session_id}/messages")
def list_messages(session_id: str, user: User = Depends(require_permission("agent:chat"))):
    try:
        return chat_svc.list_messages(session_id, user.username)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc


@router.post("/chat")
def agent_chat(
    payload: AgentChatRequest,
    user: User = Depends(require_permission("agent:chat")),
):
    try:
        # Do not trust client tool_args for mutations — agent parses NL (+ JSON in message).
        return agent_svc.chat(
            session_id=payload.session_id,
            message=payload.message,
            actor=user.username,
            role=user.role,
            tool_args=None,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/hitl/pending")
def pending_hitl(user: User = Depends(require_permission("workflow:approve_close"))):
    # Approvers/admins see all pending; others none
    return chat_svc.list_pending_hitl()


@router.post("/hitl/{request_id}/resolve")
def resolve_hitl(
    request_id: str,
    payload: HitlResolveRequest,
    user: User = Depends(require_permission("workflow:approve_close")),
):
    try:
        return agent_svc.resume_hitl(
            request_id=request_id,
            approved=payload.approved,
            resolved_by=user.username,
            note=payload.note,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="HITL request not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
