"""Core DB models: users, intake reports, chat history, agent HITL."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import CoreBase


class User(CoreBase):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(128))
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), index=True)  # admin|reviewer|operator|approver
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Report(CoreBase):
    __tablename__ = "reports"
    __table_args__ = (UniqueConstraint("reference_id", name="uq_reference_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    reference_id: Mapped[str] = mapped_column(String(32), index=True)
    report_type: Mapped[str] = mapped_column(String(64))
    product_name: Mapped[str] = mapped_column(String(128))
    batch_lot_number: Mapped[str] = mapped_column(String(32), index=True)
    date_received: Mapped[str] = mapped_column(String(16))
    reporter_type: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text)
    event_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_onset_date: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="New", index=True)
    pending_close: Mapped[bool] = mapped_column(default=False)
    # Reviewer triage notes before requesting approver close (required on close request)
    reviewer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Approver optional comment on approve/reject close
    approver_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(64))
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class ChatSession(CoreBase):
    """Per-user chat session (agent or RAG knowledge conversations)."""

    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255), default="New chat")
    # agent = LangGraph agent chat; rag = Knowledge Query chat history
    session_kind: Mapped[str] = mapped_column(String(16), default="agent", index=True)
    thread_id: Mapped[str] = mapped_column(String(64), index=True)  # LangGraph thread / rag thread
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class ChatMessage(CoreBase):
    """Messages belonging to one session (user/assistant/tool/system)."""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    username: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(32))  # user|assistant|tool|system
    content: Mapped[str] = mapped_column(Text)
    intent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class AgentHitlRequest(CoreBase):
    """Human-in-the-loop approvals for agent tool actions (e.g. close case)."""

    __tablename__ = "agent_hitl_requests"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    thread_id: Mapped[str] = mapped_column(String(64), index=True)
    username: Mapped[str] = mapped_column(String(64), index=True)
    tool_name: Mapped[str] = mapped_column(String(64))
    payload_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    # pending | approved | rejected
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
