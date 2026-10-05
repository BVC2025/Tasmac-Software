"""Admin API for the admin portal.

Roles: VIEWER reads everything, OPERATOR can act on operations (alerts, payout
re-check, enable/disable machines), ADMIN manages machines, keys and brands.
"""

import csv
import io
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .. import services as svc
from ..db import get_db
from ..models import (
    AdminUser, Alert, AuditLog, EligibleBrand, Machine, RefundClaim, Role, RvmSession, SmsMessage, Transaction,
    TxnStatus, utcnow,
)
from ..schemas import MachineOut, StatsOut, TxnAdminOut
from ..security import current_admin, hash_api_key, new_api_key, require_role

router = APIRouter(prefix="/api/admin/v1", tags=["admin"], dependencies=[Depends(current_admin)])
operator = require_role(Role.OPERATOR)
admin_only = require_role(Role.ADMIN)

IST = timezone(timedelta(hours=5, minutes=30), "IST")  # India has no DST
ONLINE_WINDOW = timedelta(minutes=2)


def _today_start() -> datetime:
    """Midnight today in India, as a UTC timestamp."""
    return datetime.combine(datetime.now(IST).date(), time.min, tzinfo=IST).astimezone(timezone.utc)


def _actor(user: AdminUser) -> str:
    return f"admin:{user.username}"


# ---------------- dashboard ----------------

@router.get("/stats", response_model=StatsOut)
async def stats(db: AsyncSession = Depends(get_db)):
    today = _today_start()
    now = datetime.now(timezone.utc)

    async def count(q):
        return (await db.execute(q)).scalar_one()

    return StatsOut(
        machines_total=await count(select(func.count()).select_from(Machine).where(Machine.active.is_(True))),
        machines_online=await count(select(func.count()).select_from(Machine)
                                    .where(Machine.active.is_(True), Machine.last_seen_at > now - ONLINE_WINDOW)),
        sessions_today=await count(select(func.count()).select_from(RvmSession)
                                   .where(RvmSession.started_at >= today)),
        bottles_accepted_today=await count(select(func.count()).select_from(RvmSession).where(
            RvmSession.started_at >= today, RvmSession.outcome == "ACCEPTED")),
        bottles_returned_today=await count(select(func.count()).select_from(RvmSession).where(
            RvmSession.started_at >= today, RvmSession.outcome == "RETURNED")),
        refunds_success_today=await count(select(func.count()).select_from(Transaction).where(
            Transaction.created_at >= today, Transaction.status == TxnStatus.SUCCESS)),
        refunds_pending=await count(select(func.count()).select_from(Transaction)
                                    .where(Transaction.status == TxnStatus.PENDING)),
        refunds_failed_today=await count(select(func.count()).select_from(Transaction).where(
            Transaction.created_at >= today, Transaction.status == TxnStatus.FAILED)),
        amount_refunded_today_paise=await count(select(func.coalesce(func.sum(Transaction.amount_paise), 0)).where(
            Transaction.created_at >= today, Transaction.status == TxnStatus.SUCCESS)),
        open_alerts=await count(select(func.count()).select_from(Alert).where(Alert.status == "OPEN")),
    )


# ---------------- machines ----------------

class MachineCreateIn(BaseModel):
    id: str = Field(min_length=3, max_length=32, pattern=r"^[A-Z0-9-]+$")
    name: str = Field(min_length=1, max_length=120)
    location: str | None = Field(default=None, max_length=255)


class MachineUpdateIn(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    location: str | None = Field(default=None, max_length=255)
    active: bool | None = None


@router.get("/machines", response_model=list[MachineOut])
async def machines(db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(Machine).order_by(Machine.id))).scalars().all()


@router.post("/machines", status_code=201)
async def create_machine(body: MachineCreateIn, user: AdminUser = Depends(admin_only),
                         db: AsyncSession = Depends(get_db)):
    key = new_api_key()
    db.add(Machine(id=body.id, name=body.name, location=body.location, api_key_hash=hash_api_key(key)))
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(409, "Machine ID already exists")
    svc.audit(db, _actor(user), "MACHINE_CREATED", "machine", body.id, name=body.name)
    await db.commit()
    return {"id": body.id, "api_key": key}  # shown once


