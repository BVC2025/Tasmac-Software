"""Local session log (SQLite) - the machine's own audit trail.

Kept on the industrial PC even when the central server is unreachable, so
every bottle interaction can be traced locally (field service, disputes).
One row per session (customer batch); the bottles of the batch are stored as JSON.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class SessionLog:
    def __init__(self, path: str | Path):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path))
        self._db.execute(
            """CREATE TABLE IF NOT EXISTS batch_sessions (
                id TEXT PRIMARY KEY, started_at TEXT, ended_at TEXT, outcome TEXT, reason TEXT,
                bottles TEXT, accepted INTEGER, amount_paise INTEGER, destination TEXT,
                input_source TEXT, sms TEXT, txn_id TEXT, payout_status TEXT)"""
        )
        self._db.commit()

    def record(self, s) -> None:
        """`s` is an orchestrator Session."""
        bottles = [
            {"lane": b.lane, "step": b.step.value, "reason": b.reason, "refund_qr": b.refund_qr,
             "mfg_qr": b.mfg_qr, "frames": len(b.frames), "amount_paise": b.amount_paise}
            for b in sorted(s.bottles.values(), key=lambda b: b.lane)
        ]
        accepted = [b for b in bottles if b["step"] == "ACCEPTED"]
        self._db.execute(
            "INSERT OR REPLACE INTO batch_sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (s.id, s.started_at, datetime.now(timezone.utc).isoformat(), s.outcome, s.reason,
             json.dumps(bottles), len(accepted), sum(b["amount_paise"] for b in accepted),
             s.destination.masked() if s.destination else None, s.input_source,
             ("XXXXXX" + s.sms_mobile[-4:]) if s.sms_mobile else None, s.txn_id,
             s.payout_status.value if s.payout_status else None),
        )
        self._db.commit()

    def recent(self, limit: int = 20) -> list[dict]:
        cur = self._db.execute("SELECT * FROM batch_sessions ORDER BY started_at DESC LIMIT ?", (limit,))
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        for r in rows:
            r["bottles"] = json.loads(r["bottles"] or "[]")
        return rows

    def count(self) -> int:
        return self._db.execute("SELECT COUNT(*) FROM batch_sessions").fetchone()[0]
