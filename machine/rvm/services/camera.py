"""Real camera + QR decoding (OpenCV + zxing-cpp).

Works with any camera OpenCV can open:
  * a USB / laptop webcam, or a phone through DroidCam / Iriun (shows up as a webcam): device index 0, 1, ...
  * a network stream, e.g. DroidCam over Wi-Fi: "http://<phone-ip>:4747/video"
  * a recorded video file (plays in a loop) - handy for repeatable demos and tests
  * later the industrial lane cameras (if they expose a UVC / RTSP stream)

One reader thread per source keeps only the newest frame, so a slow consumer never
sees stale, buffered images. Several lanes can share one source.
"""

import asyncio
import logging
import threading
import time
from dataclasses import dataclass

from .vision import Camera, Frame, QRReader

log = logging.getLogger(__name__)

try:  # optional: only needed with vision_driver = camera / for image decoding
    import cv2
    import zxingcpp
except ImportError:  # pragma: no cover - mock mode works without them
    cv2 = zxingcpp = None


def _require() -> None:
    if cv2 is None or zxingcpp is None:
        raise RuntimeError("Camera mode needs: pip install opencv-python-headless zxing-cpp")


@dataclass
class Code:
    text: str
    format: str
    box: list[tuple[int, int]]   # 4 corners in image pixels


def decode_image(image) -> list[Code]:
    """All QR / DataMatrix codes in a BGR or grayscale numpy image."""
    _require()
    formats = (zxingcpp.BarcodeFormat.QRCode, zxingcpp.BarcodeFormat.MicroQRCode, zxingcpp.BarcodeFormat.DataMatrix)
    out = []
    for r in zxingcpp.read_barcodes(image, formats=formats):
        if not r.valid or not r.text:
            continue
        p = r.position
        box = [(p.top_left.x, p.top_left.y), (p.top_right.x, p.top_right.y),
               (p.bottom_right.x, p.bottom_right.y), (p.bottom_left.x, p.bottom_left.y)]
        out.append(Code(text=r.text, format=str(r.format).split(".")[-1], box=box))
    return out


def decode_bytes(data: bytes) -> list[Code]:
    """Decode an uploaded image file (JPEG / PNG / ...)."""
    _require()
    import numpy as np

    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Not an image")
    codes = decode_image(img)
    if not codes and max(img.shape[:2]) > 1600:
        # large phone photos: a smaller copy is often easier for the detector
        scale = 1600 / max(img.shape[:2])
        codes = decode_image(cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA))
    return codes


class CameraSource:
    """Background reader for one camera / stream; keeps the latest frame."""

    def __init__(self, source: int | str, width: int, height: int, backend: str):
        _require()
        self.source = source
        self.width, self.height, self.backend = width, height, backend
        self._frame = None
        self._frame_at = 0.0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.connected = False
        self.error: str | None = None
        self.fps = 0.0

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name=f"camera-{self.source}", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def latest(self):
        """(frame copy or None, age in seconds)."""
        with self._lock:
            if self._frame is None:
                return None, None
            return self._frame.copy(), time.monotonic() - self._frame_at

    def _open(self):
        api = {"dshow": cv2.CAP_DSHOW, "msmf": cv2.CAP_MSMF}.get(self.backend, cv2.CAP_ANY)
        cap = cv2.VideoCapture(self.source, api) if isinstance(self.source, int) else cv2.VideoCapture(self.source)
        if isinstance(self.source, int):
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def _run(self) -> None:
        while not self._stop.is_set():
            cap = self._open()
            if not cap.isOpened():
                self.connected, self.error = False, f"Cannot open camera {self.source!r}"
                log.warning("%s - retrying in 3 s", self.error)
                cap.release()
                self._stop.wait(3)
                continue
            log.info("Camera %r opened", self.source)
            self.connected, self.error = True, None
            # a recorded video file plays at its own speed and loops (live cameras pace themselves)
            is_file = isinstance(self.source, str) and "://" not in self.source
            file_delay = 1 / (cap.get(cv2.CAP_PROP_FPS) or 15) if is_file else 0
            n, t0 = 0, time.monotonic()
            while not self._stop.is_set():
                ok, frame = cap.read()
                if is_file and not ok:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ok, frame = cap.read()
                if file_delay:
                    self._stop.wait(file_delay)
                if not ok or frame is None:
                    self.connected, self.error = False, f"Camera {self.source!r} stopped sending frames"
                    log.warning("%s - reconnecting", self.error)
                    break
                with self._lock:
                    self._frame, self._frame_at = frame, time.monotonic()
                n += 1
                if n == 30:
                    self.fps, n, t0 = 30 / max(time.monotonic() - t0, 1e-6), 0, time.monotonic()
            cap.release()
            self._stop.wait(1)


class OpenCVCamera(Camera):
    """Camera per lane; lanes without their own source share the first one."""

    def __init__(self, sources: dict[int, int | str], width: int = 1280, height: int = 720,
                 frame_interval_s: float = 0.35, backend: str = "auto"):
        _require()
        if not sources:
            raise ValueError("camera.sources is empty")
        by_source: dict[int | str, CameraSource] = {}
        self.lanes: dict[int, CameraSource] = {}
        for lane, src in sorted(sources.items()):
            if src not in by_source:
                by_source[src] = CameraSource(src, width, height, backend)
            self.lanes[lane] = by_source[src]
        self._default = self.lanes[min(self.lanes)]
        self.sources = list(by_source.values())
        self.frame_interval_s = frame_interval_s

    def start(self) -> None:
        for s in self.sources:
            s.start()

    def stop(self) -> None:
        for s in self.sources:
            s.stop()

    def source(self, lane: int) -> CameraSource:
        return self.lanes.get(lane, self._default)

    async def capture(self, lane: int, angle_index: int) -> Frame:
        # give the rollers (or, in a demo, the person holding the bottle) time to turn it
        await asyncio.sleep(self.frame_interval_s)
        image, _ = self.source(lane).latest()
        return Frame(lane=lane, angle_index=angle_index, image=image)


class ZxingQRReader(QRReader):
    async def decode(self, frame: Frame) -> list[str]:
        if frame.image is None:
            return []
        codes = await asyncio.to_thread(decode_image, frame.image)
        return [c.text for c in codes]
