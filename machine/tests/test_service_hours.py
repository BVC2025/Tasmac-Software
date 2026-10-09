"""Service hours: the machine takes bottles only inside its opening windows (India time)."""

import asyncio
from datetime import datetime

from rvm.core.events import MachineState
from rvm.core.schedule import IST, ServiceHours, ServiceHoursStore
from rvm.plc.registers import LaneSensor

from .conftest import bottle


def at(hh: int, mm: int = 0) -> datetime:
    return datetime(2026, 10, 9, hh, mm, tzinfo=IST)


def test_windows_and_next_open():
    h = ServiceHours([{"start": "10:00", "end": "11:30"}, {"start": "17:00", "end": "21:00"}])
    assert not h.is_open(at(9, 59)) and h.is_open(at(10, 0)) and h.is_open(at(11, 29))
    assert not h.is_open(at(11, 30)) and h.is_open(at(18)) and not h.is_open(at(21))
    assert h.next_open(at(12)) == at(17)
    assert h.next_open(at(22)) == datetime(2026, 10, 10, 10, 0, tzinfo=IST)   # tomorrow morning
    assert h.next_open(at(10, 30)) is None
    assert ServiceHours([]).is_open(at(3)) and ServiceHours(None).always_open


def test_window_past_midnight():
    h = ServiceHours([{"start": "22:00", "end": "02:00"}])
    assert h.is_open(at(23)) and h.is_open(at(1, 59)) and not h.is_open(at(2)) and not h.is_open(at(12))


def test_store_remembers_hours(tmp_path):
    store = ServiceHoursStore(str(tmp_path / "hours.json"))
    assert store.load() is None
    store.save([{"start": "10:00", "end": "11:30"}])
    assert store.load() == [{"start": "10:00", "end": "11:30"}]


async def test_closed_outside_hours_then_opens(make_rig):
    async with make_rig([bottle()], lanes=1) as rig:
        now = {"t": at(9, 0)}
        rig.orch._clock = lambda: now["t"]
        rig.orch.set_service_hours([{"start": "10:00", "end": "11:30"}])
        await rig.wait_state(MachineState.CLOSED, timeout=5)
        assert rig.orch.state == MachineState.CLOSED
        assert rig.sim.lane_sensors[1] & LaneSensor.INLET_DOOR_CLOSED   # no bottles while closed

        now["t"] = at(10, 0)
        await rig.wait_state(MachineState.READY, timeout=5)
        assert (await rig.insert_and_wait(1)).outcome == "ACCEPTED"


async def test_customer_inside_is_finished_when_hours_end(make_rig):
    async with make_rig([bottle()], lanes=1, step_min_display_s=0.3) as rig:
        now = {"t": at(11, 29)}
        rig.orch._clock = lambda: now["t"]
        rig.orch.set_service_hours([{"start": "10:00", "end": "11:30"}])
        await rig.wait_state(MachineState.READY)
        await asyncio.sleep(0.1)
        rig.sim.insert_bottle(1)
        await rig.wait_state(MachineState.CHECKING, timeout=5)
        now["t"] = at(11, 31)                      # closing time while the bottle is checked
        await rig.wait_state(MachineState.CLOSED, timeout=20)
        assert rig.orch.sessions[-1].outcome == "ACCEPTED"   # the customer still got paid
