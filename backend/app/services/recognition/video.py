"""Remote video session access and ownership. No video decoding or inference."""
from urllib.parse import quote
from fastapi import HTTPException
from app.models.video_session import RecognitionSession
from app.services.recognition.client import RecognitionServiceError


class VideoSessionManager:
    def __init__(self, client, results, factory):
        self.client, self.results, self.factory = client, results, factory

    def create(self, path, user_id):
        session_id = self.client.create_video(path)
        try:
            with self.factory() as db, db.begin():
                db.add(RecognitionSession(session_id=session_id, user_id=user_id))
        except Exception:
            try:
                self.client.delete_video(session_id)
            except RecognitionServiceError:
                pass  # Remote TTL reclaims an orphan even when the service is unreachable.
            raise
        return session_id

    def authorize(self, session_id, user_id):
        with self.factory() as db:
            row = db.get(RecognitionSession, session_id)
            if row is None or row.user_id != user_id:
                raise HTTPException(404, "Video session олдсонгүй.")

    def stream(self, session_id):
        return self.client.stream(f"/video/sessions/{quote(session_id, safe='')}/stream")

    def poll(self, session_id, sequence):
        return self.results.tracking_events(f"/video/sessions/{quote(session_id, safe='')}/events", sequence)

    def delete(self, session_id):
        try:
            self.client.delete_video(session_id)
        except RecognitionServiceError as error:
            if error.status_code != 404:
                raise
        with self.factory() as db, db.begin():
            row = db.get(RecognitionSession, session_id)
            if row:
                db.delete(row)
