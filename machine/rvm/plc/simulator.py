"""Software PLC simulator (Modbus TCP server).

Implements the same register map and handshake that the real PLC program
must implement, so the whole machine flow can be developed and tested
without hardware.

Run standalone:
    python -m rvm.plc.simulator --port 5020 --auto-insert 10

Simulation-only control registers (not part of the real PLC map):
    200 SIM_INSERT_BOTTLE   write 1 -> a bottle appears at the inlet
    201 SIM_ESTOP           1 = pressed, 0 = released
    202 SIM_JAM_NEXT        write 1 -> next motion command fails with JAM
    203 SIM_HAND            1 = hand in the light curtain
"""

import argparse
import asyncio
import logging
from typing import Callable

from pymodbus.datastore import ModbusDeviceContext, ModbusSequentialDataBlock, ModbusServerContext
from pymodbus.server import ModbusTcpServer

from .registers import Cmd, CmdResult, CmdStatus, FaultCode, PlcState, ReadReg, Sensor, WriteReg

log = logging.getLogger(__name__)

SIM_INSERT, SIM_ESTOP, SIM_JAM_NEXT, SIM_HAND = 200, 201, 202, 203

# Simulated motion durations (seconds, before time_scale)
DURATIONS = {
    Cmd.OPEN_INLET: 0.3,
    Cmd.CLOSE_INLET: 0.3,
    Cmd.MOVE_TO_SCAN: 0.6,
    Cmd.ROTATE_BOTTLE: 0.25,
    Cmd.MOVE_TO_HOLD: 0.5,
    Cmd.ACCEPT_BOTTLE: 0.8,
    Cmd.REJECT_BOTTLE: 0.8,
    Cmd.LIGHT_ON: 0.05,
    Cmd.LIGHT_OFF: 0.05,
    Cmd.RESET_FAULT: 0.2,
    Cmd.SAFE_STOP: 0.2,
}
MOTION_CMDS = {Cmd.MOVE_TO_SCAN, Cmd.MOVE_TO_HOLD, Cmd.ACCEPT_BOTTLE, Cmd.REJECT_BOTTLE}
BIN_CAPACITY = 500
CUSTOMER_PICKUP_S = 1.5  # time for a customer to take a returned bottle