@router.patch("/machines/{machine_id}", response_model=MachineOut)
async def update_machine(machine_id: str, body: MachineUpdateIn, user: AdminUser = Depends(operator),
                         db: AsyncSession = Depends(get_db)):
    m = await db.get(Machine, machine_id)
    if m is None:
        raise HTTPException(404, "Machine not found")
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(m, k, v)
    svc.audit(db, _actor(user), "MACHINE_UPDATED", "machine", machine_id, **{k: str(v) for k, v in changes.items()})
    await db.commit()
    return m


@router.post("/machines/{machine_id}/rotate-key")
async def rotate_key(machine_id: str, user: AdminUser = Depends(admin_only), db: AsyncSession = Depends(get_db)):
    m = await db.get(Machine, machine_id)
    if m is None:
        raise HTTPException(404, "Machine not found")
    key = new_api_key()
    m.api_key_hash = hash_api_key(key)
    svc.audit(db, _actor(user), "MACHINE_KEY_ROTATED", "machine", machine_id)
    await db.commit()
    return {"id": machine_id, "api_key": key}


# ---------------- brands ----------------

class BrandIn(BaseModel):
    code: str = Field(min_length=1, max_length=16, pattern=r"^[A-Z0-9-]+$")
    name: str = Field(min_length=1, max_length=120)
    active: bool = True


class BrandUpdateIn(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    active: bool | None = None


@router.get("/brands")
async def brands(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(EligibleBrand).order_by(EligibleBrand.code))).scalars().all()
    return [{"code": b.code, "name": b.name, "active": b.active} for b in rows]


@router.post("/brands", status_code=201)
async def create_brand(body: BrandIn, user: AdminUser = Depends(admin_only), db: AsyncSession = Depends(get_db)):
    db.add(EligibleBrand(code=body.code, name=body.name, active=body.active))
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(409, "Brand code already exists")
    svc.audit(db, _actor(user), "BRAND_CREATED", "brand", body.code, name=body.name)
    await db.commit()
    return body


@router.patch("/brands/{code}")
async def update_brand(code: str, body: BrandUpdateIn, user: AdminUser = Depends(admin_only),
                       db: AsyncSession = Depends(get_db)):
    b = await db.get(EligibleBrand, code)
    if b is None:
        raise HTTPException(404, "Brand not found")
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(b, k, v)
    svc.audit(db, _actor(user), "BRAND_UPDATED", "brand", code, **{k: str(v) for k, v in changes.items()})
    await db.commit()
    return {"code": b.code, "name": b.name, "active": b.active}


# ---------------- alerts ----------------

class ResolveIn(BaseModel):
    note: str = Field(min_length=3, max_length=255)


@router.get("/alerts")
async def alerts(status: str | None = "OPEN", limit: int = Query(100, le=500), db: AsyncSession = Depends(get_db)):
    q = select(Alert).order_by(Alert.created_at.desc()).limit(limit)
    if status:
        q = q.where(Alert.status == status)
    rows = (await db.execute(q)).scalars().all()
    return [{"id": a.id, "type": a.type, "severity": a.severity, "machine_id": a.machine_id, "entity_id": a.entity_id,
             "message": a.message, "status": a.status, "auto": a.auto, "created_at": a.created_at,
             "resolved_at": a.resolved_at, "resolved_by": a.resolved_by, "note": a.note} for a in rows]


@router.post("/alerts/{alert_id}/resolve", status_code=204)
async def resolve_alert(alert_id: int, body: ResolveIn, user: AdminUser = Depends(operator),
                        db: AsyncSession = Depends(get_db)):
    a = await db.get(Alert, alert_id)
    if a is None:
        raise HTTPException(404, "Alert not found")
    if a.status != "OPEN":
        raise HTTPException(409, "Alert already resolved")
    a.status, a.resolved_at, a.resolved_by, a.note = "RESOLVED", utcnow(), user.username, body.note
    svc.audit(db, _actor(user), "ALERT_RESOLVED", "alert", str(alert_id), type=a.type, note=body.note)
    await db.commit()


