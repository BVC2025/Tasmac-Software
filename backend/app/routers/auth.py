"""Admin login and user management."""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db import get_db
from ..models import AdminUser, Role, utcnow
from ..security import (
    create_token, current_admin, hash_password, password_problem, require_role, verify_password,
)
from ..services import audit

router = APIRouter(prefix="/api/admin/v1", tags=["auth"])

# Used to keep the login timing the same when the user does not exist
_DUMMY_HASH = hash_password("dummy-password-123")


class LoginIn(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: str
    role: str
    active: bool
    last_login_at: datetime | None
    locked_until: datetime | None


class LoginOut(BaseModel):
    access_token: str
    user: UserOut


class PasswordIn(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(max_length=128)


class UserCreateIn(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9._-]+$")
    full_name: str = Field(min_length=1, max_length=120)
    role: Role
    password: str = Field(max_length=128)


class UserUpdateIn(BaseModel):
    full_name: str | None = Field(default=None, max_length=120)
    role: Role | None = None
    active: bool | None = None
    password: str | None = Field(default=None, max_length=128)   # admin reset


@router.post("/auth/login", response_model=LoginOut)
async def login(body: LoginIn, db: AsyncSession = Depends(get_db)):
    s = get_settings()
    user = (await db.execute(select(AdminUser).where(AdminUser.username == body.username.strip()))).scalar_one_or_none()
    now = utcnow()
    if user and user.locked_until and user.locked_until > now:
        raise HTTPException(423, f"Account locked after failed attempts. Try again after {user.locked_until:%H:%M} UTC")
    ok = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    if not user or not ok or not user.active:
        if user:
            user.failed_logins += 1
            if user.failed_logins >= s.login_max_failures:
                user.locked_until = now + timedelta(minutes=s.login_lockout_minutes)
                user.failed_logins = 0
                audit(db, f"admin:{user.username}", "LOGIN_LOCKED", "user", str(user.id))
            await db.commit()
        raise HTTPException(401, "Invalid username or password")
    user.failed_logins, user.locked_until, user.last_login_at = 0, None, now
    audit(db, f"admin:{user.username}", "LOGIN", "user", str(user.id))
    await db.commit()
    return LoginOut(access_token=create_token(user), user=UserOut.model_validate(user))


@router.get("/auth/me", response_model=UserOut)
async def me(user: AdminUser = Depends(current_admin)):
    return user


@router.post("/auth/password", status_code=204)
async def change_password(body: PasswordIn, user: AdminUser = Depends(current_admin), db: AsyncSession = Depends(get_db)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Current password is wrong")
    if problem := password_problem(body.new_password):
        raise HTTPException(422, problem)
    user.password_hash = hash_password(body.new_password)
    audit(db, f"admin:{user.username}", "PASSWORD_CHANGED", "user", str(user.id))
    await db.commit()


# ---------------- users (ADMIN) ----------------

@router.get("/users", response_model=list[UserOut])
async def list_users(_: AdminUser = Depends(require_role(Role.ADMIN)), db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(AdminUser).order_by(AdminUser.username))).scalars().all()


@router.post("/users", response_model=UserOut, status_code=201)
async def create_user(body: UserCreateIn, admin: AdminUser = Depends(require_role(Role.ADMIN)),
                      db: AsyncSession = Depends(get_db)):
    if problem := password_problem(body.password):
        raise HTTPException(422, problem)
    user = AdminUser(username=body.username, full_name=body.full_name, role=body.role,
                     password_hash=hash_password(body.password))
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(409, "Username already exists")
    audit(db, f"admin:{admin.username}", "USER_CREATED", "user", str(user.id), username=user.username, role=body.role)
    await db.commit()
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(user_id: int, body: UserUpdateIn, admin: AdminUser = Depends(require_role(Role.ADMIN)),
                      db: AsyncSession = Depends(get_db)):
    user = await db.get(AdminUser, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    if user.id == admin.id and (body.active is False or (body.role and body.role != Role.ADMIN)):
        raise HTTPException(400, "You cannot disable or demote yourself")
    changes = body.model_dump(exclude_unset=True, exclude={"password"})
    for k, v in changes.items():
        setattr(user, k, v)
    if body.password:
        if problem := password_problem(body.password):
            raise HTTPException(422, problem)
        user.password_hash = hash_password(body.password)
        user.locked_until, user.failed_logins = None, 0
        changes["password"] = "reset"
    audit(db, f"admin:{admin.username}", "USER_UPDATED", "user", str(user.id), **{k: str(v) for k, v in changes.items()})
    await db.commit()
    return user
