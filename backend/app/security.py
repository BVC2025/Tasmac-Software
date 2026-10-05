import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .db import get_db
from .models import ROLE_RANK, AdminUser, Machine, Role

# ---------------- machine API keys ----------------


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def new_api_key() -> str:
    return secrets.token_urlsafe(32)


async def current_machine(
    x_machine_id: str = Header(...),
    x_api_key: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> Machine:
    machine = await db.get(Machine, x_machine_id)
    if machine is None or not hmac.compare_digest(machine.api_key_hash, hash_api_key(x_api_key)):
        raise HTTPException(401, "Invalid machine credentials")
    if not machine.active:
        raise HTTPException(403, "Machine disabled")
    return machine


# ---------------- admin passwords (scrypt, stdlib) ----------------

_N, _R, _P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${base64.b64encode(salt).decode()}${base64.b64encode(h).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, h = stored.split("$")
        if algo != "scrypt":
            return False
        calc = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p),
                              dklen=len(base64.b64decode(h)))
        return hmac.compare_digest(calc, base64.b64decode(h))
    except (ValueError, TypeError):
        return False


def password_problem(password: str) -> str | None:
    if len(password) < 10:
        return "Password must be at least 10 characters"
    if password.isalpha() or password.isdigit():
        return "Password must mix letters and numbers or symbols"
    return None


# ---------------- admin JWT ----------------

def create_token(user: AdminUser) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user.id), "usr": user.username, "role": user.role, "iat": now,
               "exp": now + timedelta(minutes=s.jwt_ttl_minutes)}
    return jwt.encode(payload, s.jwt_secret, algorithm="HS256")


_bearer = HTTPBearer(auto_error=False)


async def current_admin(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> AdminUser:
    if creds is None:
        raise HTTPException(401, "Not signed in")
    try:
        payload = jwt.decode(creds.credentials, get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Session expired, please sign in again")
    user = await db.get(AdminUser, int(payload["sub"]))
    if user is None or not user.active:
        raise HTTPException(401, "User disabled")
    return user


def require_role(min_role: Role):
    async def dep(user: AdminUser = Depends(current_admin)) -> AdminUser:
        if ROLE_RANK[Role(user.role)] < ROLE_RANK[min_role]:
            raise HTTPException(403, f"Requires {min_role.value} role")
        return user
    return dep
