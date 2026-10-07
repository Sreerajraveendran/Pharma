import asyncio
import hashlib
import hmac
import secrets
from typing import Optional

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from starlette.concurrency import run_in_threadpool

from app.core import config

# Argon2id with the library's RFC 9106 "low memory" defaults
_hasher = PasswordHasher()

# Verified against when the account doesn't exist, so the response time of a
# failed login doesn't reveal whether an email is registered.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(32))


# Argon2 is deliberately slow (~50-100 ms CPU, 64 MiB RAM per call). It runs in worker
# threads so it never blocks the event loop, and the semaphore bounds memory under load.
_argon2_slots = asyncio.Semaphore(4)


def _verify_sync(password_hash: Optional[str], password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


async def hash_password(password: str) -> str:
    async with _argon2_slots:
        return await run_in_threadpool(_hasher.hash, password)


async def verify_password(password_hash: Optional[str], password: str) -> bool:
    async with _argon2_slots:
        return await run_in_threadpool(_verify_sync, password_hash, password)


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    # Session tokens are stored hashed so a database leak doesn't expose live sessions
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def tokens_match(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def password_policy_error(password: str, email: str = "", name: str = "") -> Optional[str]:
    if len(password) < config.PASSWORD_MIN_LENGTH:
        return f"Password must be at least {config.PASSWORD_MIN_LENGTH} characters."
    if len(password) > config.PASSWORD_MAX_LENGTH:
        return f"Password must be at most {config.PASSWORD_MAX_LENGTH} characters."
    lowered = password.lower()
    if email and email.split("@")[0].lower() in lowered and len(email.split("@")[0]) >= 4:
        return "Password must not contain your email address."
    if name and name.lower().replace(" ", "") in lowered.replace(" ", "") and len(name) >= 4:
        return "Password must not contain your name."
    if len(set(password)) < 5:
        return "Password is too repetitive."
    return None
