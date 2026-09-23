"""Protect HTTP, static crops and WebSocket handshakes before processing uploads."""
from time import monotonic

from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.services.auth import current_user


class SessionEnded(Exception):
    pass


class AuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] not in ('http', 'websocket'):
            return await self.app(scope, receive, send)
        connection = HTTPConnection(scope)
        path = scope['path'].rstrip('/') or '/'
        prefix = settings.api_prefix.rstrip('/')
        service_paths = {prefix + '/inference/vehicle', prefix + '/inference/vehicle/upload'}
        public = {'/', '/docs', '/docs/oauth2-redirect', '/redoc', '/openapi.json',
                  prefix + '/health', prefix + '/auth/login', prefix + '/auth/logout'}
        websocket = scope['type'] == 'websocket'
        method = scope.get('method', 'GET')
        if not websocket and method == 'OPTIONS':
            return await self.app(scope, receive, send)
        service = path in service_paths and not websocket
        origin = connection.headers.get('origin')
        # Explicit trusted Origin required for all browser mutations, including login.
        if not service and (websocket or method not in ('GET', 'HEAD')):
            if origin not in settings.cors_origins:
                if websocket:
                    return await send({'type': 'websocket.close', 'code': 1008})
                return await JSONResponse({'detail': 'Origin зөвшөөрөгдөөгүй.'}, 403)(scope, receive, send)
        protected = not service and path not in public
        token = connection.cookies.get(settings.session_cookie)
        factory = connection.app.state.db_sessions
        if protected:
            user = await run_in_threadpool(current_user, factory, token)
            if user is None:
                if websocket:
                    return await send({'type': 'websocket.close', 'code': 4401})
                return await JSONResponse({'detail': 'Нэвтэрнэ үү.'}, 401)(scope, receive, send)
            scope['user'] = user
        last_check = monotonic()

        async def checked_send(message):
            nonlocal last_check
            if protected and message['type'] in ('http.response.body', 'websocket.send'):
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
