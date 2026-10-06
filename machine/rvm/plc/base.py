"""PLC abstraction used by the orchestrator.

The orchestrator only talks to `PLC`; the transport (Modbus TCP today,
maybe S7/OPC-UA later) lives behind it.
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from .registers import Cmd, CmdResult, CmdStatus, FaultCode, LaneSensor, PlcState, Sensor


class PLCError(Exception):
    """Base class for PLC errors."""


class PLCFault(PLCError):
    """PLC unreachable, heartbeat lost, e-stop or fault state.

    The machine must go out of service until the fault clears.
    """

    def __init__(self, message: str, fault_code: FaultCode = FaultCode.NONE):
        super().__init__(message)
        self.fault_code = fault_code


class PLCCommandError(PLCError):
    """A single command failed (jam, interlock, ...). Machine may recover."""

    def __init__(self, cmd: Cmd, result: CmdResult, lane: int = 0):
        where = f"lane {lane} " if lane else ""
        super().__init__(f"{where}{cmd.name} failed: {result.name}")
        self.cmd = cmd
        self.result = result
        self.lane = lane


class PLCTimeout(PLCError):
    """Command or sensor wait timed out."""


@dataclass
class ChannelStatus:
    ack_seq: int = 0
    status: CmdStatus = CmdStatus.IDLE
    result: CmdResult = CmdResult.OK


@dataclass
class LaneStatus:
    sensors: LaneSensor = LaneSensor(0)
    channel: ChannelStatus = field(default_factory=ChannelStatus)

    def has(self, sensor: LaneSensor) -> bool:
        return bool(self.sensors & sensor)


@dataclass
class PLCStatus:
    connected: bool = False
    heartbeat: int = 0
    state: PlcState = PlcState.BOOTING
    sensors: Sensor = Sensor(0)
    machine_channel: ChannelStatus = field(default_factory=ChannelStatus)
    lanes: dict[int, LaneStatus] = field(default_factory=dict)
    fault_code: FaultCode = FaultCode.NONE
    bin_count: int = 0
    bin_fill_pct: int = 0
    plc_version: int = 0
    heartbeat_changed_at: float = field(default_factory=time.monotonic)

    def has(self, sensor: Sensor) -> bool:
        return bool(self.sensors & sensor)

    def lane_has(self, lane: int, sensor: LaneSensor) -> bool:
        ls = self.lanes.get(lane)
        return bool(ls and ls.has(sensor))

    def channel(self, ch: int) -> ChannelStatus:
        return self.machine_channel if ch == 0 else self.lanes[ch].channel


class PLC(ABC):
    lanes: list[int]   # lane numbers this machine has, e.g. [1, 2, 3]

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @property
    @abstractmethod
    def status(self) -> PLCStatus: ...

    @abstractmethod
    def check_healthy(self) -> None:
        """Raise PLCFault if the PLC cannot be used right now."""

    @abstractmethod
    async def command(self, cmd: Cmd, param: int = 0, timeout: float | None = None, lane: int = 0) -> None:
        """Execute a command on a lane (1..3) or the machine channel (0) and wait for completion.

        Raises PLCCommandError, PLCTimeout or PLCFault.
        """

    @abstractmethod
    async def wait_for_lane(self, lane: int, sensor: LaneSensor, present: bool = True,
                            timeout: float | None = None) -> None:
        """Wait until a lane sensor bit is set (or cleared). Raises PLCTimeout / PLCFault."""

    @abstractmethod
    async def wait_any_lane(self, sensor: LaneSensor, timeout: float | None = None) -> int:
        """Wait until the sensor is set on any lane; returns the lane. Raises PLCTimeout / PLCFault."""
