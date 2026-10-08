import asyncio
import itertools
from contextlib import asynccontextmanager

import pytest

from rvm.config import FlowConfig, MachineConfig, PLCConfig, SimulatorConfig
from rvm.core.events import MachineState
from rvm.main import build
from rvm.plc.modbus_plc import ModbusPLC
from rvm.plc.simulator import PLCSimulator
from rvm.services import qr_codec
from rvm.services.sim_feed import SimBottle, SimBottleFeed

SECRET = "test-secret"
_ports = itertools.count(15100)
_serials = itertools.count(1000000000)


def fast_config(port: int) -> MachineConfig:
    return MachineConfig(
        plc=PLCConfig(
            port=port, poll_interval_s=0.02, heartbeat_interval_s=0.1,
            plc_heartbeat_timeout_s=1.0, default_cmd_timeout_s=3.0, lanes=3,   # tests cover the 3-inlet design too
        ),
        simulator=SimulatorConfig(enabled=True, time_scale=0.05),
        session_log_path=":memory:",
        flow=FlowConfig(
            payout_poll_interval_s=0.05, payout_pending_wait_s=0.3,
            fault_retry_interval_s=0.2, hand_retry_interval_s=0.1,
            customer_input_timeout_s=2.0, backend_check_interval_s=0.1, batch_window_s=0.3,
        ),
        qr={"test_signing_secret": SECRET},
    )


def bottle(name: str = "ok", **kw) -> SimBottle:
    n = next(_serials)
    defaults = dict(
        refund_qr=qr_codec.make_refund_qr(SECRET, f"R{n}"),
        mfg_qr=qr_codec.make_mfg_qr(SECRET, "KF", "B1", f"M{n}"),
        destination="ravi@okaxis",
    )
    defaults.update(kw)
    return SimBottle(name=name, **defaults)


class Rig:
    def __init__(self, sim, plc, orch, bus, feed):
        self.sim, self.plc, self.orch, self.bus, self.feed = sim, plc, orch, bus, feed
        self.backend = orch.backend

    async def wait_state(self, state: MachineState, timeout: float = 5.0) -> None:
        async def _w():
            while self.orch.state != state:
                await asyncio.sleep(0.01)
        await asyncio.wait_for(_w(), timeout)

    async def insert_and_wait(self, lanes: int | list[int] = 1, gap_s: float = 0.0, timeout: float = 10.0):
        """Insert feed bottles (1 = one bottle, 3 = all inlets, or explicit lanes) and
        return the finished session."""
        await self.wait_state(MachineState.READY)
        await asyncio.sleep(0.1)  # let OPEN_INLET finish
        n = len(self.orch.sessions)
        for lane in (range(1, lanes + 1) if isinstance(lanes, int) else lanes):
            assert self.sim.insert_bottle(lane), f"simulator refused insertion in lane {lane}"
            if gap_s:
                await asyncio.sleep(gap_s)

        async def _w():
            while len(self.orch.sessions) == n:
                await asyncio.sleep(0.01)
        await asyncio.wait_for(_w(), timeout)
        return self.orch.sessions[-1]


@pytest.fixture
def make_rig():
    @asynccontextmanager
    async def _make(bottles: list[SimBottle], customer_driver: str = "auto", lanes: int = 3, **cfg_overrides):
        port = next(_ports)
        cfg = fast_config(port)
        cfg.customer_driver = customer_driver
        cfg.plc.lanes = lanes
        for k, v in cfg_overrides.items():
            setattr(cfg.flow, k, v)
        feed = SimBottleFeed(bottles)
        sim = PLCSimulator(port=port, time_scale=cfg.simulator.time_scale, on_insert=feed.advance, lanes=lanes)
        await sim.start()
        orch, plc, bus = build(cfg, feed)
        await plc.start()
        task = asyncio.create_task(orch.run())
        try:
            yield Rig(sim, plc, orch, bus, feed)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await plc.stop()
            await sim.stop()

    return _make


@pytest.fixture
async def plc_pair():
    """Raw PLC client + simulator, no orchestrator."""
    port = next(_ports)
    cfg = fast_config(port)
    sim = PLCSimulator(port=port, time_scale=0.05)
    await sim.start()
    plc = ModbusPLC(cfg.plc)
    await plc.start()
    for _ in range(100):
        if plc.status.connected and plc.status.state.name == "READY":
            break
        await asyncio.sleep(0.02)
    yield sim, plc
    await plc.stop()
    await sim.stop()
