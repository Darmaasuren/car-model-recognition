"""Small structured events; never log exception bodies or request credentials."""
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
import inspect
import json
import logging
import os
from time import perf_counter
from urllib.parse import urlsplit, urlunsplit

record_id = ContextVar("record_id", default=None)
log = logging.getLogger("app.operations")


def configure_logging():
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        level = "INFO"
    # Configure only application events, not verbose third-party HTTP loggers.
    log.setLevel(level)
    if not log.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        log.addHandler(handler)
    log.propagate = False


def safe_url(value):
    if not isinstance(value, str):
        return None
    try:
        parts = urlsplit(value)
        return urlunsplit((parts.scheme, parts.netloc.rsplit("@", 1)[-1],
                           parts.path, "REDACTED" if parts.query else "", ""))
    except ValueError:
        return "<invalid-url>"


def event(name, level=logging.INFO, **fields):
    payload = {"timestamp": datetime.now(timezone.utc).isoformat(),
               "level": logging.getLevelName(level), "service": "comparison",
               "event": name, "record_id": record_id.get(), **fields}
    log.log(level, json.dumps(payload, ensure_ascii=False, default=str))


def operation(name):
    def decorate(func):
        signature = inspect.signature(func)
        @wraps(func)
        def wrapped(*args, **kwargs):
            arguments = signature.bind(*args, **kwargs).arguments
            started = perf_counter()
            try:
                return func(*args, **kwargs)
            except Exception as error:
                response = getattr(error, "response", None)
                cause = getattr(error, "__cause__", None)
                if response is None and cause is not None:
                    response = getattr(cause, "response", None)
                fields = {}
                if "record_id" in arguments:
                    fields["record_id"] = arguments["record_id"]
                if "url" in arguments:
                    fields["url"] = safe_url(arguments["url"])
                if name == "image.url":
                    fields["full_photo"] = safe_url(arguments["record"].get("full_photo"))
                event(name + ".failed", logging.ERROR, **fields,
                      error_type=type(error).__name__,
                      reason=str(error) if type(error).__name__ == "ServiceComparisonError" else None,
                      status=getattr(error, "status_code", None) or getattr(response, "status_code", None),
                      duration_ms=round((perf_counter() - started) * 1000))
                raise
        return wrapped
    return decorate
