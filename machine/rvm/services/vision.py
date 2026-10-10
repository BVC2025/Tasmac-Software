"""Camera, bottle inspection and QR decoding.

Interfaces + mock implementations. Real implementations (industrial
camera SDK, YOLO/ONNX model, zxing-cpp) plug in here in the vision phase.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from .sim_feed import SimBottleFeed


@dataclass
class Frame:
    lane: int
    angle_index: int
    image: Any = None  # numpy array in the real implementation


@dataclass
class InspectionResult:
    ok: bool
    reason: str = ""           # e.g. DAMAGED, FOREIGN_OBJECT
    confidence: float = 1.0
    details: dict = field(default_factory=dict)


class Camera(ABC):
    """One camera per lane (multi-channel machine); `lane` selects it."""

    @abstractmethod
    async def capture(self, lane: int, angle_index: int) -> Frame: ...


class BottleInspector(ABC):
    @abstractmethod
    async def inspect(self, lane: int, frames: list[Frame]) -> InspectionResult: ...


class QRReader(ABC):
    @abstractmethod
    async def decode(self, frame: Frame) -> list[str]:
        """Return all QR payloads readable in this frame."""


# ---------------- mocks (driven by the simulated bottle feed) ----------------


class MockCamera(Camera):
    async def capture(self, lane: int, angle_index: int) -> Frame:
        return Frame(lane=lane, angle_index=angle_index)


class MockInspector(BottleInspector):
    def __init__(self, feed: SimBottleFeed):
        self.feed = feed

    async def inspect(self, lane: int, frames: list[Frame]) -> InspectionResult:
        cond = self.feed.at(lane).condition
        if cond == "ok":
            return InspectionResult(ok=True, confidence=0.97)
        # where the damage is (normalised x, y, w, h) and in which frame, as a real model would report it
        details = {"box": [0.395, 0.488, 0.221, 0.209], "frame": 1} if cond == "damaged" else {"frame": 0}
        return InspectionResult(ok=False, reason=cond.upper(), confidence=0.93, details=details)


class MockQRReader(QRReader):
    def __init__(self, feed: SimBottleFeed, angles_per_turn: int):
        self.feed = feed
        self.angles_per_turn = angles_per_turn

    async def decode(self, frame: Frame) -> list[str]:
        b = self.feed.at(frame.lane)
        angle = frame.angle_index % self.angles_per_turn
        codes = []
        if b.refund_qr and angle == b.refund_angle:
            codes.append(b.refund_qr)
        if b.mfg_qr and angle == b.mfg_angle:
            codes.append(b.mfg_qr)
        return codes
