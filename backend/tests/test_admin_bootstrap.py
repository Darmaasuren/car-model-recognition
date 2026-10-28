"""Startup admin creation and preservation of existing accounts."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from app.core.database import Base
from app.core.passwords import verify_password
from app.models.user import User
from app.services.auth import ensure_initial_admin


class AdminBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        User.__table__.create(self.engine)
        self.factory = sessionmaker(self.engine)
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.engine.dispose()

    def test_create_and_restart_preserves_password_and_role(self):
        os.environ.update(ADMIN_USERNAME=" MD ", ADMIN_PASSWORD="first-password")
        self.assertTrue(ensure_initial_admin(self.factory))
        with self.factory() as db, db.begin():
            user = db.scalar(select(User))
            self.assertEqual(user.username, "md")
            self.assertEqual(user.role, "admin")
            self.assertTrue(verify_password(user.password_hash, "first-password"))
            saved_hash = user.password_hash
            user.role = "viewer"
        os.environ["ADMIN_PASSWORD"] = "different-password"
        self.assertFalse(ensure_initial_admin(self.factory))
        with self.factory() as db:
            user = db.scalar(select(User))
            self.assertEqual(user.password_hash, saved_hash)
            self.assertEqual(user.role, "viewer")
            self.assertEqual(db.scalar(select(func.count()).select_from(User)), 1)

    def test_unconfigured_is_optional(self):
        self.assertFalse(ensure_initial_admin(self.factory))

    def test_incomplete_configuration_rejected(self):
        for values in ({"ADMIN_USERNAME": "md"}, {"ADMIN_PASSWORD": "secret"},
                       {"ADMIN_USERNAME": "md", "ADMIN_PASSWORD": "   "}):
            with self.subTest(values=list(values)), patch.dict(os.environ, values, clear=True):
                with self.assertRaises(ValueError):
                    ensure_initial_admin(self.factory)


if __name__ == "__main__":
    unittest.main()
