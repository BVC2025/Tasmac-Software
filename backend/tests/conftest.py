import os

from pathlib import Path


def _test_db_url() -> str:
    """RVM_TEST_DATABASE_URL from the environment or backend/.env (never the main DB)."""
    if os.environ.get("RVM_TEST_DATABASE_URL"):
        return os.environ["RVM_TEST_DATABASE_URL"]
    env = Path(__file__).resolve().parents[1] / ".env"
    for line in env.read_text().splitlines() if env.exists() else []:
        if line.startswith("RVM_TEST_DATABASE_URL="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("Set RVM_TEST_DATABASE_URL (tests drop and recreate all tables)")


os.environ["RVM_DATABASE_URL"] = _test_db_url()
os.environ["RVM_QR_SIGNING_SECRET"] = "test-secret"
os.environ["RVM_RECONCILE_AFTER_S"] = "0"

import hashlib  # noqa: E402
import hmac  # noqa: E402
import itertools  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import AdminUser, EligibleBrand, Machine, Role  # noqa: E402
from app.security import hash_api_key, hash_password  # noqa: E402

SECRET = "test-secret"
ADMIN_PASSWORD = "Test-pass-123"
_PW_HASH = None  # computed once (scrypt is deliberately slow)
MACHINE_HEADERS = {"X-Machine-Id": "RVM-T1", "X-Api-Key": "key-1"}
MACHINE2_HEADERS = {"X-Machine-Id": "RVM-T2", "X-Api-Key": "key-2"}
_serial = itertools.count(1000000000)


def _sig(body: str) -> str:
    return hmac.new(SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()[:16]


def refund_qr(serial: str | None = None) -> str:
    body = f"TRQ1.{serial or f'R{next(_serial)}'}"
    return f"{body}.{_sig(body)}"


def mfg_qr(brand: str = "KF", serial: str | None = None) -> str:
    body = f"TMQ1.{brand}.B1.{serial or f'M{next(_serial)}'}"
    return f"{body}.{_sig(body)}"


@pytest.fixture(scope="session", autouse=True)
async def schema():
    global _PW_HASH
    _PW_HASH = hash_password(ADMIN_PASSWORD)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest.fixture(autouse=True)
async def clean_db(schema):
    async with engine.begin() as conn:
        tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
        await conn.execute(text(f"TRUNCATE {tables} CASCADE"))
    async with SessionLocal() as db:
        db.add_all([
            Machine(id="RVM-T1", name="T1", api_key_hash=hash_api_key("key-1")),
            Machine(id="RVM-T2", name="T2", api_key_hash=hash_api_key("key-2")),
            EligibleBrand(code="KF", name="KF"),
            *[AdminUser(username=r.value.lower(), full_name=r.value, role=r, password_hash=_PW_HASH) for r in Role],
        ])
        await db.commit()


@pytest.fixture
async def client():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


class MachineClient:
    """Drives the API the same way the machine does."""

    def __init__(self, client: httpx.AsyncClient, headers: dict = MACHINE_HEADERS):
        self.c, self.h = client, headers

    async def post(self, path: str, json: dict | None = None):
        return await self.c.post(f"/api/machine/v1{path}", json=json or {}, headers=self.h)

    async def get(self, path: str):
        return await self.c.get(f"/api/machine/v1{path}", headers=self.h)

    async def reserve(self, sid: str, refund: str, mfg: str) -> dict:
        r = await self.post(f"/sessions/{sid}/eligibility", {"refund_raw": refund, "mfg_raw": mfg})
        assert r.status_code == 200, r.text
        return r.json()

    async def full_refund(self, sid: str, refund: str, mfg: str, upi: str = "ravi@okaxis") -> dict:
        v = await self.reserve(sid, refund, mfg)
        assert v["ok"], v
        txn = (await self.post(f"/sessions/{sid}/transaction", {"kind": "upi", "value": upi})).json()
        txn = (await self.post(f"/transactions/{txn['id']}/payout")).json()
        return txn


@pytest.fixture
def machine(client):
    return MachineClient(client)


@pytest.fixture
def machine2(client):
    return MachineClient(client, MACHINE2_HEADERS)


async def login(client: httpx.AsyncClient, username: str) -> dict:
    r = await client.post("/api/admin/v1/auth/login", json={"username": username, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
async def admin_h(client):
    return await login(client, "admin")


@pytest.fixture
async def operator_h(client):
    return await login(client, "operator")


@pytest.fixture
async def viewer_h(client):
    return await login(client, "viewer")
