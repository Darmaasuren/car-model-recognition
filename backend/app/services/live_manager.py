from collections import deque
from threading import Lock, Thread
from time import sleep

import cv2

from app.schemas.recognition import RecognitionEvent
from app.services.pipeline import (
    RecognitionPipeline,
    TrackingState,
)


class LiveSession:
    def __init__(
        self,
        camera_id: str,
        source: str,
    ):
        self.camera_id = camera_id
        self.source = source
        self.latest_frame: bytes | None = None
        self.events = deque(maxlen=100)
        self.event_sequence = 0
        self.running = False
        self.error: str | None = None
        self.worker: Thread | None = None
        self.lock = Lock()
        self.tracking_state = TrackingState()


class LiveManager:
    def __init__(
        self,
        pipeline: RecognitionPipeline,
        camera_sources: dict[str, str],
    ):
        self.pipeline = pipeline
        self.sessions = {
            camera_id: LiveSession(
                camera_id,
                source,
            )
            for camera_id, source
            in camera_sources.items()
        }

    def get_session(
        self,
        camera_id: str,
    ) -> LiveSession:
        session = self.sessions.get(camera_id)

        if session is None or not session.source:
            raise KeyError(
                f"Camera олдсонгүй: {camera_id}"
            )

        return session

    def start(self, camera_id: str) -> None:
        session = self.get_session(camera_id)

        with session.lock:
            if session.running:
                return

            session.running = True
            session.error = None
            session.worker = Thread(
                target=self._run,
                args=(session,),
                daemon=True,
            )
            session.worker.start()

    @staticmethod
    def _capture_source(source: str):
        return int(source) if source.isdecimal() else source

    def _run(self, session: LiveSession):
        capture = cv2.VideoCapture(
            self._capture_source(session.source)
        )

        try:
            if not capture.isOpened():
                raise RuntimeError(
                    f"Камерын stream нээгдсэнгүй: {session.camera_id}"
                )

            while session.running:
                success, frame = capture.read()

                if not success:
                    raise RuntimeError(
                        f"Камераас дүрс уншиж чадсангүй: {session.camera_id}"
                    )

                processed, results = (
                    self.pipeline.process_tracked_frame(
                        frame,
                        session.tracking_state,
                    )
                )

                success, encoded = cv2.imencode(
                    ".jpg",
                    processed,
                )

                if success:
                    with session.lock:
                        session.latest_frame = (
                            encoded.tobytes()
                        )

                for result in results:
                    event = RecognitionEvent(
                        camera_id=session.camera_id,
                        result=result,
                    )

                    with session.lock:
                        session.event_sequence += 1
                        session.events.append((
                            session.event_sequence,
                            event,
                        ))
        except Exception as error:
            with session.lock:
                session.error = str(error)
        finally:
            with session.lock:
                session.running = False
            capture.release()

    def stream(self, camera_id: str):
        session = self.get_session(camera_id)
        self.start(camera_id)

        while True:
            with session.lock:
                frame = session.latest_frame
                running = session.running
                error = session.error

            if not running:
                if error:
                    raise RuntimeError(error)
                return

            if frame is None:
                sleep(0.05)
                continue

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + frame
                + b"\r\n"
            )

            sleep(0.03)

    def events_after(
        self,
        camera_id: str,
        sequence: int,
    ):
        session = self.get_session(camera_id)
        self.start(camera_id)

        with session.lock:
            return [
                (number, event)
                for number, event in session.events
                if number > sequence
            ]

    def stop_all(self):
        for session in self.sessions.values():
            session.running = False

        for session in self.sessions.values():
            if session.worker is not None:
                session.worker.join(timeout=2)
