# RVM PLC ↔ PC Interface Specification

**Version:** 0.1 (draft, 2026-10-03)
**Audience:** PLC programmer (machine manufacturer) and RVM software team
**Reference implementation:** `machine/rvm/plc/registers.py` (register map), `machine/rvm/plc/simulator.py` (behaviour)

---

## 1. Roles

| Item | Value |
|---|---|
| Protocol | Modbus TCP |
| PLC role | **Modbus server (slave)** |
| Industrial PC role | Modbus client (master) |
| Default port / unit id | 502 / 1 (configurable on PC side) |
| Register type | Holding registers (FC03 read, FC16 write), 16-bit unsigned |
| PC poll rate | Every 100 ms (reads the whole status block in one request) |

The PLC owns **all motion and safety**: motors, interlocks, light curtain, e-stop. The PC only sends high-level commands and decides what happens to the bottle.

## 2. Register map

Addresses are zero-based protocol addresses. Both base addresses can be changed on the PC side if the PLC needs another layout.

### 2.1 PC → PLC (write block, base 0)

| Addr | Name | Description |
|---|---|---|
| 0 | `PC_HEARTBEAT` | PC increments every 500 ms (wraps at 65535) |
| 1 | `CMD_CODE` | Command, see §3 |
| 2 | `CMD_PARAM` | Command parameter (e.g. rotation degrees) |
| 3 | `CMD_SEQ` | Sequence number 1..65535. **A changed value triggers execution.** Never 0. |

The PC writes registers 1–3 in **one** FC16 request.

### 2.2 PLC → PC (read block, base 100)

| Addr | Name | Description |
|---|---|---|
| 100 | `PLC_HEARTBEAT` | PLC increments every scan / ≥ every 200 ms |
| 101 | `PLC_STATE` | 0 BOOTING, 1 READY, 2 BUSY, 3 FAULT, 4 ESTOP, 5 MAINTENANCE |
| 102 | `SENSORS` | Bit field, see §2.3 |
| 103 | `CMD_ACK_SEQ` | `CMD_SEQ` of the command being executed / last finished |
| 104 | `CMD_STATUS` | 0 IDLE, 1 RUNNING, 2 DONE, 3 FAILED |
| 105 | `CMD_RESULT` | 0 OK, 1 TIMEOUT, 2 JAM, 3 NO_BOTTLE, 4 INTERLOCK, 5 INVALID_CMD, 6 BUSY |
| 106 | `FAULT_CODE` | 0 NONE, 1 ESTOP, 2 PC_WATCHDOG, 3 MOTOR_FAULT, 4 JAM, 5 SERVICE_DOOR_OPEN, 6 BIN_FULL |
| 107 | `BIN_COUNT` | Bottles in bin since last service |
| 108 | `BIN_FILL_PCT` | 0–100 |
| 109 | `PLC_VERSION` | Program version, e.g. 102 = v1.02 |

### 2.3 `SENSORS` bits

| Bit | Name | Meaning when 1 |
|---|---|---|
| 0 | `BOTTLE_AT_INLET` | Bottle present in the inlet |
| 1 | `BOTTLE_IN_SCAN_POSITION` | Bottle on the scan rollers in front of the camera |
| 2 | `INLET_DOOR_CLOSED` | Inlet door fully closed |
| 3 | `BIN_FULL` | Collection bin full |
| 4 | `SERVICE_DOOR_OPEN` | Service door open |
| 5 | `ESTOP_ACTIVE` | Emergency stop pressed |
| 6 | `HAND_DETECTED` | Light curtain at inlet interrupted |
| 7 | `BOTTLE_IN_HOLD` | Bottle parked in the holding chamber |

## 3. Commands

