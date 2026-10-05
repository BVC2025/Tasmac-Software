# TASMAC Reverse Vending Machine (RVM) Software

Software for an automated bottle return machine that refunds ₹10 per eligible bottle.

## Components

| Folder | What | Status |
|---|---|---|
| `machine/` | Machine controller on the industrial PC: PLC integration, workflow state machine, camera/QR/vision, simulator, local kiosk API | Done (simulated hardware) |
| `backend/` | Central FastAPI + PostgreSQL: QR verification, transactions, payout, SMS, audit | Done (mock payout/SMS providers) |
| `kiosk/` | React touchscreen UI (Tamil / English): UPI QR scan, voice number entry, keypad, SMS receipt number, see [kiosk API](docs/kiosk-api.md) | Done |
| `admin/` | React admin portal: login with roles, dashboard, alerts, transactions (re-check payout), sessions, refund QRs, SMS, daily reports + CSV, machines (register / disable / rotate key), brands, users, audit log | Done |
| `docs/` | Specs, including the [PLC interface spec](docs/plc-interface-spec.md) | |

## Machine controller

```
machine/
  rvm/plc/registers.py     PLC register map (source of truth for the PLC programmer)
  rvm/plc/modbus_plc.py    Modbus TCP client: polling, heartbeat, command handshake
  rvm/plc/simulator.py     Software PLC with the same behaviour (Modbus TCP server)
  rvm/core/orchestrator.py Customer workflow state machine
  rvm/services/            Backend client, QR format, vision/camera, customer UI (mocks for now)
  tools/generate_test_qr.py  Test QR codes + simulation bottle feed
  config/                  machine.sim.yaml (simulation), machine.yaml (real PLC)
```

### Setup

```bash
cd machine
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt     # Linux: .venv/bin/pip
```

### Run the full simulation

```bash
.venv/Scripts/python tools/generate_test_qr.py     # creates config/sim_bottles.yaml + test_qr/*.png
.venv/Scripts/python -m rvm.main --config config/machine.sim.yaml
```

A simulated customer inserts a bottle every 4 s and runs through 13 scenarios: happy path (UPI and
mobile), damaged, foreign object, missing/forged/reused QR, ineligible brand, payout failed/pending,
customer walking away, and a QR that needs extra rotations.

### Run against a real PLC

Set the PLC IP in `config/machine.yaml`, then:

```bash
.venv/Scripts/python -m rvm.main --config config/machine.yaml
```

The standalone simulator can stand in for the PLC on another PC:

```bash
.venv/Scripts/python -m rvm.plc.simulator --host 0.0.0.0 --port 502 --auto-insert 10
```

### Tests

```bash
.venv/Scripts/python -m pytest -q
```

`tests/test_plc.py` covers the PLC handshake, interlocks, e-stop and watchdogs.
`tests/test_flow.py` covers the full customer workflow, including faults in the middle of a session.

## Backend

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
copy .env.example .env                      # set RVM_DATABASE_URL to your PostgreSQL
.venv/Scripts/alembic upgrade head
.venv/Scripts/python -m app.cli seed-brands
.venv/Scripts/python -m app.cli create-machine RVM-SIM-001 --name Simulator --api-key dev-sim-key-001
.venv/Scripts/python -m app.cli create-admin admin --name "Administrator" --role ADMIN   # prompts for a password
.venv/Scripts/python -m uvicorn app.main:app --port 8000 --reload
```

Admin roles: **VIEWER** (read only), **OPERATOR** (+ resolve alerts, re-check payouts, enable/disable machines),
**ADMIN** (+ users, machine registration and API keys, eligible brands). Five wrong passwords lock an account
for 15 minutes. Set a long random `RVM_JWT_SECRET` in production.

Alerts are evaluated every 15 s: machine offline (no heartbeat for 2 min), machine fault (e-stop, jam, server
unreachable…), bin ≥ 85 % full, payout pending > 10 min (all close themselves), and a paid bottle that went back
to the customer (needs an operator to resolve).

API docs: http://127.0.0.1:8000/docs. Tests need a `rvm_test` database
(set `RVM_TEST_DATABASE_URL` in `.env`; tests drop and recreate all tables there):
`.venv/Scripts/python -m pytest -q`.

The mock payout provider is controlled by the UPI ID: `fail*@...` fails, `slow*@...` succeeds after 3 s,
`pending*@...` stays pending, `invalid*@...` fails validation.

## Full stack in development

One command (opens 4 windows and the browser):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-dev.ps1
```

Or by hand, one terminal each:

```bash
cd backend && .venv/Scripts/python -m uvicorn app.main:app --port 8000          # API, http://127.0.0.1:8000/docs
cd machine && .venv/Scripts/python -m rvm.main --config config/machine.dev.yaml # PLC simulator + kiosk API :8765
cd kiosk && npm install && npm run dev                                           # http://localhost:5173
cd admin && npm install && npm run dev                                           # http://localhost:5174 (admin user from create-admin)
```

In the kiosk, the **DEV** button (bottom right, simulation only) inserts test bottles, simulates a UPI QR
scan or spoken number, presses the e-stop, and refreshes test QR codes.
Without a browser: `cd machine && .venv/Scripts/python tools/kiosk_smoke.py --bottles 13`.

Voice input uses the browser Web Speech API (Chrome, needs internet). For the offline machine this will be
replaced by on-device speech-to-text (Vosk / faster-whisper) behind the same screen.

## Key design rules

- The **central backend** makes every money and QR decision. The machine only asks.
- A refund QR is **reserved** during a session and **consumed** only when the bottle is physically in the bin.
- The bottle waits in the holding chamber until the payout is final. Failed payout → bottle returned.
  Pending after the wait time → bottle accepted and the server keeps reconciling (configurable).
- Any PLC fault → `OUT_OF_SERVICE`. After recovery, a leftover bottle goes to the bin if paid, otherwise back to the customer.
- If the central server is unreachable for 2 health checks, the machine closes the inlet and goes `OUT_OF_SERVICE`
  until it is back. Every session is also written to a local SQLite log (`machine/data/sessions.db`).
- QR format is a **test format** (`machine/rvm/services/qr_codec.py`) until TASMAC shares the real one.
