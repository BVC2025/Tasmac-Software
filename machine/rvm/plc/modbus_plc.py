"""Modbus TCP implementation of the PLC interface (multi-lane).

Background tasks:
  * poll loop      - reads the PLC status block every poll_interval_s
  * heartbeat loop - increments PC_HEARTBEAT so the PLC watchdog stays happy

Command handshake, per channel (see docs/plc-interface-spec.md):
  1. PC writes CODE, PARAM, SEQ of the channel in one request (new SEQ = trigger)
  2. PLC sets the channel's ACK_SEQ = SEQ, STATUS = RUNNING
  3. PLC sets STATUS = DONE / FAILED and RESULT
Channels run independently, so the three lanes can move at the same time.
"""

import asyncio
import logging
import time

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

from ..config import PLCConfig
from .base import PLC, ChannelStatus, LaneStatus, PLCCommandError, PLCFault, PLCStatus, PLCTimeout
from .registers import (
    MACHINE_CMDS,
    READ_BLOCK_SIZE,
    Cmd,
    CmdResult,
    CmdStatus,
    FaultCode,
    LaneReg,
    LaneSensor,
    PlcState,
    ReadReg,
    Sensor,
    WriteReg,
    cmd_base,
    lane_base,
)

log = logging.getLogger(__name__)

IO_ERRORS = (ModbusException, ConnectionError, OSError, asyncio.TimeoutError)


