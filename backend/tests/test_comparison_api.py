"""Comparison response schemas preserve existing sparse success/error payloads."""
import asyncio
from datetime import datetime, timezone
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

import httpx
from fastapi import FastAPI

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
with patch.dict(os.environ, {
    'API_PREFIX': '/api', 'API_KEY': 'test', 'CORS_ORIGINS': 'http://localhost:5173',
}):
    from app.api.comparison import router


class ComparisonAPITests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.state.recognition = Mock()
        self.app.state.service_tokens = Mock()
        self.app.state.db_sessions = Mock()
        self.app.include_router(router, prefix='/api')
        async def inline(fn, *args, **kwargs):
            return fn(*args, **kwargs)
        self.dispatch = patch('app.api.comparison.run_in_threadpool', inline)
        self.dispatch.start()

    def tearDown(self):
        self.dispatch.stop()

    def request(self, method, path):
        async def send():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://test') as client:
                return await client.request(method, '/api/service' + path)
        return asyncio.run(send())

    def test_batch_keeps_sparse_errors_and_model_metadata(self):
        payload = {'count': 2, 'items': [
            {'recordId': 'one', 'plate': '', 'prediction': None, 'imageStatus': 'NO_VEHICLE_DETECTED',
             'modelVersion': 'v3', 'imageWidth': 640, 'imageHeight': 480},
            {'recordId': 'two', 'plate': '', 'error': 'Image unavailable'},
        ]}
        with patch.dict(os.environ, {'SERVICE_WORKER_ENABLED': 'false'}), \
             patch('app.api.comparison.compare_batch', return_value=payload):
            response = self.request('POST', '/compare-batch')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), payload)

    def test_empty_history_and_not_started_worker_keep_contract(self):
        payload = {'items': [], 'count': 0, 'total': 0, 'offset': 0, 'limit': 20}
        with patch('app.api.comparison.RecognitionStore') as store:
            store.return_value.list_results.return_value = payload
            response = self.request('GET', '/comparisons')
        self.assertEqual(response.json(), payload)
        status = {'status': 'not_started', 'counts': {}}
        with patch('app.api.comparison.read_status', return_value=status):
            response = self.request('GET', '/worker-status')
        self.assertEqual(response.json(), status)

    def test_worker_timestamps_keep_existing_isoformat(self):
        timestamp = datetime(2026, 10, 9, tzinfo=timezone.utc)
        status = {'status': 'waiting', 'counts': {'completed': 2}, 'nextRequestAt': timestamp,
                  'lastSuccessAt': None, 'windowStart': None, 'windowEnd': None, 'offset': 0, 'error': None}
        with patch('app.api.comparison.read_status', return_value=status):
            response = self.request('GET', '/worker-status')
        self.assertEqual(response.json(), {**status, 'nextRequestAt': timestamp.isoformat()})
