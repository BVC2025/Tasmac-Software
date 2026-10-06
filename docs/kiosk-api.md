# Kiosk UI ↔ Machine Local API

**Audience:** frontend developers building the RVM touchscreen UI.
**Server:** machine controller, `http://127.0.0.1:8765` (enabled with `local_api.enabled: true`, see `machine/config/machine.dev.yaml`).

The machine is the source of truth. The UI **renders the current state** and **sends customer input**. It never calls the central backend directly.

## WebSocket `ws://127.0.0.1:8765/ws`

The first frame is a snapshot. After that, every machine event arrives as JSON.

```json
{"type": "snapshot", "state": "READY", "last_state": {...}, "last_message": {...},
 "waiting_for": null, "machine_id": "RVM-SIM-001", "simulation": true,
 "plc": {"connected": true, "state": "READY", "fault": "NONE", "bin_fill_pct": 1}}
```

| `type` | Fields |
|---|---|
| `state` | `state`, plus extra fields: `lanes` (READY, COLLECTING, CHECKING), `timeout_s` (COLLECTING, SELECT_REFUND_METHOD, CONFIRMING), `attempt`, `max_attempts`, `amount_paise`, `bottle_count` (SELECT_REFUND_METHOD), `reason`, `bottles` (REJECTING), `reason` (OUT_OF_SERVICE) |
| `message` | `code`, plus fields listed below |
| `session_started` | `session_id`, `lane` (first inlet used) |
| `lane` | `lane` (1..3), `step` (DETECTED, POSITIONING, INSPECTING, SCANNING_REFUND_QR, SCANNING_MFG_QR, VERIFYING, VALID, REJECTED, ACCEPTED, RETURNED), `reason`, `amount_paise` (VALID) |
| `session_ended` | `session_id`, `outcome` (ACCEPTED / RETURNED / CANCELLED / ABORTED), `reason`, `txn_id`, `bottles` (`[{lane, step, reason}]`), `accepted`, `amount_paise` |
| `fault` | `reason` |

Reconnect automatically. Re-read the snapshot after every reconnect.

## States → screens

A session is one customer with up to 3 bottles (one per inlet). Every bottle is checked in its own lane, in parallel; the refund destination is asked only after all of them are checked.

| State | Screen |
|---|---|
| `STARTING`, `HEALTH_CHECK` | Starting up |
| `READY` | Insert up to N bottles (`lane_count` in the snapshot) |
| `COLLECTING` | First bottle in; short countdown for bottles in the other inlets |
| `CHECKING` | One card per bottle, driven by `lane` events (step list, then valid / rejected with reason) |
| `SELECT_REFUND_METHOD` | Batch summary + "how do you want ₹`amount_paise`?", then UPI QR / voice / keypad |
| `CONFIRMING` | Masked destination, name, bottle count and amount, Confirm / Change |
| `PAYING`, `ACCEPTING` | Processing payment |
| `REJECTING` | Bottles handed back, with the reason (per bottle or for the whole batch, e.g. payment failed) |
| `OUT_OF_SERVICE` | Machine unavailable |

## Message codes

| Code | Fields | Meaning |
|---|---|---|
| `INSERT_BOTTLE` | — | Ready for a bottle |
| `REMOVE_HAND` | — | Hand in the inlet, door cannot close |
| `INVALID_DESTINATION` | `attempt` | Input is not a valid UPI ID or mobile number |
| `DESTINATION_NOT_FOUND` | `attempt` | UPI ID / number does not exist |
| `BATCH_RESULT` | `accepted`, `rejected`, `amount_paise`, `bottles` | All bottles checked, at least one valid |
| `CONFIRM_REFUND` | `destination` (masked), `kind`, `name`, `amount_paise`, `bottle_count`, `sms_mobile` (masked or null), `sms` (bool) | Ask the customer to confirm |
| `INVALID_SMS_MOBILE` | `attempt` | Optional SMS number is not valid |
| `PROCESSING_PAYMENT` | — | Payout in progress |
| `REFUND_SUCCESS` | `txn_id` | ₹10 sent |
| `REFUND_PENDING` | `txn_id` | Bottle accepted, payment will arrive (SMS) |
| `BOTTLE_REJECTED` | `reason`, `lane` (one bottle) or no lane (whole batch) | See reasons below |
| `TAKE_BACK_BOTTLE` | — | Bottle is at the inlet, please take it |

Reject reasons: `HAND_IN_INLET`, `BOTTLE_REMOVED`, `BOTTLE_DAMAGED`, `BOTTLE_FOREIGN`, `REFUND_QR_NOT_FOUND`, `REFUND_QR_INVALID_FORMAT`, `REFUND_QR_FORGED`, `REFUND_QR_ALREADY_USED`, `REFUND_QR_IN_USE`, `MFG_QR_NOT_FOUND`, `MFG_QR_INVALID_FORMAT`, `MFG_QR_FORGED`, `BRAND_NOT_ELIGIBLE`, `BOTTLE_ALREADY_RETURNED`, `BOTTLE_IN_USE`, `INVALID_DESTINATION`, `CUSTOMER_TIMEOUT`, `CUSTOMER_CANCELLED`, `PAYOUT_FAILED`, `PAYOUT_PENDING`, `BACKEND_UNAVAILABLE`.

All customer-facing text (Tamil / English) lives in the UI and is keyed by these codes.

## HTTP

| Method & path | Body | Notes |
|---|---|---|
| `GET /api/status` | — | Same as the snapshot |
| `GET /api/sessions?limit=20` | — | Recent sessions (destination masked) |
| `POST /api/customer/destination` | `{"value": "ravi@okaxis", "source": "qr", "sms_mobile": "9000012345"}`, `{"value": "9876543210", "source": "voice"}` or `{"cancel": true}` | Only while state = `SELECT_REFUND_METHOD`, otherwise 409. `source` is `qr`, `voice` or `keypad`. `sms_mobile` is optional (UPI IDs only) |
| `POST /api/customer/confirm` | `{"ok": true}` (false = re-enter destination) | Only while state = `CONFIRMING`, otherwise 409 |
| `GET /api/sim/bottles` | — | Simulation only: test bottle scenarios |
| `POST /api/sim/insert` | `{"bottle": "payout-failed", "lane": 2}` (both optional) | Simulation only: insert a test bottle (default: next in feed, first free inlet) |
| `POST /api/sim/insert-batch` | `{"bottles": ["happy-path-upi", "damaged-bottle", null]}` | Simulation only: bottles in several inlets at the same moment |
| `POST /api/sim/refresh` | — | Simulation only: new QR serials for all test bottles |
| `POST /api/sim/estop` | `{"pressed": true}` | Simulation only |

The customer has `customer_input_timeout_s` (default 60–90 s) to respond. After that the bottle is returned with `CUSTOMER_TIMEOUT`.
