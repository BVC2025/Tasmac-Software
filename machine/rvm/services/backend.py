"""Central backend client.

All money / QR decisions are made by the central server, never by the
machine. `MockBackend` mimics the FastAPI backend in memory until that
service is built; `HttpBackend` will implement the same interface.
"""

import logging
import re
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum

from . import qr_codec
from .sim_feed import SimBottleFeed

log = logging.getLogger(__name__)

UPI_RE = re.compile(r"^[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z][a-zA-Z0-9]{1,63}$")
MOBILE_RE = re.compile(r"^[6-9]\d{9}$")


@dataclass(frozen=True)
class Destination:
    kind: str   # "upi" | "mobile"
    value: str

    @classmethod
    def parse(cls, text: str) -> "Destination | None":
        t = text.strip()
        if "@" in t:
            return cls("upi", t.lower()) if UPI_RE.match(t) else None
        digits = re.sub(r"\D", "", t)
        if len(digits) == 12 and digits.startswith("91"):
            digits = digits[2:]
        return cls("mobile", digits) if MOBILE_RE.match(digits) else None

    @property
    def sms_number(self) -> str | None:
        """Mobile number the backend can SMS (mobile destination or a UPI ID like 98xxxxxxxx@ybl)."""
        if self.kind == "mobile":
            return self.value
        local = self.value.split("@")[0]
        return local if MOBILE_RE.match(local) else None

    def masked(self) -> str:
        if self.kind == "mobile":
            return f"XXXXXX{self.value[-4:]}"
        name, _, handle = self.value.partition("@")
        return f"{name[:2]}***@{handle}"


@dataclass
class Verdict:
    ok: bool
    reason: str = ""
    data: dict = field(default_factory=dict)