| Code | Command | Precondition | Result on success |
|---|---|---|---|
| 1 | `OPEN_INLET` | — | Door open (bit 2 = 0) |
| 2 | `CLOSE_INLET` | No hand in curtain, else `INTERLOCK` | Door closed (bit 2 = 1) |
| 3 | `MOVE_TO_SCAN` | Bottle at inlet (else `NO_BOTTLE`), door closed | Bit 0 = 0, bit 1 = 1 |
| 4 | `ROTATE_BOTTLE` | Bottle in scan position. `PARAM` = degrees | Bottle rotated, still in scan position |
| 5 | `MOVE_TO_HOLD` | Bottle in scan position | Bit 1 = 0, bit 7 = 1 |
| 6 | `ACCEPT_BOTTLE` | Bottle in scan position or hold | Bottle in bin, `BIN_COUNT` + 1 |
| 7 | `REJECT_BOTTLE` | Bottle in scan / hold / inlet | Bottle back at inlet (bit 0 = 1), door open |
| 8 | `LIGHT_ON` | — | Camera illumination on |
| 9 | `LIGHT_OFF` | — | Camera illumination off |
| 10 | `RESET_FAULT` | E-stop released (else `INTERLOCK`) | `PLC_STATE` = READY, `FAULT_CODE` = 0 |
| 11 | `SAFE_STOP` | — | All motion stopped, door closed |

## 4. Command handshake

```
PC                                   PLC
 | write CMD_CODE, CMD_PARAM, CMD_SEQ=n  |
 |-------------------------------------->|  detects CMD_SEQ != last seq
 |                                       |  CMD_ACK_SEQ = n, CMD_STATUS = RUNNING
 |          (PC polls every 100 ms)      |  ... executes ...
 |                                       |  update SENSORS / BIN_COUNT
 |                                       |  CMD_RESULT = x, CMD_STATUS = DONE or FAILED
 |<--------------------------------------|
 | sees ACK_SEQ == n and STATUS DONE/FAILED -> command finished
```

**Rules for the PLC program:**

1. Execute a command only when `CMD_SEQ` changes and is non-zero. Re-writing the same `CMD_SEQ` (PC retry after a network glitch) must **not** run the command again.
2. Set `CMD_ACK_SEQ` and `CMD_STATUS = RUNNING` in the same scan where the new command is latched.
3. **Update `SENSORS`, `PLC_STATE` and `BIN_COUNT` in the same scan as, or before, setting `CMD_STATUS = DONE/FAILED`.** The PC reads the whole block in one request and trusts the sensors once it sees DONE.
4. One command at a time. If a new `CMD_SEQ` arrives while RUNNING, finish it with `CMD_RESULT = BUSY`.
5. Every command must end within its timeout (default 10 s, accept/reject 15 s). If motion cannot complete, end with `FAILED` + `TIMEOUT` or `JAM` and go to FAULT where appropriate.

## 5. Watchdogs and safety

| Watchdog | Rule |
|---|---|
| PC → PLC | If `PC_HEARTBEAT` does not change for **3 s** (after it has been non-zero once), the PLC stops all motion, closes the inlet, sets `PLC_STATE = FAULT`, `FAULT_CODE = PC_WATCHDOG`. Clears with `RESET_FAULT`. |
| PLC → PC | If `PLC_HEARTBEAT` does not change for 3 s, the PC puts the machine out of service. |

- E-stop: PLC immediately stops motion and sets `PLC_STATE = ESTOP`, `FAULT_CODE = ESTOP`, bit 5 = 1. When released, the PLC goes to `FAULT` (not READY) until the PC sends `RESET_FAULT`.
- Light curtain: inlet door must never close while `HAND_DETECTED` = 1.
- After a fault, the PLC keeps the bottle where it is. The PC decides whether to accept or reject it after reset.

## 6. Acceptance test

The manufacturer's PLC program is accepted when `pytest machine/tests/test_plc.py` passes against the real PLC (the PC side is the same code that runs against the simulator), plus a physical check of e-stop, light curtain and jam handling.

## 7. Open points for the manufacturer

1. PLC make/model and whether Modbus TCP server is available (if not: Siemens S7 / OPC UA driver will be added on the PC side).
2. Are the refund QR and manufacturing QR on different sides of the bottle? Expected number of rotation steps for full coverage.
3. Separate sorting outputs (glass / PET / brand) on `ACCEPT_BOTTLE`? Can be added as `CMD_PARAM`.
4. Holding chamber capacity (one bottle assumed).
5. Real motion times, used to set PC timeouts.
