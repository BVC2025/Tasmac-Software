"""PLC <-> PC register map (Modbus holding registers), multi-lane version.

This file is the single source of truth for the PLC interface.
Keep it in sync with docs/plc-interface-spec.md - the PLC programmer
implements the same map on the PLC side.

A machine has 1..3 bottle lanes (inlets). Every lane has its own sensors and
its own command channel, so the PC can run the three lanes in parallel.
Channel 0 is the machine channel (fault reset, safe stop).

All addresses are offsets from the configured base addresses:
  write block (PC -> PLC) starts at `write_base`  (default 0)
  read block  (PLC -> PC) starts at `read_base`   (default 100)
"""

from enum import IntEnum, IntFlag

MAX_LANES = 3


# ---------------- PC -> PLC (write block) ----------------

class WriteReg(IntEnum):
    """Machine-level registers (offset from write_base)."""

    PC_HEARTBEAT = 0   # PC increments every heartbeat interval


class CmdReg(IntEnum):
    """Registers of one command channel, offset from cmd_base(channel)."""

    CODE = 0    # Command, see Cmd
    PARAM = 1   # Optional parameter (e.g. rotation degrees)
    SEQ = 2     # New value (1..65535) triggers execution of CODE


CMD_BLOCK = 3


def cmd_base(channel: int) -> int:
    """Offset of a command channel in the write block. 0 = machine, 1..3 = lanes."""
    return 1 + channel * CMD_BLOCK


WRITE_BLOCK_SIZE = 1 + (MAX_LANES + 1) * CMD_BLOCK   # 13


# ---------------- PLC -> PC (read block) ----------------

class ReadReg(IntEnum):
    """Machine-level registers (offset from read_base). ACK/STATUS/RESULT are for channel 0."""

    PLC_HEARTBEAT = 0    # PLC increments continuously
    PLC_STATE = 1        # See PlcState
    SENSORS = 2          # Machine bit field, see Sensor
    CMD_ACK_SEQ = 3      # Channel 0: CMD_SEQ being executed / last finished
    CMD_STATUS = 4       # Channel 0: see CmdStatus
    CMD_RESULT = 5       # Channel 0: see CmdResult
    FAULT_CODE = 6       # See FaultCode
    BIN_COUNT = 7        # Bottles in bin since last service
    BIN_FILL_PCT = 8     # 0..100
    PLC_VERSION = 9      # PLC program version (e.g. 200 = v2.00)


class LaneReg(IntEnum):
    """Registers of one lane, offset from lane_base(lane)."""

    SENSORS = 0     # See LaneSensor
    ACK_SEQ = 1     # Lane channel: CMD_SEQ being executed / last finished
    STATUS = 2      # Lane channel: see CmdStatus
    RESULT = 3      # Lane channel: see CmdResult


LANE_BLOCK = 4


def lane_base(lane: int) -> int:
    """Offset of lane 1..3 in the read block."""
    return 10 + (lane - 1) * LANE_BLOCK


READ_BLOCK_SIZE = 10 + MAX_LANES * LANE_BLOCK   # 22


# ---------------- values ----------------

class PlcState(IntEnum):
    BOOTING = 0
    READY = 1
    BUSY = 2
    FAULT = 3
    ESTOP = 4
    MAINTENANCE = 5


class Sensor(IntFlag):
    """Machine-level SENSORS register."""

    BIN_FULL = 1 << 3
    SERVICE_DOOR_OPEN = 1 << 4
    ESTOP_ACTIVE = 1 << 5


class LaneSensor(IntFlag):
    """Per-lane SENSORS register."""

    BOTTLE_AT_INLET = 1 << 0           # Bottle placed in this inlet
    BOTTLE_IN_SCAN_POSITION = 1 << 1   # Bottle on this lane's scan rollers
    INLET_DOOR_CLOSED = 1 << 2
    HAND_DETECTED = 1 << 3             # Light curtain of this inlet interrupted
    BOTTLE_IN_HOLD = 1 << 4            # Bottle parked in this lane's holding chamber


class Cmd(IntEnum):
    NONE = 0
    # lane channels (1..3)
    OPEN_INLET = 1
    CLOSE_INLET = 2
    MOVE_TO_SCAN = 3       # Inlet -> scan rollers
    ROTATE_BOTTLE = 4      # PARAM = degrees
    MOVE_TO_HOLD = 5       # Scan rollers -> holding chamber
    ACCEPT_BOTTLE = 6      # Scan/hold -> sorting / bin
    REJECT_BOTTLE = 7      # Scan/hold -> back to the customer at this lane's inlet
    LIGHT_ON = 8
    LIGHT_OFF = 9
    # machine channel (0)
    RESET_FAULT = 10
    SAFE_STOP = 11


MACHINE_CMDS = {Cmd.RESET_FAULT, Cmd.SAFE_STOP}


class CmdStatus(IntEnum):
    IDLE = 0
    RUNNING = 1
    DONE = 2
    FAILED = 3


class CmdResult(IntEnum):
    OK = 0
    TIMEOUT = 1
    JAM = 2
    NO_BOTTLE = 3
    INTERLOCK = 4   # Door open / hand detected / e-stop
    INVALID_CMD = 5
    BUSY = 6


class FaultCode(IntEnum):
    NONE = 0
    ESTOP = 1
    PC_WATCHDOG = 2    # PC heartbeat lost
    MOTOR_FAULT = 3
    JAM = 4
    SERVICE_DOOR_OPEN = 5
    BIN_FULL = 6
