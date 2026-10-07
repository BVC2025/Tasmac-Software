"""Find the camera (webcam / DroidCam / Iriun) and check that it reads bottle QRs.

    python tools/camera_check.py                     # list cameras 0..5
    python tools/camera_check.py --source 1          # read QRs live from camera 1 for 30 s
    python tools/camera_check.py --source http://192.168.1.20:4747/video
    python tools/camera_check.py --source 1 --save   # also save a snapshot to data/camera_check.jpg

Put the working source in config/machine.camera.yaml -> camera.sources.
"""

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402

from rvm.services.camera import decode_image  # noqa: E402
from rvm.services.qr_codec import classify  # noqa: E402

APIS = {"auto": cv2.CAP_ANY, "dshow": cv2.CAP_DSHOW, "msmf": cv2.CAP_MSMF}


def open_source(src: str, api: str):
    if src.isdigit():
        cap = cv2.VideoCapture(int(src), APIS[api])
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        return cap
    return cv2.VideoCapture(src)


def list_cameras(api: str) -> None:
    print(f"Looking for cameras (backend {api}) ...")
    found = 0
    for i in range(6):
        cap = open_source(str(i), api)
        ok, frame = cap.read() if cap.isOpened() else (False, None)
        if ok and frame is not None:
            found += 1
            print(f"  [{i}] OK  {frame.shape[1]}x{frame.shape[0]}")
        cap.release()
    if not found:
        print("  none found. DroidCam: start the phone app + the PC client (Start), then retry.")
    else:
        print("Next: python tools/camera_check.py --source <index>   (the phone is usually the last one)")


def live(src: str, api: str, seconds: float, save: bool) -> None:
    cap = open_source(src, api)
    if not cap.isOpened():
        hint = ("Is DroidCam \"Busy\"? Stop the DroidCam PC client - the phone serves one connection at a time."
                if "://" in src else "Try --api msmf or --api auto, and check that the camera is started.")
        sys.exit(f"Cannot open camera {src!r}. {hint}")
    print(f"Reading QRs from {src!r} for {seconds:.0f} s - hold a bottle QR in front of the camera ...")
    seen: dict[str, int] = {}
    end = time.monotonic() + seconds
    frames = 0
    while time.monotonic() < end:
        ok, frame = cap.read()
        if not ok:
            print("  camera stopped sending frames")
            break
        frames += 1
        if save and frames == 10:
            out = ROOT / "data" / "camera_check.jpg"
            out.parent.mkdir(exist_ok=True)
            cv2.imwrite(str(out), frame)
            print(f"  snapshot saved: {out}")
        for c in decode_image(frame):
            if c.text not in seen:
                kind = classify(c.text) or "unknown (register it in Admin -> QR registry)"
                print(f"  NEW {c.format}: {c.text}\n      kind: {kind}")
            seen[c.text] = seen.get(c.text, 0) + 1
    cap.release()
    print(f"Done: {frames} frames, {len(seen)} different codes.")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source", help="camera index (0, 1, ...) or stream URL")
    p.add_argument("--api", choices=list(APIS), default="dshow" if sys.platform == "win32" else "auto")
    p.add_argument("--seconds", type=float, default=30)
    p.add_argument("--save", action="store_true")
    a = p.parse_args()
    if a.source is None:
        list_cameras(a.api)
    else:
        live(a.source, a.api, a.seconds, a.save)


if __name__ == "__main__":
    main()
