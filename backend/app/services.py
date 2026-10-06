"""Refund business logic. Routers stay thin; everything money-related is here.

Guarantees:
  * A refund QR serial is paid at most once (row lock on refund_claims).
  * A manufacturing serial is consumed at most once (partial unique index).
  * One transaction per session (unique session_id) and provider idempotency key = txn id.
"""

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from . import qr
from .alerts import raise_alert
from .config import get_settings
from .models import (
    AlertType, AuditLog, BottleState, BottleStatus, SessionBottle, ClaimStatus, EligibleBrand, Machine, RefundClaim, RvmSession,
    SmsMessage, Transaction, TxnStatus, utcnow,
)
from .providers import PayoutResult, get_payout_provider, get_sms_provider

log = logging.getLogger(__name__)
settings = get_settings()

UPI_RE = re.compile(r"^[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z][a-zA-Z0-9]{1,63}$")
MOBILE_RE = re.compile(r"^[6-9]\d{9}$")
FINAL = {TxnStatus.SUCCESS, TxnStatus.FAILED}


class DomainError(Exception):
    """Request is not allowed in the current state (HTTP 409)."""

    def __init__(self, code: str, status_code: int = 409):
        super().__init__(code)
        self.code = code
        self.status_code = status_code


@dataclass
class Verdict:
    ok: bool
    reason: str = ""
    data: dict = field(default_factory=dict)


def audit(db: AsyncSession, actor: str, action: str, entity: str | None = None,
          entity_id: str | None = None, **data) -> None:
    db.add(AuditLog(actor=actor, action=action, entity=entity, entity_id=entity_id, data=data or None))


def mask(kind: str, value: str) -> str:
    if kind == "mobile":
        return "XXXXXX" + value[-4:]
    name, _, handle = value.partition("@")
    return f"{name[:2]}***@{handle}"


# ---------------- sessions ----------------

async def get_or_create_session(db: AsyncSession, machine: Machine, session_id: str) -> RvmSession:
    s = await db.get(RvmSession, session_id)
    if s is None:
        s = RvmSession(id=session_id, machine_id=machine.id)
        db.add(s)
        await db.flush()
    elif s.machine_id != machine.id:
        raise DomainError("SESSION_BELONGS_TO_OTHER_MACHINE", 403)
    return s


async def _bottle(db: AsyncSession, s: RvmSession, lane: int) -> SessionBottle:
    """The session's bottle in a lane (created on first use)."""
    res = await db.execute(select(SessionBottle).where(SessionBottle.session_id == s.id, SessionBottle.lane == lane))
    b = res.scalar_one_or_none()
    if b is None:
        b = SessionBottle(session_id=s.id, machine_id=s.machine_id, lane=lane, status=BottleState.CHECKING)
        db.add(b)
        await db.flush()
    return b


def _reject(b: SessionBottle, reason: str) -> None:
    if b.status in (BottleState.CHECKING, BottleState.VALID):
        b.status, b.reason = BottleState.REJECTED, reason


async def _claim_for_update(db: AsyncSession, serial: str) -> RefundClaim | None:
    res = await db.execute(select(RefundClaim).where(RefundClaim.refund_serial == serial).with_for_update())
    return res.scalar_one_or_none()


def _claim_blocks(claim: RefundClaim | None, session_id: str, lane: int) -> str | None:
    if claim is None:
        return None
    if claim.status == ClaimStatus.CONSUMED:
        return "REFUND_QR_ALREADY_USED"
    # Reserved by another session, or by another bottle of the same batch (copied sticker)
    if (claim.status == ClaimStatus.RESERVED and (claim.session_id != session_id or claim.lane != lane)
            and claim.reserved_until and claim.reserved_until > utcnow()):
        return "REFUND_QR_IN_USE"
    return None


async def _mfg_consumed(db: AsyncSession, mfg_serial: str) -> bool:
    res = await db.execute(select(RefundClaim.refund_serial).where(
        RefundClaim.mfg_serial == mfg_serial, RefundClaim.status == ClaimStatus.CONSUMED))
    return res.first() is not None


# ---------------- QR verification (per bottle / lane) ----------------

