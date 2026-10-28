"""Fetch records and images from the external registration system."""
import json
import logging
from time import perf_counter
from app.core.observability import event, operation, safe_url
from app.core.config import get_comparison_settings
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import unquote, urljoin, urlsplit

import cv2
import numpy as np
import requests

from app.core.config import settings
from app.services.comparison.auth import ServiceAuthError


class ServiceComparisonError(Exception):
    def __init__(self, message, *, retry_after=0, blocked=False, status_code=None):
        super().__init__(message)
        self.retry_after = retry_after
        self.blocked = blocked
        self.status_code = status_code


def retry_after_seconds(value):
    try:
        return max(0, int(value))
    except (ValueError, TypeError):
        try:
            return max(0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return 0


@operation("records.fetch")
def fetch_records(limit=20, token_provider=None, overrides=None, refresh_on_401=True, omit_date_filters=False):
    started = perf_counter()
    event("records.fetch.started", limit=limit)
    config = get_comparison_settings()
    url = (config.url or "").strip()
    token = config.token
    method = config.method.strip().upper()
    if not url or (token_provider is None and not token) or method not in {"GET", "POST"}:
        raise ServiceComparisonError("SERVICE_URL, SERVICE_TOKEN эсвэл SERVICE_METHOD тохиргоо дутуу байна.")
    try:
        params = json.loads(config.params_json)
        body = json.loads(config.body_json)
    except ValueError as error:
        raise ServiceComparisonError("SERVICE_PARAMS_JSON эсвэл SERVICE_BODY_JSON JSON формат буруу байна.") from error
    if not isinstance(params, dict) or not isinstance(body, dict):
        raise ServiceComparisonError("Service request JSON объект байх ёстой.", blocked=True)
    if omit_date_filters:
        date_fields = {"startDate", "endDate", config.date_start_field,
                       config.date_end_field}
        for field in date_fields:
            params.pop(field, None)
            body.pop(field, None)
    if overrides is not None:
        (body if method == "POST" else params).update(overrides)
    try:
        if token_provider is not None:
            token = token_provider.get_token()
        with requests.Session() as client:
            for attempt in range(2):
                response = client.request(
                    method, url,
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                    params=params,
                    json=body if method == "POST" else None,
                    timeout=(10, 30),
                    allow_redirects=False,
                )
                with response:
                    if response.status_code == 401 and token_provider is not None and attempt == 0 and refresh_on_401:
                        token = token_provider.get_token(rejected_token=token)
                        continue
                    if response.status_code == 401 and token_provider is not None and not refresh_on_401:
                        # Refresh credentials now; retry the list only on the next scheduled cycle.
                        token_provider.get_token(rejected_token=token)
                        raise ServiceComparisonError("Service token шинэчилсэн; дараагийн мөчлөгт дахин оролдоно.", retry_after=300)
                    if response.status_code in {401, 403, 429, 503}:
                        raise ServiceComparisonError(
                            f"Service HTTP {response.status_code} алдаа буцаалаа.",
                            retry_after=retry_after_seconds(response.headers.get("Retry-After")),
                            blocked=response.status_code in {401, 403},
                            status_code=response.status_code,
                        )
                    response.raise_for_status()
                    if response.is_redirect:
                        raise ServiceComparisonError("Service хаяг өөр хаяг руу чиглүүлж байна.")
                    payload = response.json()
                    break
    except ServiceAuthError as error:
        raise ServiceComparisonError(str(error)) from None
    except requests.HTTPError as error:
        code = error.response.status_code if error.response is not None else "unknown"
        raise ServiceComparisonError(f"Service HTTP {code} алдаа буцаалаа.") from error
    except (requests.RequestException, ValueError) as error:
        raise ServiceComparisonError("Service-ээс record авч чадсангүй.") from error
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise ServiceComparisonError("Service-ийн items жагсаалт буруу байна.")
    if overrides is not None and len(items) > limit:
        raise ServiceComparisonError("Service limit-ээс олон бичлэг буцаалаа.", blocked=True)
    event("records.fetch.completed", fetched=len(items[:limit]), duration_ms=round((perf_counter() - started) * 1000))
    return items[:limit]


def fetch_record(token_provider=None):
    records = fetch_records(1, token_provider)
    if not records or not isinstance(records[0], dict):
        raise ServiceComparisonError("Service-ийн эхний record байхгүй эсвэл буруу байна.")
    return records[0]


@operation("image.url")
def image_url_for(record):
    base = get_comparison_settings().image_base_url + "/"
    path = record.get("full_photo")
    event("image.url.source", logging.DEBUG, full_photo=safe_url(path), base_url=safe_url(base))
    if not base.startswith("https://") or not isinstance(path, str) or not path:
        raise ServiceComparisonError("IMAGE_BASE_URL эсвэл full_photo байхгүй байна.")
    try:
        origin = urlsplit(base)
        parsed = urlsplit(path)
        if (origin.scheme != "https" or not origin.hostname or origin.username is not None
                or origin.password is not None or origin.query or origin.fragment):
            raise ValueError("invalid base")
        if (parsed.query or parsed.fragment or parsed.username is not None
                or parsed.password is not None or path.startswith("//")):
            raise ValueError("invalid source")
        if parsed.scheme or parsed.netloc:
            if (parsed.scheme != "https" or parsed.hostname != origin.hostname
                    or (parsed.port or 443) != (origin.port or 443)):
                raise ValueError("unexpected origin")
        # Reject traversal, encoded separators and control characters before joining.
        decoded = unquote(parsed.path)
        if (any(ord(char) <= 32 or ord(char) == 127 for char in path)
                or "\\" in decoded or "%" in decoded
                or decoded.count("/") != parsed.path.count("/")
                or any(part in {".", ".."} for part in decoded.split("/"))):
            raise ValueError("invalid path")
        relative = parsed.path.lstrip("/")
        base_path = origin.path.strip("/")
        prefixes = ["file", "main"]
        if base_path and base_path not in prefixes:
            prefixes.insert(0, base_path)
        for prefix in prefixes:
            if relative == prefix or relative.startswith(prefix + "/"):
                relative = relative[len(prefix):].lstrip("/")
                break
        if not relative or ":" in relative.split("/", 1)[0]:
            raise ValueError("empty or invalid path")
    except ValueError:
        raise ServiceComparisonError("full_photo зам эсвэл IMAGE_BASE_URL буруу байна.") from None
    url = urljoin(base, relative)
    event("image.url.normalized", record_id=str(record.get("_id") or ""),
          source_url=safe_url(path), download_url=safe_url(url))
    return url


@operation("image.download")
def download_frame(url):
    started = perf_counter()
    event("image.download.started", url=safe_url(url))
    try:
        # The service token is never sent to the image host.
        with requests.get(url, stream=True, timeout=(10, 30), allow_redirects=False) as response:
            event("image.download.response", logging.DEBUG, status=response.status_code, url=safe_url(url))
            if response.status_code in {403, 429, 503}:
                raise ServiceComparisonError(
                    f"Зураг татах HTTP {response.status_code} алдаа.",
                    blocked=response.status_code == 403,
                    status_code=response.status_code,
                    retry_after=max(300, retry_after_seconds(response.headers.get("Retry-After"))),
                )
            response.raise_for_status()
            if response.is_redirect:
                raise ServiceComparisonError("Зургийн хаяг өөр сервер рүү чиглүүлж байна.")
            if response.headers.get("Content-Type", "").split(";")[0].lower() not in {
                "image/jpeg", "image/png", "image/webp",
            }:
                raise ServiceComparisonError("Зургийн төрөл дэмжигдэхгүй байна.")
            chunks = bytearray()
            for chunk in response.iter_content(64 * 1024):
                chunks.extend(chunk)
                if len(chunks) > settings.max_image_bytes:
                    raise ServiceComparisonError("Зураг 15 MB-аас их байна.")
    except requests.RequestException as error:
        raise ServiceComparisonError("Зураг татаж чадсангүй.") from error
    frame = cv2.imdecode(np.frombuffer(chunks, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None or frame.shape[0] * frame.shape[1] > settings.max_image_pixels:
        raise ServiceComparisonError("Зураг уншигдахгүй эсвэл хэт том байна.")
    event("image.download.completed", status=response.status_code, bytes=len(chunks),
          width=frame.shape[1], height=frame.shape[0], duration_ms=round((perf_counter() - started) * 1000))
    return frame


