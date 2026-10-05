"""PLC abstraction used by the orchestrator.

The orchestrator only talks to `PLC`; the transport (Modbus TCP today,
maybe S7/OPC-UA later) lives behind it.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import time

from .registers import CmdResult, CmdStatus, Cmd, FaultCode, PlcState, Sensor


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

    def __init__(self, cmd: Cmd, result: CmdResult):
        super().__init__(f"{cmd.name} failed: {result.name}")
        self.cmd = cmd
        self.result = result


class PLCTimeout(PLCError):
    """Command or sensor wait timed out."""


@dataclass
class PLCStatus:
    connected: bool = False
    heartbeat: int = 0
    state: PlcState = PlcState.BOOTING
    sensors: Sensor = Sensor(0)
    ack_seq: int = 0
    cmd_status: CmdStatus = CmdStatus.IDLE
    cmd_result: CmdResult = CmdResult.OK
    fault_code: FaultCode = FaultCode.NONE
    bin_count: int = 0
    bin_fill_pct: int = 0
    plc_version: int = 0
    heartbeat_changed_at: float = field(default_factory=time.monotonic)

    def has(self, sensor: Sensor) -> bool:
        return bool(self.sensors & sensor)


class PLC(ABC):
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
    async def command(self, cmd: Cmd, param: int = 0, timeout: float | None = None) -> None:
        """Execute a command and wait for completion.

        Raises PLCCommandError, PLCTimeout or PLCFault.
        """

    @abstractmethod
    async def wait_for(self, sensor: Sensor, present: bool = True, timeout: float | None = None) -> None:
        """Wait until a sensor bit is set (or cleared). Raises PLCTimeout / PLCFault."""
