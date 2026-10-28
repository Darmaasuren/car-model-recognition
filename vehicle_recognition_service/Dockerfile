FROM python:3.12-slim-bookworm

WORKDIR /app

# Native libraries required by the OpenCV wheel and detector dependencies.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libxcb1 \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY recognition_service ./recognition_service

COPY checkpoints/best_loss_model_v3.pt /app/checkpoints/classifier.pt
COPY checkpoints/yolo11s.pt /app/checkpoints/detector.pt

ENV MODEL_PATH=/app/checkpoints/classifier.pt \
    DETECTOR_MODEL_PATH=/app/checkpoints/detector.pt

# Catch missing native libraries and broken imports while building the image.
RUN python -c "import cv2; from recognition_service.main import app; from recognition_service.inference.detector import VehicleDetector; from recognition_service.inference.classifier import VehicleClassifier"


CMD ["uvicorn", "recognition_service.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
