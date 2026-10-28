"""Exercise real crop encoding, result serialization and database persistence together."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import uuid4

import cv2
import numpy as np
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
with patch.dict(os.environ, {'API_PREFIX': '/api', 'API_KEY': 'test', 'CORS_ORIGINS': 'http://localhost:5173'}):
    from app.models.recognition import VehicleRecognition as Row
    from app.schemas.seatbelt import ServiceResponse
    from app.services.seatbelt import SeatbeltService
    from app.services.media import MediaService
    from app.services.recognition.results import RecognitionResults
    from app.services.comparison.compare import compare_one
    from app.services.comparison.store import RecognitionStore


class ImagePathPersistenceTests(unittest.TestCase):
    def test_real_seatbelt_serialization_and_files_survive_database_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            engine = create_engine('sqlite:///' + str(root/'test.db'))
            self.addCleanup(engine.dispose)
            Row.__table__.create(engine)
            store = RecognitionStore(sessionmaker(engine))
            event_id = str(uuid4())
            remote = Mock()
            remote.recognize_image.return_value = {
                'modelVersion': 'test', 'labelGroups': {'model': ['Prius'], 'color': ['white'], 'type': ['car']},
                'results': [{'eventId': event_id, 'detectedAt': '2026-10-13T00:00:00Z',
                             'vehicleBbox': {'x1': 5, 'y1': 5, 'x2': 45, 'y2': 35},
                             'view': {'label': 'front_side', 'confidence': .99},
                             'model': {'label': 'Prius', 'confidence': .99}}]}
            with patch.dict(os.environ, {'SEATBELT_ENABLED': 'true'}):
                seatbelt = SeatbeltService(client=Mock())
            seatbelt.client.predict.return_value = ServiceResponse.model_validate({
                'width': 40, 'height': 30, 'windshields': [
                    {'bbox': [2, 3, 20, 15], 'crop_bbox': [1, 2, 22, 17], 'confidence': .99}],
                'detections': [
                    {'class_id': 1, 'label': 'person_seatbelt', 'confidence': .94,
                     'bbox': [2.2, 3.2, 10.8, 14.8], 'windshield_index': 0, 'role': 'driver',
                     'role_confidence': .98, 'person_confidence': .87, 'phone_usage': False, 'phone_confidence': .93},
                    {'class_id': 0, 'label': 'person_no_seatbelt', 'confidence': .89,
                     'bbox': [12, 3, 20, 15], 'windshield_index': 0, 'role': 'passenger'}]})
            recognition = RecognitionResults(MediaService(root/'uploads', root/'crops', root/'outputs'), remote, seatbelt)
            record = {'_id': 'source-1', 'full_photo': 'uploads/car.jpg'}
            store.enqueue(record)
            self.assertTrue(store.start(record))
            frame = np.zeros((50, 60, 3), np.uint8)
            frame[8:20, 7:16] = 240
            with patch('app.services.comparison.compare.settings') as settings, \
                 patch('app.services.comparison.compare.image_url_for', return_value='https://example.test/main/uploads/car.jpg'), \
                 patch('app.services.comparison.compare.download_frame', return_value=frame):
                settings.full_photo_dir = root/'full_photo'
                result = compare_one(record, recognition)
            store.complete(record['_id'], result)
            with sessionmaker(engine)() as db:
                row = db.scalar(select(Row))
                self.assertEqual(row.status, 'completed')
                self.assertTrue((root/row.local_image_path).is_file())
                self.assertEqual(row.source_image_path, record['full_photo'])
                self.assertEqual(row.prediction['cropUrl'], f'/media/crop/{event_id}.jpg')
                self.assertTrue((root/'crops'/f'{event_id}.jpg').is_file())
                url = row.seatbelt_result['windshields'][0]['cropUrl']
                self.assertEqual(url, f'/media/windshields/{event_id}_windshield_0.jpg')
                self.assertTrue((root/'windshields'/Path(url).name).is_file())
                self.assertEqual(row.prediction['seatbelt']['windshields'][0]['cropUrl'], url)

                people = row.seatbelt_result['detections']
                self.assertEqual(people, row.prediction['seatbelt']['detections'])
                self.assertEqual(people[0]['role'], 'driver')
                self.assertEqual(people[0]['confidence'], .94)
                self.assertEqual(people[0]['phoneUsage'], False)
                self.assertEqual(people[1]['role'], 'passenger')
                for index, person in enumerate(people):
                    self.assertEqual(person['cropUrl'], f'/media/persons/{event_id}_person_{index}.jpg')
                driver = cv2.imread(str(root/'persons'/Path(people[0]['cropUrl']).name))
                passenger = cv2.imread(str(root/'persons'/Path(people[1]['cropUrl']).name))
                self.assertEqual(driver.shape[:2], (12, 9))
                self.assertEqual(passenger.shape[:2], (12, 8))
                self.assertGreater(driver.mean(), 230)
                self.assertLess(passenger.mean(), 5)
            self.assertEqual(store.list_results()['items'][0]['prediction']['seatbelt']['detections'], people)

    def test_person_crop_failure_preserves_predictions(self):
        from types import SimpleNamespace
        media = Mock()
        media.save_person_crop.side_effect = OSError('disk full')
        recognition = RecognitionResults(media, Mock())
        person = {'bbox': [1, 1, 5, 5], 'label': 'person_seatbelt', 'confidence': .95}
        result = SimpleNamespace(event_id=str(uuid4()), seatbelt={'detections': [person]})
        recognition.save_person_crops(np.zeros((10, 10, 3), np.uint8), result)
        self.assertIsNone(person['cropUrl'])
        self.assertEqual(person['cropError'], 'CROP_SAVE_FAILED')
        self.assertEqual(person['confidence'], .95)
