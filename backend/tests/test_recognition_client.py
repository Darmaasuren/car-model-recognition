import os
import sys
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

import cv2
import numpy as np
import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
with patch.dict(os.environ, {'API_PREFIX':'/api','API_KEY':'test','CORS_ORIGINS':'http://localhost:5173'}):
    from app.services.recognition.client import RecognitionClient, RecognitionServiceError
    from app.services.media import MediaService
    from app.services.recognition.results import RecognitionResults
    from app.services.recognition.video import VideoSessionManager
from app.core.database import Base
from app.models.user import User


class ClientTests(unittest.TestCase):
    def test_network_failure_and_remote_error_are_sanitized(self):
        client=RecognitionClient(url='http://recognition/api/v1',api_key='private')
        with patch('app.services.recognition.client.requests.request',side_effect=requests.Timeout('private URL')):
            with self.assertRaises(RecognitionServiceError) as error: client.health()
            self.assertNotIn('private',str(error.exception))
        response=Mock(status_code=429)
        with patch('app.services.recognition.client.requests.request',return_value=response) as send:
            with self.assertRaises(RecognitionServiceError) as error: client.health()
            self.assertEqual(error.exception.status_code,429)
            self.assertFalse(send.call_args.kwargs['allow_redirects'])
            self.assertEqual(send.call_args.kwargs['headers'],{'API-Key':'private'})
            response.close.assert_called_once()

    def test_remote_image_result_persists_crop_without_loading_models(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            media=MediaService(root/'uploads',root/'crops',root/'outputs')
            client=RecognitionResults(media, RecognitionClient())
            frame=np.zeros((40,60,3),np.uint8)
            event_id=uuid4().hex
            with patch.object(client.client,'recognize_image',return_value={'modelVersion':'v2','labelGroups':{'model':['Prius']},
                'results':[{'eventId':event_id,'detectedAt':'2026-10-09T00:00:00Z',
                'vehicleBbox':{'x1':10,'y1':5,'x2':30,'y2':20}}]}):
                results=client.process_image(frame)
            self.assertEqual(client.model_version,'v2')
            self.assertEqual(results[0].crop_url,f'/media/crop/{event_id}.jpg')
            self.assertEqual(cv2.imread(str(root/'crops'/f'{event_id}.jpg')).shape[:2],(15,20))

    def test_windshield_images_saved_from_vehicle_coordinates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            media = MediaService(root/'uploads', root/'crops', root/'outputs')
            seatbelt = Mock()
            seatbelt.analyze.return_value = {
                'schemaVersion': 1, 'status': 'NO_OCCUPANT_DETECTED',
                'windshields': [{'cropBbox': [2, 3, 10, 8]}, {'cropBbox': [10, 0, 20, 5]}]}
            recognition = RecognitionResults(media, Mock(), seatbelt)
            event_id = uuid4().hex
            recognition.client.recognize_image.return_value = {
                'modelVersion': 'v2', 'labelGroups': {}, 'results': [{
                    'eventId': event_id, 'detectedAt': '2026-10-09T00:00:00Z',
                    'vehicleBbox': {'x1': 10, 'y1': 5, 'x2': 30, 'y2': 20}}]}
            frame = np.zeros((40, 60, 3), np.uint8)
            frame[8:13, 12:20] = 240
            result = recognition.process_image(frame)[0]
            for index, expected_shape in enumerate([(5, 8), (5, 10)]):
                filename = f'{event_id}_windshield_{index}.jpg'
                saved = cv2.imread(str(root/'windshields'/filename))
                self.assertFalse((root/'crops'/filename).exists())
                self.assertEqual(saved.shape[:2], expected_shape)
                self.assertEqual(result.seatbelt['windshields'][index]['cropUrl'], '/media/windshields/' + filename)
                if index == 0:
                    self.assertGreater(saved.mean(), 235)
            self.assertEqual(result.seatbelt['status'], 'NO_OCCUPANT_DETECTED')

    def test_windshield_save_failure_preserves_detections(self):
        media = Mock()
        media.save_windshield_crop.side_effect = OSError('disk full')
        recognition = RecognitionResults(media, Mock())
        result = SimpleNamespace(event_id=uuid4().hex, seatbelt={
            'status': 'COMPLETED', 'detections': [{'label': 'person_seatbelt'}],
            'windshields': [{'cropBbox': [1, 1, 8, 9]}]})
        with self.assertLogs('app.operations', level='ERROR'):
            recognition.save_windshield_crops(np.zeros((10, 10, 3), np.uint8), result)
        self.assertEqual(result.seatbelt['status'], 'COMPLETED')
        self.assertEqual(result.seatbelt['windshields'][0]['cropError'], 'CROP_SAVE_FAILED')
        self.assertIsNone(result.seatbelt['windshields'][0]['cropUrl'])
        self.assertEqual(len(result.seatbelt['detections']), 1)

    def test_no_windshields_produces_no_files(self):
        media = Mock()
        recognition = RecognitionResults(media, Mock())
        for status in ('DISABLED', 'SKIPPED_NOT_FRONT', 'NO_WINDSHIELD', 'ERROR'):
            result = SimpleNamespace(event_id=uuid4().hex, seatbelt={'status': status, 'windshields': []})
            recognition.save_windshield_crops(np.zeros((10, 10, 3), np.uint8), result)
        media.save_windshield_crop.assert_not_called()

    def test_stream_closes_remote_response(self):
        client=RecognitionClient()
        response=Mock(); response.iter_content.return_value=iter([b'frame'])
        with patch.object(client,'request',return_value=response):
            chunks,close=client.stream('/video/sessions/one/stream')
            self.assertEqual(list(chunks),[b'frame'])
            response.close.assert_called_once()

    def test_session_ownership_and_expired_remote_delete(self):
        engine=create_engine('sqlite://')
        Base.metadata.create_all(engine)
        factory=sessionmaker(engine)
        client=Mock(); client.create_video.return_value='session-one'
        manager=VideoSessionManager(client,Mock(),factory)
        try:
            session=manager.create(Path('unused'),1)
            manager.authorize(session,1)
            from fastapi import HTTPException
            with self.assertRaises(HTTPException): manager.authorize(session,2)
            client.delete_video.side_effect=RecognitionServiceError('expired',404)
            manager.delete(session)
            with self.assertRaises(HTTPException): manager.authorize(session,1)
        finally: engine.dispose()
