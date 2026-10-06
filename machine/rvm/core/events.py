"""Machine states and the event bus (UI / logging / backend sync subscribe here)."""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

log = logging.getLogger(__name__)


class MachineState(str, Enum):
    STARTING = "STARTING"
    HEALTH_CHECK = "HEALTH_CHECK"
    READY = "READY"
    COLLECTING = "COLLECTING"   # first bottle in; short window for bottles in the other inlets
    CHECKING = "CHECKING"       # every lane checks its bottle in parallel (see LaneStep)
    SELECT_REFUND_METHOD = "SELECT_REFUND_METHOD"
    CONFIRMING = "CONFIRMING"
    PAYING = "PAYING"
    ACCEPTING = "ACCEPTING"
    REJECTING = "REJECTING"
    OUT_OF_SERVICE = "OUT_OF_SERVICE"


class LaneStep(str, Enum):
    """Progress of one bottle in one lane (published as "lane" events)."""

    DETECTED = "DETECTED"
    POSITIONING = "POSITIONING"
    INSPECTING = "INSPECTING"
    SCANNING_REFUND_QR = "SCANNING_REFUND_QR"
    SCANNING_MFG_QR = "SCANNING_MFG_QR"
    VERIFYING = "VERIFYING"
    VALID = "VALID"           # eligible, parked in the lane's holding chamber
    REJECTED = "REJECTED"     # handed back at the lane's inlet
    ACCEPTED = "ACCEPTED"     # in the bin after a successful payout
    RETURNED = "RETURNED"     # was valid, handed back (payout failed / cancelled)


@dataclass
class Event:
    type: str                      # state | message | session_started | session_ended | fault
    data: dict[str, Any] = field(default_factory=dict)
    at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class EventBus:
    def __init__(self):
        self._subscribers: list[asyncio.Queue[Event]] = []

    def subscribe(self, maxsize: int = 1000) -> asyncio.Queue[Event]:
        q: asyncio.Queue[Event] = asyncio.Queue(maxsize=maxsize)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[Event]) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)

    def publish(self, type_: str, **data: Any) -> None:
        ev = Event(type_, data)
        for q in self._subscribers:
            if q.full():
                q.get_nowait()  # drop oldest, never block the machine
            q.put_nowait(ev)
