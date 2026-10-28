"""HTTP transport only: authentication, timeouts, uploads and streams."""
from urllib.parse import quote
import requests
from app.core.config import settings


class RecognitionServiceError(RuntimeError):
    def __init__(self, message="Recognition service-тэй холбогдож чадсангүй.", status_code=503):
        super().__init__(message)
        self.status_code = status_code


class RecognitionClient:
    def __init__(self, url=None, api_key=None):
        self.url = (url or settings.recognition_url).rstrip("/")
        self.api_key = api_key or settings.recognition_api_key

    def request(self, method, path, **kwargs):
        try:
            response = requests.request(method, self.url + path,
                headers={"API-Key": self.api_key}, timeout=kwargs.pop("timeout", (5, settings.recognition_timeout)),
                allow_redirects=False, **kwargs)
        except requests.RequestException as error:
            raise RecognitionServiceError() from error
        if not 200 <= response.status_code < 300:
            code = response.status_code
            response.close()
            public_code = code if code in {404, 409, 413, 422, 429} else 503
            messages = {404: "Recognition session олдсонгүй.", 409: "Танилтын event түүх дууссан. Session дахин үүсгэнэ үү.",
                        413: "Файл хэмжээ хэтэрсэн.", 422: "Зураг эсвэл координат буруу байна.",
                        429: "Recognition service завгүй байна."}
            raise RecognitionServiceError(messages.get(code, "Recognition service ажиллах боломжгүй байна."), public_code)
        return response

    def json(self, method, path, **kwargs):
        with self.request(method, path, **kwargs) as response:
            try:
                return response.json()
            except ValueError as error:
                raise RecognitionServiceError("Recognition service-ийн хариу буруу байна.", 502) from error

    def health(self):
        return self.json("GET", "/health", timeout=(3, 5))

    def metadata(self):
        return self.json("GET", "/metadata")

    def recognize_image(self, filename, data, content_type):
        return self.json("POST", "/inference/image", files={"file": (filename, data, content_type)})

    def tracking_events(self, path, sequence):
        return self.json("GET", path, params={"after": sequence})

    def create_video(self, path):
        with path.open("rb") as source:
            data = self.json("POST", "/video/sessions", files={"file": (path.name, source, "application/octet-stream")})
        return data["sessionId"]

    def delete_video(self, session_id):
        with self.request("DELETE", f"/video/sessions/{quote(session_id, safe='')}"):
            pass

    def stream(self, path):
        response = self.request("GET", path, stream=True)
        def chunks():
            try:
                yield from response.iter_content(chunk_size=4096)
            finally:
                response.close()
        return chunks(), response.close

