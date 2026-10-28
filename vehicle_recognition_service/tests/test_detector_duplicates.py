"""Vehicle deduplication before classification; no weights or inference needed."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
from types import SimpleNamespace
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from recognition_service.inference.detector import Detection, VehicleDetector
from recognition_service.inference.pipeline import RecognitionPipeline


class DuplicateTests(unittest.TestCase):
    def setUp(self):
        self.detector = VehicleDetector.__new__(VehicleDetector)
        self.detector.confidence = .2
        self.detector.device = None
        self.detector.model = Mock()
        self.detector.model.names = {0: 'person', 2: 'car', 5: 'bus', 7: 'truck'}

    def box(self, coordinates, category, confidence):
        return SimpleNamespace(xyxy=np.array([coordinates]), cls=np.array([category]),
                               conf=np.array([confidence]), id=None)

    def test_cross_class_duplicate_classified_once(self):
        self.detector.model.predict.return_value = [SimpleNamespace(boxes=[
            self.box([10, 10, 90, 90], 2, .7),
            self.box([12, 12, 92, 92], 7, .95),
        ])]
        classifier = Mock()
        classifier.classify.return_value = {'model': {'label': 'KIA Bongo3', 'confidence': .99}}
        result = RecognitionPipeline(self.detector, classifier).process_image(np.zeros((120, 120, 3), np.uint8))
        self.assertEqual(len(result), 1)
        classifier.classify.assert_called_once()
        args = self.detector.model.predict.call_args.kwargs
        self.assertEqual(args['classes'], [2, 5, 7])
        self.assertTrue(args['agnostic_nms'])
        self.assertEqual(args['iou'], .5)
        # The higher-confidence truck box wins before padding.
        self.assertEqual(result[0].vehicle_bbox.x1, 4)

    def test_separate_and_partially_overlapping_vehicles_remain(self):
        boxes = [Detection(0, 0, 100, 100, 'car', .9),
                 Detection(60, 0, 160, 100, 'car', .8),
                 Detection(200, 0, 300, 100, 'truck', .7)]
        self.assertEqual(self.detector._suppress_duplicates(boxes), boxes)

    def test_identical_boxes_keep_strongest_and_reject_invalid(self):
        strongest = Detection(0, 0, 100, 100, 'truck', .95, 42)
        result = self.detector._suppress_duplicates([
            Detection(0, 0, 100, 100, 'truck', .6), strongest,
            Detection(0, 0, 0, 100, 'car', .99)])
        self.assertEqual(result, [strongest])
        self.assertEqual(result[0].track_id, 42)
        self.assertEqual(self.detector._suppress_duplicates([]), [])

    def test_tracking_applies_nms_before_tracker(self):
        self.detector.model.track.return_value = []
        self.assertEqual(self.detector.track(np.zeros((10, 10, 3), np.uint8)), [])
        args = self.detector.model.track.call_args.kwargs
        self.assertTrue(args['agnostic_nms'])
        self.assertEqual(args['classes'], [2, 5, 7])
        self.assertEqual(args['iou'], .5)
        self.assertTrue(args['persist'])