class ModbusPLC(PLC):
    def __init__(self, cfg: PLCConfig):
        self.cfg = cfg
        self.lanes = list(range(1, cfg.lanes + 1))
        self._client = AsyncModbusTcpClient(cfg.host, port=cfg.port, timeout=cfg.connect_timeout_s)
        self._status = PLCStatus(lanes={lane: LaneStatus() for lane in self.lanes})
        self._io_lock = asyncio.Lock()
        self._cmd_locks = {ch: asyncio.Lock() for ch in [0, *self.lanes]}
        self._seq = {ch: 0 for ch in [0, *self.lanes]}
        self._tasks: list[asyncio.Task] = []
        self._pc_heartbeat = 0
        self._updated = asyncio.Event()
        self._running = False

    # ---------- lifecycle ----------

    async def start(self) -> None:
        self._running = True
        self._tasks = [
            asyncio.create_task(self._poll_loop(), name="plc-poll"),
            asyncio.create_task(self._heartbeat_loop(), name="plc-heartbeat"),
        ]

    async def stop(self) -> None:
        # pymodbus turns a cancelled request into ModbusException, so the
        # loops also check this flag instead of relying on cancellation alone.
        self._running = False
        for t in self._tasks:
            t.cancel()
        await asyncio.wait(self._tasks, timeout=2)
        self._client.close()

    @property
    def status(self) -> PLCStatus:
        return self._status

    # ---------- health ----------

    def check_healthy(self) -> None:
        s = self._status
        if not s.connected:
            raise PLCFault("PLC not connected")
        if time.monotonic() - s.heartbeat_changed_at > self.cfg.plc_heartbeat_timeout_s:
            raise PLCFault("PLC heartbeat lost")
        if s.state == PlcState.ESTOP or s.has(Sensor.ESTOP_ACTIVE):
            raise PLCFault("Emergency stop active", FaultCode.ESTOP)
        if s.state == PlcState.FAULT:
            raise PLCFault(f"PLC fault: {s.fault_code.name}", s.fault_code)
        if s.state in (PlcState.BOOTING, PlcState.MAINTENANCE):
            raise PLCFault(f"PLC not ready: {s.state.name}")

    # ---------- commands ----------

    def _next_seq(self, ch: int) -> int:
        self._seq[ch] = self._seq[ch] % 65535 + 1  # 1..65535, never 0
        return self._seq[ch]

    def _timeout_for(self, cmd: Cmd) -> float:
        return self.cfg.cmd_timeouts_s.get(cmd.name, self.cfg.default_cmd_timeout_s)

    async def command(self, cmd: Cmd, param: int = 0, timeout: float | None = None, lane: int = 0) -> None:
        ch = 0 if cmd in MACHINE_CMDS else lane
        if cmd not in MACHINE_CMDS and ch not in self.lanes:
            raise ValueError(f"{cmd.name} needs a lane 1..{len(self.lanes)}, got {lane}")
        async with self._cmd_locks[ch]:  # one command at a time per channel
            if cmd != Cmd.RESET_FAULT:
                self.check_healthy()
            seq = self._next_seq(ch)
            await self._write(self.cfg.write_base + cmd_base(ch), [int(cmd), param & 0xFFFF, seq])
            log.debug("PLC ch%s cmd %s param=%s seq=%s", ch, cmd.name, param, seq)

            deadline = time.monotonic() + (timeout or self._timeout_for(cmd))
            while True:
                c: ChannelStatus = self._status.channel(ch)
                if c.ack_seq == seq and c.status in (CmdStatus.DONE, CmdStatus.FAILED):
                    if c.status == CmdStatus.FAILED or c.result != CmdResult.OK:
                        raise PLCCommandError(cmd, c.result, ch)
                    return
                if cmd != Cmd.RESET_FAULT:
                    self.check_healthy()
                if time.monotonic() > deadline:
                    raise PLCTimeout(f"ch{ch} {cmd.name} (seq={seq}) not completed in time")
                await self._wait_update()

    async def wait_for_lane(self, lane: int, sensor: LaneSensor, present: bool = True,
                            timeout: float | None = None) -> None:
        deadline = None if timeout is None else time.monotonic() + timeout
        while self._status.lane_has(lane, sensor) != present:
            self.check_healthy()
            if deadline is not None and time.monotonic() > deadline:
                raise PLCTimeout(f"Lane {lane} {sensor.name} != {present}")
            await self._wait_update()

    async def wait_any_lane(self, sensor: LaneSensor, timeout: float | None = None) -> int:
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            for lane in self.lanes:
                if self._status.lane_has(lane, sensor):
                    return lane
            self.check_healthy()
            if deadline is not None and time.monotonic() > deadline:
                raise PLCTimeout(f"No lane with {sensor.name}")
            await self._wait_update()

    # ---------- background loops ----------

    async def _wait_update(self) -> None:
        try:
            await asyncio.wait_for(self._updated.wait(), timeout=self.cfg.poll_interval_s * 5)
        except asyncio.TimeoutError:
            pass

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                if not self._client.connected:
                    await self._client.connect()
                regs = await self._read(self.cfg.read_base, READ_BLOCK_SIZE)
                self._apply(regs)
            except IO_ERRORS as e:
                if self._status.connected:
                    log.error("PLC communication lost: %s", e)
                self._status.connected = False
            self._updated.set()
            self._updated = asyncio.Event()
            await asyncio.sleep(self.cfg.poll_interval_s)

    async def _heartbeat_loop(self) -> None:
        while self._running:
            if self._client.connected:
                self._pc_heartbeat = (self._pc_heartbeat + 1) % 65536
                try:
                    await self._write(self.cfg.write_base + WriteReg.PC_HEARTBEAT, [self._pc_heartbeat])
                except IO_ERRORS as e:
                    log.warning("Heartbeat write failed: %s", e)
            await asyncio.sleep(self.cfg.heartbeat_interval_s)

    def _apply(self, r: list[int]) -> None:
        s = self._status
        if not s.connected:
            log.info("PLC connected (%s:%s, %s lanes)", self.cfg.host, self.cfg.port, len(self.lanes))
            s.heartbeat_changed_at = time.monotonic()
        s.connected = True
        if r[ReadReg.PLC_HEARTBEAT] != s.heartbeat:
            s.heartbeat = r[ReadReg.PLC_HEARTBEAT]
            s.heartbeat_changed_at = time.monotonic()
        s.state = _enum(PlcState, r[ReadReg.PLC_STATE], PlcState.FAULT)
        s.sensors = Sensor(r[ReadReg.SENSORS] & int(Sensor.BIN_FULL | Sensor.SERVICE_DOOR_OPEN | Sensor.ESTOP_ACTIVE))
        s.machine_channel = _channel(r[ReadReg.CMD_ACK_SEQ], r[ReadReg.CMD_STATUS], r[ReadReg.CMD_RESULT])
        s.fault_code = _enum(FaultCode, r[ReadReg.FAULT_CODE], FaultCode.MOTOR_FAULT)
        s.bin_count = r[ReadReg.BIN_COUNT]
        s.bin_fill_pct = r[ReadReg.BIN_FILL_PCT]
        s.plc_version = r[ReadReg.PLC_VERSION]
        for lane in self.lanes:
            b = lane_base(lane)
            s.lanes[lane] = LaneStatus(
                sensors=LaneSensor(r[b + LaneReg.SENSORS] & 0x1F),
                channel=_channel(r[b + LaneReg.ACK_SEQ], r[b + LaneReg.STATUS], r[b + LaneReg.RESULT]),
            )

    # ---------- raw IO ----------

    async def _read(self, address: int, count: int) -> list[int]:
        async with self._io_lock:
            rr = await self._client.read_holding_registers(address, count=count, device_id=self.cfg.device_id)
        if rr.isError():
            raise ModbusException(f"read {address} failed: {rr}")
        return rr.registers

    async def _write(self, address: int, values: list[int]) -> None:
        async with self._io_lock:
            wr = await self._client.write_registers(address, values, device_id=self.cfg.device_id)
        if wr.isError():
            raise ModbusException(f"write {address} failed: {wr}")


def _channel(ack: int, status: int, result: int) -> ChannelStatus:
    return ChannelStatus(ack, _enum(CmdStatus, status, CmdStatus.FAILED), _enum(CmdResult, result, CmdResult.INVALID_CMD))


def _enum(enum_cls, value, fallback):
    try:
        return enum_cls(value)
    except ValueError:
        return fallback
