"""Machine entry point.

    python -m rvm.main --config config/machine.sim.yaml   # full simulation, no backend/UI needed
    python -m rvm.main --config config/machine.dev.yaml   # simulator + real backend + kiosk UI
    python -m rvm.main --config config/machine.yaml       # real PLC
"""

import argparse
import asyncio
import logging

import uvicorn

from .api.server import create_app
from .config import MachineConfig, load_config
from .core.events import EventBus
from .core.orchestrator import Orchestrator
from .plc.modbus_plc import ModbusPLC
from .plc.simulator import PLCSimulator
from .services.backend import Backend, MockBackend
from .services.customer import AutoCustomer, CustomerInterface, WebCustomer
from .services.http_backend import HttpBackend
from .services.session_log import SessionLog
from .services.sim_feed import SimBottle, SimBottleFeed
from .services.vision import Camera, MockCamera, MockInspector, MockQRReader, QRReader

log = logging.getLogger("rvm")


def make_backend(cfg: MachineConfig, feed: SimBottleFeed) -> Backend:
    if cfg.backend_driver == "http":
        b = cfg.backend
        return HttpBackend(b.url, cfg.machine_id, b.api_key, b.outbox_path, b.timeout_s)
    return MockBackend(cfg.qr.test_signing_secret, feed)


def make_customer(cfg: MachineConfig, feed: SimBottleFeed) -> CustomerInterface:
    return WebCustomer() if cfg.customer_driver == "web" else AutoCustomer(feed)


def make_vision(cfg: MachineConfig, feed: SimBottleFeed) -> tuple[Camera, QRReader]:
    if cfg.vision_driver == "camera":
        from .services.camera import OpenCVCamera, ZxingQRReader

        c = cfg.camera
        return OpenCVCamera(c.sources, c.width, c.height, c.frame_interval_s, c.backend, c.rotate), ZxingQRReader()
    return MockCamera(), MockQRReader(feed, cfg.flow.inspection_angles)


def build(cfg: MachineConfig, feed: SimBottleFeed) -> tuple[Orchestrator, ModbusPLC, EventBus]:
    bus = EventBus()
    plc = ModbusPLC(cfg.plc)
    camera, qr_reader = make_vision(cfg, feed)
    orch = Orchestrator(
        cfg=cfg,
        plc=plc,
        camera=camera,
        # damage / foreign-object detection is still simulated (DEV panel picks the condition)
        inspector=MockInspector(feed),
        qr_reader=qr_reader,
        backend=make_backend(cfg, feed),
        customer=make_customer(cfg, feed),
        bus=bus,
        session_log=SessionLog(cfg.session_log_path) if cfg.session_log_path else None,
    )
    return orch, plc, bus


async def print_events(bus: EventBus) -> None:
    q = bus.subscribe()
    while True:
        ev = await q.get()
        if ev.type in ("message", "session_ended", "fault"):
            log.info("EVENT %-14s %s", ev.type, ev.data)


async def backend_housekeeping(cfg: MachineConfig, orch: Orchestrator) -> None:
    """Heartbeat to the server + retry queued notifications."""
    backend = orch.backend
    while True:
        try:
            reply = await backend.heartbeat(orch.state.value, orch.plc.status.bin_fill_pct, cfg.software_version,
                                            orch.fault_reason)
            if isinstance(reply, dict) and "service_hours" in reply:
                orch.set_service_hours(reply["service_hours"])
            if isinstance(backend, HttpBackend) and backend.outbox.count():
                sent = await backend.flush_outbox()
                if sent:
                    log.info("Outbox: delivered %s queued notifications", sent)
        except Exception as e:
            log.warning("Backend heartbeat failed: %s", e)
        await asyncio.sleep(cfg.backend.heartbeat_interval_s)


async def run(cfg: MachineConfig) -> None:
    sim_cfg = cfg.simulator
    feed = (
        SimBottleFeed.from_yaml(sim_cfg.bottles_file)
        if sim_cfg.bottles_file
        else SimBottleFeed([SimBottle(name="no-feed")])
    )
    if sim_cfg.enabled and sim_cfg.fresh_qr_on_start:
        feed.refresh_serials(cfg.qr.test_signing_secret)
    sim = None
    if sim_cfg.enabled:
        sim = PLCSimulator(
            cfg.plc.host, cfg.plc.port, cfg.plc.write_base, cfg.plc.read_base,
            time_scale=sim_cfg.time_scale, auto_insert_every_s=sim_cfg.auto_insert_every_s,
            on_insert=feed.advance, lanes=cfg.plc.lanes,
        )
        await sim.start()

    orch, plc, bus = build(cfg, feed)
    camera = orch.camera if hasattr(orch.camera, "start") else None
    if camera:
        camera.start()
    await plc.start()
    tasks = [
        asyncio.create_task(orch.run()),
        asyncio.create_task(print_events(bus)),
        asyncio.create_task(backend_housekeeping(cfg, orch)),
    ]
    if cfg.local_api.enabled:
        customer = orch.customer if isinstance(orch.customer, WebCustomer) else None
        app = create_app(orch, bus, customer, sim, feed, cfg.local_api.cors_origins)
        server = uvicorn.Server(uvicorn.Config(app, host=cfg.local_api.host, port=cfg.local_api.port,
                                               log_level="warning"))
        tasks.append(asyncio.create_task(server.serve()))
        log.info("Kiosk API on http://%s:%s (ws: /ws)", cfg.local_api.host, cfg.local_api.port)
    try:
        await asyncio.gather(*tasks)
    finally:
        for t in tasks:
            t.cancel()
        await plc.stop()
        if camera:
            camera.stop()
        if sim:
            await sim.stop()


def main() -> None:
    p = argparse.ArgumentParser(description="TASMAC RVM machine controller")
    p.add_argument("--config", default="config/machine.sim.yaml")
    p.add_argument("--debug", action="store_true")
    a = p.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if a.debug else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    for noisy in ("pymodbus", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    try:
        asyncio.run(run(load_config(a.config)))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
