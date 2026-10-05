"""QR payload format.

The real format and signing keys come from TASMAC. Until then we use a
test format with an HMAC signature so fraud cases (fake / edited QR)
can be tested end to end:

    Refund QR:         TRQ1.<serial>.<sig>
    Manufacturing QR:  TMQ1.<brand>.<batch>.<serial>.<sig>

    sig = first 16 hex chars of HMAC-SHA256(secret, everything before ".<sig>")

When the TASMAC spec arrives, only this module (and the backend's
verifier) need to change.
"""

import hashlib
import hmac
import re
from dataclasses import dataclass

REFUND_PREFIX = "TRQ1"
MFG_PREFIX = "TMQ1"
_SAFE = re.compile(r"^[A-Z0-9-]{1,32}$")


@dataclass(frozen=True)
class RefundQR:
    serial: str
    raw: str


@dataclass(frozen=True)
class MfgQR:
    brand: str
    batch: str
    serial: str
    raw: str


class QRFormatError(ValueError):
    pass


def sign(secret: str, body: str) -> str:
    return hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()[:16]


def make_refund_qr(secret: str, serial: str) -> str:
    body = f"{REFUND_PREFIX}.{serial}"
    return f"{body}.{sign(secret, body)}"


def make_mfg_qr(secret: str, brand: str, batch: str, serial: str) -> str:
    body = f"{MFG_PREFIX}.{brand}.{batch}.{serial}"
    return f"{body}.{sign(secret, body)}"


def classify(raw: str) -> str | None:
    """Return 'refund', 'mfg' or None, based on prefix only."""
    if raw.startswith(REFUND_PREFIX + "."):
        return "refund"
    if raw.startswith(MFG_PREFIX + "."):
        return "mfg"
    return None


def parse_refund(raw: str) -> RefundQR:
    parts = raw.strip().split(".")
    if len(parts) != 3 or parts[0] != REFUND_PREFIX or not _SAFE.match(parts[1]):
        raise QRFormatError("Invalid refund QR format")
    return RefundQR(serial=parts[1], raw=raw.strip())


def parse_mfg(raw: str) -> MfgQR:
    parts = raw.strip().split(".")
    if len(parts) != 5 or parts[0] != MFG_PREFIX or not all(_SAFE.match(p) for p in parts[1:4]):
        raise QRFormatError("Invalid manufacturing QR format")
    return MfgQR(brand=parts[1], batch=parts[2], serial=parts[3], raw=raw.strip())


def verify_signature(secret: str, raw: str) -> bool:
    body, _, sig = raw.strip().rpartition(".")
    return bool(body) and hmac.compare_digest(sign(secret, body), sig)
