import os
from urllib.parse import quote


def _bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    val = os.environ.get(name)
    return int(val) if val else default


def _list(name: str) -> list:
    val = os.environ.get(name, "")
    return [v.strip() for v in val.split(",") if v.strip()]


ENVIRONMENT = os.environ.get("ENVIRONMENT", "development").lower()
IS_PRODUCTION = ENVIRONMENT == "production"

# PostgreSQL. DATABASE_URL wins; otherwise it's built from the POSTGRES_* values for a
# server on this machine (local development).
DATABASE_URL = os.environ.get("DATABASE_URL") or (
    "postgresql+asyncpg://{user}:{password}@127.0.0.1:{port}/{db}".format(
        user=os.environ.get("POSTGRES_USER", "pharmacore"),
        password=quote(os.environ.get("POSTGRES_PASSWORD", ""), safe=""),
        port=os.environ.get("POSTGRES_PORT", "5432"),
        db=os.environ.get("POSTGRES_DB", "pharmacore"),
    )
)
DB_POOL_SIZE = _int("DB_POOL_SIZE", 10)
# Total time startup keeps retrying the database (e.g. while its container is booting)
DB_CONNECT_TIMEOUT_SECONDS = _int("DB_CONNECT_TIMEOUT_SECONDS", 30)

# Interactive API docs are disabled in production
ENABLE_DOCS = _bool("ENABLE_DOCS", not IS_PRODUCTION)

# Browser origins allowed to call the API cross-origin. The bundled frontend is
# served from the same origin (nginx / vite proxy), so this is empty by default.
CORS_ORIGINS = _list("CORS_ORIGINS")

# Demo data. SEED_DEMO_DATA loads sample medicines, patients and ~30 days of sales into an
# empty database at startup. ALLOW_DEMO_RESET enables the admin "Reset & Seed" action,
# which DELETES all business data. Both default to off in production.
SEED_DEMO_DATA = _bool("SEED_DEMO_DATA", not IS_PRODUCTION)
ALLOW_DEMO_RESET = _bool("ALLOW_DEMO_RESET", not IS_PRODUCTION)
DEMO_RESET_CONFIRMATION = "RESET DEMO DATA"

# Store name recorded on invoices created at the POS
STORE_NAME = os.environ.get("STORE_NAME", "PharmaCore Central")

# Session cookie settings
SESSION_COOKIE_NAME = "pc_session"
SESSION_COOKIE_PATH = "/api"
CSRF_HEADER_NAME = "X-CSRF-Token"
# Browsers treat http://localhost as a secure context, so Secure cookies work locally.
# Only disable this when serving over plain HTTP on a non-localhost host.
COOKIE_SECURE = _bool("COOKIE_SECURE", True)
SESSION_IDLE_TIMEOUT_MINUTES = _int("SESSION_IDLE_TIMEOUT_MINUTES", 30)
SESSION_ABSOLUTE_TIMEOUT_HOURS = _int("SESSION_ABSOLUTE_TIMEOUT_HOURS", 12)

# Brute-force protection (per account)
LOGIN_MAX_FAILED_ATTEMPTS = _int("LOGIN_MAX_FAILED_ATTEMPTS", 5)
LOGIN_LOCKOUT_MINUTES = _int("LOGIN_LOCKOUT_MINUTES", 15)

# Self-registration from the login page. New accounts start disabled with the
# lowest role and need administrator approval before they can sign in.
ALLOW_SELF_REGISTRATION = _bool("ALLOW_SELF_REGISTRATION", True)

# Password policy (NIST SP 800-63B: favour length over composition rules)
PASSWORD_MIN_LENGTH = _int("PASSWORD_MIN_LENGTH", 12)
PASSWORD_MAX_LENGTH = 128

# First-run administrator bootstrap. Only used when the users collection is empty;
# the account must change its password on first login.
BOOTSTRAP_ADMIN_EMAIL = os.environ.get("BOOTSTRAP_ADMIN_EMAIL", "").strip().lower()
BOOTSTRAP_ADMIN_PASSWORD = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "")
BOOTSTRAP_ADMIN_NAME = os.environ.get("BOOTSTRAP_ADMIN_NAME", "System Administrator")
