"""Kiosk local API: customer input over HTTP, events over the bus."""

import asyncio

import httpx

from rvm.api.server import create_app
from rvm.core.events import MachineState

from .conftest import bottle


async def test_kiosk_drives_refund(make_rig):
    async with make_rig([bottle()], customer_driver="web") as rig:
        app = create_app(rig.orch, rig.bus, rig.orch.customer, rig.sim, rig.feed, [])
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://k") as k:
            # input before the machine asks for it is refused
            assert (await k.post("/api/customer/destination", json={"value": "ravi@okaxis"})).status_code == 409

            await rig.wait_state(MachineState.READY)
            await asyncio.sleep(0.1)
            assert (await k.post("/api/sim/insert")).json()["inserted"]
            await rig.wait_state(MachineState.SELECT_REFUND_METHOD)
            await asyncio.sleep(0.05)

            # invalid input -> machine asks again (attempt 2)
            assert (await k.post("/api/customer/destination", json={"value": "123"})).status_code == 200
            await asyncio.sleep(0.1)
            assert (await k.get("/api/status")).json()["waiting_for"] == "destination"

            assert (await k.post("/api/customer/destination", json={"value": "ravi@okaxis"})).status_code == 200
            await rig.wait_state(MachineState.CONFIRMING)
            await asyncio.sleep(0.05)
            assert (await k.post("/api/customer/confirm", json={"ok": True})).status_code == 200

            await rig.wait_state(MachineState.READY, timeout=5)
            s = rig.orch.sessions[-1]
            assert s.outcome == "ACCEPTED"
            sessions = (await k.get("/api/sessions")).json()
            assert sessions[0]["destination"] == "ra***@okaxis"


async def test_kiosk_cancel_returns_bottle(make_rig):
    async with make_rig([bottle()], customer_driver="web") as rig:
        app = create_app(rig.orch, rig.bus, rig.orch.customer, rig.sim, rig.feed, [])
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://k") as k:
            await rig.wait_state(MachineState.READY)
            await asyncio.sleep(0.1)
            await k.post("/api/sim/insert")
            await rig.wait_state(MachineState.SELECT_REFUND_METHOD)
            await asyncio.sleep(0.05)
            await k.post("/api/customer/destination", json={"cancel": True})
            await rig.wait_state(MachineState.READY, timeout=5)
            assert rig.orch.sessions[-1].reason == "CUSTOMER_CANCELLED"