async def verify_refund_qr(db: AsyncSession, machine: Machine, session_id: str, raw: str, lane: int = 1) -> Verdict:
    s = await get_or_create_session(db, machine, session_id)
    b = await _bottle(db, s, lane)
    try:
        r = qr.parse_refund(raw, settings.qr_signing_secret)
    except qr.QRError as e:
        _reject(b, e.code)
        audit(db, f"machine:{machine.id}", "REFUND_QR_REJECTED", "session", session_id, reason=e.code, lane=lane)
        await db.commit()
        return Verdict(False, e.code)
    b.refund_serial = r.serial
    s.refund_serial = s.refund_serial or r.serial
    blocked = _claim_blocks(await db.get(RefundClaim, r.serial), session_id, lane)
    if blocked:
        _reject(b, blocked)
        audit(db, f"machine:{machine.id}", "REFUND_QR_REJECTED", "session", session_id,
              reason=blocked, serial=r.serial, lane=lane)
    await db.commit()
    return Verdict(False, blocked) if blocked else Verdict(True, data={"serial": r.serial})


async def verify_mfg_qr(db: AsyncSession, machine: Machine, session_id: str, raw: str, lane: int = 1) -> Verdict:
    s = await get_or_create_session(db, machine, session_id)
    b = await _bottle(db, s, lane)
    try:
        m = qr.parse_mfg(raw, settings.qr_signing_secret)
    except qr.QRError as e:
        _reject(b, e.code)
        await db.commit()
        return Verdict(False, e.code)
    b.mfg_serial, b.brand = m.serial, m.brand
    s.mfg_serial, s.brand = s.mfg_serial or m.serial, s.brand or m.brand
    if await _mfg_consumed(db, m.serial):
        _reject(b, "BOTTLE_ALREADY_RETURNED")
        await db.commit()
        return Verdict(False, "BOTTLE_ALREADY_RETURNED")
    await db.commit()
    return Verdict(True, data={"brand": m.brand, "batch": m.batch, "serial": m.serial})


async def _eligibility_rejected(db: AsyncSession, machine: Machine, session_id: str, lane: int, reason: str) -> Verdict:
    s = await get_or_create_session(db, machine, session_id)
    _reject(await _bottle(db, s, lane), reason)
    await db.commit()
    return Verdict(False, reason)


async def check_eligibility(db: AsyncSession, machine: Machine, session_id: str,
                            refund_raw: str, mfg_raw: str, lane: int = 1) -> Verdict:
    s = await get_or_create_session(db, machine, session_id)
    try:
        r = qr.parse_refund(refund_raw, settings.qr_signing_secret)
        m = qr.parse_mfg(mfg_raw, settings.qr_signing_secret)
    except qr.QRError as e:
        return await _eligibility_rejected(db, machine, session_id, lane, e.code)

    brand = await db.get(EligibleBrand, m.brand)
    if brand is None or not brand.active:
        return await _eligibility_rejected(db, machine, session_id, lane, "BRAND_NOT_ELIGIBLE")
    if await _mfg_consumed(db, m.serial):
        return await _eligibility_rejected(db, machine, session_id, lane, "BOTTLE_ALREADY_RETURNED")
    res = await db.execute(select(RefundClaim.refund_serial).where(
        RefundClaim.mfg_serial == m.serial, RefundClaim.status == ClaimStatus.RESERVED,
        (RefundClaim.session_id != session_id) | (RefundClaim.lane != lane),
        RefundClaim.reserved_until > utcnow()))
    if res.first():
        return await _eligibility_rejected(db, machine, session_id, lane, "BOTTLE_IN_USE")

    # Reserve the refund QR - insert if new, then lock the row
    until = utcnow() + timedelta(seconds=settings.reservation_ttl_s)
    await db.execute(pg_insert(RefundClaim).values(
        refund_serial=r.serial, mfg_serial=m.serial, brand=m.brand, status=ClaimStatus.RESERVED,
        session_id=session_id, lane=lane, machine_id=machine.id, reserved_until=until,
    ).on_conflict_do_nothing(index_elements=["refund_serial"]))
    claim = await _claim_for_update(db, r.serial)
    blocked = _claim_blocks(claim, session_id, lane)
    if blocked:
        # nothing was inserted (ON CONFLICT DO NOTHING); record the rejection, release the row lock
        return await _eligibility_rejected(db, machine, session_id, lane, blocked)
    claim.mfg_serial, claim.brand, claim.status = m.serial, m.brand, ClaimStatus.RESERVED
    claim.session_id, claim.lane, claim.machine_id, claim.reserved_until = session_id, lane, machine.id, until
    b = await _bottle(db, s, lane)
    b.refund_serial, b.mfg_serial, b.brand, b.status, b.reason = r.serial, m.serial, m.brand, BottleState.VALID, None
    audit(db, f"machine:{machine.id}", "REFUND_QR_RESERVED", "claim", r.serial, session_id=session_id, lane=lane)
    await db.commit()
    return Verdict(True, data={"amount_paise": settings.refund_amount_paise})


