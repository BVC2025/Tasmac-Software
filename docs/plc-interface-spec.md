# RVM PLC ↔ PC Interface Specification

**Version:** 0.2 (draft, 2026-10-06), multi-lane (up to 3 bottle inlets)
**Audience:** PLC programmer (machine manufacturer) and RVM software team
**Reference implementation:** `machine/rvm/plc/registers.py` (register map), `machine/rvm/plc/simulator.py` (behaviour)

**Changes from v0.1:** every inlet (lane) now has its own sensor register and its own command channel, so the three lanes can move at the same time. Machine-wide sensors (e-stop, bin, service door) stay in the machine `SENSORS` register.

---

## 1. Roles

| Item | Value |
|---|---|
| Protocol | Modbus TCP |
| PLC role | **Modbus server (slave)** |
| Industrial PC role | Modbus client (master) |
| Default port / unit id | 502 / 1 (configurable on PC side) |
| Register type | Holding registers (FC03 read, FC16 write), 16-bit unsigned |
| PC poll rate | Every 100 ms (reads the whole status block, 22 registers, in one request) |
| Lanes | 1 to 3, configured on the PC (`plc.lanes`). Unused lanes are ignored |

The PLC owns **all motion and safety**: motors, interlocks, light curtains, e-stop. The PC only sends high-level commands and decides what happens to each bottle.

## 2. How the PC uses the lanes

One customer session = up to 3 bottles, one per inlet:

1. PC opens every inlet (`OPEN_INLET` on each lane).
2. A bottle appears in any inlet → the PC waits up to 3 s for bottles in the other inlets, then closes the inlets without a bottle.
3. **Each lane runs independently and in parallel:** close inlet → move to scan → light on → rotate + photos → move to hold (valid) or reject (invalid, back to the same inlet).
4. After every lane has finished checking, the customer is paid for the valid bottles, then the PC sends `ACCEPT_BOTTLE` on every held lane (payout success) or `REJECT_BOTTLE` (payout failed).

So the PLC must accept commands on several lane channels at the same time.

## 3. Register map

Addresses are zero-based protocol addresses. Both base addresses can be changed on the PC side if the PLC needs another layout.

### 3.1 PC → PLC (write block, base 0)

| Addr | Name | Description |
|---|---|---|
| 0 | `PC_HEARTBEAT` | PC increments every 500 ms (wraps at 65535) |
| 1 / 2 / 3 | Machine channel `CODE` / `PARAM` / `SEQ` | `RESET_FAULT`, `SAFE_STOP` only |
| 4 / 5 / 6 | Lane 1 `CODE` / `PARAM` / `SEQ` | Lane 1 commands |
| 7 / 8 / 9 | Lane 2 `CODE` / `PARAM` / `SEQ` | Lane 2 commands |
| 10 / 11 / 12 | Lane 3 `CODE` / `PARAM` / `SEQ` | Lane 3 commands |

Channel `c` (0 = machine, 1..3 = lanes) starts at address `1 + 3·c`. `SEQ` is 1..65535; **a changed value triggers execution**, never 0. The PC writes the three registers of a channel in **one** FC16 request.

### 3.2 PLC → PC (read block, base 100)

| Addr | Name | Description |
|---|---|---|
| 100 | `PLC_HEARTBEAT` | PLC increments every scan / ≥ every 200 ms |
| 101 | `PLC_STATE` | 0 BOOTING, 1 READY, 2 BUSY, 3 FAULT, 4 ESTOP, 5 MAINTENANCE |
| 102 | `SENSORS` | Machine bit field, see §3.3 |
| 103 | `CMD_ACK_SEQ` | Machine channel: `SEQ` being executed / last finished |
| 104 | `CMD_STATUS` | Machine channel: 0 IDLE, 1 RUNNING, 2 DONE, 3 FAILED |
| 105 | `CMD_RESULT` | Machine channel: see result codes below |
| 106 | `FAULT_CODE` | 0 NONE, 1 ESTOP, 2 PC_WATCHDOG, 3 MOTOR_FAULT, 4 JAM, 5 SERVICE_DOOR_OPEN, 6 BIN_FULL |
| 107 | `BIN_COUNT` | Bottles in bin since last service (all lanes) |
| 108 | `BIN_FILL_PCT` | 0–100 |
| 109 | `PLC_VERSION` | Program version, e.g. 200 = v2.00 |
| 110 / 111 / 112 / 113 | Lane 1 `SENSORS` / `ACK_SEQ` / `STATUS` / `RESULT` | §3.4 |
| 114 / 115 / 116 / 117 | Lane 2 `SENSORS` / `ACK_SEQ` / `STATUS` / `RESULT` | §3.4 |
| 118 / 119 / 120 / 121 | Lane 3 `SENSORS` / `ACK_SEQ` / `STATUS` / `RESULT` | §3.4 |

Lane `n` starts at address `110 + 4·(n − 1)`.

**Result codes** (machine and lane `RESULT`): 0 OK, 1 TIMEOUT, 2 JAM, 3 NO_BOTTLE, 4 INTERLOCK, 5 INVALID_CMD, 6 BUSY.

### 3.3 Machine `SENSORS` bits (address 102)

| Bit | Name | Meaning when 1 |
|---|---|---|
| 3 | `BIN_FULL` | Collection bin full |
| 4 | `SERVICE_DOOR_OPEN` | Service door open |
| 5 | `ESTOP_ACTIVE` | Emergency stop pressed |

Bits 0–2, 6, 7 are unused (moved to the lane registers in v0.2).

### 3.4 Lane `SENSORS` bits (addresses 110 / 114 / 118)

