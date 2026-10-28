"""Bounded, single-process tracking sessions. Every session owns its detector/tracker."""
from collections import deque
from dataclasses import dataclass, field
import logging
import math
from pathlib import Path
from threading import Event, Lock, Thread
from time import monotonic
from uuid import uuid4

import cv2
from fastapi import HTTPException

from recognition_service.config import settings
from recognition_service.media import attach_crops
from recognition_service.inference.pipeline import TrackingState

log = logging.getLogger(__name__)
TERMINAL = {"completed", "error", "stopped"}


@dataclass
class TrackingSession:
    session_id: str
    source: str
    video_path: Path | None = None
    status: str = "pending"
    error: str | None = None
    sequence: int = 0
    frame_sequence: int = 0
    frame: bytes | None = None
    events: deque = field(default_factory=deque)
    event_bytes: int = 0
    touched_at: float = field(default_factory=monotonic)
    stop: Event = field(default_factory=Event)
    lock: Lock = field(default_factory=Lock)
    worker: Thread | None = None


class TrackingSessions:
    def __init__(self, pipeline_factory, inference_lock):
        self.pipeline_factory = pipeline_factory
        self.inference_lock = inference_lock
        self.sessions = {}
        self.cameras = {}
        self.lock = Lock()
        self.closed = Event()
        self.reaper = Thread(target=self._reap, daemon=True)
        self.reaper.start()

    def create(self, source, video_path=None):
        with self.lock:
            if self.closed.is_set():
                raise HTTPException(503, "Tracking service is stopping")
            if len(self.sessions) >= settings.max_sessions:
                raise HTTPException(429, "Tracking session limit reached", headers={"Retry-After": "10"})
            session = TrackingSession(uuid4().hex, str(source), video_path)
            self.sessions[session.session_id] = session
            return session

    def camera(self, camera_id):
        source = settings.camera_sources.get(camera_id)
        if not source:
            raise HTTPException(404, "Camera тохируулаагүй байна.")
        # Serialize camera creation without nesting the manager lock.
        with self.inference_lock:
            session_id = self.cameras.get(camera_id)
            if session_id:
                try:
                    return self.get(session_id)
                except HTTPException:
                    self.cameras.pop(camera_id, None)
            session = self.create(source)
            self.cameras[camera_id] = session.session_id
            return session

    def get(self, session_id):
        with self.lock:
            session = self.sessions.get(session_id)
        if session is None:
            raise HTTPException(404, "Tracking session олдсонгүй.")
        with session.lock:
            session.touched_at = monotonic()
        return session

    def start(self, session_id):
        session = self.get(session_id)
        with session.lock:
            if session.stop.is_set():
                session.status = "stopped"
                return session
            if session.status == "pending":
                session.status = "running"
                session.worker = Thread(target=self._run, args=(session,), daemon=True)
                session.worker.start()
        return session

    def _run(self, session):
        capture = None
        try:
            # A fresh detector owns its own Ultralytics predictor and tracker.
            with self.inference_lock:
                pipeline = self.pipeline_factory()
            tracking = TrackingState()
            source = int(session.source) if session.video_path is None and session.source.isdecimal() else session.source
            capture = cv2.VideoCapture()
            if isinstance(source, str) and "://" in source:
                capture.open(source, cv2.CAP_FFMPEG, [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 10000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 10000])
            else:
                capture.open(source)
            if not capture.isOpened():
                raise ValueError("Видео/камер нээгдсэнгүй.")
            fps = capture.get(cv2.CAP_PROP_FPS)
            if not math.isfinite(fps) or fps <= 0:
                fps = 25.0
            count = capture.get(cv2.CAP_PROP_FRAME_COUNT)
            if session.video_path and count > 0 and count / fps > settings.max_video_seconds:
                raise ValueError("Бичлэгийн үргэлжлэх хугацаа хэтэрсэн.")
            index = 0
            started = monotonic()
            while not session.stop.is_set():
                ok, frame = capture.read()
                if not ok:
                    if session.video_path is None:
                        raise ValueError("Камерын холболт тасарлаа.")
                    if index == 0:
                        raise ValueError("Видео frame агуулаагүй байна.")
                    break
                if frame.shape[0] * frame.shape[1] > settings.max_image_pixels:
                    raise ValueError("Frame нягтаршил хэт өндөр байна.")
                if session.video_path and index / fps >= settings.max_video_seconds:
                    raise ValueError("Бичлэгийн үргэлжлэх хугацаа хэтэрсэн.")
                # Inference is serialized; session state is never shared.
                with self.inference_lock:
                    processed, results = pipeline.process_tracked_frame(frame, tracking)
                attach_crops(frame, results)
                ok, encoded = cv2.imencode(".jpg", processed)
                with session.lock:
                    if ok:
                        session.frame = encoded.tobytes()
                        session.frame_sequence += 1
                    for result in results:
                        session.sequence += 1
                        size = len(result.crop_base64 or "")
                        session.events.append((session.sequence, result, size))
                        session.event_bytes += size
                        while len(session.events) > settings.max_events or session.event_bytes > settings.event_buffer_bytes:
                            _, _, old_size = session.events.popleft()
                            session.event_bytes -= old_size
                index += 1
                if session.video_path:
                    session.stop.wait(max(0, index / fps - (monotonic() - started)))
            with session.lock:
                session.status = "stopped" if session.stop.is_set() else "completed"
        except Exception:
            log.exception("Tracking failed for session %s", session.session_id)
            with session.lock:
                session.status = "error"
                session.error = "Видео/камер боловсруулахад алдаа гарлаа."
        finally:
            if capture is not None:
                capture.release()
            if session.video_path:
                session.video_path.unlink(missing_ok=True)

    def events_after(self, session_id, after):
        session = self.start(session_id)
        with session.lock:
            first = session.events[0][0] if session.events else session.sequence + 1
            if after < first - 1:
                raise HTTPException(409, "Event history expired; start a new session")
            return {"events": [{"sequence": n, "result": r.model_dump(mode="json", by_alias=True)}
                               for n, r, _ in session.events if n > after],
                    "status": session.status, "error": session.error}

    def stream(self, session_id):
        session = self.start(session_id)
        last = 0
        while not self.closed.is_set():
            with session.lock:
                session.touched_at = monotonic()
                frame, sequence, status = session.frame, session.frame_sequence, session.status
            if sequence != last and frame:
                last = sequence
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            if status in TERMINAL:
                return
            session.stop.wait(.03)

    def delete(self, session_id):
        session = self.get(session_id)
        with session.lock:
            session.stop.set()
            worker = session.worker
        if worker is not None:
            worker.join(timeout=12)
            if worker.is_alive():
                # Retain the slot while an in-flight model/capture owns resources.
                return
        if session.video_path:
            session.video_path.unlink(missing_ok=True)
        with self.lock:
            self.sessions.pop(session_id, None)

    def _reap(self):
        while not self.closed.wait(5):
            with self.lock:
                expired = [s.session_id for s in self.sessions.values()
                           if monotonic() - s.touched_at > settings.session_ttl or s.stop.is_set()]
            for session_id in expired:
                try:
                    self.delete(session_id)
                except HTTPException:
                    pass

    def close(self):
        self.closed.set()
        with self.lock:
            ids = list(self.sessions)
            for session in self.sessions.values():
                session.stop.set()
        self.reaper.join(timeout=6)
        for session_id in ids:
            self.delete(session_id)