class PLCSimulator:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 5020,
        write_base: int = 0,
        read_base: int = 100,
        time_scale: float = 1.0,
        auto_insert_every_s: float | None = None,
        on_insert: Callable[[], None] | None = None,
        pc_watchdog_s: float = 3.0,
    ):
        self.host, self.port = host, port
        self.wb, self.rb = write_base, read_base
        self.time_scale = time_scale
        self.auto_insert_every_s = auto_insert_every_s
        self.on_insert = on_insert
        self.pc_watchdog_s = pc_watchdog_s

        self._hr = ModbusSequentialDataBlock(0, [0] * 512)
        ctx = ModbusServerContext(devices=ModbusDeviceContext(hr=self._hr), single=True)
        self._server = ModbusTcpServer(ctx, address=(host, port))
        self._tasks: list[asyncio.Task] = []

        self.state = PlcState.BOOTING
        self.sensors = Sensor(0)
        self.fault = FaultCode.NONE
        self.bin_count = 0
        self._last_seq = 0
        self._jam_next = False
        self._pc_hb = None
        self._pc_hb_changed = 0.0
        self._busy = False
        self._sim_estop_reg = 0
        self._sim_hand_reg = 0

    # ---------- register helpers (pymodbus datablock is 1-based) ----------

    def _get(self, addr: int) -> int:
        return self._hr.getValues(addr + 1, 1)[0]

    def _set(self, addr: int, value: int) -> None:
        self._hr.setValues(addr + 1, [int(value) & 0xFFFF])

    def _set_r(self, reg: ReadReg, value: int) -> None:
        self._set(self.rb + reg, value)

    # ---------- public test hooks ----------

    def insert_bottle(self) -> bool:
        if self.sensors & Sensor.INLET_DOOR_CLOSED or self.sensors & Sensor.BOTTLE_AT_INLET:
            log.info("[SIM] cannot insert bottle: inlet closed or occupied")
            return False
        self.sensors |= Sensor.BOTTLE_AT_INLET
        log.info("[SIM] bottle inserted")
        if self.on_insert:
            self.on_insert()
        return True

    def set_estop(self, pressed: bool) -> None:
        if pressed:
            self.sensors |= Sensor.ESTOP_ACTIVE
            self.state, self.fault = PlcState.ESTOP, FaultCode.ESTOP
        else:
            self.sensors &= ~Sensor.ESTOP_ACTIVE
            if self.state == PlcState.ESTOP:
                self.state = PlcState.FAULT  # needs RESET_FAULT

    def set_hand_detected(self, present: bool) -> None:
        if present:
            self.sensors |= Sensor.HAND_DETECTED
        else:
            self.sensors &= ~Sensor.HAND_DETECTED

    def jam_next(self) -> None:
        self._jam_next = True

    # ---------- lifecycle ----------

    async def start(self) -> None:
        self._tasks = [asyncio.create_task(self._server.serve_forever(), name="sim-server")]
        await asyncio.sleep(0.2)
        self._tasks.append(asyncio.create_task(self._logic_loop(), name="sim-logic"))
        if self.auto_insert_every_s:
            self._tasks.append(asyncio.create_task(self._auto_insert_loop(), name="sim-auto"))
        log.info("[SIM] PLC simulator listening on %s:%s", self.host, self.port)

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        await self._server.shutdown()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    # ---------- PLC scan cycle ----------

    async def _sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds * self.time_scale)

    async def _logic_loop(self) -> None:
        loop = asyncio.get_running_loop()
        heartbeat = 0
        await self._sleep(1.0)  # boot time
        self.state = PlcState.READY
        self.sensors |= Sensor.INLET_DOOR_CLOSED
        while True:
            now = loop.time()
            heartbeat = (heartbeat + 1) % 65536

            # Simulation control registers
            if self._get(SIM_INSERT):
                self._set(SIM_INSERT, 0)
                self.insert_bottle()
            if self._get(SIM_JAM_NEXT):
                self._set(SIM_JAM_NEXT, 0)
                self.jam_next()
            # Level registers act only on change, so Python hooks keep working
            estop, hand = self._get(SIM_ESTOP), self._get(SIM_HAND)
            if estop != self._sim_estop_reg:
                self._sim_estop_reg = estop
                self.set_estop(bool(estop))
            if hand != self._sim_hand_reg:
                self._sim_hand_reg = hand
                self.set_hand_detected(bool(hand))

            # PC watchdog: only armed once the PC has sent a heartbeat
            pc_hb = self._get(self.wb + WriteReg.PC_HEARTBEAT)
            if pc_hb != self._pc_hb:
                self._pc_hb, self._pc_hb_changed = pc_hb, now
            elif (
                self._pc_hb not in (None, 0)
                and now - self._pc_hb_changed > self.pc_watchdog_s
                and self.state in (PlcState.READY, PlcState.BUSY)
            ):
                log.warning("[SIM] PC heartbeat lost -> FAULT")
                self.state, self.fault = PlcState.FAULT, FaultCode.PC_WATCHDOG
                self.sensors |= Sensor.INLET_DOOR_CLOSED

            # New command?
            seq = self._get(self.wb + WriteReg.CMD_SEQ)
            if seq != 0 and seq != self._last_seq and not self._busy:
                self._last_seq = seq
                cmd_val = self._get(self.wb + WriteReg.CMD_CODE)
                param = self._get(self.wb + WriteReg.CMD_PARAM)
                self._set_r(ReadReg.CMD_ACK_SEQ, seq)
                self._set_r(ReadReg.CMD_STATUS, CmdStatus.RUNNING)
                self._busy = True
                asyncio.create_task(self._execute(cmd_val, param))

            self._publish(heartbeat)
            await asyncio.sleep(0.05)

    def _publish(self, heartbeat: int) -> None:
        self._set_r(ReadReg.PLC_HEARTBEAT, heartbeat)
        self._publish_io()

    def _publish_io(self) -> None:
        if self.bin_count >= BIN_CAPACITY:
            self.sensors |= Sensor.BIN_FULL
        self._set_r(ReadReg.PLC_STATE, self.state)
        self._set_r(ReadReg.SENSORS, int(self.sensors))
        self._set_r(ReadReg.FAULT_CODE, self.fault)
        self._set_r(ReadReg.BIN_COUNT, self.bin_count)
        self._set_r(ReadReg.BIN_FILL_PCT, min(100, self.bin_count * 100 // BIN_CAPACITY))
        self._set_r(ReadReg.PLC_VERSION, 100)

    def _finish(self, result: CmdResult) -> None:
        # Sensors/state must be visible no later than the DONE status (spec rule)
        self._publish_io()
        self._set_r(ReadReg.CMD_RESULT, result)
        self._set_r(ReadReg.CMD_STATUS, CmdStatus.DONE if result == CmdResult.OK else CmdStatus.FAILED)
        self._busy = False

    async def _execute(self, cmd_val: int, param: int) -> None:
        try:
            cmd = Cmd(cmd_val)
        except ValueError:
            self._finish(CmdResult.INVALID_CMD)
            return

        if cmd == Cmd.RESET_FAULT:
            await self._sleep(DURATIONS[cmd])
            if self.sensors & Sensor.ESTOP_ACTIVE:
                self._finish(CmdResult.INTERLOCK)
                return
            self.state, self.fault = PlcState.READY, FaultCode.NONE
            self._finish(CmdResult.OK)
            return

        if self.state not in (PlcState.READY, PlcState.BUSY):
            self._finish(CmdResult.INTERLOCK)
            return

        self.state = PlcState.BUSY
        await self._sleep(DURATIONS.get(cmd, 0.1))
        if self.state != PlcState.BUSY:  # e-stop / fault while moving
            self._finish(CmdResult.INTERLOCK)
            return
        result = self._apply_command(cmd)
        if self.state == PlcState.BUSY:
            self.state = PlcState.READY
        self._finish(result)

    def _apply_command(self, cmd: Cmd) -> CmdResult:
        s = Sensor
        if cmd in MOTION_CMDS and self._jam_next:
            self._jam_next = False
            self.state, self.fault = PlcState.FAULT, FaultCode.JAM
            return CmdResult.JAM

        if cmd == Cmd.OPEN_INLET:
            self.sensors &= ~s.INLET_DOOR_CLOSED
        elif cmd == Cmd.CLOSE_INLET:
            if self.sensors & s.HAND_DETECTED:
                return CmdResult.INTERLOCK
            self.sensors |= s.INLET_DOOR_CLOSED
        elif cmd == Cmd.MOVE_TO_SCAN:
            if not self.sensors & s.BOTTLE_AT_INLET:
                return CmdResult.NO_BOTTLE
            if not self.sensors & s.INLET_DOOR_CLOSED:
                return CmdResult.INTERLOCK
            self.sensors = (self.sensors & ~s.BOTTLE_AT_INLET) | s.BOTTLE_IN_SCAN_POSITION
        elif cmd == Cmd.ROTATE_BOTTLE:
            if not self.sensors & s.BOTTLE_IN_SCAN_POSITION:
                return CmdResult.NO_BOTTLE
        elif cmd == Cmd.MOVE_TO_HOLD:
            if not self.sensors & s.BOTTLE_IN_SCAN_POSITION:
                return CmdResult.NO_BOTTLE
            self.sensors = (self.sensors & ~s.BOTTLE_IN_SCAN_POSITION) | s.BOTTLE_IN_HOLD
        elif cmd == Cmd.ACCEPT_BOTTLE:
            if not self.sensors & (s.BOTTLE_IN_SCAN_POSITION | s.BOTTLE_IN_HOLD):
                return CmdResult.NO_BOTTLE
            self.sensors &= ~(s.BOTTLE_IN_SCAN_POSITION | s.BOTTLE_IN_HOLD)
            self.bin_count += 1
        elif cmd == Cmd.REJECT_BOTTLE:
            if not self.sensors & (s.BOTTLE_IN_SCAN_POSITION | s.BOTTLE_IN_HOLD | s.BOTTLE_AT_INLET):
                return CmdResult.NO_BOTTLE
            self.sensors &= ~(s.BOTTLE_IN_SCAN_POSITION | s.BOTTLE_IN_HOLD | s.INLET_DOOR_CLOSED)
            self.sensors |= s.BOTTLE_AT_INLET
            asyncio.create_task(self._customer_takes_bottle())
        elif cmd == Cmd.SAFE_STOP:
            self.sensors |= s.INLET_DOOR_CLOSED
        return CmdResult.OK

    async def _customer_takes_bottle(self) -> None:
        await self._sleep(CUSTOMER_PICKUP_S)
        self.sensors &= ~Sensor.BOTTLE_AT_INLET
        log.info("[SIM] customer took back the returned bottle")

    async def _auto_insert_loop(self) -> None:
        while True:
            await asyncio.sleep(self.auto_insert_every_s)
            if self.state == PlcState.READY:
                self.insert_bottle()


async def _main() -> None:
    p = argparse.ArgumentParser(description="RVM PLC simulator")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=5020)
    p.add_argument("--auto-insert", type=float, default=None, help="insert a bottle every N seconds")
    p.add_argument("--time-scale", type=float, default=1.0)
    a = p.parse_args()
    sim = PLCSimulator(a.host, a.port, time_scale=a.time_scale, auto_insert_every_s=a.auto_insert)
    await sim.start()
    try:
        await asyncio.Event().wait()
    finally:
        await sim.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(_main())
