"""PLC handshake tests against the simulator (multi-lane)."""

import asyncio

import pytest

from rvm.plc.base import PLCCommandError, PLCFault
from rvm.plc.registers import Cmd, CmdResult, FaultCode, LaneSensor, PlcState


async def test_connects_and_reads_status(plc_pair):
    sim, plc = plc_pair
    plc.check_healthy()
    assert plc.status.state == PlcState.READY
    assert plc.status.plc_version == 200
    assert sorted(plc.status.lanes) == [1, 2, 3]


async def test_open_close_inlet(plc_pair):
    sim, plc = plc_pair
    await plc.command(Cmd.OPEN_INLET, lane=2)
    assert not plc.status.lane_has(2, LaneSensor.INLET_DOOR_CLOSED)
    assert plc.status.lane_has(1, LaneSensor.INLET_DOOR_CLOSED)  # other lanes untouched
    await plc.command(Cmd.CLOSE_INLET, lane=2)
    assert plc.status.lane_has(2, LaneSensor.INLET_DOOR_CLOSED)


async def test_bottle_moves_through_a_lane(plc_pair):
    sim, plc = plc_pair
    await plc.command(Cmd.OPEN_INLET, lane=3)
    assert sim.insert_bottle(3) == 3
    assert await plc.wait_any_lane(LaneSensor.BOTTLE_AT_INLET, timeout=1) == 3
    await plc.command(Cmd.CLOSE_INLET, lane=3)
    await plc.command(Cmd.MOVE_TO_SCAN, lane=3)
    assert plc.status.lane_has(3, LaneSensor.BOTTLE_IN_SCAN_POSITION)
    await plc.command(Cmd.ROTATE_BOTTLE, param=90, lane=3)
    await plc.command(Cmd.MOVE_TO_HOLD, lane=3)
    assert plc.status.lane_has(3, LaneSensor.BOTTLE_IN_HOLD)
    await plc.command(Cmd.ACCEPT_BOTTLE, lane=3)
    assert plc.status.bin_count == 1


async def test_lanes_run_commands_in_parallel(plc_pair):
    sim, plc = plc_pair
    for lane in (1, 2, 3):
        await plc.command(Cmd.OPEN_INLET, lane=lane)
        sim.insert_bottle(lane)
        await plc.command(Cmd.CLOSE_INLET, lane=lane)
    loop = asyncio.get_running_loop()
    t0 = loop.time()
    await asyncio.gather(*(plc.command(Cmd.MOVE_TO_SCAN, lane=ln) for ln in (1, 2, 3)))
    parallel = loop.time() - t0
    assert all(plc.status.lane_has(ln, LaneSensor.BOTTLE_IN_SCAN_POSITION) for ln in (1, 2, 3))
    t0 = loop.time()
    for ln in (1, 2, 3):
        await plc.command(Cmd.MOVE_TO_HOLD, lane=ln)
    sequential = loop.time() - t0
    assert parallel < sequential


async def test_command_error_is_reported(plc_pair):
    sim, plc = plc_pair
    with pytest.raises(PLCCommandError) as e:
        await plc.command(Cmd.MOVE_TO_SCAN, lane=1)  # no bottle
    assert e.value.result == CmdResult.NO_BOTTLE and e.value.lane == 1


async def test_hand_interlock_is_per_lane(plc_pair):
    sim, plc = plc_pair
    await plc.command(Cmd.OPEN_INLET, lane=1)
    await plc.command(Cmd.OPEN_INLET, lane=2)
    sim.set_hand_detected(True, lane=1)
    with pytest.raises(PLCCommandError) as e:
        await plc.command(Cmd.CLOSE_INLET, lane=1)
    assert e.value.result == CmdResult.INTERLOCK
    await plc.command(Cmd.CLOSE_INLET, lane=2)   # lane 2 unaffected


async def test_lane_command_needs_a_lane(plc_pair):
    sim, plc = plc_pair
    with pytest.raises(ValueError):
        await plc.command(Cmd.OPEN_INLET)


async def test_estop_raises_fault_and_reset_recovers(plc_pair):
    sim, plc = plc_pair
    sim.set_estop(True)
    await asyncio.sleep(0.2)
    with pytest.raises(PLCFault) as e:
        await plc.command(Cmd.OPEN_INLET, lane=1)
    assert e.value.fault_code == FaultCode.ESTOP
    sim.set_estop(False)
    await plc.command(Cmd.RESET_FAULT)
    plc.check_healthy()


async def test_plc_watchdog_trips_when_pc_heartbeat_stops(plc_pair):
    sim, plc = plc_pair
    sim.pc_watchdog_s = 0.5
    for t in plc._tasks:
        if t.get_name() == "plc-heartbeat":
            t.cancel()
    await asyncio.sleep(1.0)
    assert sim.state == PlcState.FAULT
    assert sim.fault == FaultCode.PC_WATCHDOG


async def test_pc_detects_lost_plc(plc_pair):
    sim, plc = plc_pair
    await sim.stop()
    await asyncio.sleep(1.5)
    with pytest.raises(PLCFault):
        plc.check_healthy()
