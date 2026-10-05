"""PLC <-> PC register map (Modbus holding registers).

This file is the single source of truth for the PLC interface.
Keep it in sync with docs/plc-interface-spec.md - the PLC programmer
implements the same map on the PLC side.

All addresses are offsets from the configured base addresses:
  write block (PC -> PLC) starts at `write_base`  (default 0)
  read block  (PLC -> PC) starts at `read_base`   (default 100)
"""

from enum import IntEnum, IntFlag


class WriteReg(IntEnum):
    """PC -> PLC registers (offset from write_base)."""

    PC_HEARTBEAT = 0  # PC increments every heartbeat interval
    CMD_CODE = 1      # Command, see Cmd
    CMD_PARAM = 2     # Optional command parameter
    CMD_SEQ = 3       # New value (1..65535) triggers execution of CMD_CODE


WRITE_BLOCK_SIZE = 4


class ReadReg(IntEnum):
    """PLC -> PC registers (offset from read_base)."""

    PLC_HEARTBEAT = 0    # PLC increments continuously
    PLC_STATE = 1        # See PlcState
    SENSORS = 2          # Bit field, see Sensor
    CMD_ACK_SEQ = 3      # Echo of the CMD_SEQ the PLC is working on / finished
    CMD_STATUS = 4       # See CmdStatus
    CMD_RESULT = 5       # See CmdResult (valid when CMD_STATUS is DONE/FAILED)
    FAULT_CODE = 6       # See FaultCode
    BIN_COUNT = 7        # Bottles in bin since last service
    BIN_FILL_PCT = 8     # 0..100
    PLC_VERSION = 9      # PLC program version (e.g. 102 = v1.02)


READ_BLOCK_SIZE = 10


class PlcState(IntEnum):
    BOOTING = 0
    READY = 1
    BUSY = 2
    FAULT = 3
    ESTOP = 4
    MAINTENANCE = 5


class Sensor(IntFlag):
    BOTTLE_AT_INLET = 1 << 0           # Bottle placed in the inlet
    BOTTLE_IN_SCAN_POSITION = 1 << 1   # Bottle on the scan rollers
    INLET_DOOR_CLOSED = 1 << 2
    BIN_FULL = 1 << 3
    SERVICE_DOOR_OPEN = 1 << 4
    ESTOP_ACTIVE = 1 << 5
    HAND_DETECTED = 1 << 6             # Safety light curtain at inlet
    BOTTLE_IN_HOLD = 1 << 7            # Bottle parked in holding chamber


class Cmd(IntEnum):
    NONE = 0
    OPEN_INLET = 1
    CLOSE_INLET = 2
    MOVE_TO_SCAN = 3       # Inlet -> scan rollers
    ROTATE_BOTTLE = 4      # PARAM = degrees
    MOVE_TO_HOLD = 5       # Scan rollers -> holding chamber
    ACCEPT_BOTTLE = 6      # Scan/hold -> sorting / bin
    REJECT_BOTTLE = 7      # Scan/hold -> back to customer at inlet
    LIGHT_ON = 8
    LIGHT_OFF = 9
    RESET_FAULT = 10
    SAFE_STOP = 11


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