class PayoutStatus(str, Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class Backend(ABC):
    """One session = one customer = up to 3 bottles (one per lane), paid together."""

    @abstractmethod
    async def health(self) -> bool: ...

    async def heartbeat(self, state: str, bin_fill_pct: int | None, software_version: str,
                        fault_reason: str | None = None) -> None:
        """Report machine status to the server (no-op for mocks)."""

    @abstractmethod
    async def verify_refund_qr(self, session_id: str, raw: str, lane: int = 1) -> Verdict: ...

    @abstractmethod
    async def verify_mfg_qr(self, session_id: str, raw: str, lane: int = 1) -> Verdict: ...

    @abstractmethod
    async def check_eligibility(self, session_id: str, refund_raw: str, mfg_raw: str, lane: int = 1) -> Verdict:
        """Final eligibility check. On success the refund QR is reserved for this session + lane."""

    @abstractmethod
    async def bottle_rejected(self, session_id: str, lane: int, reason: str) -> None:
        """A bottle of the batch was rejected and handed back (releases its reservation, if any)."""

    @abstractmethod
    async def validate_destination(self, session_id: str, dest: Destination) -> Verdict:
        """Check the UPI ID / mobile exists. data may contain 'name' for display."""

    @abstractmethod
    async def create_transaction(self, session_id: str, dest: Destination, amount_paise: int,
                                 sms_mobile: str | None = None) -> str:
        """One payout for all reserved bottles of the session. Idempotent per session_id."""

    @abstractmethod
    async def request_payout(self, txn_id: str) -> PayoutStatus: ...

    @abstractmethod
    async def get_payout_status(self, txn_id: str) -> PayoutStatus: ...

    @abstractmethod
    async def bottle_accepted(self, session_id: str, txn_id: str | None) -> None:
        """All held bottles of the session are in the bin: consume their QRs, send SMS."""

    @abstractmethod
    async def bottle_returned(self, session_id: str, reason: str) -> None:
        """All held bottles went back to the customer: release their reservations."""


class MockBackend(Backend):
    ELIGIBLE_BRANDS = {"KF", "MC", "OC", "RC", "BP"}  # test brand codes

    def __init__(self, secret: str, feed: SimBottleFeed | None = None):
        self.secret = secret
        self.feed = feed
        self.consumed_refund: set[str] = set()
        self.consumed_mfg: set[str] = set()
        self.reservations: dict[tuple[str, int], tuple[str, str]] = {}   # (session, lane) -> (refund, mfg)
        self.rejected: list[tuple[str, int, str]] = []
        self.transactions: dict[str, dict] = {}
        self._txn_by_session: dict[str, str] = {}
        self.sms_log: list[str] = []

    def _session_reservations(self, session_id: str) -> dict[int, tuple[str, str]]:
        return {lane: v for (s, lane), v in self.reservations.items() if s == session_id}

    async def health(self) -> bool:
        return True

    async def verify_refund_qr(self, session_id: str, raw: str, lane: int = 1) -> Verdict:
        try:
            qr = qr_codec.parse_refund(raw)
        except qr_codec.QRFormatError:
            return Verdict(False, "REFUND_QR_INVALID_FORMAT")
        if not qr_codec.verify_signature(self.secret, raw):
            return Verdict(False, "REFUND_QR_FORGED")
        if qr.serial in self.consumed_refund:
            return Verdict(False, "REFUND_QR_ALREADY_USED")
        if any(r == qr.serial for key, (r, _) in self.reservations.items() if key != (session_id, lane)):
            return Verdict(False, "REFUND_QR_IN_USE")
        return Verdict(True, data={"serial": qr.serial})

    async def verify_mfg_qr(self, session_id: str, raw: str, lane: int = 1) -> Verdict:
        try:
            qr = qr_codec.parse_mfg(raw)
        except qr_codec.QRFormatError:
            return Verdict(False, "MFG_QR_INVALID_FORMAT")
        if not qr_codec.verify_signature(self.secret, raw):
            return Verdict(False, "MFG_QR_FORGED")
        return Verdict(True, data={"brand": qr.brand, "batch": qr.batch, "serial": qr.serial})

    async def check_eligibility(self, session_id: str, refund_raw: str, mfg_raw: str, lane: int = 1) -> Verdict:
        r, m = qr_codec.parse_refund(refund_raw), qr_codec.parse_mfg(mfg_raw)
        if m.brand not in self.ELIGIBLE_BRANDS:
            return Verdict(False, "BRAND_NOT_ELIGIBLE")
        if m.serial in self.consumed_mfg:
            return Verdict(False, "BOTTLE_ALREADY_RETURNED")
        if r.serial in self.consumed_refund:
            return Verdict(False, "REFUND_QR_ALREADY_USED")
        others = [v for key, v in self.reservations.items() if key != (session_id, lane)]
        if any(rr == r.serial for rr, _ in others):
            return Verdict(False, "REFUND_QR_IN_USE")
        if any(mm == m.serial for _, mm in others):
            return Verdict(False, "BOTTLE_IN_USE")
        self.reservations[(session_id, lane)] = (r.serial, m.serial)
        return Verdict(True, data={"amount_paise": 1000})

    async def bottle_rejected(self, session_id: str, lane: int, reason: str) -> None:
        self.reservations.pop((session_id, lane), None)
        self.rejected.append((session_id, lane, reason))

    async def validate_destination(self, session_id: str, dest: Destination) -> Verdict:
        if dest.value.startswith("invalid"):
            return Verdict(False, "DESTINATION_NOT_FOUND")
        return Verdict(True, data={"name": "TEST CUSTOMER"})

    async def create_transaction(self, session_id: str, dest: Destination, amount_paise: int,
                                 sms_mobile: str | None = None) -> str:
        if session_id in self._txn_by_session:
            return self._txn_by_session[session_id]
        held = self._session_reservations(session_id)
        if not held:
            raise RuntimeError("No eligibility reservation for session")
        txn_id = f"TXN-{uuid.uuid4().hex[:12].upper()}"
        planned = self.feed.current.payout if self.feed else "success"
        self.transactions[txn_id] = {
            "session_id": session_id, "dest": dest, "amount_paise": 1000 * len(held), "bottles": len(held),
            "status": PayoutStatus.PENDING, "planned": planned, "polls": 0,
        }
        self._txn_by_session[session_id] = txn_id
        return txn_id

    async def request_payout(self, txn_id: str) -> PayoutStatus:
        t = self.transactions[txn_id]
        t["status"] = {"success": PayoutStatus.SUCCESS, "failed": PayoutStatus.FAILED}.get(
            t["planned"], PayoutStatus.PENDING
        )
        return t["status"]

    async def get_payout_status(self, txn_id: str) -> PayoutStatus:
        t = self.transactions[txn_id]
        t["polls"] += 1
        if t["planned"] == "pending_then_success" and t["polls"] >= 2:
            t["status"] = PayoutStatus.SUCCESS
        return t["status"]

    async def bottle_accepted(self, session_id: str, txn_id: str | None) -> None:
        for lane, (refund_serial, mfg_serial) in self._session_reservations(session_id).items():
            self.reservations.pop((session_id, lane))
            self.consumed_refund.add(refund_serial)
            self.consumed_mfg.add(mfg_serial)
        if txn_id:
            t = self.transactions[txn_id]
            if t["status"] == PayoutStatus.SUCCESS:
                msg = (f"Rs.{t['amount_paise'] // 100} refund credited to {t['dest'].masked()} "
                       f"for {t['bottles']} bottle(s). Ref {txn_id}")
                self.sms_log.append(msg)
                log.info("[MOCK SMS] %s", msg)

    async def bottle_returned(self, session_id: str, reason: str) -> None:
        for lane in list(self._session_reservations(session_id)):
            self.reservations.pop((session_id, lane))
