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
| `state` | `state`, plus extra fields: `session_id` (BOTTLE_DETECTED), `attempt`, `max_attempts`, `timeout_s` (SELECT_REFUND_METHOD), `timeout_s` (CONFIRMING), `reason` (REJECTING, OUT_OF_SERVICE) |
| `message` | `code`, plus fields listed below |
| `session_started` | `session_id` |
| `session_ended` | `session_id`, `outcome` (ACCEPTED / RETURNED / CANCELLED / ABORTED), `reason`, `txn_id` |
| `fault` | `reason` |

Reconnect automatically. Re-read the snapshot after every reconnect.

## States → screens

| State | Screen |
|---|---|
| `STARTING`, `HEALTH_CHECK` | Starting up |
| `READY` | Insert your bottle |
| `BOTTLE_DETECTED`, `POSITIONING`, `INSPECTING`, `SCANNING_REFUND_QR`, `SCANNING_MFG_QR`, `VERIFYING` | Checking bottle (progress steps) |
| `SELECT_REFUND_METHOD` | Choose UPI QR / speak mobile number / keypad, then send destination |
| `CONFIRMING` | Show masked destination, name and ₹ amount, with Confirm / Change buttons |
| `PAYING` | Processing payment |
| `ACCEPTING` | Success screen |
| `REJECTING` | Bottle returned, with the reason |
| `OUT_OF_SERVICE` | Machine unavailable |

## Message codes

| Code | Fields | Meaning |
|---|---|---|
| `INSERT_BOTTLE` | — | Ready for a bottle |
| `REMOVE_HAND` | — | Hand in the inlet, door cannot close |
| `INVALID_DESTINATION` | `attempt` | Input is not a valid UPI ID or mobile number |
| `DESTINATION_NOT_FOUND` | `attempt` | UPI ID / number does not exist |
| `CONFIRM_REFUND` | `destination` (masked), `kind`, `name`, `amount_paise`, `sms_mobile` (masked or null), `sms` (bool) | Ask the customer to confirm |
| `INVALID_SMS_MOBILE` | `attempt` | Optional SMS number is not valid |
| `PROCESSING_PAYMENT` | — | Payout in progress |
| `REFUND_SUCCESS` | `txn_id` | ₹10 sent |
| `REFUND_PENDING` | `txn_id` | Bottle accepted, payment will arrive (SMS) |
| `BOTTLE_REJECTED` | `reason` | See reasons below |
| `TAKE_BACK_BOTTLE` | — | Bottle is at the inlet, please take it |

Reject reasons: `BOTTLE_DAMAGED`, `BOTTLE_FOREIGN`, `REFUND_QR_NOT_FOUND`, `REFUND_QR_INVALID_FORMAT`, `REFUND_QR_FORGED`, `REFUND_QR_ALREADY_USED`, `REFUND_QR_IN_USE`, `MFG_QR_NOT_FOUND`, `MFG_QR_INVALID_FORMAT`, `MFG_QR_FORGED`, `BRAND_NOT_ELIGIBLE`, `BOTTLE_ALREADY_RETURNED`, `BOTTLE_IN_USE`, `INVALID_DESTINATION`, `CUSTOMER_TIMEOUT`, `CUSTOMER_CANCELLED`, `PAYOUT_FAILED`, `PAYOUT_PENDING`, `BACKEND_UNAVAILABLE`.

All customer-facing text (Tamil / English) lives in the UI and is keyed by these codes.

## HTTP

| Method & path | Body | Notes |
|---|---|---|
| `GET /api/status` | — | Same as the snapshot |
| `GET /api/sessions?limit=20` | — | Recent sessions (destination masked) |
| `POST /api/customer/destination` | `{"value": "ravi@okaxis", "source": "qr", "sms_mobile": "9000012345"}`, `{"value": "9876543210", "source": "voice"}` or `{"cancel": true}` | Only while state = `SELECT_REFUND_METHOD`, otherwise 409. `source` is `qr`, `voice` or `keypad`. `sms_mobile` is optional (UPI IDs only) |
| `POST /api/customer/confirm` | `{"ok": true}` (false = re-enter destination) | Only while state = `CONFIRMING`, otherwise 409 |
| `GET /api/sim/bottles` | — | Simulation only: test bottle scenarios |
| `POST /api/sim/insert` | `{"bottle": "payout-failed"}` (optional) | Simulation only: insert a test bottle (default: next in feed) |
| `POST /api/sim/refresh` | — | Simulation only: new QR serials for all test bottles |
| `POST /api/sim/estop` | `{"pressed": true}` | Simulation only |

The customer has `customer_input_timeout_s` (default 60–90 s) to respond. After that the bottle is returned with `CUSTOMER_TIMEOUT`.
