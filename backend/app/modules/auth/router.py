from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.core import config
from app.modules.auth import schemas, security, service
from app.modules.auth.dependencies import (
    client_ip,
    get_current_user_allow_password_change,
    require_admin,
)

router = APIRouter()

INVALID_CREDENTIALS = "Invalid email or password."
PENDING_APPROVAL = "Your account is awaiting administrator approval."
# Same response whether or not the email is already registered, so the form
# can't be used to discover which staff have accounts.
REGISTRATION_SUBMITTED = ("Registration submitted. An administrator must approve your account "
                          "before you can sign in.")


def _set_session_cookie(response: Response, token: str):
    response.set_cookie(
        key=config.SESSION_COOKIE_NAME,
        value=token,
        max_age=config.SESSION_ABSOLUTE_TIMEOUT_HOURS * 3600,
        path=config.SESSION_COOKIE_PATH,
        secure=config.COOKIE_SECURE,
        httponly=True,
        samesite="strict",
    )


def _clear_session_cookie(response: Response):
    response.delete_cookie(
        key=config.SESSION_COOKIE_NAME,
        path=config.SESSION_COOKIE_PATH,
        secure=config.COOKIE_SECURE,
        httponly=True,
        samesite="strict",
    )


def _session_info(user: dict, session: dict) -> dict:
    return {
        "user": service.user_to_public(user),
        "csrf_token": session["csrf_token"],
        "expires_at": service.session_expiry(session),
    }


@router.post("/auth/login", response_model=schemas.SessionInfo)
async def login(body: schemas.LoginRequest, request: Request, response: Response):
    ip = client_ip(request)
    ua = request.headers.get("user-agent", "")
    try:
        user, reason = await service.authenticate(body.email, body.password)
    except service.AuthUnavailable:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Authentication service unavailable")

    if not user:
        await service.record_event("login_failed", email=body.email, ip=ip, user_agent=ua, detail=reason)
        # Only reached after the correct password, so this reveals nothing to a guesser
        if reason == "pending":
            raise HTTPException(status.HTTP_403_FORBIDDEN, PENDING_APPROVAL)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID_CREDENTIALS)

    # Never reuse a session id that existed before authentication (session fixation)
    old_token = request.cookies.get(config.SESSION_COOKIE_NAME)
    if old_token:
        await service.delete_session(old_token)

    token, session = await service.create_session(user, ip, ua)
    _set_session_cookie(response, token)
    await service.record_event("login_success", email=user["email"], user_id=str(user["id"]), ip=ip, user_agent=ua)
    return _session_info(user, session)


@router.get("/auth/config")
async def auth_config():
    return {
        "registration_enabled": config.ALLOW_SELF_REGISTRATION,
        "password_min_length": config.PASSWORD_MIN_LENGTH,
    }


@router.post("/auth/register", status_code=status.HTTP_202_ACCEPTED)
async def register(body: schemas.RegisterRequest, request: Request):
    if not config.ALLOW_SELF_REGISTRATION:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    error = security.password_policy_error(body.password, body.email, body.full_name)
    if error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, error)

    ip = client_ip(request)
    ua = request.headers.get("user-agent", "")
    try:
        # Self-registered accounts get the lowest role and stay disabled until approved
        user = await service.create_user(body.email, body.full_name, "cashier", body.password,
                                         pending_approval=True)
        await service.record_event("registration_requested", email=body.email,
                                   user_id=str(user["id"]), ip=ip, user_agent=ua)
    except service.EmailTaken:
        await service.record_event("registration_duplicate", email=body.email, ip=ip, user_agent=ua)
    except service.AuthUnavailable:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Authentication service unavailable")
    return {"message": REGISTRATION_SUBMITTED}


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request):
    token = request.cookies.get(config.SESSION_COOKIE_NAME)
    if token:
        try:
            session = await service.get_valid_session(token)
            await service.delete_session(token)
            if session:
                await service.record_event("logout", user_id=session["user_id"], ip=client_ip(request))
        except service.AuthUnavailable:
            pass
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_session_cookie(response)
    return response


