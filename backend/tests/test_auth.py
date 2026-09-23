"""Auth service tests with an in-memory database; no model or network access."""
import sys
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.user_model import Session, User, utcnow
from app.core.passwords import hasher
from app.services.auth import LoginLimiter, current_user, login, logout, token_hash


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(self.engine, expire_on_commit=False)
        with self.factory() as db:
            db.add(User(
                username="admin",
                password_hash=hasher.hash("test-password-123"),
                role="admin",
            ))
            db.commit()

    def tearDown(self):
        self.engine.dispose()

    def test_login_stores_only_token_hash(self):
        user, token = login(
            self.factory, "admin", "test-password-123", 3600
        )
        self.assertEqual(user.username, "admin")
        self.assertEqual(current_user(self.factory, token).username, "admin")
        with self.factory() as db:
            stored = db.scalar(select(Session))
            self.assertEqual(stored.token_hash, token_hash(token))
            self.assertNotEqual(stored.token_hash, token)
            self.assertTrue(
                db.scalar(select(User)).password_hash.startswith("$argon2id$")
            )

    def test_invalid_password_and_expired_sessions(self):
        with self.assertRaises(HTTPException) as wrong:
            login(self.factory, "admin", "wrong", 3600)
        self.assertEqual(wrong.exception.status_code, 401)

        _, token = login(self.factory, "admin", "test-password-123", 3600)
        with self.factory() as db:
            db.scalar(select(Session)).expires_at = (
                utcnow() - timedelta(seconds=1)
            )
            db.commit()
        self.assertIsNone(current_user(self.factory, token))

    def test_session_rotation_logout_and_rate_limit(self):
        _, first = login(self.factory, "admin", "test-password-123", 3600)
        _, second = login(
            self.factory,
            "admin",
            "test-password-123",
            3600,
            old_token=first,
        )
        self.assertIsNone(current_user(self.factory, first))
        self.assertIsNotNone(current_user(self.factory, second))
        logout(self.factory, second)
        self.assertIsNone(current_user(self.factory, second))

        limiter = LoginLimiter(limit=1)
        limiter.check("client")
        with self.assertRaises(HTTPException) as limited:
            limiter.check("client")
        self.assertEqual(limited.exception.status_code, 429)
        limiter.reset("client")
        limiter.check("client")


if __name__ == "__main__":
    unittest.main()
