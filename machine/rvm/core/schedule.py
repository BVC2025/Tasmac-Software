"""Service hours: when the machine takes bottles (India time).

Windows repeat every day. A window whose end is before its start runs past
midnight (22:00-02:00). No windows means open 24 hours.
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


@dataclass(frozen=True)
class Window:
    start: time
    end: time

    def contains(self, t: time) -> bool:
        if self.start < self.end:
            return self.start <= t < self.end
        return t >= self.start or t < self.end   # past midnight

    def as_dict(self) -> dict:
        return {"start": self.start.strftime("%H:%M"), "end": self.end.strftime("%H:%M")}


def _parse(hhmm: str) -> time:
    h, m = hhmm.strip().split(":")
    return time(int(h), int(m))


class ServiceHours:
    def __init__(self, windows: list[dict] | None = None):
        self.windows: list[Window] = []
        for w in windows or []:
            start, end = _parse(w["start"]), _parse(w["end"])
            if start != end:
                self.windows.append(Window(start, end))

    @property
    def always_open(self) -> bool:
        return not self.windows

    def as_list(self) -> list[dict]:
        return [w.as_dict() for w in self.windows]

    def is_open(self, now: datetime | None = None) -> bool:
        if self.always_open:
            return True
        t = (now or datetime.now(IST)).astimezone(IST).time().replace(second=0, microsecond=0)
        return any(w.contains(t) for w in self.windows)

    def next_open(self, now: datetime | None = None) -> datetime | None:
        """Next time the machine opens (None when it is open now or always open)."""
        now = (now or datetime.now(IST)).astimezone(IST)
        if self.is_open(now):
            return None
        starts = []
        for day in (0, 1):
            d = (now + timedelta(days=day)).date()
            for w in self.windows:
                at = datetime.combine(d, w.start, IST)
                if at > now:
                    starts.append(at)
        return min(starts) if starts else None

    def __eq__(self, other: object) -> bool:
        return isinstance(other, ServiceHours) and self.as_list() == other.as_list()


class ServiceHoursStore:
    """Remembers the last service hours from the server, so they apply offline and after a restart."""

    def __init__(self, path: str | None):
        self.path = Path(path) if path else None

    def load(self) -> list[dict] | None:
        if not self.path or not self.path.exists():
            return None
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            log.warning("Ignoring unreadable %s: %s", self.path, e)
            return None

    def save(self, windows: list[dict]) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(windows), encoding="utf-8")