# ---------------- transactions ----------------

@router.get("/transactions", response_model=list[TxnAdminOut])
async def transactions(
    status: str | None = None,
    machine_id: str | None = None,
    q: str | None = Query(None, max_length=64, description="Search txn id, refund QR, UPI/mobile"),
    limit: int = Query(50, le=500),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    query = select(Transaction).order_by(Transaction.created_at.desc()).limit(limit).offset(offset)
    if status:
        query = query.where(Transaction.status == status)
    if machine_id:
        query = query.where(Transaction.machine_id == machine_id)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(Transaction.id.ilike(like) | Transaction.refund_serial.ilike(like)
                            | Transaction.dest_value.ilike(like))
    return (await db.execute(query)).scalars().all()


@router.post("/transactions/{txn_id}/recheck", response_model=TxnAdminOut)
async def recheck_payout(txn_id: str, user: AdminUser = Depends(operator), db: AsyncSession = Depends(get_db)):
    txn = (await db.execute(select(Transaction).where(Transaction.id == txn_id).with_for_update())).scalar_one_or_none()
    if txn is None:
        raise HTTPException(404, "Transaction not found")
    before = txn.status
    svc.audit(db, _actor(user), "PAYOUT_RECHECK", "transaction", txn_id, before=before)
    await svc.refresh_payout(db, txn)  # commits
    return txn


# ---------------- reports ----------------

def _report_range(from_: date | None, to: date | None) -> tuple[date, date, datetime, datetime]:
    to = to or datetime.now(IST).date()
    from_ = from_ or to - timedelta(days=6)
    if from_ > to or (to - from_).days > 366:
        raise HTTPException(422, "Invalid date range (max 1 year)")
    start = datetime.combine(from_, time.min, tzinfo=IST)
    end = datetime.combine(to + timedelta(days=1), time.min, tzinfo=IST)
    return from_, to, start, end


async def _daily_rows(db: AsyncSession, start: datetime, end: datetime, machine_id: str | None) -> list[dict]:
    s_day = func.date(func.timezone("Asia/Kolkata", RvmSession.started_at))
    sq = (select(s_day.label("day"), RvmSession.machine_id,
                 func.count().label("sessions"),
                 func.sum(case((RvmSession.outcome == "ACCEPTED", 1), else_=0)).label("accepted"),
                 func.sum(case((RvmSession.outcome == "RETURNED", 1), else_=0)).label("returned"))
          .where(RvmSession.started_at >= start, RvmSession.started_at < end)
          .group_by(s_day, RvmSession.machine_id))
    t_day = func.date(func.timezone("Asia/Kolkata", Transaction.created_at))
    tq = (select(t_day.label("day"), Transaction.machine_id,
                 func.sum(case((Transaction.status == TxnStatus.SUCCESS, 1), else_=0)).label("paid"),
                 func.sum(case((Transaction.status == TxnStatus.SUCCESS, Transaction.amount_paise), else_=0)).label("amount"),
                 func.sum(case((Transaction.status == TxnStatus.FAILED, 1), else_=0)).label("failed"),
                 func.sum(case((Transaction.status == TxnStatus.PENDING, 1), else_=0)).label("pending"))
          .where(Transaction.created_at >= start, Transaction.created_at < end)
          .group_by(t_day, Transaction.machine_id))
    if machine_id:
        sq = sq.where(RvmSession.machine_id == machine_id)
        tq = tq.where(Transaction.machine_id == machine_id)

    rows: dict[tuple, dict] = {}
    blank = {"sessions": 0, "accepted": 0, "returned": 0, "paid": 0, "amount_paise": 0, "failed": 0, "pending": 0}
    for r in (await db.execute(sq)).all():
        d = rows.setdefault((r.day, r.machine_id), {"day": r.day.isoformat(), "machine_id": r.machine_id, **blank})
        d.update(sessions=r.sessions, accepted=int(r.accepted), returned=int(r.returned))
    for r in (await db.execute(tq)).all():
        d = rows.setdefault((r.day, r.machine_id), {"day": r.day.isoformat(), "machine_id": r.machine_id, **blank})
        d.update(paid=int(r.paid), amount_paise=int(r.amount), failed=int(r.failed), pending=int(r.pending))
    return [rows[k] for k in sorted(rows, key=lambda k: (k[0], k[1]), reverse=True)]


@router.get("/reports/daily")
async def daily_report(from_: date | None = Query(None, alias="from"), to: date | None = None,
                       machine_id: str | None = None, db: AsyncSession = Depends(get_db)):
    f, t, start, end = _report_range(from_, to)
    rows = await _daily_rows(db, start, end, machine_id)
    totals = {k: sum(r[k] for r in rows) for k in ("sessions", "accepted", "returned", "paid", "amount_paise", "failed", "pending")}
    return {"from": f.isoformat(), "to": t.isoformat(), "rows": rows, "totals": totals}


@router.get("/reports/daily.csv")
async def daily_report_csv(from_: date | None = Query(None, alias="from"), to: date | None = None,
                           machine_id: str | None = None, db: AsyncSession = Depends(get_db)):
    f, t, start, end = _report_range(from_, to)
    rows = await _daily_rows(db, start, end, machine_id)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Date", "Machine", "Sessions", "Bottles accepted", "Bottles returned", "Refunds paid",
                "Amount (Rs)", "Refunds failed", "Refunds pending"])
    for r in rows:
        w.writerow([r["day"], r["machine_id"], r["sessions"], r["accepted"], r["returned"], r["paid"],
                    f"{r['amount_paise'] / 100:.2f}", r["failed"], r["pending"]])
    name = f"rvm-daily-{f.isoformat()}-to-{t.isoformat()}.csv"
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ---------------- lists ----------------

