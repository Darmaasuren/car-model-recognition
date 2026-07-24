from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock, Thread
from time import perf_counter, sleep
from typing import Literal
from uuid import uuid4

import cv2

from schemas import RecognitionResult
from services.media import MediaService
from services.pipeline import RecognitionPipeline, TrackingState


VideoStatus = Literal[
    "pending",
    "running",
    "completed",
    "error",
    "stopped",
]


@dataclass
class VideoSession:
    session_id: str
    video_path: Path
    status: VideoStatus = "pending"
    error: str | None = None
    latest_frame: bytes | None = None
    frame_sequence: int = 0
    events: deque[tuple[int, RecognitionResult]] = field(
        default_factory=lambda: deque(maxlen=1000)
    )
    crop_urls: set[str] = field(default_factory=set)
    event_sequence: int = 0
    stop_requested: bool = False
    delete_requested: bool = False
    worker: Thread | None = None
    lock: Lock = field(default_factory=Lock)
    tracking_state: TrackingState = field(default_factory=TrackingState)


class VideoSessionManager:
    def __init__(
        self,
        pipeline: RecognitionPipeline,
        media: MediaService,
    ):
        self.pipeline = pipeline
        self.media = media
        self.sessions: dict[str, VideoSession] = {}
        self.lock = Lock()

    def create(self, video_path: Path) -> VideoSession:
        session = VideoSession(
            session_id=uuid4().hex,
            video_path=video_path,
        )

        with self.lock:
            self.sessions[session.session_id] = session

        return session

    def get(self, session_id: str) -> VideoSession:
        with self.lock:
            session = self.sessions.get(session_id)

        if session is None:
            raise KeyError(f"Video session олдсонгүй: {session_id}")

        return session

    def start(self, session_id: str) -> VideoSession:
        session = self.get(session_id)

        with session.lock:
            if session.status != "pending":
                return session

            session.status = "running"
            session.worker = Thread(
                target=self._run,
                args=(session,),
                daemon=True,
            )
            session.worker.start()

        return session

    def _run(self, session: VideoSession) -> None:
        capture = cv2.VideoCapture(str(session.video_path))

        try:
            if not capture.isOpened():
                raise RuntimeError("Бичлэгийг уншиж чадсангүй.")

            fps = capture.get(cv2.CAP_PROP_FPS)
            if fps <= 0:
                fps = 25.0

            frame_index = 0
            started_at = perf_counter()

            while True:
                with session.lock:
                    if session.stop_requested:
                        session.status = "stopped"
                        break

                success, frame = capture.read()
                if not success:
                    with session.lock:
                        session.status = "completed"
                    break

                processed, results = self.pipeline.process_tracked_frame(
                    frame,
                    session.tracking_state,
                )

                encoded_success, encoded = cv2.imencode(
                    ".jpg",
                    processed,
                )

                with session.lock:
                    if encoded_success:
                        session.latest_frame = encoded.tobytes()
                        session.frame_sequence += 1

                    for result in results:
                        session.event_sequence += 1
                        session.events.append(
                            (session.event_sequence, result)
                        )
                        if result.crop_url is not None:
                            session.crop_urls.add(result.crop_url)

                frame_index += 1
                target_elapsed = frame_index / fps
                remaining = target_elapsed - (
                    perf_counter() - started_at
                )
                if remaining > 0:
                    sleep(remaining)
        except Exception as error:
            with session.lock:
                session.status = "error"
                session.error = str(error)
        finally:
            capture.release()
            self.media.remove_file(session.video_path)
            if session.delete_requested:
                self._remove_session_crops(session)

    def stream(self, session_id: str):
        session = self.start(session_id)
        last_frame_sequence = 0

        while True:
            with session.lock:
                frame = session.latest_frame
                frame_sequence = session.frame_sequence
                status = session.status

            if frame is not None and frame_sequence != last_frame_sequence:
                last_frame_sequence = frame_sequence
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + frame
                    + b"\r\n"
                )

            if status in {"completed", "error", "stopped"}:
                return

            sleep(0.01)

    def events_after(
        self,
        session_id: str,
        sequence: int,
    ) -> list[tuple[int, RecognitionResult]]:
        session = self.start(session_id)

        with session.lock:
            return [
                (number, result)
                for number, result in session.events
                if number > sequence
            ]

    def get_status(
        self,
        session_id: str,
    ) -> tuple[VideoStatus, str | None]:
        session = self.get(session_id)

        with session.lock:
            return session.status, session.error

    def delete(self, session_id: str) -> None:
        with self.lock:
            session = self.sessions.pop(session_id, None)

        if session is None:
            raise KeyError(f"Video session олдсонгүй: {session_id}")

        with session.lock:
            session.stop_requested = True
            session.delete_requested = True
            worker = session.worker

            if session.status == "pending":
                session.status = "stopped"
                self.media.remove_file(session.video_path)

        if worker is not None:
            worker.join(timeout=2)

        self._remove_session_crops(session)

    def _remove_session_crops(
        self,
        session: VideoSession,
    ) -> None:
        with session.lock:
            crop_urls = list(session.crop_urls)
            session.crop_urls.clear()
            session.events.clear()
            session.latest_frame = None

        for crop_url in crop_urls:
            self.media.remove_crop(crop_url)

    def stop_all(self) -> None:
        with self.lock:
            session_ids = list(self.sessions)

        for session_id in session_ids:
            try:
                self.delete(session_id)
            except KeyError:
                pass
