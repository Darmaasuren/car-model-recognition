"""Public bbox endpoints delegate to the right remote contract, retaining auth."""
import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import httpx
from fastapi import FastAPI, Header
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
with patch.dict(os.environ, {'API_PREFIX':'/api','API_KEY':'test','CORS_ORIGINS':'http://localhost:5173'}):
    from app.api.recognition import router
    from app.core.security import require_api_key
    from app.core.config import settings
    from app.middleware.auth import AuthMiddleware


class VehicleBboxTests(unittest.TestCase):
    def setUp(self):
        self.app=FastAPI()
        self.client=Mock()
        self.box={'x1':1,'y1':2,'x2':10,'y2':20}
        self.client.json.return_value={'eventId':'event-1','vehicleBbox':self.box,
                                      'result':{'model':{'label':'Toyota Prius','confidence':.95}}}
        self.app.state.recognition_client=self.client
        self.app.state.db_sessions=Mock(side_effect=AssertionError('Service routes must not query user DB'))
        self.app.include_router(router,prefix=settings.api_prefix)
        self.app.add_middleware(AuthMiddleware)
        async def check(key: str | None = Header(None,alias='API-Key')): require_api_key(key)
        self.app.dependency_overrides[require_api_key]=check
        async def inline(fn,*args,**kwargs): return fn(*args,**kwargs)
        self.dispatch=patch('app.api.recognition.run_in_threadpool',inline); self.dispatch.start()

    def tearDown(self): self.dispatch.stop()

    def request(self,suffix='',**kwargs):
        async def send():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='http://test') as client:
                return await client.post(settings.api_prefix+'/inference/vehicle-bbox'+suffix,**kwargs)
        return asyncio.run(send())

    def test_base64_delegates_vehicle_not_plate(self):
        body={'eventId':'event-1','vehicleBbox':self.box,'imageBase64':'encoded'}
        response=self.request(headers={'API-Key':settings.api_key},json=body)
        self.assertEqual(response.status_code,200,response.text)
        self.client.json.assert_called_once_with('POST','/inference/vehicle',json=body)
        self.assertEqual(response.json()['result']['model']['label'],'Toyota Prius')
        self.app.state.db_sessions.assert_not_called()

    def test_api_key_and_bbox_validation_before_remote_call(self):
        body={'vehicleBbox':self.box,'imageBase64':'encoded'}
        self.assertEqual(self.request(json=body).status_code,401)
        body['vehicleBbox']={'x1':10,'y1':0,'x2':1,'y2':10}
        self.assertEqual(self.request(json=body,headers={'API-Key':settings.api_key}).status_code,422)
        self.client.json.assert_not_called()

    def test_upload_size_limit(self):
        from dataclasses import replace
        with patch('app.api.recognition.settings',replace(settings,max_image_bytes=3)):
            response=self.request('/upload',headers={'API-Key':settings.api_key},
                files={'file':('car.png',b'1234','image/png')},
                data={'vehicle_x1':1,'vehicle_y1':2,'vehicle_x2':10,'vehicle_y2':20})
        self.assertEqual(response.status_code,413)
        self.client.json.assert_not_called()
