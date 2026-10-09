"""Payout and SMS provider adapters.

Real adapters (RazorpayX / Cashfree payouts, MSG91 / Gupshup / NIC SMS)
implement the same interfaces once accounts and DLT templates exist.
"""

import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx

from .config import get_settings

log = logging.getLogger(__name__)


@dataclass
class PayoutResult:
    status: str                  # PENDING | SUCCESS | FAILED
    provider_ref: str | None = None
    failure_reason: str | None = None


@dataclass
class AccountCheck:
    ok: bool
    name: str | None = None
    reason: str | None = None


class PayoutProvider(ABC):
    name: str

    @abstractmethod
    async def validate_account(self, kind: str, value: str) -> AccountCheck: ...

    @abstractmethod
    async def create_payout(self, idempotency_key: str, kind: str, value: str, amount_paise: int) -> PayoutResult: ...

    @abstractmethod
    async def get_status(self, provider_ref: str) -> PayoutResult: ...


class MockPayoutProvider(PayoutProvider):
    """Behaviour is driven by the UPI ID local part, for testing:

        fail*@...     -> FAILED
        pending*@...  -> stays PENDING
        slow*@...     -> PENDING, SUCCESS after 3 s
        invalid*@...  -> account validation fails
        anything else -> SUCCESS immediately
    """

    name = "mock"

    def __init__(self):
        self._payouts: dict[str, dict] = {}
        self._by_key: dict[str, str] = {}

    async def validate_account(self, kind: str, value: str) -> AccountCheck:
        if value.startswith("invalid"):
            return AccountCheck(False, reason="DESTINATION_NOT_FOUND")
        return AccountCheck(True, name="TEST CUSTOMER")

    async def create_payout(self, idempotency_key: str, kind: str, value: str, amount_paise: int) -> PayoutResult:
        if idempotency_key in self._by_key:  # provider-side idempotency
            return await self.get_status(self._by_key[idempotency_key])
        ref = f"MOCKPAY-{uuid.uuid4().hex[:12]}"
        mode = next((m for m in ("fail", "pending", "slow") if value.startswith(m)), "ok")
        self._payouts[ref] = {"mode": mode, "created": time.monotonic()}
        self._by_key[idempotency_key] = ref
        log.info("[MOCK PAYOUT] %s Rs.%.2f to %s (%s)", ref, amount_paise / 100, value, mode)
        return await self.get_status(ref)

    async def get_status(self, provider_ref: str) -> PayoutResult:
        p = self._payouts.get(provider_ref)
        if p is None:
            return PayoutResult("FAILED", provider_ref, "UNKNOWN_REFERENCE")
        if p["mode"] == "fail":
            return PayoutResult("FAILED", provider_ref, "BENEFICIARY_BANK_DECLINED")
        if p["mode"] == "pending":
            return PayoutResult("PENDING", provider_ref)
        if p["mode"] == "slow" and time.monotonic() - p["created"] < 3:
            return PayoutResult("PENDING", provider_ref)
        return PayoutResult("SUCCESS", provider_ref)


class SmsProvider(ABC):
    @abstractmethod
    async def send(self, mobile: str, body: str) -> tuple[bool, str | None]:
        """Returns (sent, provider_ref)."""


class MockSmsProvider(SmsProvider):
    async def send(self, mobile: str, body: str) -> tuple[bool, str | None]:
        log.info("[MOCK SMS] to %s: %s", mobile, body)
        return True, f"MOCKSMS-{uuid.uuid4().hex[:10]}"


class AndroidGatewaySmsProvider(SmsProvider):
    """Real SMS from a test phone running "SMS Gateway for Android" (Local Server mode).

    For internal testing only: the SMS goes out from that phone's own SIM and number.
    Production needs TRAI DLT registration and a registered SMS provider.
    """

    def __init__(self, url: str, username: str, password: str, timeout_s: float = 10.0,
                 transport: httpx.AsyncBaseTransport | None = None):
        if not url:
            raise ValueError("RVM_SMS_GATEWAY_URL is not set")
        self._c = httpx.AsyncClient(base_url=url.rstrip("/"), auth=(username, password), timeout=timeout_s,
                                    transport=transport)

    async def send(self, mobile: str, body: str) -> tuple[bool, str | None]:
        number = mobile if mobile.startswith("+") else "+91" + mobile[-10:]
        try:
            r = await self._c.post("/message", json={"textMessage": {"text": body}, "phoneNumbers": [number]})
        except httpx.HTTPError as e:
            log.warning("SMS gateway unreachable: %s", e)
            return False, f"gateway unreachable: {type(e).__name__}"[:120]
        if r.status_code >= 400:
            log.warning("SMS gateway refused (%s): %s", r.status_code, r.text[:200])
            return False, f"gateway HTTP {r.status_code}"
        try:
            ref = r.json().get("id")
        except ValueError:
            ref = None
        log.info("SMS to %s accepted by the gateway (%s)", number[:-4] + "XXXX", ref)
        return True, ref or f"GW-{uuid.uuid4().hex[:10]}"


_payout: PayoutProvider | None = None
_sms: SmsProvider | None = None


def get_payout_provider() -> PayoutProvider:
    global _payout
    if _payout is None:
        _payout = MockPayoutProvider()
    return _payout


def get_sms_provider() -> SmsProvider:
    global _sms
    if _sms is None:
        s = get_settings()
        if s.sms_provider == "android_gateway":
            _sms = AndroidGatewaySmsProvider(s.sms_gateway_url, s.sms_gateway_username, s.sms_gateway_password,
                                             s.sms_gateway_timeout_s)
        elif s.sms_provider == "mock":
            _sms = MockSmsProvider()
        else:
            raise ValueError(f"Unknown RVM_SMS_PROVIDER {s.sms_provider!r} (mock | android_gateway)")
    return _sms
