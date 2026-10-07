from fastapi import Depends, HTTPException, Request, status

from app.core import config
from app.modules.auth import security, service

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def client_ip(request: Request) -> str:
    return request.client.host if request.client else ""


async def _resolve_user(request: Request, allow_pending_password_change: bool) -> dict:
    token = request.cookies.get(config.SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        session = await service.get_valid_session(token)
    except service.AuthUnavailable:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Authentication service unavailable")
    if not session:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")

    # Synchronizer-token CSRF check: the token is only readable by same-origin JS
    if request.method in UNSAFE_METHODS:
        sent = request.headers.get(config.CSRF_HEADER_NAME, "")
        if not sent or not security.tokens_match(sent, session["csrf_token"]):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF validation failed")

    user = await service.get_user_by_id(session["user_id"])
    if not user or not user.get("is_active", True):
        await service.delete_session(token)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")

    if user.get("must_change_password") and not allow_pending_password_change:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Password change required")

    request.state.session = session
    request.state.user = user
    return user


async def get_current_user(request: Request) -> dict:
    return await _resolve_user(request, allow_pending_password_change=False)


async def get_current_user_allow_password_change(request: Request) -> dict:
    return await _resolve_user(request, allow_pending_password_change=True)


def require_roles(*roles: str):
    async def checker(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission to perform this action")
        return user
    return checker


# Role groups used by the routers
require_admin = require_roles("admin")
require_pharmacist = require_roles("admin", "pharmacist")
