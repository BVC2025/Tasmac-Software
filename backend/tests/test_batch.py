"""Multi-bottle sessions: one customer, up to 3 bottles (one per lane), one payout."""

from sqlalchemy import select

from app.db import SessionLocal
from app.models import RefundClaim, SessionBottle, SmsMessage, Transaction

from .conftest import mfg_qr, refund_qr


async def reserve(machine, sid: str, lane: int, refund: str | None = None, mfg: str | None = None) -> dict:
    r = await machine.post(f"/sessions/{sid}/eligibility",
                           {"refund_raw": refund or refund_qr(), "mfg_raw": mfg or mfg_qr(), "lane": lane})
    assert r.status_code == 200, r.text
    return r.json()


async def bottles(sid: str) -> dict[int, tuple[str, str | None]]:
    async with SessionLocal() as db:
        rows = (await db.execute(select(SessionBottle).where(SessionBottle.session_id == sid))).scalars().all()
        return {b.lane: (b.status, b.reason) for b in rows}


async def test_three_bottles_one_payout(machine):
    for lane in (1, 2, 3):
        assert (await reserve(machine, "s1", lane))["ok"]
    txn = (await machine.post("/sessions/s1/transaction", {"kind": "mobile", "value": "9876543210"})).json()
    assert txn["amount_paise"] == 3000 and txn["bottle_count"] == 3
    paid = (await machine.post(f"/transactions/{txn['id']}/payout")).json()
    assert paid["status"] == "SUCCESS"
    await machine.post("/sessions/s1/accepted", {"txn_id": txn["id"]})
    assert await bottles("s1") == {1: ("ACCEPTED", None), 2: ("ACCEPTED", None), 3: ("ACCEPTED", None)}
    async with SessionLocal() as db:
        statuses = (await db.execute(select(RefundClaim.status))).scalars().all()
        assert statuses == ["CONSUMED"] * 3
        sms = (await db.execute(select(SmsMessage))).scalar_one()
        assert "Rs.30.00" in sms.body and "3 bottles" in sms.body


async def test_rejected_lane_is_not_paid(machine):
    assert (await reserve(machine, "s1", 1))["ok"]
    r = await machine.post("/sessions/s1/bottles/2/rejected", {"reason": "BOTTLE_DAMAGED"})
    assert r.status_code == 204
    assert (await reserve(machine, "s1", 3))["ok"]
    txn = (await machine.post("/sessions/s1/transaction", {"kind": "upi", "value": "ravi@okaxis"})).json()
    assert txn["amount_paise"] == 2000 and txn["bottle_count"] == 2
    assert (await bottles("s1"))[2] == ("REJECTED", "BOTTLE_DAMAGED")


async def test_rejecting_a_reserved_lane_releases_its_qr(machine):
    r = refund_qr()
    assert (await reserve(machine, "s1", 1, refund=r))["ok"]
    await machine.post("/sessions/s1/bottles/1/rejected", {"reason": "BOTTLE_REMOVED"})
    assert (await reserve(machine, "s2", 1, refund=r))["ok"]   # free again for another customer


async def test_same_refund_qr_in_two_lanes(machine):
    r = refund_qr()
    assert (await reserve(machine, "s1", 1, refund=r))["ok"]
    v = await reserve(machine, "s1", 2, refund=r)
    assert v == {"ok": False, "reason": "REFUND_QR_IN_USE", "data": {}}
    assert (await bottles("s1"))[2] == ("REJECTED", "REFUND_QR_IN_USE")
    pre = (await machine.post("/sessions/s1/refund-qr", {"raw": r, "lane": 3})).json()
    assert pre["reason"] == "REFUND_QR_IN_USE"


async def test_same_bottle_in_two_lanes(machine):
    m = mfg_qr()
    assert (await reserve(machine, "s1", 1, mfg=m))["ok"]
    assert (await reserve(machine, "s1", 2, mfg=m))["reason"] == "BOTTLE_IN_USE"


async def test_payout_failed_returns_whole_batch(machine):
    for lane in (1, 2):
        await reserve(machine, "s1", lane)
    txn = (await machine.post("/sessions/s1/transaction", {"kind": "upi", "value": "fail.x@okaxis"})).json()
    assert (await machine.post(f"/transactions/{txn['id']}/payout")).json()["status"] == "FAILED"
    await machine.post("/sessions/s1/returned", {"reason": "PAYOUT_FAILED"})
    assert await bottles("s1") == {1: ("RETURNED", "PAYOUT_FAILED"), 2: ("RETURNED", "PAYOUT_FAILED")}
    async with SessionLocal() as db:
        assert set((await db.execute(select(RefundClaim.status))).scalars()) == {"RELEASED"}
        t = await db.get(Transaction, txn["id"])
        assert t.bottle_count == 2 and not t.sms_sent


async def test_stats_and_report_count_bottles(machine, client, viewer_h):
    await reserve(machine, "s1", 1)
    await machine.post("/sessions/s1/bottles/2/rejected", {"reason": "BOTTLE_DAMAGED"})
    await reserve(machine, "s1", 3)
    txn = (await machine.post("/sessions/s1/transaction", {"kind": "upi", "value": "ravi@okaxis"})).json()
    await machine.post(f"/transactions/{txn['id']}/payout")
    await machine.post("/sessions/s1/accepted", {"txn_id": txn["id"]})
    s = (await client.get("/api/admin/v1/stats", headers=viewer_h)).json()
    assert (s["sessions_today"], s["bottles_accepted_today"], s["bottles_returned_today"]) == (1, 2, 1)
    assert s["amount_refunded_today_paise"] == 2000
    rep = (await client.get("/api/admin/v1/reports/daily", headers=viewer_h)).json()["totals"]
    assert (rep["sessions"], rep["accepted"], rep["returned"], rep["paid"], rep["amount_paise"]) == (1, 2, 1, 1, 2000)
    sess = (await client.get("/api/admin/v1/sessions", headers=viewer_h)).json()[0]
    assert [(b["lane"], b["status"]) for b in sess["bottles"]] == [(1, "ACCEPTED"), (2, "REJECTED"), (3, "ACCEPTED")]
    t = (await client.get("/api/admin/v1/transactions", headers=viewer_h)).json()[0]
    assert t["bottle_count"] == 2