async def bottle_rejected(db: AsyncSession, machine: Machine, session_id: str, lane: int, reason: str) -> None:
    """The machine handed one bottle of the batch back (vision fail, QR missing, ...)."""
    s = await get_or_create_session(db, machine, session_id)
    b = await _bottle(db, s, lane)
    _reject(b, reason)
    res = await db.execute(select(RefundClaim).where(
        RefundClaim.session_id == session_id, RefundClaim.lane == lane,
        RefundClaim.status == ClaimStatus.RESERVED).with_for_update())
    for claim in res.scalars():
        claim.status, claim.reserved_until = ClaimStatus.RELEASED, None
    audit(db, f"machine:{machine.id}", "BOTTLE_REJECTED", "session", session_id, lane=lane, reason=reason)
    await db.commit()


# ---------------- destination + transaction ----------------

def normalize_destination(kind: str, value: str) -> tuple[str, str]:
    value = value.strip()
    if kind == "upi" and UPI_RE.match(value):
        return "upi", value.lower()
    if kind == "mobile":
        digits = re.sub(r"\D", "", value)
        if len(digits) == 12 and digits.startswith("91"):
            digits = digits[2:]
        if MOBILE_RE.match(digits):
            return "mobile", digits
    raise DomainError("INVALID_DESTINATION", 422)


async def validate_destination(kind: str, value: str) -> Verdict:
    try:
        kind, value = normalize_destination(kind, value)
    except DomainError as e:
        return Verdict(False, e.code)
    chk = await get_payout_provider().validate_account(kind, value)
    if not chk.ok:
        return Verdict(False, chk.reason or "DESTINATION_NOT_FOUND")
    return Verdict(True, data={"name": chk.name or "", "masked": mask(kind, value)})


