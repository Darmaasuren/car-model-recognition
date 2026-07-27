# Vehicle Recognition Backend

FastAPI backend for the React frontend. The recognition flow is:

1. YOLO detects and tracks a vehicle.
2. The pipeline accepts vehicles inside the ROI.
3. The detected vehicle is cropped.
4. The multi-task classifier predicts model, color, type, and view.
5. The API returns the predictions and, where enabled, a crop URL.

The classifier reads all required metadata directly from
`train/checkpoints/best_model.pt`. A separate `manifest.json` is not needed.

Set `DETECTOR_MODEL_PATH` to the YOLO weight and
`CLASSIFIER_MODEL_PATH` to the checkpoint produced by `train/src/train.py`.
Open `http://127.0.0.1:8000/docs` for the API documentation.

## Endpoints

- `GET /api/v1/health`
- `POST /api/v1/inference/image`
- `POST /api/v1/inference/video`
- `POST /api/v1/inference/plate-vehicle` (Base64 JSON + plate bbox)
- `POST /api/v1/inference/plate-vehicle/upload` (file + plate bbox)
- `POST /api/v1/inference/video/sessions`
- `GET /api/v1/inference/video/sessions/{session_id}/stream`
- `WS /api/v1/inference/video/sessions/{session_id}/events`
- `DELETE /api/v1/inference/video/sessions/{session_id}`
- `GET /api/v1/live/cameras/camera-1/stream`
- `WS /api/v1/live/cameras/camera-1/events`

No database is used. Uploads are deleted after processing. Base64 plate
inference does not store crops; image, live, video, and plate upload flows
keep crops under `runtime/crops` so the frontend can display them.

The Base64 plate endpoint decodes and processes the image in memory. It does
not store the source image or the matched vehicle crop.

Example Base64 request:

```json
{
  "eventId": "camera-event-001",
  "imageBase64": "/9j/4AAQSkZJRgABAQ...",
  "plateBbox": {
    "x1": 420,
    "y1": 310,
    "x2": 510,
    "y2": 345
  }
}
```

Run tests from the backend directory:

```bash
PYTHONPATH=app python -m unittest discover -s tests -v
```
