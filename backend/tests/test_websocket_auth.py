import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

with patch.dict(os.environ, {
    'API_PREFIX': '/api', 'API_KEY': 'test',
    'CORS_ORIGINS': 'http://localhost:5173',
}):
    from app.middleware.auth import AuthMiddleware
    from app.core.config import settings

from fastapi import FastAPI, WebSocket
from app.api.live import router


class WebSocketAuthTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.state.db_sessions = Mock()
        self.app.add_middleware(AuthMiddleware)
        self.app.include_router(router, prefix=settings.api_prefix)
        self.headers = {'origin': settings.cors_origins[0]}

    async def connect(self, path):
        messages = []
        scope = {
            'type': 'websocket', 'path': path, 'raw_path': path.encode(),
            'scheme': 'ws', 'query_string': b'', 'root_path': '',
            'headers': [(b'origin', settings.cors_origins[0].encode())],
            'client': ('127.0.0.1', 1234), 'server': ('localhost', 8000),
            'subprotocols': [],
        }
        receive = AsyncMock(return_value={'type': 'websocket.connect'})
        async def send(message):
            messages.append(message)
        await self.app(scope, receive, send)
        return messages

    async def test_missing_camera_does_not_report_expired_session(self):
        self.app.state.live_manager = SimpleNamespace(
            events_after=Mock(side_effect=KeyError('Camera not configured')),
        )
        with patch('app.middleware.auth.run_in_threadpool', new=AsyncMock(return_value=object())):
            messages = await self.connect(settings.api_prefix + '/live/cameras/camera-1/events')
        self.assertEqual(messages[-1]['type'], 'websocket.close')
        self.assertEqual(messages[-1]['code'], 1008)

    async def test_expired_session_uses_auth_specific_close_code(self):
        @self.app.websocket('/test-events')
        async def events(socket: WebSocket):
            await socket.accept()
            await socket.send_json({'type': 'test'})

        with patch('app.middleware.auth.run_in_threadpool', new=AsyncMock(side_effect=[object(), None])):
            with patch('app.middleware.auth.monotonic', side_effect=[0, 6, 6]):
                messages = await self.connect('/test-events')
        self.assertEqual(messages[-1]['type'], 'websocket.close')
        self.assertEqual(messages[-1]['code'], 4401)
