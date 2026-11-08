"""LangGraph SQLite checkpointer for HITL interrupt/resume."""

from __future__ import annotations

import sqlite3
from functools import lru_cache
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

from app.core.config import BACKEND_ROOT


@lru_cache
def get_checkpointer() -> SqliteSaver:
    """
    Persistent LangGraph checkpointer.
    Stores graph state so HITL interrupts can resume later.
    """
    path = BACKEND_ROOT / "data" / "langgraph_checkpoints.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    return SqliteSaver(conn)
