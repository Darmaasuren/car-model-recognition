"""Protect HTTP, static crops and WebSocket handshakes before processing uploads."""
from time import monotonic

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.services.auth import BASIC_CHALLENGE, LoginLimiter, basic_user, current_user


class SessionEnded(Exception):
    pass


class AuthMiddleware:
    def __init__(self, app):
        self.app = app
        self.basic_limiter = LoginLimiter()

    async def __call__(self, scope, receive, send):
        if scope['type'] not in ('http', 'websocket'):
            return await self.app(scope, receive, send)
        connection = HTTPConnection(scope)
        path = scope['path'].rstrip('/') or '/'
        prefix = settings.api_prefix.rstrip('/')
        service_paths = {prefix + '/inference/' + route for route in (
            'vehicle', 'vehicle/upload', 'vehicle-bbox', 'vehicle-bbox/upload')}
        public = {'/', '/docs', '/docs/oauth2-redirect', '/redoc', '/openapi.json',
                  prefix + '/health', prefix + '/auth/login', prefix + '/auth/logout'}
        websocket = scope['type'] == 'websocket'
        method = scope.get('method', 'GET')
        if not websocket and method == 'OPTIONS':
            return await self.app(scope, receive, send)
        service = path in service_paths and not websocket
        protected = not service and path not in public
        authorization = connection.headers.get('authorization')
        basic_request = protected and not websocket and authorization is not None
        origin = connection.headers.get('origin')
        # Browser mutations retain Origin checks; direct Basic clients need no Origin.
        if not service and (websocket or method not in ('GET', 'HEAD')):
            if origin not in settings.cors_origins and not (basic_request and origin is None):
                if websocket:
                    return await send({'type': 'websocket.close', 'code': 1008})
                return await JSONResponse({'detail': 'Origin зөвшөөрөгдөөгүй.'}, 403)(scope, receive, send)
        token = connection.cookies.get(settings.session_cookie)
        factory = connection.app.state.db_sessions
        if protected:
            if basic_request:
                client_key = connection.client.host if connection.client else 'unknown'
                try:
                    self.basic_limiter.check(client_key)
                    user = await run_in_threadpool(basic_user, factory, authorization)
                except HTTPException as error:
                    return await JSONResponse({'detail': error.detail}, error.status_code,
                                              headers=error.headers)(scope, receive, send)
                except SQLAlchemyError:
                    self.basic_limiter.reset(client_key)
                    return await JSONResponse({'detail': 'Database холболтын алдаа.'}, 503)(scope, receive, send)
                self.basic_limiter.reset(client_key)
            else:
                user = await run_in_threadpool(current_user, factory, token)
            if user is None:
                if websocket:
                    return await send({'type': 'websocket.close', 'code': 4401})
                return await JSONResponse({'detail': 'Нэвтэрнэ үү.'}, 401, headers=BASIC_CHALLENGE)(scope, receive, send)
            scope['user'] = user
        last_check = monotonic()

        async def checked_send(message):
            nonlocal last_check
            if protected and not basic_request and message['type'] in ('http.response.body', 'websocket.send'):
                if monotonic() - last_check >= 5:
                    last_check = monotonic()
                    if await run_in_threadpool(current_user, factory, token) is None:
                        if websocket:
                            await send({'type': 'websocket.close', 'code': 4401})
                        else:
                            await send({'type': 'http.response.body', 'body': b'', 'more_body': False})
                        raise SessionEnded()
            if protected and message['type'] == 'http.response.start':
                message = {**message, 'headers': [*message.get('headers', []),
                                                 (b'cache-control', b'no-store')]}
            await send(message)
        try:
            await self.app(scope, receive, checked_send)
        except SessionEnded:
            pass
