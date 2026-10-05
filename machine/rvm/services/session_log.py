"""Local session log (SQLite) - the machine's own audit trail.

Kept on the industrial PC even when the central server is unreachable, so
every bottle interaction can be traced locally (field service, disputes).
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class SessionLog:
    def __init__(self, path: str | Path):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path))
        self._db.execute(
            """CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY, started_at TEXT, ended_at TEXT, outcome TEXT, reason TEXT,
                refund_qr TEXT, mfg_qr TEXT, destination TEXT, input_source TEXT, sms TEXT,
                txn_id TEXT, payout_status TEXT, frames INTEGER)"""
        )
        self._db.commit()

    def record(self, s) -> None:
        """`s` is an orchestrator Session."""
        self._db.execute(
            "INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (s.id, s.started_at, datetime.now(timezone.utc).isoformat(), s.outcome, s.reason,
             s.refund_qr, s.mfg_qr, s.destination.masked() if s.destination else None, s.input_source,
             ("XXXXXX" + s.sms_mobile[-4:]) if s.sms_mobile else None, s.txn_id,
             s.payout_status.value if s.payout_status else None, len(s.frames)),
        )
        self._db.commit()

    def recent(self, limit: int = 20) -> list[dict]:
        cur = self._db.execute("SELECT * FROM sessions ORDER BY started_at DESC LIMIT ?", (limit,))
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def count(self) -> int:
        return self._db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
