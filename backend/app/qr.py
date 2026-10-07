"""QR verification - test format (same as machine/rvm/services/qr_codec.py).

    Refund QR:         TRQ1.<serial>.<sig>
    Manufacturing QR:  TMQ1.<brand>.<batch>.<serial>.<sig>

Replace this module when TASMAC provides the real QR format / verification API.
"""

import hashlib
import hmac
import re
from dataclasses import dataclass

_SAFE = re.compile(r"^[A-Z0-9-]{1,32}$")


@dataclass(frozen=True)
class RefundQR:
    serial: str


@dataclass(frozen=True)
class MfgQR:
    brand: str
    batch: str
    serial: str


class QRError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def code_hash(raw: str) -> str:
    return hashlib.sha256(raw.strip().encode()).hexdigest()


def registry_serial(raw: str) -> str:
    """Stable serial for a registered real QR (its payload format is unknown to us)."""
    return "Q" + code_hash(raw)[:15].upper()


def classify(raw: str) -> str | None:
    """'refund' / 'mfg' for the test format, else None."""
    raw = raw.strip()
    if raw.startswith("TRQ1."):
        return "refund"
    if raw.startswith("TMQ1."):
        return "mfg"
    return None


def _sign(secret: str, body: str) -> str:
    return hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()[:16]


def _check_sig(secret: str, raw: str) -> bool:
    body, _, sig = raw.rpartition(".")
    return bool(body) and hmac.compare_digest(_sign(secret, body), sig)


def parse_refund(raw: str, secret: str) -> RefundQR:
    raw = raw.strip()
    parts = raw.split(".")
    if len(parts) != 3 or parts[0] != "TRQ1" or not _SAFE.match(parts[1]):
        raise QRError("REFUND_QR_INVALID_FORMAT")
    if not _check_sig(secret, raw):
        raise QRError("REFUND_QR_FORGED")
    return RefundQR(serial=parts[1])


def parse_mfg(raw: str, secret: str) -> MfgQR:
    raw = raw.strip()
    parts = raw.split(".")
    if len(parts) != 5 or parts[0] != "TMQ1" or not all(_SAFE.match(p) for p in parts[1:4]):
        raise QRError("MFG_QR_INVALID_FORMAT")
    if not _check_sig(secret, raw):
        raise QRError("MFG_QR_FORGED")
    return MfgQR(brand=parts[1], batch=parts[2], serial=parts[3])
