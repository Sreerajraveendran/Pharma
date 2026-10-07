import logging
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from app.core import config
from app.modules.auth import security
from app.core.common import now_utc, utc
from app.db.engine import DatabaseUnavailable
from app.modules.auth import repository as accounts

logger = logging.getLogger("app.modules.auth.service")

# Authentication needs the database; kept as a name for the router's 503 handling
AuthUnavailable = DatabaseUnavailable
EmailTaken = accounts.EmailTaken  # for the router


def user_to_public(user: dict) -> dict:
    return {
        "id": user["id"],
        "email": user["email"],
        "full_name": user.get("full_name", ""),
        "role": user["role"],
        "is_active": user.get("is_active", True),
        "must_change_password": user.get("must_change_password", False),
        "pending_approval": user.get("pending_approval", False),
        "created_at": user.get("created_at"),
        "last_login_at": user.get("last_login_at"),
    }


async def bootstrap_admin():
    if await accounts.count_users() > 0:
        return
    email = config.BOOTSTRAP_ADMIN_EMAIL
    password = config.BOOTSTRAP_ADMIN_PASSWORD
    if not email or not password:
        logger.warning(
            "No users exist and BOOTSTRAP_ADMIN_EMAIL / BOOTSTRAP_ADMIN_PASSWORD are not set. "
            "Nobody can log in until an administrator is created."
        )
        return
    await create_user(email, config.BOOTSTRAP_ADMIN_NAME, "admin", password, must_change_password=True)
    logger.info(f"Bootstrapped administrator account {email} (password change required on first login)")


async def record_event(event_type: str, *, email: str = "", user_id: Optional[str] = None,
                       ip: str = "", user_agent: str = "", detail: str = ""):
    try:
        await accounts.insert_auth_event({
            "timestamp": now_utc(), "type": event_type, "email": email, "user_id": user_id,
            "ip": ip, "user_agent": user_agent[:256], "detail": detail,
        })
    except Exception as e:
        logger.error(f"Failed to record auth event {event_type}: {e}")


# Users

async def get_user_by_id(user_id: str) -> Optional[dict]:
    return await accounts.get_user(user_id)


async def get_user_by_email(email: str) -> Optional[dict]:
    return await accounts.get_user_by_email(email)


async def list_users() -> List[dict]:
    return [user_to_public(u) for u in await accounts.list_users()]


async def create_user(email: str, full_name: str, role: str, password: str,
                      must_change_password: bool = False, pending_approval: bool = False) -> dict:
    """Raises EmailTaken if the email is already registered."""
    now = now_utc()
    return await accounts.insert_user({
        "email": email,
        "full_name": full_name,
        "role": role,
        "password_hash": await security.hash_password(password),
        "is_active": not pending_approval,
        "pending_approval": pending_approval,
        "must_change_password": must_change_password,
        "created_at": now,
        "updated_at": now,
        "password_changed_at": now,
    })


async def update_user(user_id: str, fields: dict) -> Optional[dict]:
    return await accounts.update_user(user_id, {**fields, "updated_at": now_utc()})


async def delete_user(user_id: str):
    await accounts.delete_user(user_id)


async def count_active_admins() -> int:
    return await accounts.count_active_admins()


async def set_password(user_id: str, new_password: str, must_change_password: bool = False):
    now = now_utc()
    await accounts.update_user(user_id, {
        "password_hash": await security.hash_password(new_password),
        "must_change_password": must_change_password,
        "password_changed_at": now,
        "updated_at": now,
        "failed_login_attempts": 0,
        "locked_until": None,
    })


# Login

async def authenticate(email: str, password: str) -> Tuple[Optional[dict], str]:
    """Returns (user, failure_reason). failure_reason is for the audit log only;
    callers must show the same generic message for every failure."""
    user = await accounts.get_user_by_email(email)
    now = now_utc()

    if user is None:
        await security.verify_password(None, password)  # equalise timing
        return None, "unknown_email"

    locked_until = utc(user.get("locked_until"))
    if locked_until and locked_until > now:
        await security.verify_password(None, password)
        return None, "locked"

    if not await security.verify_password(user["password_hash"], password):
        attempts = user.get("failed_login_attempts", 0) + 1
        update = {"failed_login_attempts": attempts}
        reason = "bad_password"
        if attempts >= config.LOGIN_MAX_FAILED_ATTEMPTS:
            update["locked_until"] = now + timedelta(minutes=config.LOGIN_LOCKOUT_MINUTES)
            update["failed_login_attempts"] = 0
            reason = "bad_password_locked"
        await accounts.update_user(user["id"], update)
        return None, reason

    if not user.get("is_active", True):
        return None, "pending" if user.get("pending_approval") else "inactive"

    update = {"failed_login_attempts": 0, "locked_until": None, "last_login_at": now}
    if security.needs_rehash(user["password_hash"]):
        update["password_hash"] = await security.hash_password(password)
    return await accounts.update_user(user["id"], update), ""


# Sessions

async def create_session(user: dict, ip: str, user_agent: str) -> Tuple[str, dict]:
    token = security.new_token()
    now = now_utc()
    session = await accounts.insert_session({
        "token_hash": security.hash_token(token),
        "user_id": user["id"],
        "csrf_token": security.new_token(),
        "created_at": now,
        "last_seen_at": now,
        "expires_at": now + timedelta(hours=config.SESSION_ABSOLUTE_TIMEOUT_HOURS),
        "ip": ip,
        "user_agent": user_agent[:256],
    })
    return token, session


async def get_valid_session(token: str) -> Optional[dict]:
    session = await accounts.get_session_by_token_hash(security.hash_token(token))
    if not session:
        return None
    now = now_utc()
    if session["expires_at"] <= now or session["last_seen_at"] + timedelta(minutes=config.SESSION_IDLE_TIMEOUT_MINUTES) <= now:
        await accounts.delete_session(session["id"])
        return None
    # Slide the idle window, but avoid a write on every request
    if (now - session["last_seen_at"]) > timedelta(seconds=60):
        await accounts.touch_session(session["id"], now)
        session["last_seen_at"] = now
    return session


def session_expiry(session: dict) -> datetime:
    idle_expiry = session["last_seen_at"] + timedelta(minutes=config.SESSION_IDLE_TIMEOUT_MINUTES)
    return min(idle_expiry, session["expires_at"])


async def delete_session(token: str):
    await accounts.delete_session_by_token_hash(security.hash_token(token))


async def delete_user_sessions(user_id: str, except_session_id: Optional[str] = None):
    await accounts.delete_user_sessions(user_id, except_session_id)


async def delete_expired_sessions() -> int:
    return await accounts.delete_expired_sessions(now_utc())