@router.get("/audit")
async def audit_log(entity_id: str | None = None, actor: str | None = None, limit: int = Query(100, le=1000),
                    db: AsyncSession = Depends(get_db)):
    q = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    if entity_id:
        q = q.where(AuditLog.entity_id == entity_id)
    if actor:
        q = q.where(AuditLog.actor.ilike(f"%{actor}%"))
    rows = (await db.execute(q)).scalars().all()
    return [{"at": r.at, "actor": r.actor, "action": r.action, "entity": r.entity,
             "entity_id": r.entity_id, "data": r.data} for r in rows]


@router.get("/sessions")
async def sessions(machine_id: str | None = None, outcome: str | None = None,
                   limit: int = Query(50, le=500), db: AsyncSession = Depends(get_db)):
    q = select(RvmSession).order_by(RvmSession.started_at.desc()).limit(limit)
    if machine_id:
        q = q.where(RvmSession.machine_id == machine_id)
    if outcome:
        q = q.where(RvmSession.outcome == outcome)
    rows = (await db.execute(q)).scalars().all()
    return [{"id": r.id, "machine_id": r.machine_id, "refund_serial": r.refund_serial, "mfg_serial": r.mfg_serial,
             "brand": r.brand, "outcome": r.outcome, "reason": r.reason, "started_at": r.started_at,
             "ended_at": r.ended_at} for r in rows]


@router.get("/sms")
async def sms_messages(limit: int = Query(50, le=500), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(SmsMessage).order_by(SmsMessage.id.desc()).limit(limit))).scalars().all()
    return [{"id": r.id, "txn_id": r.txn_id, "mobile": "XXXXXX" + r.mobile[-4:], "body": r.body,
             "status": r.status, "created_at": r.created_at} for r in rows]


@router.get("/claims")
async def claims(status: str | None = None, q: str | None = Query(None, max_length=64),
                 limit: int = Query(50, le=500), db: AsyncSession = Depends(get_db)):
    query = select(RefundClaim).order_by(RefundClaim.updated_at.desc()).limit(limit)
    if status:
        query = query.where(RefundClaim.status == status)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(RefundClaim.refund_serial.ilike(like) | RefundClaim.mfg_serial.ilike(like))
    rows = (await db.execute(query)).scalars().all()
    return [{"refund_serial": r.refund_serial, "mfg_serial": r.mfg_serial, "brand": r.brand, "status": r.status,
             "machine_id": r.machine_id, "session_id": r.session_id, "consumed_at": r.consumed_at,
             "updated_at": r.updated_at} for r in rows]
