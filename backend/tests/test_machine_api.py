import asyncio
import hashlib
import hmac
import json

from sqlalchemy import select

from app.db import SessionLocal
from app.models import AuditLog, RefundClaim, SmsMessage, Transaction
from app import services as svc

from .conftest import mfg_qr, refund_qr


async def test_auth_required(client):
    r = await client.post("/api/machine/v1/heartbeat", json={}, headers={"X-Machine-Id": "RVM-T1", "X-Api-Key": "x"})
    assert r.status_code == 401


async def test_heartbeat(machine):
    r = await machine.post("/heartbeat", {"state": "READY", "bin_fill_pct": 12})
    assert r.status_code == 204


async def test_refund_qr_verification(machine):
    ok = (await machine.post("/sessions/s1/refund-qr", {"raw": refund_qr()})).json()
    assert ok["ok"]
    forged = refund_qr()[:-4] + "0000"
    assert (await machine.post("/sessions/s1/refund-qr", {"raw": forged})).json()["reason"] == "REFUND_QR_FORGED"
    assert (await machine.post("/sessions/s1/refund-qr", {"raw": "hello"})).json()["reason"] == "REFUND_QR_INVALID_FORMAT"


async def test_brand_not_eligible(machine):
    v = await machine.reserve("s1", refund_qr(), mfg_qr(brand="XX"))
    assert v == {"ok": False, "reason": "BRAND_NOT_ELIGIBLE", "data": {}}


async def test_happy_path_and_sms(machine):
    r, m = refund_qr(), mfg_qr()
    txn = await machine.full_refund("s1", r, m, upi="9876543210@ybl")
    assert txn["status"] == "SUCCESS" and txn["amount_paise"] == 1000
    assert (await machine.post("/sessions/s1/accepted", {"txn_id": txn["id"]})).status_code == 204
    async with SessionLocal() as db:
        sms = (await db.execute(select(SmsMessage))).scalars().all()
        assert len(sms) == 1 and sms[0].mobile == "9876543210"
        claim = (await db.execute(select(RefundClaim))).scalar_one()
        assert claim.status == "CONSUMED"


async def test_refund_qr_used_only_once(machine):
    r = refund_qr()
    txn = await machine.full_refund("s1", r, mfg_qr())
    await machine.post("/sessions/s1/accepted", {"txn_id": txn["id"]})
    assert (await machine.post("/sessions/s2/refund-qr", {"raw": r})).json()["reason"] == "REFUND_QR_ALREADY_USED"
    assert (await machine.reserve("s2", r, mfg_qr()))["reason"] == "REFUND_QR_ALREADY_USED"


async def test_same_bottle_cannot_be_refunded_with_another_refund_qr(machine):
    m = mfg_qr()
    txn = await machine.full_refund("s1", refund_qr(), m)
    await machine.post("/sessions/s1/accepted", {"txn_id": txn["id"]})
    assert (await machine.reserve("s2", refund_qr(), m))["reason"] == "BOTTLE_ALREADY_RETURNED"


async def test_reservation_blocks_other_machine(machine, machine2):
    r = refund_qr()
    assert (await machine.reserve("s1", r, mfg_qr()))["ok"]
    assert (await machine2.reserve("s2", r, mfg_qr()))["reason"] == "REFUND_QR_IN_USE"
    # returned bottle releases the reservation
    await machine.post("/sessions/s1/returned", {"reason": "CUSTOMER_CANCELLED"})
    assert (await machine2.reserve("s2", r, mfg_qr()))["ok"]


async def test_concurrent_reservations_only_one_wins(machine, machine2):
    r = refund_qr()
    a, b = await asyncio.gather(machine.reserve("s1", r, mfg_qr()), machine2.reserve("s2", r, mfg_qr()))
    assert sorted([a["ok"], b["ok"]]) == [False, True]


async def test_transaction_requires_reservation(machine):
    r = await machine.post("/sessions/nope/transaction", {"kind": "upi", "value": "ab@okaxis"})
    assert r.status_code == 409 and r.json()["detail"] == "NO_ACTIVE_RESERVATION"


async def test_transaction_idempotent_per_session(machine):
    await machine.reserve("s1", refund_qr(), mfg_qr())
    t1 = (await machine.post("/sessions/s1/transaction", {"kind": "upi", "value": "ab@okaxis"})).json()
    t2 = (await machine.post("/sessions/s1/transaction", {"kind": "upi", "value": "ab@okaxis"})).json()
    assert t1["id"] == t2["id"]
    p1 = (await machine.post(f"/transactions/{t1['id']}/payout")).json()
    p2 = (await machine.post(f"/transactions/{t1['id']}/payout")).json()
    assert p1["status"] == p2["status"] == "SUCCESS"


async def test_other_machine_cannot_touch_transaction(machine, machine2):
    txn = await machine.full_refund("s1", refund_qr(), mfg_qr())
    assert (await machine2.get(f"/transactions/{txn['id']}")).status_code == 404


