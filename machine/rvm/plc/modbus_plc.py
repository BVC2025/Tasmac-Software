"""Modbus TCP implementation of the PLC interface.

Background tasks:
  * poll loop      - reads the PLC status block every poll_interval_s
  * heartbeat loop - increments PC_HEARTBEAT so the PLC watchdog stays happy

Command handshake (see docs/plc-interface-spec.md):
  1. PC writes CMD_CODE, CMD_PARAM, CMD_SEQ in one request (new SEQ = trigger)
  2. PLC sets CMD_ACK_SEQ = SEQ, CMD_STATUS = RUNNING
  3. PLC sets CMD_STATUS = DONE / FAILED and CMD_RESULT
"""

import asyncio
import logging
import time

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

from ..config import PLCConfig
from .base import PLC, PLCCommandError, PLCFault, PLCStatus, PLCTimeout
from .registers import (
    READ_BLOCK_SIZE,
    Cmd,
    CmdResult,
    CmdStatus,
    FaultCode,
    PlcState,
    ReadReg,
    Sensor,
    WriteReg,
)

log = logging.getLogger(__name__)


class ModbusPLC(PLC):
    def __init__(self, cfg: PLCConfig):
        self.cfg = cfg
        self._client = AsyncModbusTcpClient(cfg.host, port=cfg.port, timeout=cfg.connect_timeout_s)
        self._status = PLCStatus()
        self._io_lock = asyncio.Lock()
        self._cmd_lock = asyncio.Lock()
        self._tasks: list[asyncio.Task] = []
        self._seq = 0
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

    def _next_seq(self) -> int:
        self._seq = self._seq % 65535 + 1  # 1..65535, never 0
        return self._seq

    def _timeout_for(self, cmd: Cmd) -> float:
        return self.cfg.cmd_timeouts_s.get(cmd.name, self.cfg.default_cmd_timeout_s)

    async def command(self, cmd: Cmd, param: int = 0, timeout: float | None = None) -> None:
        async with self._cmd_lock:  # one command at a time
            if cmd != Cmd.RESET_FAULT:
                self.check_healthy()
            seq = self._next_seq()
            base = self.cfg.write_base
            await self._write(base + WriteReg.CMD_CODE, [int(cmd), param & 0xFFFF, seq])
            log.debug("PLC cmd %s param=%s seq=%s", cmd.name, param, seq)

            deadline = time.monotonic() + (timeout or self._timeout_for(cmd))
            while True:
                s = self._status
                if s.ack_seq == seq and s.cmd_status in (CmdStatus.DONE, CmdStatus.FAILED):
                    if s.cmd_status == CmdStatus.FAILED or s.cmd_result != CmdResult.OK:
                        raise PLCCommandError(cmd, s.cmd_result)
                    return
                if cmd != Cmd.RESET_FAULT:
                    self.check_healthy()
                if time.monotonic() > deadline:
                    raise PLCTimeout(f"{cmd.name} (seq={seq}) not completed in time")
                await self._wait_update()

    async def wait_for(self, sensor: Sensor, present: bool = True, timeout: float | None = None) -> None:
        deadline = None if timeout is None else time.monotonic() + timeout
        while self._status.has(sensor) != present:
            self.check_healthy()
            if deadline is not None and time.monotonic() > deadline:
                raise PLCTimeout(f"Sensor {sensor.name} != {present}")
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
            except (ModbusException, ConnectionError, OSError, asyncio.TimeoutError) as e:
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
                except (ModbusException, ConnectionError, OSError, asyncio.TimeoutError) as e:
                    log.warning("Heartbeat write failed: %s", e)
            await asyncio.sleep(self.cfg.heartbeat_interval_s)

    def _apply(self, r: list[int]) -> None:
        s = self._status
        if not s.connected:
            log.info("PLC connected (%s:%s)", self.cfg.host, self.cfg.port)
            s.heartbeat_changed_at = time.monotonic()
        s.connected = True
        if r[ReadReg.PLC_HEARTBEAT] != s.heartbeat:
            s.heartbeat = r[ReadReg.PLC_HEARTBEAT]
            s.heartbeat_changed_at = time.monotonic()
        s.state = _enum(PlcState, r[ReadReg.PLC_STATE], PlcState.FAULT)
        s.sensors = Sensor(r[ReadReg.SENSORS] & 0xFF)
        s.ack_seq = r[ReadReg.CMD_ACK_SEQ]
        s.cmd_status = _enum(CmdStatus, r[ReadReg.CMD_STATUS], CmdStatus.FAILED)
        s.cmd_result = _enum(CmdResult, r[ReadReg.CMD_RESULT], CmdResult.INVALID_CMD)
        s.fault_code = _enum(FaultCode, r[ReadReg.FAULT_CODE], FaultCode.MOTOR_FAULT)
        s.bin_count = r[ReadReg.BIN_COUNT]
        s.bin_fill_pct = r[ReadReg.BIN_FILL_PCT]
        s.plc_version = r[ReadReg.PLC_VERSION]

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


def _enum(enum_cls, value, fallback):
    try:
        return enum_cls(value)
    except ValueError:
        return fallback
