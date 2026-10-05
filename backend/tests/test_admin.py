import asyncio
from datetime import timedelta

from sqlalchemy import select, update

from app.alerts import evaluate_alerts
from app.db import SessionLocal
from app.models import Alert, Machine, Transaction, utcnow

from .conftest import ADMIN_PASSWORD, mfg_qr, refund_qr

API = "/api/admin/v1"


async def test_login_and_me(client, admin_h):
    me = (await client.get(f"{API}/auth/me", headers=admin_h)).json()
    assert me["username"] == "admin" and me["role"] == "ADMIN"


async def test_bad_password_and_lockout(client):
    for _ in range(5):
        r = await client.post(f"{API}/auth/login", json={"username": "viewer", "password": "wrong-pass-1"})
        assert r.status_code == 401
    r = await client.post(f"{API}/auth/login", json={"username": "viewer", "password": ADMIN_PASSWORD})
    assert r.status_code == 423  # locked even with the right password


async def test_unknown_user_same_error(client):
    r = await client.post(f"{API}/auth/login", json={"username": "nobody", "password": "x"})
    assert r.status_code == 401 and r.json()["detail"] == "Invalid username or password"


async def test_invalid_token(client):
    r = await client.get(f"{API}/stats", headers={"Authorization": "Bearer junk"})
    assert r.status_code == 401


async def test_change_password(client, operator_h):
    r = await client.post(f"{API}/auth/password", headers=operator_h,
                          json={"current_password": ADMIN_PASSWORD, "new_password": "New-pass-2026"})
    assert r.status_code == 204
    ok = await client.post(f"{API}/auth/login", json={"username": "operator", "password": "New-pass-2026"})
    assert ok.status_code == 200


async def test_roles(client, viewer_h, operator_h, admin_h):
    # viewer: read only
    assert (await client.get(f"{API}/transactions", headers=viewer_h)).status_code == 200
    assert (await client.patch(f"{API}/machines/RVM-T1", json={"active": False}, headers=viewer_h)).status_code == 403
    # operator: can disable a machine, cannot register one
    assert (await client.patch(f"{API}/machines/RVM-T1", json={"active": False}, headers=operator_h)).status_code == 200
    assert (await client.post(f"{API}/machines", json={"id": "RVM-X", "name": "X"}, headers=operator_h)).status_code == 403
    # admin only: users
    assert (await client.get(f"{API}/users", headers=operator_h)).status_code == 403
    assert len((await client.get(f"{API}/users", headers=admin_h)).json()) == 3


async def test_disabled_machine_rejected(client, machine, operator_h):
    await client.patch(f"{API}/machines/RVM-T1", json={"active": False}, headers=operator_h)
    assert (await machine.post("/heartbeat", {})).status_code == 403


async def test_create_machine_and_rotate_key(client, admin_h):
    r = await client.post(f"{API}/machines", json={"id": "RVM-NEW-01", "name": "New", "location": "Chennai"}, headers=admin_h)
    assert r.status_code == 201
    key = r.json()["api_key"]
    hdr = {"X-Machine-Id": "RVM-NEW-01", "X-Api-Key": key}
    assert (await client.post("/api/machine/v1/heartbeat", json={}, headers=hdr)).status_code == 204
    new_key = (await client.post(f"{API}/machines/RVM-NEW-01/rotate-key", headers=admin_h)).json()["api_key"]
    assert new_key != key
    assert (await client.post("/api/machine/v1/heartbeat", json={}, headers=hdr)).status_code == 401


async def test_user_management(client, admin_h):
    body = {"username": "op2", "full_name": "Op", "role": "OPERATOR", "password": "short"}
    assert (await client.post(f"{API}/users", json=body, headers=admin_h)).status_code == 422
    body["password"] = "Strong-pass-42"
    r = await client.post(f"{API}/users", json=body, headers=admin_h)
    assert r.status_code == 201
    creds = {"username": "op2", "password": "Strong-pass-42"}
    assert (await client.post(f"{API}/auth/login", json=creds)).status_code == 200
    await client.patch(f"{API}/users/{r.json()['id']}", json={"active": False}, headers=admin_h)
    assert (await client.post(f"{API}/auth/login", json=creds)).status_code == 401
    me = (await client.get(f"{API}/auth/me", headers=admin_h)).json()
    assert (await client.patch(f"{API}/users/{me['id']}", json={"active": False}, headers=admin_h)).status_code == 400


async def test_brand_toggle_affects_eligibility(client, admin_h, machine):
    await client.patch(f"{API}/brands/KF", json={"active": False}, headers=admin_h)
    assert (await machine.reserve("s1", refund_qr(), mfg_qr()))["reason"] == "BRAND_NOT_ELIGIBLE"
    assert (await client.post(f"{API}/brands", json={"code": "NB", "name": "New brand"}, headers=admin_h)).status_code == 201
    assert (await machine.reserve("s2", refund_qr(), mfg_qr(brand="NB")))["ok"]


