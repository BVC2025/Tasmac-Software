"""Test bottle feed for simulation.

Describes the bottles a simulated customer inserts, so mock camera,
vision, QR reader, customer and backend all agree on "the bottle that is
in the machine right now".
"""

import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

from . import qr_codec


@dataclass
class SimBottle:
    name: str
    condition: Literal["ok", "damaged", "foreign"] = "ok"
    refund_qr: str | None = None
    mfg_qr: str | None = None
    refund_angle: int = 0                  # inspection frame where the QR is readable
    mfg_angle: int = 2
    destination: str | None = "test@upi"   # UPI ID or 10-digit mobile; None = customer walks away
    payout: Literal["success", "pending_then_success", "pending", "failed"] = "success"


class SimBottleFeed:
    def __init__(self, bottles: list[SimBottle]):
        if not bottles:
            raise ValueError("Bottle feed is empty")
        self.bottles = bottles
        self._index = -1
        self._in_lane: dict[int, SimBottle] = {}   # bottle currently inside each lane
        self._last: SimBottle | None = None

    @classmethod
    def from_yaml(cls, path: str | Path) -> "SimBottleFeed":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or []
        return cls([SimBottle(**b) for b in data])

    def select_next(self, name: str) -> None:
        """Make `name` the bottle returned by the next advance()."""
        for i, b in enumerate(self.bottles):
            if b.name == name:
                self._index = i - 1
                return
        raise KeyError(name)

    def set_custom(self, bottle: SimBottle) -> None:
        """Add (or replace) the DEV-panel bottle with QR codes typed / uploaded by the tester."""
        for i, b in enumerate(self.bottles):
            if b.name == bottle.name:
                self.bottles[i] = bottle   # a bottle already inside a lane keeps its old object
                return
        self.bottles.append(bottle)

    def refresh_serials(self, secret: str) -> None:
        """Give every test bottle new QR serials (same scenario, same signature validity).

        The backend remembers used refund QRs, so a feed can only be paid once.
        Bottles that shared a QR (the "reused" scenario) keep sharing the new one.
        """
        mapping: dict[str, str] = {}

        def fresh(raw: str | None) -> str | None:
            if raw is None:
                return None
            if raw not in mapping:
                valid = qr_codec.verify_signature(secret, raw)
                n = f"{secrets.randbelow(10**10):010d}"
                if raw.startswith(qr_codec.REFUND_PREFIX + "."):
                    new = qr_codec.make_refund_qr(secret, "R" + n)
                else:
                    brand, batch = raw.split(".")[1:3]
                    new = qr_codec.make_mfg_qr(secret, brand, batch, "M" + n)
                mapping[raw] = new if valid else new[:-4] + "0000"
            return mapping[raw]

        for b in self.bottles:
            b.refund_qr, b.mfg_qr = fresh(b.refund_qr), fresh(b.mfg_qr)

    def advance(self, lane: int = 1) -> None:
        """A bottle was inserted into `lane`: it becomes the next bottle of the feed."""
        self._index = (self._index + 1) % len(self.bottles)
        self._last = self.bottles[self._index]
        self._in_lane[lane] = self._last

    def at(self, lane: int) -> SimBottle:
        """The bottle currently in a lane."""
        return self._in_lane.get(lane) or self.current

    @property
    def current(self) -> SimBottle:
        """The most recently inserted bottle."""
        return self._last or self.bottles[max(self._index, 0)]