def normalize_mobile(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if not MOBILE_RE.match(digits):
        raise DomainError("INVALID_SMS_MOBILE", 422)
    return digits


async def create_transaction(db: AsyncSession, machine: Machine, session_id: str,
                             kind: str, value: str, sms_mobile: str | None = None) -> Transaction:
    existing = (await db.execute(select(Transaction).where(Transaction.session_id == session_id))).scalar_one_or_none()
    if existing:
        return existing  # idempotent retry from the machine
    s = await get_or_create_session(db, machine, session_id)
    res = await db.execute(select(RefundClaim).where(
        RefundClaim.session_id == session_id, RefundClaim.status == ClaimStatus.RESERVED,
        RefundClaim.reserved_until > utcnow()).order_by(RefundClaim.lane).with_for_update())
    claims = res.scalars().all()
    if not claims:
        raise DomainError("NO_ACTIVE_RESERVATION")
    kind, value = normalize_destination(kind, value)
    sms = normalize_mobile(sms_mobile) if sms_mobile else None
    # One payout for every eligible bottle of the batch; the server decides the amount
    txn = Transaction(
        id=f"TXN-{uuid.uuid4().hex[:12].upper()}", session_id=s.id, machine_id=machine.id,
        refund_serial=claims[0].refund_serial, bottle_count=len(claims),
        amount_paise=settings.refund_amount_paise * len(claims),
        dest_kind=kind, dest_value=value, sms_mobile=sms, provider=get_payout_provider().name,
    )
    db.add(txn)
    audit(db, f"machine:{machine.id}", "TXN_CREATED", "transaction", txn.id, session_id=session_id,
          dest=mask(kind, value), bottles=len(claims), amount_paise=txn.amount_paise)
    await db.commit()
    return txn


async def get_txn_for_machine(db: AsyncSession, machine: Machine, txn_id: str, lock: bool = False) -> Transaction:
    q = select(Transaction).where(Transaction.id == txn_id)
    if lock:
        q = q.with_for_update()
    txn = (await db.execute(q)).scalar_one_or_none()
    if txn is None or txn.machine_id != machine.id:
        raise DomainError("TXN_NOT_FOUND", 404)
    return txn


# ---------------- payout ----------------

async def request_payout(db: AsyncSession, txn: Transaction) -> Transaction:
    """txn must be locked by the caller. Safe to call twice (provider idempotency key = txn.id)."""
    if txn.status != TxnStatus.CREATED:
        return txn
    txn.status = TxnStatus.PENDING  # from here money may move
    await db.flush()
    try:
        result = await get_payout_provider().create_payout(txn.id, txn.dest_kind, txn.dest_value, txn.amount_paise)
    except Exception as e:  # unknown outcome -> reconciler retries with the same idempotency key
        log.exception("Payout request failed for %s", txn.id)
        audit(db, "system", "PAYOUT_REQUEST_ERROR", "transaction", txn.id, error=str(e))
        await db.commit()
        return txn
    await apply_payout_result(db, txn, result, actor="provider")
    await db.commit()
    return txn


async def refresh_payout(db: AsyncSession, txn: Transaction) -> Transaction:
    """Poll the provider for a PENDING transaction (txn locked by caller)."""
    if txn.status != TxnStatus.PENDING:
        return txn
    provider = get_payout_provider()
    if txn.provider_ref:
        result = await provider.get_status(txn.provider_ref)
    else:
        result = await provider.create_payout(txn.id, txn.dest_kind, txn.dest_value, txn.amount_paise)
    await apply_payout_result(db, txn, result, actor="provider")
    await db.commit()
    return txn


async def apply_payout_result(db: AsyncSession, txn: Transaction, result: PayoutResult, actor: str) -> None:
    if result.provider_ref and not txn.provider_ref:
        txn.provider_ref = result.provider_ref
    new = TxnStatus(result.status)
    if txn.status in FINAL:
        if new != txn.status:
            audit(db, actor, "PAYOUT_STATUS_CONFLICT", "transaction", txn.id,
                  current=txn.status, received=new.value)
        return
    if new == txn.status:
        return
    txn.status = new
    if new in FINAL:
        txn.completed_at = utcnow()
    if new == TxnStatus.FAILED:
        txn.failure_reason = result.failure_reason
    audit(db, actor, f"PAYOUT_{new.value}", "transaction", txn.id, provider_ref=txn.provider_ref,
          reason=result.failure_reason)
    await maybe_send_sms(db, txn)


# ---------------- bottle outcome ----------------

async def bottle_accepted(db: AsyncSession, machine: Machine, session_id: str, txn_id: str | None) -> None:
    s = await get_or_create_session(db, machine, session_id)
    res = await db.execute(select(RefundClaim).where(
        RefundClaim.session_id == session_id,
        RefundClaim.status.in_([ClaimStatus.RESERVED, ClaimStatus.CONSUMED])).with_for_update())
    claims = res.scalars().all()
    if not claims:
        raise DomainError("NO_ACTIVE_RESERVATION")
    for claim in claims:
        if claim.status != ClaimStatus.CONSUMED:
            claim.status, claim.consumed_at, claim.reserved_until = ClaimStatus.CONSUMED, utcnow(), None
    bottles = (await db.execute(select(SessionBottle).where(
        SessionBottle.session_id == session_id, SessionBottle.status == BottleState.VALID))).scalars().all()
    for b in bottles:
        b.status = BottleState.ACCEPTED
    s.outcome, s.reason, s.ended_at = "ACCEPTED", None, utcnow()
    if txn_id:
        txn = await get_txn_for_machine(db, machine, txn_id, lock=True)
        txn.bottle_status = BottleStatus.ACCEPTED
        await maybe_send_sms(db, txn)
    audit(db, f"machine:{machine.id}", "BOTTLE_ACCEPTED", "session", session_id, txn_id=txn_id)
    await db.commit()


async def bottle_returned(db: AsyncSession, machine: Machine, session_id: str, reason: str) -> None:
    s = await get_or_create_session(db, machine, session_id)
    res = await db.execute(select(RefundClaim).where(
        RefundClaim.session_id == session_id, RefundClaim.status == ClaimStatus.RESERVED).with_for_update())
    for claim in res.scalars():
        claim.status, claim.reserved_until = ClaimStatus.RELEASED, None
    bottles = (await db.execute(select(SessionBottle).where(
        SessionBottle.session_id == session_id, SessionBottle.status == BottleState.VALID))).scalars().all()
    for b in bottles:
        b.status, b.reason = BottleState.RETURNED, reason[:64]
    txn = (await db.execute(select(Transaction).where(Transaction.session_id == session_id))).scalar_one_or_none()
    if txn:
        txn.bottle_status = BottleStatus.RETURNED
        if txn.status in (TxnStatus.SUCCESS, TxnStatus.PENDING):
            # Customer may have been paid and still has the bottle -> needs review
            audit(db, "system", "ALERT_PAID_BOTTLE_RETURNED", "transaction", txn.id, status=txn.status)
            await raise_alert(db, AlertType.PAID_BOTTLE_RETURNED, txn.id,
                              f"Payout {txn.id} is {txn.status} but the bottle went back to the customer ({reason})",
                              machine.id, auto=False)
    s.outcome, s.reason, s.ended_at = "RETURNED", reason, utcnow()
    audit(db, f"machine:{machine.id}", "BOTTLE_RETURNED", "session", session_id, reason=reason)
    await db.commit()


# ---------------- SMS ----------------

def sms_mobile(txn: Transaction) -> str | None:
    if txn.sms_mobile:
        return txn.sms_mobile
    if txn.dest_kind == "mobile":
        return txn.dest_value
    local = txn.dest_value.split("@")[0]
    return local if MOBILE_RE.match(local) else None


async def maybe_send_sms(db: AsyncSession, txn: Transaction) -> None:
    """Send once, when the payout succeeded AND the bottle is in the bin."""
    if txn.sms_sent or txn.status != TxnStatus.SUCCESS or txn.bottle_status != BottleStatus.ACCEPTED:
        return
    mobile = sms_mobile(txn)
    txn.sms_sent = True
    if not mobile:
        return
    bottles = f"{txn.bottle_count} bottles" if txn.bottle_count > 1 else "your bottle"
    body = (f"Rs.{txn.amount_paise / 100:.2f} refunded to {mask(txn.dest_kind, txn.dest_value)} "
            f"for returning {bottles} at {txn.machine_id}. Ref {txn.id}. -TASMAC")
    try:
        sent, ref = await get_sms_provider().send(mobile, body)
    except Exception as e:
        log.exception("SMS failed for %s", txn.id)
        sent, ref = False, str(e)[:120]
    db.add(SmsMessage(txn_id=txn.id, mobile=mobile, body=body, status="SENT" if sent else "FAILED", provider_ref=ref))


# ---------------- background reconciliation ----------------

async def reconcile_once(db: AsyncSession) -> int:
    """Poll stale PENDING payouts and expire abandoned reservations. Returns rows touched."""
    now = utcnow()
    touched = 0
    stale = now - timedelta(seconds=settings.reconcile_after_s)
    ids = (await db.execute(select(Transaction.id).where(
        Transaction.status == TxnStatus.PENDING, Transaction.updated_at < stale).limit(100))).scalars().all()
    for txn_id in ids:
        txn = (await db.execute(select(Transaction).where(Transaction.id == txn_id).with_for_update())).scalar_one()
        try:
            await refresh_payout(db, txn)
            touched += 1
        except Exception:
            log.exception("Reconcile failed for %s", txn_id)
            await db.rollback()

    res = await db.execute(select(RefundClaim).where(
        RefundClaim.status == ClaimStatus.RESERVED, RefundClaim.reserved_until < now).with_for_update(skip_locked=True))
    for claim in res.scalars():
        has_txn = (await db.execute(select(Transaction.id).where(
            Transaction.session_id == claim.session_id))).first()
        if not has_txn:
            claim.status, claim.reserved_until = ClaimStatus.RELEASED, None
            audit(db, "system", "RESERVATION_EXPIRED", "claim", claim.refund_serial)
            touched += 1
    await db.commit()
    return touched


async def heartbeat(db: AsyncSession, machine: Machine, state: str | None, bin_fill_pct: int | None,
                    software_version: str | None, fault_reason: str | None = None) -> None:
    machine.state, machine.bin_fill_pct = state, bin_fill_pct
    machine.fault_reason = fault_reason
    machine.software_version = software_version or machine.software_version
    machine.last_seen_at = utcnow()
    await db.commit()