async def test_alerts_auto_open_and_close(client, machine, operator_h):
    await machine.post("/heartbeat", {"state": "OUT_OF_SERVICE", "bin_fill_pct": 90, "fault_reason": "Emergency stop active"})
    async with SessionLocal() as db:
        await evaluate_alerts(db)
    open_ = (await client.get(f"{API}/alerts", headers=operator_h)).json()
    assert {a["type"] for a in open_} == {"MACHINE_FAULT", "BIN_FULL"}
    assert "Emergency stop" in next(a["message"] for a in open_ if a["type"] == "MACHINE_FAULT")
    async with SessionLocal() as db:  # evaluating again must not duplicate
        await evaluate_alerts(db)
    assert len((await client.get(f"{API}/alerts", headers=operator_h)).json()) == 2
    await machine.post("/heartbeat", {"state": "READY", "bin_fill_pct": 10})
    async with SessionLocal() as db:
        await evaluate_alerts(db)
    assert (await client.get(f"{API}/alerts", headers=operator_h)).json() == []


async def test_fault_alert_while_retrying_health_check(client, machine, operator_h):
    await machine.post("/heartbeat", {"state": "HEALTH_CHECK", "fault_reason": "Emergency stop active"})
    async with SessionLocal() as db:
        await evaluate_alerts(db)
    assert [a["type"] for a in (await client.get(f"{API}/alerts", headers=operator_h)).json()] == ["MACHINE_FAULT"]


async def test_machine_offline_alert(client, operator_h, machine):
    await machine.post("/heartbeat", {"state": "READY"})
    async with SessionLocal() as db:
        await db.execute(update(Machine).where(Machine.id == "RVM-T1")
                         .values(last_seen_at=utcnow() - timedelta(minutes=10)))
        await db.commit()
        await evaluate_alerts(db)
    types = [a["type"] for a in (await client.get(f"{API}/alerts", headers=operator_h)).json()]
    assert types == ["MACHINE_OFFLINE"]


async def test_paid_bottle_returned_manual_alert(client, machine, operator_h, viewer_h):
    txn = await machine.full_refund("s1", refund_qr(), mfg_qr())
    await machine.post("/sessions/s1/returned", {"reason": "PAYOUT_PENDING"})
    alerts = (await client.get(f"{API}/alerts", headers=operator_h)).json()
    a = next(a for a in alerts if a["type"] == "PAID_BOTTLE_RETURNED")
    assert a["entity_id"] == txn["id"] and a["auto"] is False
    path = f"{API}/alerts/{a['id']}/resolve"
    assert (await client.post(path, json={"note": "ok!"}, headers=viewer_h)).status_code == 403
    assert (await client.post(path, json={"note": "Customer verified"}, headers=operator_h)).status_code == 204
    resolved = (await client.get(f"{API}/alerts?status=RESOLVED", headers=operator_h)).json()
    assert resolved[0]["resolved_by"] == "operator"


async def test_payout_stuck_alert_and_recheck(client, machine, operator_h):
    txn = await machine.full_refund("s1", refund_qr(), mfg_qr(), upi="slow.x@okaxis")
    async with SessionLocal() as db:
        await db.execute(update(Transaction).where(Transaction.id == txn["id"])
                         .values(created_at=utcnow() - timedelta(hours=1)))
        await db.commit()
        await evaluate_alerts(db)
    assert (await client.get(f"{API}/alerts", headers=operator_h)).json()[0]["type"] == "PAYOUT_STUCK"
    await asyncio.sleep(3.1)
    r = await client.post(f"{API}/transactions/{txn['id']}/recheck", headers=operator_h)
    assert r.json()["status"] == "SUCCESS"
    async with SessionLocal() as db:
        await evaluate_alerts(db)
        assert (await db.execute(select(Alert).where(Alert.status == "OPEN"))).first() is None


async def test_daily_report_and_csv(client, machine, viewer_h):
    for sid in ("s1", "s2"):
        txn = await machine.full_refund(sid, refund_qr(), mfg_qr())
        await machine.post(f"/sessions/{sid}/accepted", {"txn_id": txn["id"]})
    await machine.post("/sessions/s3/refund-qr", {"raw": "junk"})
    await machine.post("/sessions/s3/returned", {"reason": "REFUND_QR_INVALID_FORMAT"})
    rep = (await client.get(f"{API}/reports/daily", headers=viewer_h)).json()
    assert rep["totals"] == {"sessions": 3, "accepted": 2, "returned": 1, "paid": 2,
                             "amount_paise": 2000, "failed": 0, "pending": 0}
    csv_r = await client.get(f"{API}/reports/daily.csv", headers=viewer_h)
    assert csv_r.headers["content-type"].startswith("text/csv")
    assert "RVM-T1" in csv_r.text and "20.00" in csv_r.text


async def test_search_transactions(client, machine, viewer_h):
    txn = await machine.full_refund("s1", refund_qr(), mfg_qr(), upi="findme@okaxis")
    rows = (await client.get(f"{API}/transactions?q=findme", headers=viewer_h)).json()
    assert [r["id"] for r in rows] == [txn["id"]]
