"""Local machine API for the kiosk touchscreen UI (localhost only).

    WS   /ws                       live events: snapshot, state, message, session_started/ended, fault
    GET  /api/status               current state + PLC status
    POST /api/customer/destination {"value": "ravi@okaxis"} or {"cancel": true}
    POST /api/customer/confirm     {"ok": true}

Testing aids:
    GET  /api/camera               real cameras (vision_driver: camera): status per lane
    GET  /api/camera/{lane}/preview  latest frame (JPEG, data URL) + codes found in it
    POST /api/qr/decode            body = an image file; returns every QR in it

Simulation only (when the PLC simulator runs in-process):
    POST /api/sim/insert           insert the next test bottle
    POST /api/sim/insert-custom    insert a bottle with given QR texts
    POST /api/sim/estop            {"pressed": true|false}
"""

import asyncio
import base64
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from typing import Literal

from pydantic import BaseModel, Field

from ..core.events import Event, EventBus
from ..core.orchestrator import Orchestrator
from ..plc.simulator import PLCSimulator
from ..services.customer import RefundInput, WebCustomer
from ..services import qr_codec
from ..services.sim_feed import SimBottle, SimBottleFeed

log = logging.getLogger(__name__)


class DestinationIn(BaseModel):
    value: str | None = Field(default=None, max_length=255)
    sms_mobile: str | None = Field(default=None, max_length=20)
    source: Literal["qr", "voice", "keypad"] = "keypad"
    cancel: bool = False


class SimInsertIn(BaseModel):
    bottle: str | None = None   # scenario name; default = next in feed
    lane: int | None = None     # inlet 1..3; default = first free inlet


class SimBatchIn(BaseModel):
    bottles: list[str | None] = Field(default_factory=list, max_length=3)  # one per lane, None = next in feed


class RotateIn(BaseModel):
    degrees: Literal[0, 90, 180, 270]


class SimCustomIn(BaseModel):
    refund_qr: str | None = Field(default=None, max_length=512)
    mfg_qr: str | None = Field(default=None, max_length=512)
    condition: Literal["ok", "damaged", "foreign"] = "ok"
    lane: int | None = None


