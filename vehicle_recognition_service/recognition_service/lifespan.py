from contextlib import asynccontextmanager
from threading import RLock
import re

from recognition_service.config import settings
from recognition_service.inference.pipeline import RecognitionPipeline
from recognition_service.tracking.sessions import TrackingSessions


@asynccontextmanager
async def lifespan(app):
    if not settings.api_key.strip():
        raise RuntimeError("API_KEY тохируулаагүй байна.")
    from recognition_service.inference.classifier import VehicleClassifier
    from recognition_service.inference.detector import VehicleDetector

    # Single process owns this temporary directory; recover orphan uploads after restart.
    settings.runtime_dir.mkdir(parents=True, exist_ok=True)
    for path in settings.runtime_dir.iterdir():
        if path.is_file() and re.fullmatch(r"[0-9a-f]{32}\.(mp4|mov|avi|mkv)", path.name):
            path.unlink()
    classifier = VehicleClassifier(settings.model_path, settings.device)
    lock = RLock()
    def pipeline_factory():
        detector = VehicleDetector(settings.detector_model_path, settings.detector_confidence, str(classifier.device))
        pipeline = RecognitionPipeline(detector, classifier)
        if len(settings.roi) != 4 or not (0 <= settings.roi[0] < settings.roi[2] <= 1 and 0 <= settings.roi[1] < settings.roi[3] <= 1):
            raise ValueError("TRACKING_ROI must be normalized x1,y1,x2,y2")
        pipeline.roi_ratio = settings.roi
        return pipeline

    app.state.classifier = classifier
    app.state.pipeline = pipeline_factory()
    app.state.inference_lock = lock
    app.state.sessions = TrackingSessions(pipeline_factory, lock)
    try:
        yield
    finally:
        app.state.sessions.close()
        app.state.pipeline = None
        app.state.classifier = None


