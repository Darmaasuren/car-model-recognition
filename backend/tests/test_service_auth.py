import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.database import Base
from app.models.service_token import ServiceToken
from app.services.service_auth import ServiceAuthError, ServiceTokenProvider
with patch.dict(os.environ, {"API_PREFIX": "/api", "API_KEY": "test", "CORS_ORIGINS": "http://localhost:5173"}):
    from app.services.service_comparison import ServiceComparisonError, fetch_records


def jwt(exp):
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return f"header.{payload}.signature"


def response(body, code=200):
    value = MagicMock()
    value.__enter__.return_value = value
    value.status_code = code
    value.is_redirect = False
    value.json.return_value = body
    return value


class ServiceTokenTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{self.temp.name}/test.db")
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(self.engine)
        self.provider = ServiceTokenProvider(self.factory)
        self.env = patch.dict(os.environ, {
            "SERVICE_LOGIN_URL": "https://example.test/login",
            "SERVICE_USERNAME": "test-user",
            "SERVICE_PASSWORD": "test-password",
            "SERVICE_PASSWORD_SHA256": "test-hash",
            "SERVICE_URL": "https://example.test/records",
            "SERVICE_METHOD": "POST", "SERVICE_PARAMS_JSON": "{}", "SERVICE_BODY_JSON": "{}",
        })
        self.env.start()
        self.token = jwt((datetime.now(timezone.utc) + timedelta(days=1)).timestamp())

    def tearDown(self):
        self.env.stop()
        self.engine.dispose()
        self.temp.cleanup()

    def test_persists_and_reuses_after_provider_restart(self):
        with patch("app.services.service_auth.requests.post", return_value=response(
                {"success": True, "token": self.token})) as login:
            self.assertEqual(self.provider.get_token(), self.token)
            self.assertEqual(ServiceTokenProvider(self.factory).get_token(), self.token)
        login.assert_called_once()
        self.assertEqual(login.call_args.kwargs["json"], {
            "username": "test-user", "password": "test-password", "sha256": "test-hash",
        })

    def test_refreshes_near_expiry_and_rejected_token(self):
        with patch("app.services.service_auth.requests.post", return_value=response(
                {"success": True, "token": self.token})) as login:
            self.provider.get_token()
            with self.factory.begin() as db:
                db.scalar(select(ServiceToken)).expires_at = datetime.now(timezone.utc) + timedelta(seconds=30)
            self.provider.get_token()
            self.provider.get_token(rejected_token=self.token)
            self.assertEqual(login.call_count, 3)

    def test_concurrent_calls_login_only_once(self):
        with patch("app.services.service_auth.requests.post", return_value=response(
                {"success": True, "token": self.token})) as login:
            with ThreadPoolExecutor(max_workers=4) as pool:
                tokens = list(pool.map(lambda _: self.provider.get_token(), range(8)))
            self.assertEqual(tokens, [self.token] * 8)
            login.assert_called_once()

    def test_failed_login_does_not_persist_or_expose_secrets(self):
        for body in ({"success": False, "token": "secret"}, {"success": True},
                     {"success": True, "token": "malformed"}):
            with patch("app.services.service_auth.requests.post", return_value=response(body)):
                with self.assertRaises(ServiceAuthError) as caught:
                    self.provider.get_token()
                self.assertNotIn("test-hash", str(caught.exception))
                self.assertNotIn("test-password", str(caught.exception))
                self.assertNotIn("secret", str(caught.exception))
            with self.factory() as db:
                self.assertIsNone(db.scalar(select(ServiceToken)))

    def test_expired_token_is_not_saved(self):
        expired = jwt((datetime.now(timezone.utc) - timedelta(seconds=1)).timestamp())
        with patch("app.services.service_auth.requests.post", return_value=response(
                {"success": True, "token": expired})):
            with self.assertRaises(ServiceAuthError):
                self.provider.get_token()

    def test_401_refreshes_and_retries_once(self):
        provider = MagicMock()
        provider.get_token.side_effect = ["old", "new"]
        with patch("app.services.service_comparison.requests.Session") as sessions:
            request = sessions.return_value.__enter__.return_value.request
            request.side_effect = [response({}, 401), response({"items": [{"_id": "one"}]})]
            self.assertEqual(fetch_records(token_provider=provider), [{"_id": "one"}])
            self.assertEqual(request.call_count, 2)
            self.assertEqual(request.call_args.kwargs["headers"]["Authorization"], "Bearer new")
        provider.get_token.assert_any_call(rejected_token="old")

    def test_repeated_401_stops(self):
        import requests
        denied = response({}, 401)
        denied.raise_for_status.side_effect = requests.HTTPError(response=denied)
        provider = MagicMock()
        provider.get_token.side_effect = ["old", "new"]
        with patch("app.services.service_comparison.requests.Session") as sessions:
            request = sessions.return_value.__enter__.return_value.request
            request.side_effect = [response({}, 401), denied]
            with self.assertRaises(ServiceComparisonError):
                fetch_records(token_provider=provider)
            self.assertEqual(request.call_count, 2)


if __name__ == "__main__":
    unittest.main()
