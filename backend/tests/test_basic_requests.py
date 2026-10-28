"""Direct Basic HTTP requests must not require a login, cookie, or Origin."""
import asyncio
import tempfile
import unittest
from pathlib import Path

import httpx
from fastapi import Depends
from fastapi.staticfiles import StaticFiles
import test_login_basic as login_tests
from app.api import auth
from app.core.security import require_api_key
from app.models.user import Session
from app.services.auth import LoginLimiter


class BasicRequestTests(unittest.TestCase):
    def setUp(self):
        login_tests.BasicLoginTests.setUp(self)
        self.temp = tempfile.TemporaryDirectory()
        Path(self.temp.name, 'sample.jpg').write_bytes(b'example-image')
        self.app.mount('/media/crop', StaticFiles(directory=self.temp.name))

        @self.app.post('/protected')
        def protected():
            return {'ok': True}

        @self.app.post(auth.settings.api_prefix + '/inference/vehicle',
                       dependencies=[Depends(require_api_key)])
        def service():
            return {'ok': True}

    def tearDown(self):
        self.temp.cleanup()
        login_tests.BasicLoginTests.tearDown(self)

    header = login_tests.BasicLoginTests.header

    def request(self, method='GET', path='/media/crop/sample.jpg', **kwargs):
        async def send():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),
                                         base_url='http://test') as client:
                return await client.request(method, path, **kwargs)
        return asyncio.run(send())

    def test_image_without_cookie_or_login(self):
        result = self.request(headers=self.header('admin:test-password-123'))
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.content, b'example-image')
        self.assertNotIn('set-cookie', result.headers)
        self.assertEqual(result.headers['cache-control'], 'no-store')
        with self.factory() as db:
            self.assertEqual(db.query(Session).count(), 0)

    def test_missing_wrong_and_malformed_basic(self):
        for headers in ({}, self.header('admin:wrong'), {'Authorization': 'Basic !!!'},
                        self.header('missing:password'), {'Authorization': 'Bearer token'}):
            with self.subTest(headers=headers):
                response = self.request(headers=headers)
                self.assertEqual(response.status_code, 401)
                self.assertTrue(response.headers['www-authenticate'].startswith('Basic '))
                self.assertNotIn(b'example-image', response.content)

    def test_me_uses_basic_identity(self):
        response = self.request(path=auth.settings.api_prefix + '/auth/me',
                                headers=self.header('admin:test-password-123'))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['username'], 'admin')

    def test_direct_post_without_origin(self):
        response = self.request('POST', '/protected', headers=self.header('admin:test-password-123'))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.request('POST', '/protected', headers=self.header('admin:wrong')).status_code, 401)

    def test_untrusted_origin_and_cookie_only_mutations_rejected(self):
        headers = {**self.header('admin:test-password-123'), 'Origin': 'https://untrusted.example'}
        self.assertEqual(self.request('POST', '/protected', headers=headers).status_code, 403)
        self.assertEqual(self.request('POST', '/protected').status_code, 403)

    def test_basic_does_not_replace_service_api_key(self):
        path = auth.settings.api_prefix + '/inference/vehicle'
        self.assertEqual(self.request('POST', path, headers=self.header('admin:test-password-123')).status_code, 401)
        self.assertEqual(self.request('POST', path, headers={'API-Key': auth.settings.api_key}).status_code, 200)

    def test_bad_basic_does_not_fall_back_to_valid_cookie(self):
        from app.services.auth import login
        _, token = login(self.factory, 'admin', 'test-password-123', 3600)
        response = self.request(headers={**self.header('admin:wrong'),
                                'Cookie': f'{auth.settings.session_cookie}={token}'})
        self.assertEqual(response.status_code, 401)

    def test_failure_rate_limit(self):
        # Build the middleware, then use a smaller limit for this test.
        self.request()
        self.app.middleware_stack.app.basic_limiter = LoginLimiter(limit=1)
        self.assertEqual(self.request(headers=self.header('admin:wrong')).status_code, 401)
        self.assertEqual(self.request(headers=self.header('admin:test-password-123')).status_code, 429)
