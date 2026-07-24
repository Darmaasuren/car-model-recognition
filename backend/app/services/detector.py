from dataclasses import dataclass
from pathlib import Path

from ultralytics import YOLO


@dataclass(frozen=True)
class Detection:
    x1: int
    y1: int
    x2: int
    y2: int
    class_name: str
    confidence: float
    track_id: int | None = None


class VehicleDetector:
    allowed_classes = {"car", "bus", "truck"}

    def __init__(
        self,
        model_path: Path,
        confidence: float,
        device: str,
    ):
        if not model_path.exists():
            raise FileNotFoundError(
                f"Detector model олдсонгүй: {model_path}"
            )

        self.model = YOLO(str(model_path))
        self.confidence = confidence
        self.device = None if device == "auto" else device

    def detect(self, frame) -> list[Detection]:
        arguments = dict(
            source=frame,
            conf=self.confidence,
            verbose=False,
        )
        if self.device is not None:
            arguments["device"] = self.device
        results = self.model.predict(**arguments)

        return self._convert_results(results)

    def track(self, frame) -> list[Detection]:
        arguments = dict(
            source=frame,
            conf=self.confidence,
            persist=True,
            verbose=False,
        )
        if self.device is not None:
            arguments["device"] = self.device
        results = self.model.track(**arguments)

        return self._convert_results(results)

    def _convert_results(self, results) -> list[Detection]:
        detections: list[Detection] = []

        for result in results:
            if result.boxes is None:
                continue

            for box in result.boxes:
                class_id = int(box.cls[0].item())
                class_name = self.model.names[class_id]

                if class_name not in self.allowed_classes:
                    continue

                x1, y1, x2, y2 = map(
                    int,
                    box.xyxy[0].tolist(),
                )

                track_id = None

                if box.id is not None:
                    track_id = int(box.id[0].item())

                detections.append(
                    Detection(
                        x1=x1,
                        y1=y1,
                        x2=x2,
                        y2=y2,
                        class_name=class_name,
                        confidence=float(
                            box.conf[0].item()
                        ),
                        track_id=track_id,
                    )
                )

        return detections