MAX_IMAGE_BYTES = 15 * 1024 * 1024


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
    lanes_now: dict[int, dict] = {}   # latest step of each lane in the current session

    async def remember():
        q = bus.subscribe()
        while True:
            ev = await q.get()
            if ev.type in ("state", "message"):
                last[ev.type] = _event_json(ev)
            elif ev.type == "session_started":
                lanes_now.clear()
            elif ev.type == "lane":
                lanes_now[ev.data["lane"]] = _event_json(ev)

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
            "lane_count": len(orch.lanes),
            "lanes": list(lanes_now.values()),
            "simulation": sim is not None,
            "server_ok": orch.backend_ok,
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
            accepted = [b for b in s.bottles.values() if b.step.value == "ACCEPTED"]
            out.append({
                "id": s.id, "started_at": s.started_at, "outcome": s.outcome, "reason": s.reason,
                "bottles": s.summary(), "accepted": len(accepted),
                "amount_paise": sum(b.amount_paise for b in accepted),
                "destination": s.destination.masked() if s.destination else None,
                "txn_id": s.txn_id, "payout_status": s.payout_status.value if s.payout_status else None,
            })
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
        lane = sim.insert_bottle(body.lane if body else None)
        return {"inserted": lane is not None, "lane": lane,
                "bottle": feed.at(lane).name if (lane and feed) else None}

    @app.post("/api/sim/insert-batch")
    async def sim_insert_batch(body: SimBatchIn):
        """Insert bottles into several inlets at the same moment (one per lane)."""
        if sim is None:
            raise HTTPException(404, "Not in simulation mode")
        names = body.bottles or [None] * len(orch.lanes)
        placed = []
        for lane, name in zip(orch.lanes, names):
            if name and feed:
                try:
                    feed.select_next(name)
                except KeyError:
                    raise HTTPException(404, f"Unknown test bottle {name}")
            got = sim.insert_bottle(lane)
            if got:
                placed.append({"lane": got, "bottle": feed.at(got).name if feed else None})
        return {"inserted": placed}

    @app.post("/api/sim/insert-custom")
    async def sim_insert_custom(body: SimCustomIn):
        """A bottle carrying the given QR texts (e.g. read from a real TASMAC bottle with a phone)."""
        if sim is None or feed is None:
            raise HTTPException(404, "Not in simulation mode")
        feed.set_custom(SimBottle(name="custom", condition=body.condition,
                                  refund_qr=(body.refund_qr or "").strip() or None,
                                  mfg_qr=(body.mfg_qr or "").strip() or None))
        feed.select_next("custom")
        lane = sim.insert_bottle(body.lane)
        return {"inserted": lane is not None, "lane": lane}

    # ---------------- QR / camera testing aids ----------------

    async def kinds_of(texts: list[str], record: bool = True) -> dict[str, str | None]:
        if not texts:
            return {}
        try:
            return await orch.backend.classify_qr(texts, record)
        except Exception:
            return {t: qr_codec.classify(t) for t in texts}

    @app.post("/api/qr/decode")
    async def qr_decode(request: Request):
        """Every QR in an uploaded photo; kind = refund / mfg / null (unknown to the server)."""
        from ..services.camera import decode_bytes

        data = await request.body()
        if not data or len(data) > MAX_IMAGE_BYTES:
            raise HTTPException(413 if data else 400, "Send one image up to 15 MB as the request body")
        try:
            codes = await asyncio.to_thread(decode_bytes, data)
        except ValueError:
            raise HTTPException(400, "Not an image")
        except RuntimeError as e:
            raise HTTPException(501, str(e))
        kinds = await kinds_of([c.text for c in codes])
        return {"codes": [{"text": c.text, "format": c.format, "kind": kinds.get(c.text)} for c in codes]}

    def camera_or_404():
        cam = orch.camera
        if not hasattr(cam, "source"):
            raise HTTPException(404, "No real camera (vision_driver is mock)")
        return cam

    @app.get("/api/camera")
    async def camera_status():
        cam = orch.camera
        if not hasattr(cam, "source"):
            return {"enabled": False, "lanes": {}}
        return {"enabled": True, "lanes": {
            ln: {"source": str(src.source), "connected": src.connected, "error": src.error, "fps": round(src.fps, 1),
                 "rotate": src.rotate}
            for ln, src in cam.lanes.items()}}

    @app.post("/api/camera/{lane}/rotate")
    async def camera_rotate(lane: int, body: RotateIn):
        """Turn the picture (until restart; set camera.rotate in the config to keep it)."""
        camera_or_404().source(lane).rotate = body.degrees
        return {"rotate": body.degrees}

    @app.get("/api/camera/{lane}/preview")
    async def camera_preview(lane: int, width: int = 640):
        """Latest frame with the codes it contains outlined (for aiming the bottle)."""
        from ..services.camera import cv2, decode_image

        src = camera_or_404().source(lane)
        frame, age = src.latest()
        if frame is None:
            return {"connected": src.connected, "error": src.error, "image": None, "codes": []}
        codes = await asyncio.to_thread(decode_image, frame)
        kinds = await kinds_of([c.text for c in codes], record=False)
        for c in codes:
            color = {"refund": (40, 167, 69), "mfg": (255, 140, 0)}.get(kinds.get(c.text), (0, 0, 230))
            for i in range(4):
                cv2.line(frame, c.box[i], c.box[(i + 1) % 4], color, 4)
        scale = min(1.0, max(160, min(width, 1280)) / frame.shape[1])
        if scale < 1:
            frame = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        return {"connected": src.connected, "error": src.error, "age_s": round(age, 2),
                "image": "data:image/jpeg;base64," + base64.b64encode(jpg.tobytes()).decode() if ok else None,
                "codes": [{"text": c.text, "format": c.format, "kind": kinds.get(c.text)} for c in codes]}

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
