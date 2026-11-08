"""Per-user chat sessions + messages in core SQLite."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from app.db.models.core import AgentHitlRequest, ChatMessage, ChatSession
from app.db.session import DatabaseKind, db_manager


class ChatHistoryService:
    def create_session(
        self,
        username: str,
        title: str | None = None,
        *,
        session_kind: str = "agent",
    ) -> dict[str, Any]:
        kind = (session_kind or "agent").strip().lower()
        if kind not in {"agent", "rag"}:
            kind = "agent"
        prefix = "RAG" if kind == "rag" else "SES"
        session_id = f"{prefix}-{uuid.uuid4().hex[:12].upper()}"
        thread_id = f"{kind}-{username}-{session_id}"
        default_title = "Knowledge chat" if kind == "rag" else "New chat"
        with db_manager.session(DatabaseKind.CORE) as session:
            row = ChatSession(
                session_id=session_id,
                username=username,
                title=(title or default_title)[:255],
                session_kind=kind,
                thread_id=thread_id,
                is_active=True,
            )
            session.add(row)
        return self.get_session(session_id, username=username)

    def list_sessions(self, username: str, session_kind: str | None = "agent") -> list[dict[str, Any]]:
        with db_manager.session(DatabaseKind.CORE) as session:
            q = session.query(ChatSession).filter(
                ChatSession.username == username,
                ChatSession.is_active.is_(True),
            )
            if session_kind:
                q = q.filter(ChatSession.session_kind == session_kind)
            rows = q.order_by(ChatSession.updated_at.desc()).all()
            return [self._session_dict(r) for r in rows]

    def get_session(self, session_id: str, username: str | None = None) -> dict[str, Any]:
        with db_manager.session(DatabaseKind.CORE) as session:
            q = session.query(ChatSession).filter(ChatSession.session_id == session_id)
            if username:
                q = q.filter(ChatSession.username == username)
            row = q.first()
            if not row:
                raise KeyError(session_id)
            return self._session_dict(row)

    def rename_session(self, session_id: str, username: str, title: str) -> dict[str, Any]:
        with db_manager.session(DatabaseKind.CORE) as session:
            row = (
                session.query(ChatSession)
                .filter(ChatSession.session_id == session_id, ChatSession.username == username)
                .first()
            )
            if not row:
                raise KeyError(session_id)
            row.title = title[:255]
            row.updated_at = datetime.utcnow()
        return self.get_session(session_id, username)

    def soft_delete_session(self, session_id: str, username: str) -> None:
        with db_manager.session(DatabaseKind.CORE) as session:
            row = (
                session.query(ChatSession)
                .filter(ChatSession.session_id == session_id, ChatSession.username == username)
                .first()
            )
            if not row:
                raise KeyError(session_id)
            row.is_active = False

    def add_message(
        self,
        *,
        session_id: str,
        username: str,
        role: str,
        content: str,
        intent: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with db_manager.session(DatabaseKind.CORE) as session:
            # ownership check
            owner = (
                session.query(ChatSession)
                .filter(ChatSession.session_id == session_id, ChatSession.username == username)
                .first()
            )
            if not owner:
                raise KeyError(session_id)
            msg = ChatMessage(
                session_id=session_id,
                username=username,
                role=role,
                content=content,
                intent=intent,
                metadata_json=json.dumps(metadata or {}),
            )
            session.add(msg)
            owner.updated_at = datetime.utcnow()
            if owner.title == "New chat" and role == "user":
                owner.title = content.strip()[:60] or "New chat"
            session.flush()
            return self._message_dict(msg)

    def list_messages(self, session_id: str, username: str, limit: int = 200) -> list[dict[str, Any]]:
        with db_manager.session(DatabaseKind.CORE) as session:
            owner = (
                session.query(ChatSession)
                .filter(ChatSession.session_id == session_id, ChatSession.username == username)
                .first()
            )
            if not owner:
                raise KeyError(session_id)
            rows = (
                session.query(ChatMessage)
                .filter(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at.asc())
                .limit(limit)
                .all()
            )
            return [self._message_dict(r) for r in rows]

    def create_hitl(
        self,
        *,
        session_id: str,
        thread_id: str,
        username: str,
        tool_name: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        request_id = f"HITL-{uuid.uuid4().hex[:10].upper()}"
        with db_manager.session(DatabaseKind.CORE) as session:
            row = AgentHitlRequest(
                request_id=request_id,
                session_id=session_id,
                thread_id=thread_id,
                username=username,
                tool_name=tool_name,
                payload_json=json.dumps(payload),
                status="pending",
            )
            session.add(row)
        return self.get_hitl(request_id)

    def get_hitl(self, request_id: str) -> dict[str, Any]:
        with db_manager.session(DatabaseKind.CORE) as session:
            row = session.query(AgentHitlRequest).filter(AgentHitlRequest.request_id == request_id).first()
            if not row:
                raise KeyError(request_id)
            return self._hitl_dict(row)

    def list_pending_hitl(self, username: str | None = None) -> list[dict[str, Any]]:
        with db_manager.session(DatabaseKind.CORE) as session:
            q = session.query(AgentHitlRequest).filter(AgentHitlRequest.status == "pending")
            if username:
                q = q.filter(AgentHitlRequest.username == username)
            rows = q.order_by(AgentHitlRequest.created_at.desc()).all()
            return [self._hitl_dict(r) for r in rows]

    def resolve_hitl(
        self,
        request_id: str,
        *,
        approved: bool,
        resolved_by: str,
        note: str | None = None,
    ) -> dict[str, Any]:
        with db_manager.session(DatabaseKind.CORE) as session:
            row = session.query(AgentHitlRequest).filter(AgentHitlRequest.request_id == request_id).first()
            if not row:
                raise KeyError(request_id)
            if row.status != "pending":
                raise ValueError(f"HITL request already {row.status}")
            row.status = "approved" if approved else "rejected"
            row.resolved_by = resolved_by
            row.resolution_note = note
            row.resolved_at = datetime.utcnow()
            payload = json.loads(row.payload_json)
            data = self._hitl_dict(row)
        data["payload"] = payload
        return data

    @staticmethod
    def _session_dict(r: ChatSession) -> dict[str, Any]:
        return {
            "session_id": r.session_id,
            "username": r.username,
            "title": r.title,
            "session_kind": getattr(r, "session_kind", None) or "agent",
            "thread_id": r.thread_id,
            "is_active": r.is_active,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }

    @staticmethod
    def _message_dict(r: ChatMessage) -> dict[str, Any]:
        meta = {}
        if r.metadata_json:
            try:
                meta = json.loads(r.metadata_json)
            except Exception:
                meta = {}
        return {
            "id": r.id,
            "session_id": r.session_id,
            "username": r.username,
            "role": r.role,
            "content": r.content,
            "intent": r.intent,
            "metadata": meta,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }

    @staticmethod
    def _hitl_dict(r: AgentHitlRequest) -> dict[str, Any]:
        return {
            "request_id": r.request_id,
            "session_id": r.session_id,
            "thread_id": r.thread_id,
            "username": r.username,
            "tool_name": r.tool_name,
            "status": r.status,
            "payload": json.loads(r.payload_json) if r.payload_json else {},
            "resolution_note": r.resolution_note,
            "resolved_by": r.resolved_by,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
        }
