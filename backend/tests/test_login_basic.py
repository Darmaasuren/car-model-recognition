"""Login HTTP contract: Basic credentials establish the existing cookie session."""
import asyncio
import base64
import os
import unittest
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from test_auth import AuthTests

with patch.dict(os.environ, {
    'API_PREFIX': '/api', 'API_KEY': 'test',
    'CORS_ORIGINS': 'http://localhost:5173',
}):
    from app.api import auth
    from app.middleware.auth import AuthMiddleware
from app.services.auth import LoginLimiter
from app.models.user import User
from app.core.passwords import hasher


class BasicLoginTests(unittest.TestCase):
    def setUp(self):
        AuthTests.setUp(self)
        self.app = FastAPI()
        self.app.state.db_sessions = self.factory
        self.app.include_router(auth.router, prefix=auth.settings.api_prefix)
        self.app.add_middleware(AuthMiddleware)
        self.limiter_patch = patch.object(auth, 'limiter', LoginLimiter())
        self.limiter_patch.start()

    def tearDown(self):
        self.limiter_patch.stop()
        AuthTests.tearDown(self)

    def header(self, text):
        return {'Authorization': 'Basic ' + base64.b64encode(text.encode()).decode()}

    def request(self, **kwargs):
        async def send():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),
                                         base_url='https://test') as client:
                return await client.post(auth.settings.api_prefix + '/auth/login',
                    headers={'Origin': auth.settings.cors_origins[0], **kwargs.pop('headers', {})},
                    **kwargs)
        return asyncio.run(send())

    def test_basic_login_session_and_logout(self):
        async def send():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),
                    base_url='https://test', headers={'Origin': auth.settings.cors_origins[0]}) as client:
                prefix = auth.settings.api_prefix + '/auth'
                response = await client.post(prefix + '/login', headers=self.header('ADMIN:test-password-123'))
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()['username'], 'admin')
                self.assertIn('HttpOnly', response.headers['set-cookie'])
                self.assertEqual(response.headers['cache-control'], 'no-store')
                self.assertEqual((await client.get(prefix + '/me')).status_code, 200)
                self.assertEqual((await client.post(prefix + '/logout')).status_code, 204)
                self.assertEqual((await client.get(prefix + '/me')).status_code, 401)
        asyncio.run(send())

    def test_invalid_credentials_and_headers(self):
        for headers in ({}, {'Authorization': 'Bearer token'},
                        {'Authorization': 'Basic !!!'}, self.header('no-colon'),
                        self.header(':password'), self.header('admin:'),
                        self.header('admin:wrong'), self.header('missing:wrong')):
            with self.subTest(headers=headers):
                response = self.request(headers=headers)
                self.assertEqual(response.status_code, 401, response.text)
                self.assertTrue(response.headers['www-authenticate'].startswith('Basic '))
                self.assertNotIn('set-cookie', response.headers)

    def test_json_credentials_no_longer_accepted(self):
        self.assertEqual(self.request(json={'username': 'admin', 'password': 'test-password-123'}).status_code, 401)

    def test_utf8_password_with_colon(self):
        with self.factory() as db:
            db.query(User).filter_by(username='admin').one().password_hash = hasher.hash('нууц:үг')
            db.commit()
        self.assertEqual(self.request(headers=self.header('admin:нууц:үг')).status_code, 200)

    def test_rate_limit(self):
        with patch.object(auth, 'limiter', LoginLimiter(limit=1)):
            self.assertEqual(self.request(headers=self.header('admin:wrong')).status_code, 401)
            self.assertEqual(self.request(headers=self.header('admin:test-password-123')).status_code, 429)

    def test_openapi_uses_basic_without_body(self):
        schema = self.app.openapi()
        operation = schema['paths'][auth.settings.api_prefix + '/auth/login']['post']
        self.assertNotIn('requestBody', operation)
        scheme = next(iter(operation['security'][0]))
        self.assertEqual(schema['components']['securitySchemes'][scheme]['scheme'], 'basic')