@router.get("/auth/me", response_model=schemas.SessionInfo)
async def me(request: Request, user: dict = Depends(get_current_user_allow_password_change)):
    return _session_info(user, request.state.session)


@router.post("/auth/change-password", response_model=schemas.SessionInfo)
async def change_password(body: schemas.ChangePasswordRequest, request: Request,
                          user: dict = Depends(get_current_user_allow_password_change)):
    if not await security.verify_password(user["password_hash"], body.current_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect.")
    if body.new_password == body.current_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "New password must be different from the current password.")
    error = security.password_policy_error(body.new_password, user["email"], user.get("full_name", ""))
    if error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, error)

    user_id = str(user["id"])
    session = request.state.session
    await service.set_password(user_id, body.new_password)
    # Sign out every other device that knew the old password
    await service.delete_user_sessions(user_id, except_session_id=session["id"])
    await service.record_event("password_changed", email=user["email"], user_id=user_id, ip=client_ip(request))
    return _session_info(await service.get_user_by_id(user_id), session)


# User administration (admin only)

@router.get("/users", response_model=List[schemas.UserRead])
async def list_users(_: dict = Depends(require_admin)):
    return await service.list_users()


@router.post("/users", response_model=schemas.UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(body: schemas.UserCreate, request: Request, admin: dict = Depends(require_admin)):
    error = security.password_policy_error(body.password, body.email, body.full_name)
    if error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, error)
    try:
        # Admin-set passwords are temporary: the user picks their own on first login
        user = await service.create_user(body.email, body.full_name, body.role, body.password,
                                         must_change_password=True)
    except service.EmailTaken:
        raise HTTPException(status.HTTP_409_CONFLICT, "A user with this email already exists.")
    await service.record_event("user_created", email=body.email, user_id=str(admin["id"]),
                               ip=client_ip(request), detail=f"role={body.role}")
    return service.user_to_public(user)


@router.patch("/users/{user_id}", response_model=schemas.UserRead)
async def update_user(user_id: str, body: schemas.UserUpdate, request: Request, admin: dict = Depends(require_admin)):
    target = await service.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    fields = body.model_dump(exclude_unset=True, exclude_none=True)
    if not fields:
        return service.user_to_public(target)

    removes_admin = target["role"] == "admin" and target.get("is_active", True) and (
        fields.get("role", "admin") != "admin" or fields.get("is_active") is False
    )
    if removes_admin and await service.count_active_admins() <= 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot remove the last active administrator.")
    if str(target["id"]) == str(admin["id"]) and fields.get("is_active") is False:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot deactivate your own account.")

    approving = target.get("pending_approval") and fields.get("is_active") is True
    if approving:
        fields["pending_approval"] = False

    updated = await service.update_user(user_id, fields)
    if approving:
        await service.record_event("registration_approved", email=target["email"], user_id=str(admin["id"]),
                                   ip=client_ip(request), detail=f"role={updated['role']}")
    # Role or status changes take effect immediately
    if "role" in fields or fields.get("is_active") is False:
        await service.delete_user_sessions(user_id)
    await service.record_event("user_updated", email=target["email"], user_id=str(admin["id"]),
                               ip=client_ip(request), detail=str(fields))
    return service.user_to_public(updated)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def reject_registration(user_id: str, request: Request, admin: dict = Depends(require_admin)):
    target = await service.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    # Approved accounts are disabled rather than deleted, to keep the audit trail intact
    if not target.get("pending_approval"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Only pending registrations can be rejected. Disable active accounts instead.")
    await service.delete_user(user_id)
    await service.record_event("registration_rejected", email=target["email"], user_id=str(admin["id"]),
                               ip=client_ip(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/users/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(user_id: str, body: schemas.PasswordResetRequest, request: Request,
                         admin: dict = Depends(require_admin)):
    target = await service.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    error = security.password_policy_error(body.new_password, target["email"], target.get("full_name", ""))
    if error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, error)
    await service.set_password(user_id, body.new_password, must_change_password=True)
    await service.delete_user_sessions(user_id)
    await service.record_event("password_reset", email=target["email"], user_id=str(admin["id"]),
                               ip=client_ip(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
