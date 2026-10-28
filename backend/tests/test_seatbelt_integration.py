"""Contract, gating and failure isolation for the standalone seatbelt API."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import numpy as np
import requests
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
with patch.dict(os.environ, {'API_PREFIX': '/api', 'API_KEY': 'test', 'CORS_ORIGINS': 'http://localhost:5173'}):
    from app.core.config import settings
    from app.services.seatbelt import SeatbeltService
    from app.schemas.recognition import Prediction, BoundingBox


class SeatbeltTests(unittest.TestCase):
    def setUp(self):
        with patch.dict(os.environ, {'SEATBELT_ENABLED': 'true', 'SEATBELT_API_KEY': 'test-seatbelt'}):
            self.service = SeatbeltService()
        self.crop = np.zeros((100, 200, 3), dtype=np.uint8)
        self.box = BoundingBox(x1=20, y1=30, x2=220, y2=130)
        self.view = Prediction(label='front_side', confidence=.99)
        self.payload = {'image': {'width': 200, 'height': 100}, 'windshield_count': 1, 'person_count': 1,
                        'windshields': [{'id': 7, 'bbox': [10, 10, 190, 90], 'confidence': .95,
                          'persons': [{'person_id': 0, 'bbox': [20, 20, 80, 80], 'confidence': .88,
                            'role': {'value': 'driver', 'confidence': .97},
                            'seatbelt': {'value': True, 'confidence': .94},
                            'phone_usage': {'value': False, 'confidence': .91}}]}]}

    def run_response(self, payload):
        response = MagicMock(status_code=200)
        response.__enter__.return_value = response
        response.json.return_value = payload
        with patch('app.services.seatbelt.client.requests.post', return_value=response) as post:
            result = self.service.analyze(self.crop, self.view, self.box)
            self.assertEqual(post.call_count, 1)
            self.assertIn('file', post.call_args.kwargs['files'])
            self.assertTrue(post.call_args.args[0].endswith('/detect'))
            self.assertEqual(post.call_args.kwargs['headers'], {'API-Key': 'test-seatbelt'})
            self.assertNotIn('params', post.call_args.kwargs)
        return result

    def test_front_view_contract_and_crop_coordinates(self):
        result = self.run_response(self.payload)
        self.assertEqual(result['status'], 'COMPLETED')
        self.assertEqual(result['detections'][0]['windshieldIndex'], 0)
        self.assertEqual(result['detections'][0]['bbox'], (20, 20, 80, 80))
        self.assertEqual(result['image']['vehicleBboxInOriginal']['x1'], 20)

    def test_gates_do_not_contact_service(self):
        with patch('app.services.seatbelt.client.requests.post') as post:
            for view, status in [(None, 'SKIPPED_UNCERTAIN_VIEW'),
                                 (Prediction(label='front_side', confidence=.4), 'SKIPPED_UNCERTAIN_VIEW'),
                                 (Prediction(label='rear_side', confidence=.99), 'SKIPPED_NOT_FRONT')]:
                self.assertEqual(self.service.analyze(self.crop, view, self.box)['status'], status)
            from dataclasses import replace
            self.service.config = replace(self.service.config, enabled=False)
            self.assertEqual(self.service.analyze(self.crop, self.view, self.box)['status'], 'DISABLED')
            post.assert_not_called()

    def test_timeout_is_isolated(self):
        with patch('app.services.seatbelt.client.requests.post', side_effect=requests.Timeout):
            result = self.service.analyze(self.crop, self.view, self.box)
        self.assertEqual(result['status'], 'ERROR')
        self.assertEqual(result['error']['code'], 'SERVICE_TIMEOUT')

    def test_empty_and_invalid_responses(self):
        from copy import deepcopy
        empty = {'image': {'width': 200, 'height': 100}, 'windshield_count': 0, 'person_count': 0, 'windshields': []}
        self.assertEqual(self.run_response(empty)['status'], 'NO_WINDSHIELD')
        no_people = deepcopy(self.payload)
        no_people['windshields'][0]['persons'] = []
        no_people['person_count'] = 0
        self.assertEqual(self.run_response(no_people)['status'], 'NO_OCCUPANT_DETECTED')
        invalid = deepcopy(self.payload)
        invalid['image']['width'] = 201
        self.assertEqual(self.run_response(invalid)['status'], 'ERROR')
        invalid = deepcopy(self.payload)
        invalid['windshields'][0]['persons'][0]['bbox'] = [0, 0, 300, 90]
        self.assertEqual(self.run_response(invalid)['status'], 'ERROR')
        self.assertEqual(self.run_response({**self.payload, 'person_count': 4})['status'], 'ERROR')

    def test_classification_false_and_unknown(self):
        person = self.payload['windshields'][0]['persons'][0]
        person['seatbelt']['value'] = False
        result = self.run_response(self.payload)
        detection = result['detections'][0]
        self.assertEqual(detection['label'], 'person_no_seatbelt')
        self.assertEqual(detection['confidence'], .94)
        self.assertEqual(detection['personConfidence'], .88)
        self.assertEqual(detection['phoneUsage'], False)
        self.assertEqual(result['windshields'][0]['cropBbox'], (10, 10, 190, 90))
        person['seatbelt'] = {'value': None, 'confidence': None}
        result = self.run_response(self.payload)
        self.assertEqual(result['status'], 'COMPLETED')
        self.assertEqual(result['detections'][0]['label'], 'person_unknown')

    def test_unauthorized_is_isolated(self):
        response = MagicMock(status_code=401)
        response.__enter__.return_value = response
        with patch('app.services.seatbelt.client.requests.post', return_value=response):
            self.assertEqual(self.service.analyze(self.crop, self.view, self.box)['status'], 'ERROR')

class PersistenceTests(unittest.TestCase):
    def test_versioned_result_round_trip(self):
        from sqlalchemy import create_engine, select
        from sqlalchemy.orm import sessionmaker
        from app.models.recognition import VehicleRecognition as Row
        from app.services.comparison.store import RecognitionStore
        engine = create_engine('sqlite://')
        self.addCleanup(engine.dispose)
        Row.__table__.create(engine)
        factory = sessionmaker(engine)
        store = RecognitionStore(factory)
        record = {'_id': 'seatbelt-event'}
        seatbelt = {'schemaVersion': 1, 'status': 'COMPLETED', 'detections': [],
                    'windshields': [{'cropUrl': '/media/windshields/event_windshield_0.jpg'}]}
        store.enqueue(record)
        store.start(record)
        store.complete('seatbelt-event', {'imageUrl': '/media/full_photo/test.jpg',
                       'imageWidth': 200, 'imageHeight': 100,
                       'prediction': {'seatbelt': seatbelt}})
        with factory() as db:
            self.assertEqual(db.scalar(select(Row)).seatbelt_result, seatbelt)
        self.assertEqual(store.list_results()['items'][0]['prediction']['seatbelt'], seatbelt)
