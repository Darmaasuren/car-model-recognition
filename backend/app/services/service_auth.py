"""Persist service credentials' access token; never log login payloads or tokens."""
import base64
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import math
import os
from threading import Lock
from urllib.parse import urlsplit

import requests
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.models.service_token import ServiceToken


class ServiceAuthError(Exception):
    pass


class ServiceTokenProvider:
    def __init__(self, factory):
        self.factory = factory
        self.lock = Lock()

    def get_token(self, rejected_token=None):
        url = os.getenv("SERVICE_LOGIN_URL", "").strip()
        username = os.getenv("SERVICE_USERNAME", "").strip()
        password = os.getenv("SERVICE_PASSWORD", "")
        password_hash = os.getenv("SERVICE_PASSWORD_SHA256", "").strip()
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username
                or parsed.password or not username or not password or not password_hash):
            raise ServiceAuthError("Service login тохиргоо дутуу эсвэл HTTPS URL буруу байна.")
        key = sha256(json.dumps([url, username, password, password_hash]).encode()).hexdigest()
        try:
            with self.lock, self.factory() as db, db.begin():
                # Serializes refreshes across backend processes, including the first insert.
                if db.bind.dialect.name == "postgresql":
                    db.execute(text("SELECT pg_advisory_xact_lock(731904821)"))
                cached = db.get(ServiceToken, key)
                now = datetime.now(timezone.utc)
                if cached:
                    expiry = cached.expires_at
                    if expiry.tzinfo is None:
                        expiry = expiry.replace(tzinfo=timezone.utc)
                    if expiry > now + timedelta(seconds=60) and cached.token != rejected_token:
                        return cached.token
                token, expiry = self._login(url, username, password, password_hash, now)
                if cached:
                    cached.token, cached.expires_at = token, expiry
                else:
                    db.add(ServiceToken(key=key, token=token, expires_at=expiry))
                return token
        except SQLAlchemyError:
            raise ServiceAuthError("Service token-ийг database-д уншиж/хадгалж чадсангүй.") from None

    @staticmethod
    def _login(url, username, password, password_hash, now):
        try:
            response = requests.post(
                url,
                json={"username": username, "password": password, "sha256": password_hash},
                timeout=(10, 30),
                allow_redirects=False,
            )
            with response:
                if response.status_code != 200:
                    raise ServiceAuthError("Service-д нэвтэрч чадсангүй. Нэвтрэх тохиргоогоо шалгана уу.")
                body = response.json()
        except (requests.RequestException, ValueError):
            raise ServiceAuthError("Service login хүсэлт амжилтгүй боллоо.") from None
        if (not isinstance(body, dict) or body.get("success") is not True
                or not isinstance(body.get("token"), str) or not body["token"].strip()):
            raise ServiceAuthError("Service login response token агуулаагүй байна.")
        token = body["token"].strip()
        # JWT claims are used only for refresh scheduling, never for authentication.
        expiry = now + timedelta(days=1)
        try:
            segment = token.split(".")[1]
            claims = json.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)))
            exp = claims.get("exp")
            if exp is not None:
                if isinstance(exp, bool) or not isinstance(exp, (int, float)) or not math.isfinite(exp):
                    raise ValueError()
                expiry = datetime.fromtimestamp(exp, timezone.utc)
        except (IndexError, ValueError, TypeError, AttributeError, OverflowError, OSError):
            raise ServiceAuthError("Service token-ийн хугацааны бүтэц буруу байна.") from None
        if expiry <= now + timedelta(seconds=60):
            raise ServiceAuthError("Service хугацаа дууссан эсвэл дуусах дөхсөн token буцаалаа.")
        return token, expiry
