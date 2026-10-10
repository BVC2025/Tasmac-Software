"""Backend client for the central FastAPI server.

Bottle accepted/returned notifications must never be lost (they consume or
release the refund QR), so if the server is unreachable they go into a
local SQLite outbox and are retried in the background.
"""

import asyncio
import base64
import json
import logging
import sqlite3
from pathlib import Path

import httpx

from . import qr_codec
from .backend import Backend, Destination, PayoutStatus, Verdict

log = logging.getLogger(__name__)

RETRYABLE = (httpx.TransportError, httpx.TimeoutException)


class Outbox:
    def __init__(self, path: str | Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path))
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS outbox (id INTEGER PRIMARY KEY, path TEXT, body TEXT, "
            "attempts INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP)"
        )
        self._db.commit()

    def add(self, path: str, body: dict) -> None:
        self._db.execute("INSERT INTO outbox (path, body) VALUES (?, ?)", (path, json.dumps(body)))
        self._db.commit()

    def pending(self, limit: int = 50) -> list[tuple[int, str, dict]]:
        rows = self._db.execute("SELECT id, path, body FROM outbox ORDER BY id LIMIT ?", (limit,)).fetchall()
        return [(i, p, json.loads(b)) for i, p, b in rows]

    def done(self, row_id: int) -> None:
        self._db.execute("DELETE FROM outbox WHERE id = ?", (row_id,))
        self._db.commit()

    def failed(self, row_id: int) -> None:
        self._db.execute("UPDATE outbox SET attempts = attempts + 1 WHERE id = ?", (row_id,))
        self._db.commit()

    def count(self) -> int:
        return self._db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]


class HttpBackend(Backend):
    def __init__(self, base_url: str, machine_id: str, api_key: str, outbox_path: str,
                 timeout_s: float = 8.0, retries: int = 2):
        self._root = base_url.rstrip("/")
        self._c = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/api/machine/v1",
            headers={"X-Machine-Id": machine_id, "X-Api-Key": api_key},
            timeout=timeout_s,
        )
        self._retries = retries
        self.outbox = Outbox(outbox_path)

    async def close(self) -> None:
        await self._c.aclose()

    async def _request(self, method: str, path: str, body: dict | None = None) -> dict | None:
        for attempt in range(self._retries + 1):
            try:
                r = await self._c.request(method, path, json=body)
                r.raise_for_status()
                return r.json() if r.content else None
            except RETRYABLE:
                if attempt == self._retries:
                    raise
                await asyncio.sleep(0.5 * (attempt + 1))

    @staticmethod
    def _verdict(d: dict) -> Verdict:
        return Verdict(d["ok"], d.get("reason", ""), d.get("data", {}))

    # ---- Backend interface ----

    async def health(self) -> bool:
        try:
            r = await self._c.get(self._root + "/health")
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    async def heartbeat(self, state: str, bin_fill_pct: int | None, software_version: str,
                        fault_reason: str | None = None) -> dict | None:
        return await self._request("POST", "/heartbeat", {
            "state": state, "bin_fill_pct": bin_fill_pct, "software_version": software_version,
            "fault_reason": (fault_reason or "")[:128] or None})

    async def classify_qr(self, codes: list[str], record: bool = True) -> dict[str, str | None]:
        """Test-format codes locally; anything else (real TASMAC QRs) is looked up on the server."""
        kinds = {c: qr_codec.classify(c) for c in codes}
        unknown = [c for c, k in kinds.items() if k is None]
        if unknown:
            d = await self._request("POST", "/qr/classify", {"codes": unknown, "record": record})
            server = d["kinds"]
            kinds.update({c: server.get(c.strip()) for c in unknown})
        return kinds

    async def verify_refund_qr(self, session_id: str, raw: str, lane: int = 1) -> Verdict:
        return self._verdict(await self._request(
            "POST", f"/sessions/{session_id}/refund-qr", {"raw": raw, "lane": lane}))

    async def verify_mfg_qr(self, session_id: str, raw: str, lane: int = 1) -> Verdict:
        return self._verdict(await self._request(
            "POST", f"/sessions/{session_id}/mfg-qr", {"raw": raw, "lane": lane}))

    async def check_eligibility(self, session_id: str, refund_raw: str, mfg_raw: str, lane: int = 1) -> Verdict:
        return self._verdict(await self._request(
            "POST", f"/sessions/{session_id}/eligibility",
            {"refund_raw": refund_raw, "mfg_raw": mfg_raw, "lane": lane}))

    async def bottle_rejected(self, session_id: str, lane: int, reason: str) -> None:
        await self._notify(f"/sessions/{session_id}/bottles/{lane}/rejected", {"reason": reason[:64]})

    async def bottle_evidence(self, session_id: str, lane: int, reason: str, jpeg: bytes,
                              box: list[float] | None = None) -> None:
        # queued in the outbox like the other notifications when the server is unreachable
        await self._notify(f"/sessions/{session_id}/bottles/{lane}/evidence", {
            "reason": reason[:64], "content_type": "image/jpeg", "box": box,
            "image_b64": base64.b64encode(jpeg).decode()})

    async def validate_destination(self, session_id: str, dest: Destination) -> Verdict:
        return self._verdict(await self._request(
            "POST", f"/sessions/{session_id}/destination", {"kind": dest.kind, "value": dest.value}))

    async def create_transaction(self, session_id: str, dest: Destination, amount_paise: int,
                                 sms_mobile: str | None = None) -> str:
        d = await self._request("POST", f"/sessions/{session_id}/transaction",
                                {"kind": dest.kind, "value": dest.value, "sms_mobile": sms_mobile})
        return d["id"]

    async def request_payout(self, txn_id: str) -> PayoutStatus:
        return PayoutStatus((await self._request("POST", f"/transactions/{txn_id}/payout"))["status"])

    async def get_payout_status(self, txn_id: str) -> PayoutStatus:
        return PayoutStatus((await self._request("GET", f"/transactions/{txn_id}"))["status"])

    async def bottle_accepted(self, session_id: str, txn_id: str | None) -> None:
        await self._notify(f"/sessions/{session_id}/accepted", {"txn_id": txn_id})

    async def bottle_returned(self, session_id: str, reason: str) -> None:
        await self._notify(f"/sessions/{session_id}/returned", {"reason": reason})

    # ---- outbox ----

    async def _notify(self, path: str, body: dict) -> None:
        try:
            await self._request("POST", path, body)
        except httpx.HTTPError as e:  # covers transport errors, timeouts and 4xx/5xx
            log.error("Backend notify failed, queued in outbox: %s %s", path, e)
            self.outbox.add(path, body)

    async def flush_outbox(self) -> int:
        sent = 0
        for row_id, path, body in self.outbox.pending():
            try:
                await self._request("POST", path, body)
                self.outbox.done(row_id)
                sent += 1
            except httpx.HTTPStatusError as e:
                if 400 <= e.response.status_code < 500:
                    log.error("Outbox item %s rejected by server (%s), dropping", row_id, e.response.text)
                    self.outbox.done(row_id)
                else:
                    self.outbox.failed(row_id)
                    break
            except RETRYABLE:
                self.outbox.failed(row_id)
                break
        return sent
