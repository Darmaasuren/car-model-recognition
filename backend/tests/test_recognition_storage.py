"""Exercise storage transactions without contacting the source service or loading models."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
with patch.dict(os.environ, {'API_PREFIX': '/api', 'API_KEY': 'test',
                             'CORS_ORIGINS': 'http://localhost:5173'}):
    from app.models.vehicle_recognition import VehicleRecognition as Row
    from app.services.service_comparison import compare_batch, ServiceComparisonError
    from app.services.recognition_store import RecognitionStore


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Row.__table__.create(self.engine)
        self.factory = sessionmaker(self.engine)
        self.record = {'_id': 'one', 'plate': '1234УБА', 'mark': 'Toyota',
                       'model': 'Prius', 'color': 'Цагаан', 'typeNameEng': 'car',
                       'full_photo': 'uploads/one.jpg', 'event_date': '2026-09-23T02:00:00Z'}
        self.result = {'recordId': 'one', 'imageUrl': '/media/crops/one.jpg',
                       'imageWidth': 1920, 'imageHeight': 1080, 'imageStatus': 'OK',
                       'modelStatus': 'MATCH', 'prediction': {
                           'vehicleBbox': {'x1': 10, 'y1': 20, 'x2': 210, 'y2': 120},
                           'model': {'label': 'Toyota Prius', 'confidence': .97}},
                       'seatbelt': {'status': 'completed', 'image': {'width': 200, 'height': 100},
                                    'detections': [{'className': 'seatbelt', 'confidence': .95,
                                                    'bbox': [1, 2, 30, 40]}]}}

    def tearDown(self):
        self.engine.dispose()

    def run_batch(self, records, process):
        with patch('app.services.service_comparison.fetch_records', return_value=records), \
             patch('app.services.service_comparison.compare_one', side_effect=process):
            return compare_batch(object(), db_sessions=self.factory)

    def test_batch_saved_before_images_and_duplicate_updates_same_row(self):
        def process(record, pipeline):
            with self.factory() as db:
                rows = db.scalars(select(Row)).all()
                self.assertEqual(len(rows), 2)
            return self.result
        records = [self.record, {**self.record, '_id': 'two'}]
        self.run_batch(records, process)
        self.run_batch(records, process)
        with self.factory() as db:
            rows = db.scalars(select(Row)).all()
            self.assertEqual(len(rows), 2)
            row = rows[0]
            self.assertEqual(row.status, 'completed')
            self.assertEqual(row.attempt_count, 2)
            self.assertEqual(row.source_model, 'Prius')
            self.assertEqual(row.image_width, 1920)
            self.assertEqual(row.vehicle_bbox['box']['x1'], 10)
            self.assertEqual(row.seatbelt_result['coordinateSpace'], 'vehicle_crop')
            self.assertEqual(row.seatbelt_result['detections'][0]['bbox'], [1, 2, 30, 40])
            self.assertEqual(row.seatbelt_result['cropOrigin']['y1'], 20)
            self.assertEqual(row.local_image_path, 'crops/one.jpg')

    def test_failure_persisted_other_records_continue_and_retry_clears_error(self):
        def process(record, pipeline):
            if record['_id'] == 'one':
                raise ServiceComparisonError('Image unavailable')
            return self.result
        result = self.run_batch([self.record, {**self.record, '_id': 'two'}], process)
        self.assertEqual(result['count'], 2)
        with self.factory() as db:
            row = db.scalar(select(Row).where(Row.source_record_id == 'one'))
            self.assertEqual(row.status, 'failed')
            self.assertEqual(row.last_error, 'Image unavailable')
        self.run_batch([self.record], lambda *args: self.result)
        with self.factory() as db:
            row = db.scalar(select(Row).where(Row.source_record_id == 'one'))
            self.assertEqual(row.status, 'completed')
            self.assertIsNone(row.last_error)
            self.assertEqual(row.attempt_count, 2)

    def test_missing_id_or_invalid_date_not_processed(self):
        process = unittest.mock.Mock()
        result = self.run_batch([{}, {**self.record, 'event_date': 'invalid'}], process)
        self.assertTrue(all('error' in item for item in result['items']))
        process.assert_not_called()

    def test_active_record_cannot_be_claimed_twice(self):
        store = RecognitionStore(self.factory)
        store.enqueue(self.record)
        self.assertTrue(store.start(self.record))
        self.assertFalse(store.start(self.record))

    def test_no_vehicle_is_completed_not_failed(self):
        result = {**self.result, 'prediction': None, 'imageStatus': 'NO_VEHICLE_DETECTED',
                  'seatbelt': {'status': 'skipped', 'detections': []}}
        self.run_batch([self.record], lambda *args: result)
        with self.factory() as db:
            row = db.scalar(select(Row))
            self.assertEqual(row.status, 'completed')
            self.assertIsNone(row.vehicle_bbox)
            self.assertEqual(row.comparison['imageStatus'], 'NO_VEHICLE_DETECTED')

    def test_history_pagination_and_result_mapping(self):
        self.run_batch([self.record, {**self.record, '_id': 'two'}], lambda *args: self.result)
        store = RecognitionStore(self.factory)
        first = store.list_results(0, 1)
        second = store.list_results(1, 1)
        self.assertEqual(first['total'], 2)
        self.assertEqual(first['count'], 1)
        self.assertEqual(first['items'][0]['recordId'], 'two')
        item = second['items'][0]
        self.assertEqual(item['sourceModel'], 'Prius')
        self.assertEqual(item['modelStatus'], 'MATCH')
        self.assertEqual(item['prediction'], self.result['prediction'])
        self.assertEqual(item['seatbelt']['detections'], self.result['seatbelt']['detections'])
        self.assertEqual(store.list_results(2, 1)['items'], [])

    def test_history_pending_failed_and_missing_image(self):
        store = RecognitionStore(self.factory)
        store.enqueue(self.record)
        item = store.list_results()['items'][0]
        self.assertEqual(item['imageStatus'], 'pending')
        self.assertIsNone(item['prediction'])
        self.assertIsNone(item['imageUrl'])
        store.start(self.record)
        store.fail('one', 'Download failed')
        item = store.list_results()['items'][0]
        self.assertEqual(item['error'], 'Download failed')
        self.assertEqual(item['imageStatus'], 'failed')
        self.run_batch([self.record], lambda *args: self.result)
        with patch('app.services.recognition_store.Path.is_file', return_value=False):
            self.assertIsNone(store.list_results()['items'][0]['imageUrl'])
        with patch('app.services.recognition_store.Path.is_file', return_value=True):
            self.assertEqual(store.list_results()['items'][0]['imageUrl'], '/media/crops/one.jpg')

    def test_empty_history(self):
        self.assertEqual(RecognitionStore(self.factory).list_results(),
                         {'items': [], 'count': 0, 'total': 0, 'offset': 0, 'limit': 20})