async def test_payout_failed_then_return_releases_qr(machine):
    r = refund_qr()
    txn = await machine.full_refund("s1", r, mfg_qr(), upi="fail.test@okaxis")
    assert txn["status"] == "FAILED"
    await machine.post("/sessions/s1/returned", {"reason": "PAYOUT_FAILED"})
    assert (await machine.reserve("s2", r, mfg_qr()))["ok"]  # customer can try again


async def test_destination_validation(machine):
    assert (await machine.post("/sessions/s1/destination", {"kind": "upi", "value": "ravi@okaxis"})).json()["ok"]
    assert (await machine.post("/sessions/s1/destination", {"kind": "mobile", "value": "+91 98765 43210"})).json()["ok"]
    bad = (await machine.post("/sessions/s1/destination", {"kind": "mobile", "value": "12345"})).json()
    assert bad["reason"] == "INVALID_DESTINATION"
    nf = (await machine.post("/sessions/s1/destination", {"kind": "upi", "value": "invalid@okaxis"})).json()
    assert nf["reason"] == "DESTINATION_NOT_FOUND"


async def test_pending_payout_reconciled_and_sms_after_accept(machine):
    txn = await machine.full_refund("s1", refund_qr(), mfg_qr(), upi="slow.9876543210@okaxis")
    assert txn["status"] == "PENDING"
    await machine.post("/sessions/s1/accepted", {"txn_id": txn["id"]})  # accept-on-pending policy
    await asyncio.sleep(3.1)
    async with SessionLocal() as db:
        await svc.reconcile_once(db)
        t = await db.get(Transaction, txn["id"])
        assert t.status == "SUCCESS" and t.sms_sent


async def test_paid_bottle_returned_raises_alert(machine):
    txn = await machine.full_refund("s1", refund_qr(), mfg_qr())
    await machine.post("/sessions/s1/returned", {"reason": "PAYOUT_PENDING"})
    async with SessionLocal() as db:
        alerts = (await db.execute(select(AuditLog).where(AuditLog.action == "ALERT_PAID_BOTTLE_RETURNED"))).all()
        assert len(alerts) == 1


async def test_webhook_signature_and_update(machine, client):
    txn = await machine.full_refund("s1", refund_qr(), mfg_qr(), upi="pending.x@okaxis")
    async with SessionLocal() as db:
        ref = (await db.get(Transaction, txn["id"])).provider_ref
    body = json.dumps({"provider_ref": ref, "status": "SUCCESS"}).encode()
    bad = await client.post("/api/webhooks/payout", content=body, headers={"X-Signature": "bad"})
    assert bad.status_code == 401
    sig = hmac.new(b"change-me", body, hashlib.sha256).hexdigest()
    ok = await client.post("/api/webhooks/payout", content=body, headers={"X-Signature": sig})
    assert ok.status_code == 204
    assert (await machine.get(f"/transactions/{txn['id']}")).json()["status"] == "SUCCESS"


async def test_admin_stats(machine, client, viewer_h):
    txn = await machine.full_refund("s1", refund_qr(), mfg_qr())
    await machine.post("/sessions/s1/accepted", {"txn_id": txn["id"]})
    assert (await client.get("/api/admin/v1/stats")).status_code == 401  # not signed in
    h = viewer_h
    s = (await client.get("/api/admin/v1/stats", headers=h)).json()
    assert s["bottles_accepted_today"] == 1 and s["amount_refunded_today_paise"] == 1000
    assert len((await client.get("/api/admin/v1/transactions", headers=h)).json()) == 1
    assert (await client.get("/api/admin/v1/sessions", headers=h)).json()[0]["outcome"] == "ACCEPTED"
    assert (await client.get("/api/admin/v1/claims", headers=h)).json()[0]["status"] == "CONSUMED"
    assert (await client.get("/api/admin/v1/sms", headers=h)).status_code == 200


async def test_optional_sms_mobile_for_upi_customer(machine):
    await machine.reserve("s1", refund_qr(), mfg_qr())
    txn = (await machine.post("/sessions/s1/transaction",
                              {"kind": "upi", "value": "ravi.kumar@okaxis", "sms_mobile": "+91 90000 12345"})).json()
    await machine.post(f"/transactions/{txn['id']}/payout")
    await machine.post("/sessions/s1/accepted", {"txn_id": txn["id"]})
    async with SessionLocal() as db:
        sms = (await db.execute(select(SmsMessage))).scalar_one()
        assert sms.mobile == "9000012345"
    bad = await machine.post("/sessions/s1/transaction", {"kind": "upi", "value": "x@ok", "sms_mobile": "123"})
    assert bad.status_code == 200  # idempotent: existing transaction returned


async def test_invalid_sms_mobile_rejected(machine):
    await machine.reserve("s1", refund_qr(), mfg_qr())
    r = await machine.post("/sessions/s1/transaction", {"kind": "upi", "value": "ravi@okaxis", "sms_mobile": "123"})
    assert r.status_code == 422 and r.json()["detail"] == "INVALID_SMS_MOBILE"
