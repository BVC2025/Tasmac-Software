"""PLC handshake tests against the simulator."""

import asyncio

import pytest

from rvm.plc.base import PLCCommandError, PLCFault
from rvm.plc.registers import Cmd, CmdResult, FaultCode, PlcState, Sensor


async def test_connects_and_reads_status(plc_pair):
    sim, plc = plc_pair
    plc.check_healthy()
    assert plc.status.state == PlcState.READY
    assert plc.status.plc_version == 100


async def test_open_close_inlet(plc_pair):
    sim, plc = plc_pair
    await plc.command(Cmd.OPEN_INLET)
    assert not plc.status.has(Sensor.INLET_DOOR_CLOSED)
    await plc.command(Cmd.CLOSE_INLET)
    assert plc.status.has(Sensor.INLET_DOOR_CLOSED)


async def test_bottle_moves_through_machine(plc_pair):
    sim, plc = plc_pair
    await plc.command(Cmd.OPEN_INLET)
    assert sim.insert_bottle()
    await plc.wait_for(Sensor.BOTTLE_AT_INLET, timeout=1)
    await plc.command(Cmd.CLOSE_INLET)
    await plc.command(Cmd.MOVE_TO_SCAN)
    assert plc.status.has(Sensor.BOTTLE_IN_SCAN_POSITION)
    await plc.command(Cmd.ROTATE_BOTTLE, param=90)
    await plc.command(Cmd.MOVE_TO_HOLD)
    assert plc.status.has(Sensor.BOTTLE_IN_HOLD)
    await plc.command(Cmd.ACCEPT_BOTTLE)
    assert plc.status.bin_count == 1


async def test_command_error_is_reported(plc_pair):
    sim, plc = plc_pair
    with pytest.raises(PLCCommandError) as e:
        await plc.command(Cmd.MOVE_TO_SCAN)  # no bottle
    assert e.value.result == CmdResult.NO_BOTTLE


async def test_hand_interlock(plc_pair):
    sim, plc = plc_pair
    await plc.command(Cmd.OPEN_INLET)
    sim.set_hand_detected(True)
    with pytest.raises(PLCCommandError) as e:
        await plc.command(Cmd.CLOSE_INLET)
    assert e.value.result == CmdResult.INTERLOCK


async def test_estop_raises_fault_and_reset_recovers(plc_pair):
    sim, plc = plc_pair
    sim.set_estop(True)
    await asyncio.sleep(0.2)
    with pytest.raises(PLCFault) as e:
        await plc.command(Cmd.OPEN_INLET)
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
