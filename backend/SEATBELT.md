# Seatbelt integration

Image upload (`/inference/image`) and source-comparison processing enrich each
recognized vehicle using its original-resolution crop. The backend and worker
construct the same `SeatbeltService`. The recognition model service is unchanged.

Only `front_side` with view confidence >= 0.90 invokes `POST /detect` on the
person_detection_in_car service (windshield → person crops → occupant classification). Other views produce explicit
skip results. Timeouts, invalid responses and upstream failures produce ERROR
without discarding vehicle classification. No automatic seatbelt-only retry is
implemented; reprocessing the record runs the check again.

The root .env enables this integration in backend and worker, targeting the
existing separately running container at `http://host.docker.internal:8011`.
Requests use the API-Key header with SEATBELT_API_KEY matching the new service API_KEY.
The integration does not start or rebuild the separate seatbelt container.

Configuration (backend and worker environment):

- SEATBELT_ENABLED: false by default; enabled in root .env
- SEATBELT_URL: http://host.docker.internal:8011
- SEATBELT_TIMEOUT_SECONDS: 30 (read timeout; connect timeout is 5 seconds)
- SEATBELT_FRONT_VIEW_MIN_CONFIDENCE: 0.90
- SEATBELT_API_KEY: must match the new service API_KEY
- WINDSHIELD_MODEL_VERSION / SEATBELT_MODEL_VERSION: unknown unless configured

Rebuild backend/worker after installing the change:

```sh
docker compose -f /home/darmaa/Documents/person_detection_in_car/compose.yaml up -d --build api
docker compose -f backend/docker-compose.yaml up -d --build backend worker
```

Rebuild/serve the frontend through the existing frontend deployment workflow.
For direct local backend execution, explicitly set SEATBELT_ENABLED=true and
SEATBELT_URL=http://localhost:8011.

The source-comparison store writes schemaVersion=1 results into the existing
vehicle_recognitions.seatbelt_result JSONB column. History exposes this as
prediction.seatbelt; fresh image responses expose results[].seatbelt. Unversioned
legacy data remains stored but is not exposed. Reprocessing clears versioned
seatbelt data so failed attempts cannot display stale results. Existing completed
records are not automatically reprocessed. Startup Alembic migrations add seatbelt_result if missing and preserve existing
data. See migrations/README.md for adoption and upgrade instructions.

Coordinates are xyxy pixels relative to the vehicle crop. The result also stores
vehicleBboxInOriginal, dimensions, thresholds, processedAt and model versions.
No image bytes are stored in JSON. People with ambiguous geometry keep an unknown
role. Empty detections do not mean that a person is unbelted.

Frontend result cards and comparison history display status and individual
occupant labels/confidences. This change does not add image overlays, live/video
seatbelt processing, direct /vehicle and /vehicle-bbox enrichment, or persistent
history for manual image uploads.

Implementation: schemas/seatbelt.py defines the wire contract; services/seatbelt/client.py
handles HTTP and encoding; services/seatbelt/service.py handles view gating and results.
All environment configuration is defined in app/core/config.py.

Windshield images are saved after still-image seatbelt analysis (including service
worker comparisons) using each validated `cropBbox` in vehicle-crop coordinates.
Files live in `runtime/windshields/<event_id>_windshield_<index>.jpg`, served through
`/media/windshields/`. Vehicle crops remain in `runtime/crops/`. Each windshield has a `cropUrl` in the response and persisted
seatbelt JSON. Save failures preserve detections, set `cropUrl` to null and
`cropError` to `CROP_SAVE_FAILED`, and emit `windshield.crop.failed`.
No windshield files are created for skipped/disabled/failed detection or no
windshields. Existing records are not backfilled. Tracking events currently do
not run seatbelt analysis, so this does not add windshield crops for live/video.

The adapter maps nested persons into existing detections, preserving role, person confidence and phone predictions. Null seatbelt predictions use person_unknown, never unbelted. Coordinates are already relative to the submitted vehicle crop. SEATBELT_CONFIDENCE is legacy and is not sent. The old seatbelt-detection service was removed from backend Compose.

Windshield and person confidence thresholds are owned by person_detection_in_car (defaults 0.25 and 0.20). The backend sends no threshold query parameters and does not duplicate these values in result metadata.

Person crops are saved under `runtime/persons/<event_id>_person_<index>.jpg`
and served by the authenticated `/media/persons/` route. Each detection stores
its own `cropUrl`, preserving the link to its role, belt and phone predictions
in comparison history. Crops use the same outward bbox rounding as classification.
Save failures preserve predictions with a null cropUrl and CROP_SAVE_FAILED.
Existing records have no person crops until reprocessed.
