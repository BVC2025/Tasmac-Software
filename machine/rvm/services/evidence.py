"""Evidence photo for a bottle rejected by the camera inspection (damaged / not a bottle).

With a real camera the photo is the inspection frame itself, with the damaged area
boxed in red. In simulation (no camera) a clearly marked SIMULATION picture is drawn,
so it can never be mistaken for a real photo.

The picture is shown to the customer on the kiosk and stored on the server, so every
"bottle damaged" decision has proof.
"""

import io
import logging
import re
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ..core.schedule import IST
from .vision import Frame, InspectionResult

log = logging.getLogger(__name__)

RED = (220, 38, 38)
LABEL = {"DAMAGED": "BOTTLE DAMAGED", "FOREIGN": "NOT AN ACCEPTED BOTTLE"}
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _font(size: int):
    for name in ("arialbd.ttf", "DejaVuSans-Bold.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _frame_image(frames: list[Frame], index: int | None) -> Image.Image | None:
    """The inspection frame as a PIL image (real camera frames are BGR numpy arrays)."""
    usable = [f for f in frames if f.image is not None and hasattr(f.image, "shape")]
    if not usable:
        return None
    f = usable[index] if index is not None and 0 <= index < len(usable) else usable[-1]
    rgb = f.image[:, :, ::-1] if f.image.ndim == 3 else f.image
    return Image.fromarray(rgb).convert("RGB")


def _simulated_bottle(w: int = 640, h: int = 480) -> Image.Image:
    """Stand-in picture for simulation: an amber bottle on a dark background."""
    img = Image.new("RGB", (w, h), (15, 23, 42))
    d = ImageDraw.Draw(img)
    cx = w // 2
    body = [(cx - 14, 40), (cx + 14, 40), (cx + 16, 150), (cx + 70, 215), (cx + 70, 440),
            (cx - 70, 440), (cx - 70, 215), (cx - 16, 150)]
    d.polygon(body, fill=(150, 82, 22))
    d.rectangle([cx - 70, 270, cx + 70, 360], fill=(236, 230, 214))
    d.rectangle([cx - 70, 270, cx + 70, 285], fill=(30, 58, 95))
    d.rectangle([cx - 16, 26, cx + 16, 44], fill=(212, 190, 110))
    d.line([(cx - 48, 225), (cx - 48, 430)], fill=(255, 255, 255), width=6)
    return img


def _draw_crack(d: ImageDraw.ImageDraw, x: int, y: int, bw: int, bh: int) -> None:
    pts = [(x + bw * 0.2, y + bh * 0.1), (x + bw * 0.45, y + bh * 0.4), (x + bw * 0.35, y + bh * 0.6),
           (x + bw * 0.7, y + bh * 0.9)]
    d.line(pts, fill=(255, 255, 255), width=3)
    d.line([(x + bw * 0.45, y + bh * 0.4), (x + bw * 0.8, y + bh * 0.3)], fill=(255, 255, 255), width=2)


def make_evidence(frames: list[Frame], result: InspectionResult, lane: int, simulated: bool) -> bytes:
    """JPEG with the damaged area boxed and a caption (reason, inlet, time)."""
    img = _frame_image(frames, result.details.get("frame"))
    fake = img is None
    if fake:
        img = _simulated_bottle()
    img.thumbnail((960, 960))
    w, h = img.size
    d = ImageDraw.Draw(img)
    box = result.details.get("box")   # normalised [x, y, w, h] of the damaged area, if the inspector found one
    if box:
        x, y, bw, bh = int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)
        if fake:
            _draw_crack(d, x, y, bw, bh)
        d.rectangle([x, y, x + bw, y + bh], outline=RED, width=max(3, w // 160))
    else:
        d.rectangle([2, 2, w - 3, h - 3], outline=RED, width=max(3, w // 160))

    bar = max(34, h // 12)
    d.rectangle([0, h - bar, w, h], fill=(0, 0, 0))
    when = datetime.now(IST).strftime("%d %b %Y %I:%M:%S %p IST")
    text = f"{LABEL.get(result.reason, 'REJECTED')} · inlet {lane} · {when}"
    d.text((10, h - bar + bar // 4), text, fill=(255, 255, 255), font=_font(max(14, bar // 2)))
    if fake or simulated:
        d.text((10, 8), "SIMULATION - NOT A REAL PHOTO", fill=(250, 204, 21), font=_font(max(14, h // 24)))

    out = io.BytesIO()
    img.save(out, "JPEG", quality=82)
    return out.getvalue()


class EvidenceStore:
    """Evidence photos kept on the machine (data/evidence/<session>-<lane>.jpg)."""

    def __init__(self, folder: str | None):
        self.folder = Path(folder) if folder else None

    def path(self, session_id: str, lane: int) -> Path | None:
        if not self.folder or not _SAFE_ID.match(session_id):
            return None
        return self.folder / f"{session_id}-{int(lane)}.jpg"

    def save(self, session_id: str, lane: int, jpeg: bytes) -> Path | None:
        p = self.path(session_id, lane)
        if p is None:
            return None
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(jpeg)
        return p
