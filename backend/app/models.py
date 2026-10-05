"""Database models.

Money is stored in paise (integer). All timestamps are UTC.
"""

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ClaimStatus(str, Enum):
    RESERVED = "RESERVED"     # held by an in-progress session
    CONSUMED = "CONSUMED"     # bottle in bin, refund QR can never be used again
    RELEASED = "RELEASED"     # session ended without accepting the bottle


class TxnStatus(str, Enum):
    CREATED = "CREATED"
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class BottleStatus(str, Enum):
    HELD = "HELD"             # in holding chamber
    ACCEPTED = "ACCEPTED"
    RETURNED = "RETURNED"


class Machine(Base):
    __tablename__ = "machines"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)        # e.g. RVM-CHN-0001
    name: Mapped[str] = mapped_column(String(120))
    location: Mapped[str | None] = mapped_column(String(255))
    api_key_hash: Mapped[str] = mapped_column(String(128))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    state: Mapped[str | None] = mapped_column(String(32))                 # last reported machine state
    bin_fill_pct: Mapped[int | None] = mapped_column(Integer)
    software_version: Mapped[str | None] = mapped_column(String(32))
    fault_reason: Mapped[str | None] = mapped_column(String(128))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EligibleBrand(Base):
    __tablename__ = "eligible_brands"

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class RefundClaim(Base):
    """One row per refund QR serial: the one-time-use guarantee lives here."""

    __tablename__ = "refund_claims"

    refund_serial: Mapped[str] = mapped_column(String(64), primary_key=True)
    mfg_serial: Mapped[str] = mapped_column(String(64))
    brand: Mapped[str] = mapped_column(String(16))
    status: Mapped[ClaimStatus] = mapped_column(String(16))
    session_id: Mapped[str] = mapped_column(String(64))
    machine_id: Mapped[str] = mapped_column(ForeignKey("machines.id"))
    reserved_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (
        # A physical bottle (manufacturing serial) can be refunded only once
        Index("uq_claim_mfg_consumed", "mfg_serial", unique=True,
              postgresql_where=text("status = 'CONSUMED'")),
        Index("ix_claim_session", "session_id"),
    )


class RvmSession(Base):
    """One customer interaction with a bottle (created by the machine)."""

    __tablename__ = "rvm_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    machine_id: Mapped[str] = mapped_column(ForeignKey("machines.id"), index=True)
    refund_serial: Mapped[str | None] = mapped_column(String(64))
    mfg_serial: Mapped[str | None] = mapped_column(String(64))
    brand: Mapped[str | None] = mapped_column(String(16))
    outcome: Mapped[str] = mapped_column(String(16), default="IN_PROGRESS")  # ACCEPTED | RETURNED | ...
    reason: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)          # TXN-XXXXXXXXXXXX
    session_id: Mapped[str] = mapped_column(ForeignKey("rvm_sessions.id"), unique=True)  # idempotency
    machine_id: Mapped[str] = mapped_column(ForeignKey("machines.id"), index=True)
    refund_serial: Mapped[str] = mapped_column(String(64))
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    dest_kind: Mapped[str] = mapped_column(String(8))                        # upi | mobile
    dest_value: Mapped[str] = mapped_column(String(255))
    dest_name: Mapped[str | None] = mapped_column(String(120))
    sms_mobile: Mapped[str | None] = mapped_column(String(10))               # optional SMS number
    status: Mapped[TxnStatus] = mapped_column(String(16), default=TxnStatus.CREATED, index=True)
    bottle_status: Mapped[BottleStatus] = mapped_column(String(16), default=BottleStatus.HELD)
    provider: Mapped[str] = mapped_column(String(32))
    provider_ref: Mapped[str | None] = mapped_column(String(128), unique=True)
    failure_reason: Mapped[str | None] = mapped_column(String(255))
    sms_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SmsMessage(Base):
    __tablename__ = "sms_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    txn_id: Mapped[str | None] = mapped_column(ForeignKey("transactions.id"))
    mobile: Mapped[str] = mapped_column(String(15))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))
    provider_ref: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(64))          # machine:<id> | admin | system | provider
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity: Mapped[str | None] = mapped_column(String(32))
    entity_id: Mapped[str | None] = mapped_column(String(64), index=True)
    data: Mapped[dict | None] = mapped_column(JSON)


class Role(str, Enum):
    VIEWER = "VIEWER"       # read only
    OPERATOR = "OPERATOR"   # + resolve alerts, re-check payouts, enable/disable machines
    ADMIN = "ADMIN"         # + users, machine registration / keys, brands


ROLE_RANK = {Role.VIEWER: 1, Role.OPERATOR: 2, Role.ADMIN: 3}


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    full_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(String(16))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AlertType(str, Enum):
    MACHINE_OFFLINE = "MACHINE_OFFLINE"
    MACHINE_FAULT = "MACHINE_FAULT"
    BIN_FULL = "BIN_FULL"
    PAYOUT_STUCK = "PAYOUT_STUCK"
    PAID_BOTTLE_RETURNED = "PAID_BOTTLE_RETURNED"


class Alert(Base):
    """Operational alerts. Automatic ones open/close themselves; others need a human to resolve."""

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    type: Mapped[AlertType] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(8))          # info | warning | critical
    machine_id: Mapped[str | None] = mapped_column(ForeignKey("machines.id"))
    entity_id: Mapped[str] = mapped_column(String(64))         # machine id / txn id
    message: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="OPEN")   # OPEN | RESOLVED
    auto: Mapped[bool] = mapped_column(Boolean, default=True)  # closes itself when the condition clears
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[str | None] = mapped_column(String(64))
    note: Mapped[str | None] = mapped_column(String(255))

    __table_args__ = (
        Index("uq_alert_open", "type", "entity_id", unique=True, postgresql_where=text("status = 'OPEN'")),
    )
