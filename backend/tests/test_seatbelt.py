import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.seatbelt_client import check_seatbelt


class SeatbeltTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "SEATBELT_URL": "http://seatbelt:8000/predict",
            "SEATBELT_VIEW_MIN_CONFIDENCE": "0.90",
        })
        self.env.start()
        self.frame = np.arange(100 * 120 * 3, dtype=np.uint8).reshape(100, 120, 3)
        self.prediction = SimpleNamespace(
            view=SimpleNamespace(label="front_side", confidence=.98),
            vehicle_bbox=SimpleNamespace(x1=10, y1=20, x2=90, y2=80),
        )

    def tearDown(self):
        self.env.stop()

    def response(self, detections=None, code=200):
        response = MagicMock()
        response.__enter__.return_value = response
        response.status_code = code
        response.json.return_value = {
            "image": {"width": 80, "height": 60},
            "detections": detections or [], "count": len(detections or []),
        }
        return response

    def detection(self, label):
        return {"class_id": 1, "class_name": label, "confidence": .94, "bbox": [1, 2, 30, 40]}

    def test_original_resolution_crop_is_sent_as_lossless_png(self):
        detections = [self.detection("person-seatbelt"), self.detection("person-noseatbelt")]
        with patch("app.services.seatbelt_client.requests.post", return_value=self.response(detections)) as post:
            result = check_seatbelt(self.frame, self.prediction)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(result["detections"]), 2)
        request = post.call_args.kwargs
        self.assertEqual(request["headers"], {"Content-Type": "image/png"})
        decoded = cv2.imdecode(np.frombuffer(request["data"], np.uint8), cv2.IMREAD_COLOR)
        np.testing.assert_array_equal(decoded, self.frame[20:80, 10:90])

    def test_non_front_low_confidence_and_missing_prediction_do_not_call(self):
        with patch("app.services.seatbelt_client.requests.post") as post:
            self.assertEqual(check_seatbelt(self.frame, None)["status"], "skipped")
            self.prediction.view.label = "rear_side"
            self.assertEqual(check_seatbelt(self.frame, self.prediction)["status"], "skipped")
            self.prediction.view.label = "front_side"
            self.prediction.view.confidence = .8
            self.assertEqual(check_seatbelt(self.frame, self.prediction)["status"], "skipped")
            post.assert_not_called()

    def test_empty_and_windshield_only_are_unknown(self):
        for detections in ([], [self.detection("windshield")], [self.detection("seatbelt")]):
            with patch("app.services.seatbelt_client.requests.post", return_value=self.response(detections)):
                self.assertEqual(check_seatbelt(self.frame, self.prediction)["status"], "unknown")

    def test_busy_retries_once_and_recovers(self):
        with patch("app.services.seatbelt_client.requests.post",
                   side_effect=[self.response(code=503), self.response()]) as post:
            with patch("app.services.seatbelt_client.sleep"):
                self.assertEqual(check_seatbelt(self.frame, self.prediction)["status"], "unknown")
            self.assertEqual(post.call_count, 2)

    def test_persistent_busy_and_timeout_return_error(self):
        with patch("app.services.seatbelt_client.requests.post", return_value=self.response(code=503)) as post:
            with patch("app.services.seatbelt_client.sleep"):
                self.assertEqual(check_seatbelt(self.frame, self.prediction)["status"], "error")
            self.assertEqual(post.call_count, 2)
        with patch("app.services.seatbelt_client.requests.post", side_effect=requests.Timeout):
            self.assertEqual(check_seatbelt(self.frame, self.prediction)["status"], "error")

    def test_invalid_response_and_coordinates_are_errors(self):
        response = self.response()
        response.json.return_value = {"detections": []}
        with patch("app.services.seatbelt_client.requests.post", return_value=response):
            self.assertEqual(check_seatbelt(self.frame, self.prediction)["status"], "error")
        response = self.response([self.detection("person-seatbelt")])
        response.json.return_value["detections"][0]["bbox"] = [0, 0, 1000, 1000]
        with patch("app.services.seatbelt_client.requests.post", return_value=response):
            self.assertEqual(check_seatbelt(self.frame, self.prediction)["status"], "error")

    def test_file_image_enriches_each_vehicle_and_serializes_for_frontend(self):
        from datetime import datetime, timezone
        from app.schemas.recognition import BoundingBox, Prediction, RecognitionResult, InferenceResponse
        from app.services.seatbelt_client import recognize_file_image

        def vehicle(event, label):
            return RecognitionResult(
                event_id=event, detected_at=datetime.now(timezone.utc),
                view=Prediction(label=label, confidence=.98),
                vehicle_bbox=BoundingBox(x1=10, y1=20, x2=90, y2=80),
            )

        front, rear = vehicle("front", "front_side"), vehicle("rear", "rear_side")
        pipeline = SimpleNamespace(process_image=lambda frame: [front, rear])
        with patch("app.services.seatbelt_client.requests.post",
                   return_value=self.response([self.detection("person-seatbelt")])) as post:
            results = recognize_file_image(pipeline, self.frame)
        post.assert_called_once()
        payload = InferenceResponse(results=results).model_dump(mode="json", by_alias=True)
        self.assertEqual(payload["results"][0]["seatbelt"]["detections"][0]["className"], "person-seatbelt")
        self.assertEqual(payload["results"][1]["seatbelt"]["status"], "skipped")

    def test_video_enrichment_preserves_event_and_error_is_serializable(self):
        from datetime import datetime, timezone
        from app.schemas.recognition import BoundingBox, Prediction, RecognitionResult, VideoRecognitionEvent
        from app.services.seatbelt_client import enrich_results

        result = RecognitionResult(
            event_id="tracked-event", track_id=7, detected_at=datetime.now(timezone.utc),
            view=Prediction(label="front_side", confidence=.98),
            vehicle_bbox=BoundingBox(x1=10, y1=20, x2=90, y2=80),
        )
        with patch("app.services.seatbelt_client.requests.post", side_effect=requests.Timeout):
            enriched = enrich_results(self.frame, [result])
        payload = VideoRecognitionEvent(session_id="video", result=enriched[0]).model_dump(
            mode="json", by_alias=True)
        self.assertEqual(payload["result"]["eventId"], "tracked-event")
        self.assertEqual(payload["result"]["trackId"], 7)
        self.assertEqual(payload["result"]["seatbelt"]["status"], "error")

    def test_service_comparison_keeps_main_result_on_seatbelt_failure(self):
        with patch.dict(os.environ, {"API_PREFIX": "/api", "API_KEY": "test",
                                    "CORS_ORIGINS": "http://localhost:5173"}):
            from app.services.service_comparison import compare_record
        self.prediction.model = SimpleNamespace(label="Toyota Prius", confidence=.95)
        self.prediction.color = SimpleNamespace(label="white", confidence=.96)
        self.prediction.vehicle_type = SimpleNamespace(label="car", confidence=.99)
        self.prediction.model_dump = lambda **kw: {"view": {"label": "front_side", "confidence": .98}}
        pipeline = SimpleNamespace(
            process_image=lambda frame: [self.prediction],
            classifier=SimpleNamespace(label_groups={
                "model": ["Toyota Prius"], "color": ["white"], "type": ["car"],
            }),
        )
        with patch("app.services.seatbelt_client.requests.post", side_effect=requests.ConnectionError):
            result = compare_record({"mark": "Toyota", "model": "Prius", "color": "цагаан"},
                                    self.frame, pipeline)
        self.assertEqual(result["imageStatus"], "OK")
        self.assertEqual(result["modelStatus"], "MATCH")
        self.assertIsNotNone(result["prediction"])
        self.assertEqual(result["seatbelt"]["status"], "error")


if __name__ == "__main__":
    unittest.main()
