# Backend configuration and service boundaries

All backend environment reads live in `app/core/config.py`:

| Group | Loader | Environment |
| --- | --- | --- |
| API/media/recognition | `get_settings()` / lazy cached `settings` | API_PREFIX, API_KEY, CORS_ORIGINS, SESSION_SECONDS, COOKIE_SECURE, RECOGNITION_URL, RECOGNITION_API_KEY, RECOGNITION_TIMEOUT_SECONDS |
| Database | `get_database_settings()` | DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME |
| Bootstrap admin | `get_admin_settings()` | ADMIN_USERNAME, ADMIN_PASSWORD |
| External comparison | `get_comparison_settings()` | SERVICE_URL, SERVICE_METHOD, SERVICE_BODY_JSON, SERVICE_PARAMS_JSON, SERVICE_TOKEN, SERVICE_LOGIN_URL, SERVICE_USERNAME, SERVICE_PASSWORD, SERVICE_PASSWORD_SHA256, IMAGE_BASE_URL, SERVICE_DATE_START_FIELD, SERVICE_DATE_END_FIELD, SERVICE_WORKER_ENABLED |
| Seatbelt | `get_seatbelt_settings()` | SEATBELT_ENABLED, SEATBELT_URL, SEATBELT_API_KEY, SEATBELT_TIMEOUT_SECONDS, SEATBELT_FRONT_VIEW_MIN_CONFIDENCE, SEATBELT_CONFIDENCE, WINDSHIELD_MODEL_VERSION, SEATBELT_MODEL_VERSION |

Groups are frozen dataclasses. Database/admin tools can load their own group without
requiring API settings. Comparison loaders retain operation-time loading and raw
fingerprint inputs, preserving existing worker cursors and test configuration
behavior. Seatbelt configuration is captured when constructing the service and can
be injected alongside a client in tests. Secret fields in the new configuration
groups are excluded from dataclass repr output.

Seatbelt responsibilities:

- `app/schemas/seatbelt.py`: response shape, confidence and coordinate validation.
- `app/services/seatbelt/client.py`: crop encoding, HTTP request, response validation.
- `app/services/seatbelt/service.py`: view gating, result metadata, status selection,
  failure isolation.
- `app/services/seatbelt/__init__.py`: stable `SeatbeltService` import for callers.

No API payload, database field name or endpoint changes are required by this split.
See `SEATBELT.md` for runtime behavior and `migrations/README.md` for database upgrades.

## Comparison operation logs

Backend and worker emit JSON events to stderr, with UTC timestamps, level,
service, event, and record_id for per-record work. LOG_LEVEL defaults to INFO;
set LOG_LEVEL=DEBUG for sanitized full_photo/base/resolved URL details and HTTP
response events. URL user information, query values, and fragments are removed.
Exception bodies from libraries and upstream response bodies are not logged.

Events cover records.fetch, records.saved (new/existing counts), image.url,
image.download (status, bytes, dimensions, duration), recognition.completed
(labels/confidences), record.saved, retries, cycle.completed (selected/succeeded/
failed/skipped/remaining), and poll.completed. cycle.completed describes a pending
processing batch; poll.completed marks a successful scheduled fetch cycle even
when there is no pending work. retry_not_before is the earliest retry eligibility,
not a guaranteed execution time. Blocked or exhausted retries are explicitly stopped.

From the repository root:

```sh
docker compose -f backend/docker-compose.yaml logs -f backend worker
```

Rebuild/recreate backend and worker after code or environment changes. Image URLs accept HTTPS URLs on the IMAGE_BASE_URL origin and relative paths.
Leading file/ or main/ prefixes are replaced by the configured base path; uploads/
paths are appended directly. The original source_image_path in the database is
preserved. image.url.normalized logs source_url and download_url at INFO level.
Foreign origins, credentials, query strings, fragments and traversal are rejected.
Previously exhausted retry counts are not reset by this change.
