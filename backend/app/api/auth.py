import logging

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.schemas.auth import LoginRequest, UserResponse
from app.services.auth import LoginLimiter, current_user, login, logout

router = APIRouter(prefix='/auth', tags=['auth'])
limiter = LoginLimiter()
logger = logging.getLogger(__name__)


@router.post('/login', response_model=UserResponse)
def sign_in(payload: LoginRequest, request: Request, response: Response):
    client_key = request.client.host if request.client else 'unknown'
    limiter.check(client_key)
    try:
        user, token = login(request.app.state.db_sessions, payload.username.strip().lower(),
                            payload.password, settings.session_seconds,
                            request.cookies.get(settings.session_cookie))
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
    try:
        user = current_user(request.app.state.db_sessions, request.cookies.get(settings.session_cookie))
    except SQLAlchemyError as error:
        logger.exception('Session lookup failed')
        raise HTTPException(503, 'Database холболт эсвэл хүснэгтийн алдаа. Backend log шалгана уу.') from error
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
