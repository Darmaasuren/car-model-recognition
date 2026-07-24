from dataclasses import dataclass, field
from datetime import datetime
from math import hypot
from uuid import uuid4

import cv2

from schemas import BoundingBox, Prediction, RecognitionResult
from services.classifier import VehicleClassifier
from services.detector import Detection, VehicleDetector
from services.media import MediaService


@dataclass
class TrackingState:
    recognized_track_ids: set[int] = field(
        default_factory=set
    )


class RecognitionPipeline:
    padding_ratio = 0.10
    roi_ratio = (0.20, 0.60, 1.00, 0.97)

    def __init__(
        self,
        detector: VehicleDetector,
        classifier: VehicleClassifier,
        media: MediaService,
    ):
        self.detector = detector
        self.classifier = classifier
        self.media = media

    def process_image(
        self,
        frame,
    ) -> list[RecognitionResult]:
        detections = self.detector.detect(frame)

        return self._classify_detections(
            frame=frame,
            detections=detections,
            tracking_state=None,
        )

    def process_plate_event(
        self,
        frame,
        plate_bbox: BoundingBox,
        persist_crop: bool = False,
    ) -> tuple[BoundingBox, float, RecognitionResult] | None:
        detections = self.detector.detect(frame)

        match = self._match_plate_to_vehicle(
            frame=frame,
            plate_bbox=plate_bbox,
            detections=detections,
        )

        if match is None:
            return None

        detection, match_score = match

        results = self._classify_detections(
            frame=frame,
            detections=[detection],
            tracking_state=None,
            persist_crop=persist_crop,
        )

        if not results:
            return None

        frame_height, frame_width = frame.shape[:2]

        x1, y1, x2, y2 = self._pad_box(
            detection,
            frame_width,
            frame_height,
        )

        padded_vehicle_bbox = BoundingBox(
            x1=x1,
            y1=y1,
            x2=x2,
            y2=y2,
        )

        return (
            padded_vehicle_bbox,
            match_score,
            results[0],
        )
        # frame_height, frame_width = frame.shape[:2]

        # crop_x1 = max(0, detection.x1)
        # crop_y1 = max(0, detection.y1)
        # crop_x2 = min(frame_width, detection.x2)
        # crop_y2 = min(frame_height, detection.y2)

        # vehicle_crop = frame[
        #     crop_y1:crop_y2,
        #     crop_x1:crop_x2,
        # ]

        # if vehicle_crop.size == 0:
        #     return None

        # vehicle_crop_base64 = (
        #     self.media.encode_image_data_url(vehicle_crop)
        # )

        return (
            detection,
            match_score,
            results[0],
            # vehicle_crop_base64,
        )

    def process_tracked_frame(
        self,
        frame,
        tracking_state: TrackingState,
    ) -> tuple[object, list[RecognitionResult]]:
        detections = self.detector.track(frame)
        processed_frame = frame.copy()

        height, width = frame.shape[:2]
        roi = self._get_roi(width, height)

        cv2.rectangle(
            processed_frame,
            (roi[0], roi[1]),
            (roi[2], roi[3]),
            (255, 0, 0),
            1,
        )

        eligible = []

        for detection in detections:
            if detection.track_id is None:
                continue

            if (
                detection.track_id
                in tracking_state.recognized_track_ids
            ):
                continue

            if not self._inside_roi(detection, roi):
                continue

            eligible.append(detection)

            cv2.rectangle(
                processed_frame,
                (detection.x1, detection.y1),
                (detection.x2, detection.y2),
                (0, 255, 0),
                2,
            )

        results = self._classify_detections(
            frame=frame,
            detections=eligible,
            tracking_state=tracking_state,
        )

        return processed_frame, results

    def _match_plate_to_vehicle(
        self,
        frame,
        plate_bbox: BoundingBox,
        detections: list[Detection],
    ):
        frame_height, frame_width = frame.shape[:2]

        plate_area = (
            (plate_bbox.x2 - plate_bbox.x1)
            * (plate_bbox.y2 - plate_bbox.y1)
        )

        if plate_area <= 0:
            return None

        plate_center_x = (plate_bbox.x1 + plate_bbox.x2) / 2
        plate_center_y = (plate_bbox.y1 + plate_bbox.y2) / 2

        candidates = []

        for detection in detections:
            vehicle_box = self._expand_box(
                detection=detection,
                frame_width=frame_width,
                frame_height=frame_height,
                ratio=0.05,
            )

            vx1, vy1, vx2, vy2 = vehicle_box

            center_inside = (
                vx1 <= plate_center_x <= vx2
                and vy1 <= plate_center_y <= vy2
            )

            intersection_x1 = max(plate_bbox.x1, vx1)
            intersection_y1 = max(plate_bbox.y1, vy1)
            intersection_x2 = min(plate_bbox.x2, vx2)
            intersection_y2 = min(plate_bbox.y2, vy2)

            intersection_width = max(
                0,
                intersection_x2 - intersection_x1,
            )
            intersection_height = max(
                0,
                intersection_y2 - intersection_y1,
            )

            intersection_area = (
                intersection_width * intersection_height
            )

            plate_coverage = intersection_area / plate_area

            if not center_inside or plate_coverage < 0.8:
                continue

            vehicle_center_x = (vx1 + vx2) / 2
            vehicle_center_y = (vy1 + vy2) / 2

            distance = hypot(
                plate_center_x - vehicle_center_x,
                plate_center_y - vehicle_center_y,
            )

            vehicle_diagonal = max(
                hypot(vx2 - vx1, vy2 - vy1),
                1,
            )

            center_proximity = 1 - min(
                distance / vehicle_diagonal,
                1,
            )

            match_score = (
                plate_coverage * 0.7
                + center_proximity * 0.2
                + detection.confidence * 0.1
            )

            vehicle_area = (vx2 - vx1) * (vy2 - vy1)

            candidates.append(
                (
                    match_score,
                    -vehicle_area,
                    detection,
                )
            )

        if not candidates:
            return None

        candidates.sort(
            key=lambda candidate: (
                candidate[0],
                candidate[1],
            ),
            reverse=True,
        )

        match_score, _, detection = candidates[0]

        return detection, match_score

    def _classify_detections(
        self,
        frame,
        detections: list[Detection],
        tracking_state: TrackingState | None,
        persist_crop: bool = True,
    ) -> list[RecognitionResult]:
        height, width = frame.shape[:2]
        recognition_results = []

        for detection in detections:
            x1, y1, x2, y2 = self._pad_box(
                detection,
                width,
                height,
            )

            crop = frame[y1:y2, x1:x2]

            if crop.size == 0:
                continue

            predictions = self.classifier.classify(crop)
            event_id = uuid4().hex

            crop_url = None

            if persist_crop:
                crop_url = self.media.save_crop(
                    crop,
                    event_id,
                )

            recognition_results.append(
                RecognitionResult(
                    event_id=event_id,
                    track_id=detection.track_id,
                    detected_at=datetime.now().astimezone(),
                    crop_url=crop_url,
                    model=self._prediction(
                        predictions.get("model")
                    ),
                    color=self._prediction(
                        predictions.get("color")
                    ),
                    vehicle_type=self._prediction(
                        predictions.get("type")
                        or predictions.get("vehicle_type")
                    ),
                    view=self._prediction(
                        predictions.get("view")
                    ),
                )
            )

            if (
                tracking_state is not None
                and detection.track_id is not None
            ):
                tracking_state.recognized_track_ids.add(
                    detection.track_id
                )

        return recognition_results

    @staticmethod
    def _prediction(value):
        if value is None:
            return None

        return Prediction(**value)

    def _pad_box(
        self,
        detection: Detection,
        frame_width: int,
        frame_height: int,
    ):
        width = detection.x2 - detection.x1
        height = detection.y2 - detection.y1

        padding_x = int(width * self.padding_ratio)
        padding_y = int(height * self.padding_ratio)

        return (
            max(0, detection.x1 - padding_x),
            max(0, detection.y1 - padding_y),
            min(
                frame_width,
                detection.x2 + padding_x,
            ),
            min(
                frame_height,
                detection.y2 + padding_y,
            ),
        )

    @staticmethod
    def _expand_box(
        detection: Detection,
        frame_width: int,
        frame_height: int,
        ratio: float,
    ):
        width = detection.x2 - detection.x1
        height = detection.y2 - detection.y1

        padding_x = int(width * ratio)
        padding_y = int(height * ratio)

        return (
            max(0, detection.x1 - padding_x),
            max(0, detection.y1 - padding_y),
            min(frame_width, detection.x2 + padding_x),
            min(frame_height, detection.y2 + padding_y),
        )

    def _get_roi(
        self,
        width: int,
        height: int,
    ):
        x1, y1, x2, y2 = self.roi_ratio

        return (
            int(width * x1),
            int(height * y1),
            int(width * x2),
            int(height * y2),
        )

    @staticmethod
    def _inside_roi(
        detection: Detection,
        roi,
    ) -> bool:
        rx1, ry1, rx2, ry2 = roi

        return (
            detection.x1 >= rx1
            and detection.y1 >= ry1
            and detection.x2 <= rx2
            and detection.y2 <= ry2
        )