| Bit | Name | Meaning when 1 |
|---|---|---|
| 0 | `BOTTLE_AT_INLET` | Bottle present in this inlet |
| 1 | `BOTTLE_IN_SCAN_POSITION` | Bottle on this lane's scan rollers in front of its camera |
| 2 | `INLET_DOOR_CLOSED` | This inlet's door fully closed |
| 3 | `HAND_DETECTED` | This inlet's light curtain interrupted |
| 4 | `BOTTLE_IN_HOLD` | Bottle parked in this lane's holding chamber |

## 4. Commands

Lane commands go to the lane's channel and act only on that lane. Machine commands go to channel 0. A command sent to the wrong channel ends with `INVALID_CMD`.

| Code | Command | Channel | Precondition | Result on success |
|---|---|---|---|---|
| 1 | `OPEN_INLET` | lane | — | Door open (bit 2 = 0) |
| 2 | `CLOSE_INLET` | lane | No hand in this curtain, else `INTERLOCK` | Door closed (bit 2 = 1) |
| 3 | `MOVE_TO_SCAN` | lane | Bottle at inlet (else `NO_BOTTLE`), door closed | Bit 0 = 0, bit 1 = 1 |
| 4 | `ROTATE_BOTTLE` | lane | Bottle in scan position. `PARAM` = degrees | Bottle rotated, still in scan position |
| 5 | `MOVE_TO_HOLD` | lane | Bottle in scan position | Bit 1 = 0, bit 4 = 1 |
| 6 | `ACCEPT_BOTTLE` | lane | Bottle in scan position or hold | Bottle in bin, `BIN_COUNT` + 1 |
| 7 | `REJECT_BOTTLE` | lane | Bottle in scan / hold / inlet | Bottle back at **this lane's** inlet (bit 0 = 1), door open |
| 8 | `LIGHT_ON` | lane | — | This lane's camera illumination on |
| 9 | `LIGHT_OFF` | lane | — | Illumination off |
| 10 | `RESET_FAULT` | machine | E-stop released (else `INTERLOCK`) | `PLC_STATE` = READY, `FAULT_CODE` = 0 |
| 11 | `SAFE_STOP` | machine | — | All motion stopped, all doors closed |

## 5. Command handshake (per channel)

```
PC                                         PLC
 | write CODE, PARAM, SEQ=n of channel c       |
 |-------------------------------------------->|  detects SEQ(c) != last SEQ(c)
 |                                             |  ACK_SEQ(c) = n, STATUS(c) = RUNNING
 |          (PC polls every 100 ms)            |  ... executes ...
 |                                             |  update lane SENSORS / BIN_COUNT
 |                                             |  RESULT(c) = x, STATUS(c) = DONE or FAILED
 |<--------------------------------------------|
 | sees ACK_SEQ(c) == n and STATUS DONE/FAILED -> command finished
```

**Rules for the PLC program:**

1. Execute a channel's command only when its `SEQ` changes and is non-zero. Re-writing the same `SEQ` (PC retry after a network glitch) must **not** run the command again.
2. Set the channel's `ACK_SEQ` and `STATUS = RUNNING` in the same scan where the new command is latched.
3. **Update the lane `SENSORS`, `PLC_STATE` and `BIN_COUNT` in the same scan as, or before, setting `STATUS = DONE/FAILED`.** The PC reads the whole block in one request and trusts the sensors once it sees DONE.
4. One command at a time **per channel**. Different channels run at the same time. If a new `SEQ` arrives on a channel that is RUNNING, finish it with `RESULT = BUSY`.
5. Every command must end within its timeout (default 10 s, accept/reject 15 s). If motion cannot complete, end with `FAILED` + `TIMEOUT` or `JAM` and go to FAULT where appropriate.
6. `PLC_STATE` = BUSY while any channel is running, READY when all are idle.

## 6. Watchdogs and safety

| Watchdog | Rule |
|---|---|
| PC → PLC | If `PC_HEARTBEAT` does not change for **3 s** (after it has been non-zero once), the PLC stops all motion, closes **all** inlets, sets `PLC_STATE = FAULT`, `FAULT_CODE = PC_WATCHDOG`. Clears with `RESET_FAULT`. |
| PLC → PC | If `PLC_HEARTBEAT` does not change for 3 s, the PC puts the machine out of service. |

- E-stop: PLC immediately stops motion on all lanes and sets `PLC_STATE = ESTOP`, `FAULT_CODE = ESTOP`, machine bit 5 = 1. When released, the PLC goes to `FAULT` (not READY) until the PC sends `RESET_FAULT`.
- Light curtains: an inlet door must never close while its own `HAND_DETECTED` = 1. Other inlets are not affected.
- After a fault, the PLC keeps every bottle where it is. After reset, the PC decides per lane whether to accept (already paid) or reject it.

## 7. Acceptance test

The manufacturer's PLC program is accepted when `pytest machine/tests/test_plc.py` passes against the real PLC (the PC side is the same code that runs against the simulator), including `test_lanes_run_commands_in_parallel`, plus a physical check of e-stop, each light curtain and jam handling.

## 8. Open points for the manufacturer

1. PLC make/model and whether a Modbus TCP server is available (if not: Siemens S7 / OPC UA driver will be added on the PC side).
2. Number of lanes in the final design (software supports 1–3) and whether each lane has its own camera, rollers and holding chamber (assumed: yes, one each).
3. Are the refund QR and manufacturing QR on different sides of the bottle? Expected number of rotation steps for full coverage.
4. Separate sorting outputs (glass / PET / brand) on `ACCEPT_BOTTLE`? Can be added as `PARAM`.
5. Real motion times, used to set PC timeouts.
