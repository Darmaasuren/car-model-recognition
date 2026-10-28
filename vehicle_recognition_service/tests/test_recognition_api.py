"""Service HTTP contracts and session isolation without real model weights."""
import asyncio
import base64
from pathlib import Path
import sys
from threading import RLock
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import cv2
import httpx
import numpy as np
from fastapi import FastAPI, Header

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from recognition_service.api import health, recognition as recognition_api, video, live
from recognition_service.config import settings
from recognition_service.inference.pipeline import RecognitionPipeline
from recognition_service.api.security import require_api_key


class RecognitionTests(unittest.TestCase):
    def setUp(self):
        self.detector = Mock()
        self.detector.detect.return_value = [SimpleNamespace(x1=10,y1=10,x2=60,y2=50,track_id=None,confidence=.95)]
        self.classifier = Mock()
        self.classifier.classify.return_value = {'model': {'label':'Toyota Prius','confidence':.96}}
        self.classifier.label_groups = {'model':['Toyota Prius'], 'color':[], 'type':[], 'view':[]}
        self.app = FastAPI()
        self.app.state.classifier = self.classifier
        self.app.state.pipeline = RecognitionPipeline(self.detector,self.classifier)
        self.app.state.inference_lock = RLock()
        for module in (health, recognition_api, video, live):
            self.app.include_router(module.router, prefix='/api/v1')
        async def inline(fn,*args,**kwargs): return fn(*args,**kwargs)
        self.dispatch=patch('recognition_service.api.recognition.run_in_threadpool',inline); self.dispatch.start()
        async def key(value: str | None = Header(None,alias='API-Key')):
            with patch('recognition_service.api.security.settings',SimpleNamespace(api_key='test')):
                require_api_key(value)
        self.app.dependency_overrides[require_api_key]=key
        self.frame=np.arange(60*80*3,dtype=np.uint8).reshape(60,80,3)
        self.png=cv2.imencode('.png',self.frame)[1].tobytes()
        self.encoded=base64.b64encode(self.png).decode()

    def tearDown(self): self.dispatch.stop()

    def request(self,path,**kwargs):
        async def send():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='http://test') as client:
                return await client.post('/api/v1'+path,**kwargs)
        return asyncio.run(send())

    def test_vehicle_bbox_skips_detector_and_crops_exactly(self):
        response=self.request('/inference/vehicle',headers={'API-Key':'test'},json={
            'imageBase64':self.encoded,'vehicleBbox':{'x1':10,'y1':15,'x2':50,'y2':45}})
        self.assertEqual(response.status_code,200,response.text)
        self.detector.detect.assert_not_called()
        np.testing.assert_array_equal(self.classifier.classify.call_args.args[0],self.frame[15:45,10:50])

    def test_image_detects_all_and_exposes_model_metadata(self):
        response=self.request('/inference/image',headers={'API-Key':'test'},files={'file':('car.png',self.png,'image/png')})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(len(response.json()['results']),1)
        self.assertEqual(response.json()['labelGroups']['model'],['Toyota Prius'])
        self.assertIn('modelVersion',response.json())
        self.detector.detect.assert_called_once()

    def test_plate_matches_vehicle_and_detects(self):
        response=self.request('/inference/plate',headers={'API-Key':'test'},json={
            'imageBase64':self.encoded,'plateBbox':{'x1':25,'y1':30,'x2':40,'y2':40}})
        self.assertEqual(response.status_code,200,response.text)
        self.assertTrue(response.json()['matched'])
        self.detector.detect.assert_called_once()

    def test_auth_and_invalid_bbox_prevent_inference(self):
        response=self.request('/inference/image',files={'file':('car.png',self.png,'image/png')})
        self.assertEqual(response.status_code,401)
        response=self.request('/inference/vehicle',headers={'API-Key':'test'},json={
            'imageBase64':self.encoded,'vehicleBbox':{'x1':0,'y1':0,'x2':81,'y2':10}})
        self.assertEqual(response.status_code,422)
        self.classifier.classify.assert_not_called()

    def test_oversized_image_rejected(self):
        from dataclasses import replace
        with patch('recognition_service.media.settings',replace(settings,max_image_bytes=10)):
            response=self.request('/inference/vehicle',headers={'API-Key':'test'},json={
                'imageBase64':self.encoded,'vehicleBbox':{'x1':0,'y1':0,'x2':10,'y2':10}})
        self.assertEqual(response.status_code,413)


