from collections import OrderedDict
from datetime import timedelta
from hashlib import sha256
from secrets import token_urlsafe
from threading import Lock
from time import monotonic

from fastapi import HTTPException
from sqlalchemy import delete, select

from app.models.user_model import Session, User, utcnow
from app.core.passwords import DUMMY_HASH, hasher, verify_password


def token_hash(token):
    return sha256(token.encode()).hexdigest()


def current_user(factory, token):
    if not token or len(token) > 128:
        return None
    with factory() as db:
        return db.scalar(
            select(User).join(Session, Session.user_id == User.id).where(
                Session.token_hash == token_hash(token),
                Session.expires_at > utcnow(),
            )
        )


def login(factory, username, password, lifetime, old_token=None):
    with factory() as db:
        user = db.scalar(select(User).where(User.username == username))
        valid = verify_password(user.password_hash if user else DUMMY_HASH, password)
        if not valid or not user:
            raise HTTPException(401, 'Username эсвэл password буруу байна.')
        if hasher.check_needs_rehash(user.password_hash):
            user.password_hash = hasher.hash(password)
        db.execute(delete(Session).where(Session.expires_at <= utcnow()))
        if old_token:
            db.execute(delete(Session).where(Session.token_hash == token_hash(old_token)))
        token = token_urlsafe(32)
        db.add(Session(token_hash=token_hash(token), user_id=user.id,
                       expires_at=utcnow() + timedelta(seconds=lifetime)))
        db.commit()
        return user, token


def logout(factory, token):
    if token:
        with factory() as db:
            db.execute(delete(Session).where(Session.token_hash == token_hash(token)))
            db.commit()


class LoginLimiter:
    """Bounded, per-process limiter. Deployment currently uses one worker."""
    def __init__(self, limit=10, window=300):
        self.limit, self.window = limit, window
        self.entries = OrderedDict()
        self.lock = Lock()

    def check(self, key):
        now = monotonic()
        with self.lock:
            start, count = self.entries.get(key, (now, 0))
            if now - start >= self.window:
                start, count = now, 0
            if count >= self.limit:
                raise HTTPException(429, 'Олон удаа оролдлоо. Түр хүлээнэ үү.',
                                    headers={'Retry-After': str(max(1, int(self.window - (now-start))))})
            self.entries[key] = (start, count + 1)
            self.entries.move_to_end(key)
            if len(self.entries) > 10000:
                self.entries.popitem(last=False)

    def reset(self, key):
        """A successful login must not consume the failure budget."""
        with self.lock:
            self.entries.pop(key, None)
