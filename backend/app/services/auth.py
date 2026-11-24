"""Login, tokens and roles.

- Passwords: salted PBKDF2-SHA256 (Python standard library), never stored or logged in plain text.
- Tokens: signed JWTs (HS256) with the username, role and an expiry; the server trusts nothing else.
- Lockout: 5 wrong passwords lock an account for 5 minutes (per server process).
- Roles: INTAKE (create, upload, verify), REVIEWER (+ decisions, fraud graph, monitoring), ADMIN (everything).

In production this would sit behind the company's identity provider (e.g. Microsoft Entra ID single sign-on),
with roles from directory groups; the role checks below stay the same.
"""
import base64
import hashlib
import hmac
import os
import secrets
import time
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import User
from ..observability import log_event

ITERATIONS = 200_000
MAX_FAILURES, LOCK_SECONDS = 5, 300
ROLES = ("INTAKE", "REVIEWER", "ADMIN")
DEMO_USERS = [("intake01", "Priya Nair (intake)", "INTAKE"),
              ("reviewer01", "Rahul Verma (claims reviewer)", "REVIEWER"),
              ("admin01", "Anita Rao (admin)", "ADMIN")]

_bearer = HTTPBearer(auto_error=False)
_failures: dict[str, list[float]] = {}
_dev_secret = secrets.token_urlsafe(32)  # used only when AUTH_SECRET is not set (tokens die on restart)


# ---------------------------------------------------------------- passwords
def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt, digest = stored.split("$")
        check = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt), int(iters))
        return hmac.compare_digest(check, base64.b64decode(digest))
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------- tokens
def _secret() -> str:
    return settings.auth_secret or _dev_secret


def create_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    claims = {"sub": user.username, "role": user.role, "name": user.full_name,
              "iat": now, "exp": now + timedelta(minutes=settings.auth_token_minutes)}
    return jwt.encode(claims, _secret(), algorithm="HS256")


def _unauthorized(detail: str = "Please sign in.") -> HTTPException:
    return HTTPException(401, detail, headers={"WWW-Authenticate": "Bearer"})


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
                 db: Session = Depends(get_db)) -> User:
    """FastAPI dependency: the signed-in user, or 401."""
    if creds is None:
        raise _unauthorized()
    try:
        claims = jwt.decode(creds.credentials, _secret(), algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Your session has expired. Please sign in again.")
    except jwt.InvalidTokenError:
        raise _unauthorized("Invalid sign-in token.")
    user = db.scalar(select(User).where(User.username == claims.get("sub")))
    if user is None or not user.is_active:
        raise _unauthorized("This account is not active.")
    return user


def require_role(*roles: str):
    """FastAPI dependency factory: allow only these roles (ADMIN is always allowed)."""
    def check(user: User = Depends(current_user)) -> User:
        if user.role != "ADMIN" and user.role not in roles:
            raise HTTPException(403, f"Your role ({user.role.lower()}) can't do this.")
        return user
    return check


# ---------------------------------------------------------------- login
def _locked(username: str) -> bool:
    now = time.monotonic()
    recent = [t for t in _failures.get(username, []) if now - t < LOCK_SECONDS]
    _failures[username] = recent
    return len(recent) >= MAX_FAILURES


def authenticate(db: Session, username: str, password: str) -> User:
    username = username.strip().lower()
    if _locked(username):
        log_event("login_locked", username=username)
        raise HTTPException(429, "Too many failed attempts. Try again in 5 minutes.")
    user = db.scalar(select(User).where(User.username == username))
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        _failures.setdefault(username, []).append(time.monotonic())
        log_event("login_failed", username=username)
        raise _unauthorized("Wrong username or password.")
    _failures.pop(username, None)
    log_event("login", username=username, role=user.role)
    return user


def reset_lockouts() -> None:
    _failures.clear()


def ensure_demo_users(db: Session) -> None:
    """Create the three demo accounts if there are no users yet (fresh database)."""
    if db.scalar(select(User).limit(1)) is not None:
        return
    password = settings.demo_password
    if not password:
        password = "ClaimSense@2026"
        log_event("demo_password_default", warning="DEMO_PASSWORD not set; using the documented default. "
                                                   "Set DEMO_PASSWORD in .env before deploying.")
    for username, name, role in DEMO_USERS:
        db.add(User(username=username, full_name=name, role=role, password_hash=hash_password(password)))
    db.commit()
