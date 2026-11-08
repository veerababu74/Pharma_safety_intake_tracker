"""Seed sample users — two accounts per role."""

from __future__ import annotations

from app.core.logging import get_logger
from app.core.security import hash_password
from app.db.models.core import User
from app.db.session import DatabaseKind, db_manager

logger = get_logger("seed")

SAMPLE_USERS = [
    # admin × 2
    {"username": "admin", "full_name": "Sam Admin", "password": "Admin@123", "role": "admin"},
    {"username": "admin2", "full_name": "Alex Admin", "password": "Admin2@123", "role": "admin"},
    # reviewer × 2
    {
        "username": "reviewer",
        "full_name": "Arjun Reviewer",
        "password": "Reviewer@123",
        "role": "reviewer",
    },
    {
        "username": "reviewer2",
        "full_name": "Rina Reviewer",
        "password": "Reviewer2@123",
        "role": "reviewer",
    },
    # operator × 2
    {
        "username": "operator",
        "full_name": "Maya Operator",
        "password": "Operator@123",
        "role": "operator",
    },
    {
        "username": "operator2",
        "full_name": "Omar Operator",
        "password": "Operator2@123",
        "role": "operator",
    },
    # approver × 2
    {
        "username": "approver",
        "full_name": "Priya Approver",
        "password": "Approver@123",
        "role": "approver",
    },
    {
        "username": "approver2",
        "full_name": "Paul Approver",
        "password": "Approver2@123",
        "role": "approver",
    },
]


def seed_users() -> None:
    from app.core.config import get_settings

    settings = get_settings()
    env = (settings.app_env or "development").lower()
    # Never auto-create demo passwords in production unless explicitly forced.
    if env in {"production", "prod"} and not getattr(settings, "seed_demo_users", False):
        logger.info("seed_users_skipped", reason="production", env=env)
        return

    with db_manager.session(DatabaseKind.CORE) as session:
        for item in SAMPLE_USERS:
            existing = session.query(User).filter(User.username == item["username"]).first()
            if existing:
                continue
            session.add(
                User(
                    username=item["username"],
                    full_name=item["full_name"],
                    hashed_password=hash_password(item["password"]),
                    role=item["role"],
                    is_active=True,
                )
            )
            logger.info("seeded_user", username=item["username"], role=item["role"])
