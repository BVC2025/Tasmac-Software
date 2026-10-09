from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class VerdictOut(BaseModel):
    ok: bool
    reason: str = ""
    data: dict = Field(default_factory=dict)


class ClassifyIn(BaseModel):
    codes: list[str] = Field(max_length=16)
    record: bool = True   # False: only look up, do not log unknown codes


class QRIn(BaseModel):
    raw: str = Field(max_length=512)
    lane: int = Field(default=1, ge=1, le=3)


class EligibilityIn(BaseModel):
    refund_raw: str = Field(max_length=512)
    mfg_raw: str = Field(max_length=512)
    lane: int = Field(default=1, ge=1, le=3)


class BottleRejectedIn(BaseModel):
    reason: str = Field(max_length=64)


class DestinationIn(BaseModel):
    kind: Literal["upi", "mobile"]
    value: str = Field(max_length=255)


class TransactionIn(DestinationIn):
    sms_mobile: str | None = Field(default=None, max_length=20)  # optional, for UPI-only customers


class TxnOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    amount_paise: int
    bottle_count: int = 1


class AcceptedIn(BaseModel):
    txn_id: str | None = None


class ReturnedIn(BaseModel):
    reason: str = Field(max_length=64)


class HeartbeatIn(BaseModel):
    state: str | None = None
    bin_fill_pct: int | None = Field(default=None, ge=0, le=100)
    software_version: str | None = None
    fault_reason: str | None = Field(default=None, max_length=128)


# ---------- admin ----------

class ServiceWindow(BaseModel):
    """One opening window per day, India time. end < start means it runs past midnight."""
    start: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


class MachineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    location: str | None
    active: bool
    state: str | None
    bin_fill_pct: int | None
    software_version: str | None
    fault_reason: str | None
    service_hours: list[ServiceWindow] | None = None
    last_seen_at: datetime | None


class TxnAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    machine_id: str
    refund_serial: str
    bottle_count: int
    amount_paise: int
    dest_kind: str
    dest_value: str
    status: str
    bottle_status: str
    provider_ref: str | None
    failure_reason: str | None
    sms_sent: bool
    created_at: datetime
    completed_at: datetime | None


class StatsOut(BaseModel):
    machines_total: int
    machines_online: int
    sessions_today: int
    bottles_accepted_today: int
    bottles_returned_today: int
    refunds_success_today: int
    refunds_pending: int
    refunds_failed_today: int
    amount_refunded_today_paise: int
    open_alerts: int
