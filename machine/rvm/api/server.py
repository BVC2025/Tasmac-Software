"""Local machine API for the kiosk touchscreen UI (localhost only).

    WS   /ws                       live events: snapshot, state, message, session_started/ended, fault
    GET  /api/status               current state + PLC status
    POST /api/customer/destination {"value": "ravi@okaxis"} or {"cancel": true}
    POST /api/customer/confirm     {"ok": true}

Simulation only (when the PLC simulator runs in-process):
    POST /api/sim/insert           insert the next test bottle
    POST /api/sim/estop            {"pressed": true|false}
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from typing import Literal

from pydantic import BaseModel, Field

from ..core.events import Event, EventBus
from ..core.orchestrator import Orchestrator
from ..plc.simulator import PLCSimulator
from ..services.customer import RefundInput, WebCustomer
from ..services.sim_feed import SimBottleFeed

log = logging.getLogger(__name__)


class DestinationIn(BaseModel):
    value: str | None = Field(default=None, max_length=255)
    sms_mobile: str | None = Field(default=None, max_length=20)
    source: Literal["qr", "voice", "keypad"] = "keypad"
    cancel: bool = False


class SimInsertIn(BaseModel):
    bottle: str | None = None   # scenario name; default = next in feed


class ConfirmIn(BaseModel):
    ok: bool


class EstopIn(BaseModel):
    pressed: bool


def _event_json(ev: Event) -> dict:
    return {"type": ev.type, "at": ev.at, **ev.data}


def create_app(orch: Orchestrator, bus: EventBus, customer: WebCustomer | None,
               sim: PLCSimulator | None, feed: SimBottleFeed | None, cors_origins: list[str]) -> FastAPI:
    # Keep the latest state/message so a (re)connecting kiosk can render immediately
    last: dict[str, dict] = {}

    async def remember():
        q = bus.subscribe()
        while True:
            ev = await q.get()
            if ev.type in ("state", "message"):
                last[ev.type] = _event_json(ev)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(remember())
        yield
        task.cancel()

    app = FastAPI(title="RVM machine local API", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=cors_origins, allow_methods=["*"], allow_headers=["*"])

    def snapshot() -> dict:
        s = orch.plc.status
        return {
            "type": "snapshot",
            "state": orch.state.value,
            "last_state": last.get("state"),
            "last_message": last.get("message"),
            "waiting_for": customer.waiting_for if customer else None,
            "machine_id": orch.cfg.machine_id,
            "simulation": sim is not None,
            "plc": {"connected": s.connected, "state": s.state.name, "fault": s.fault_code.name,
                    "bin_fill_pct": s.bin_fill_pct},
        }

    @app.get("/api/status")
    async def status():
        return snapshot()

    @app.get("/api/sessions")
    async def sessions(limit: int = 20):
        out = []
        for s in orch.sessions[-limit:][::-1]:
            d = asdict(s)
            d.pop("frames", None)
            d["destination"] = s.destination.masked() if s.destination else None
            out.append(d)
        return out

    @app.post("/api/customer/destination")
    async def destination(body: DestinationIn):
        if customer is None:
            raise HTTPException(409, "Customer input is not from the kiosk (customer_driver != web)")
        value = None if body.cancel else RefundInput(
            (body.value or "").strip(), (body.sms_mobile or "").strip() or None, body.source)
        if not customer.submit_destination(value):
            raise HTTPException(409, "Machine is not waiting for a refund destination")
        return {"accepted": True}

    @app.post("/api/customer/confirm")
    async def confirm(body: ConfirmIn):
        if customer is None or not customer.submit_confirm(body.ok):
            raise HTTPException(409, "Machine is not waiting for confirmation")
        return {"accepted": True}

    @app.get("/api/sim/bottles")
    async def sim_bottles():
        if sim is None or feed is None:
            raise HTTPException(404, "Not in simulation mode")
        return [{"name": b.name, "condition": b.condition, "destination": b.destination,
                 "payout": b.payout, "has_refund_qr": bool(b.refund_qr), "has_mfg_qr": bool(b.mfg_qr)}
                for b in feed.bottles]

    @app.post("/api/sim/refresh")
    async def sim_refresh():
        """New QR serials for all test bottles (after a full round they are all 'already used')."""
        if sim is None or feed is None:
            raise HTTPException(404, "Not in simulation mode")
        feed.refresh_serials(orch.cfg.qr.test_signing_secret)
        return {"refreshed": len(feed.bottles)}

    @app.post("/api/sim/insert")
    async def sim_insert(body: SimInsertIn | None = None):
        if sim is None:
            raise HTTPException(404, "Not in simulation mode")
        if body and body.bottle and feed:
            try:
                feed.select_next(body.bottle)
            except KeyError:
                raise HTTPException(404, f"Unknown test bottle {body.bottle}")
        inserted = sim.insert_bottle()
        return {"inserted": inserted, "bottle": feed.current.name if (inserted and feed) else None}

    @app.post("/api/sim/estop")
    async def sim_estop(body: EstopIn):
        if sim is None:
            raise HTTPException(404, "Not in simulation mode")
        sim.set_estop(body.pressed)
        return {"pressed": body.pressed}

    @app.websocket("/ws")
    async def ws(websocket: WebSocket):
        await websocket.accept()
        q = bus.subscribe()
        try:
            await websocket.send_json(snapshot())
            while True:
                ev = await q.get()
                await websocket.send_json(_event_json(ev))
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            bus.unsubscribe(q)

    return app
