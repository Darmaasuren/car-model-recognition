import logging

from fastapi import APIRouter, HTTPException, Request, Response, Security
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.security.http import HTTPBase
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.schemas.auth import UserResponse
from app.services.auth import BASIC_CHALLENGE, LoginLimiter, decode_basic, login, logout

router = APIRouter(prefix='/auth', tags=['auth'])
limiter = LoginLimiter()
logger = logging.getLogger(__name__)
basic_auth = HTTPBase(scheme='basic', auto_error=False)
basic_challenge = BASIC_CHALLENGE


@router.post('/login', response_model=UserResponse)
def sign_in(request: Request, response: Response,
            credentials: HTTPAuthorizationCredentials | None = Security(basic_auth)):
    client_key = request.client.host if request.client else 'unknown'
    limiter.check(client_key)
    username, password = decode_basic(
        f'{credentials.scheme} {credentials.credentials}' if credentials else None)
    try:
        user, token = login(request.app.state.db_sessions, username.strip().lower(),
                            password, settings.session_seconds,
                            request.cookies.get(settings.session_cookie))
    except HTTPException as error:
        if error.status_code == 401:
            error.headers = {**(error.headers or {}), **basic_challenge}
        raise
    except SQLAlchemyError as error:
        limiter.reset(client_key)
        logger.exception('Login database operation failed')
        raise HTTPException(503, 'Database холболт эсвэл хүснэгтийн алдаа. Backend log шалгана уу.') from error
    limiter.reset(client_key)
    response.set_cookie(settings.session_cookie, token, max_age=settings.session_seconds,
                        httponly=True, secure=settings.cookie_secure, samesite='lax', path='/')
    response.headers['Cache-Control'] = 'no-store'
    return user


@router.get('/me', response_model=UserResponse)
def me(request: Request, response: Response):
    user = request.scope.get('user')
    if user is None:
        raise HTTPException(401, 'Нэвтэрнэ үү.')
    response.headers['Cache-Control'] = 'no-store'
    return user


@router.post('/logout', status_code=204)
def sign_out(request: Request):
    try:
        logout(request.app.state.db_sessions, request.cookies.get(settings.session_cookie))
    except SQLAlchemyError as error:
        logger.exception('Logout database operation failed')
        raise HTTPException(503, 'Database холболт эсвэл хүснэгтийн алдаа. Backend log шалгана уу.') from error
    response = Response(status_code=204, headers={'Cache-Control': 'no-store'})
    response.delete_cookie(settings.session_cookie, path='/', httponly=True,
                           secure=settings.cookie_secure, samesite='lax')
    return response
