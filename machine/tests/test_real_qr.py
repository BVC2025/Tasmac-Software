"""Real (non test-format) QRs, camera driver and the QR testing endpoints."""

import asyncio
from pathlib import Path

import httpx
import pytest

from rvm.api.server import create_app
from rvm.core.events import MachineState
from rvm.services.backend import Verdict

from .conftest import bottle

REAL_REFUND = "https://tasmac.example/r?id=A1B2C3"
REAL_MFG = "8901234567890|KF|B77|SN123"
QR_PNG = Path(__file__).resolve().parents[1] / "test_qr" / "01_refund_qr.png"


async def test_unknown_real_qr_is_invalid_format(make_rig):
    async with make_rig([bottle(refund_qr=REAL_REFUND)]) as rig:
        s = await rig.insert_and_wait()
        assert (s.outcome, s.reason) == ("RETURNED", "REFUND_QR_INVALID_FORMAT")


async def test_server_classifies_registered_real_qrs(make_rig):
    async with make_rig([bottle(refund_qr=REAL_REFUND, mfg_qr=REAL_MFG)]) as rig:
        b, seen = rig.backend, []

        async def classify(codes, record=True):
            return {c: {REAL_REFUND: "refund", REAL_MFG: "mfg"}.get(c) for c in codes}

        async def ok(*args, **kw):
            return Verdict(True)

        async def eligible(sid, refund, mfg, lane=1):
            seen.append((refund, mfg))
            b.reservations[(sid, lane)] = ("RS", "MS")   # what the server would reserve
            return Verdict(True, data={"amount_paise": 1000})

        b.classify_qr, b.verify_refund_qr, b.verify_mfg_qr, b.check_eligibility = classify, ok, ok, eligible
        s = await rig.insert_and_wait()
        assert s.outcome == "ACCEPTED", s.reason
        assert seen == [(REAL_REFUND, REAL_MFG)]


async def test_classify_failure_is_backend_unavailable(make_rig):
    async with make_rig([bottle(refund_qr=REAL_REFUND)]) as rig:
        async def broken(codes, record=True):
            raise httpx.ConnectError("down")

        rig.backend.classify_qr = broken
        s = await rig.insert_and_wait()
        assert s.reason == "BACKEND_UNAVAILABLE"


async def test_insert_custom_and_decode_endpoints(make_rig):
    pytest.importorskip("zxingcpp")
    async with make_rig([bottle()], customer_driver="web") as rig:
        app = create_app(rig.orch, rig.bus, rig.orch.customer, rig.sim, rig.feed, [])
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://k") as k:
            codes = (await k.post("/api/qr/decode", content=QR_PNG.read_bytes())).json()["codes"]
            assert len(codes) == 1 and codes[0]["kind"] == "refund" and codes[0]["text"].startswith("TRQ1.")
            assert (await k.post("/api/qr/decode", content=b"not an image")).status_code == 400
            assert (await k.get("/api/camera")).json() == {"enabled": False, "lanes": {}}

            await rig.wait_state(MachineState.READY)
            await asyncio.sleep(0.1)
            r = await k.post("/api/sim/insert-custom", json={"refund_qr": REAL_REFUND, "mfg_qr": REAL_MFG, "lane": 2})
            assert r.json() == {"inserted": True, "lane": 2}
            for _ in range(200):
                if rig.orch.sessions:
                    break
                await asyncio.sleep(0.05)
            s = rig.orch.sessions[-1]
            assert (s.bottles[2].refund_qr, s.reason) == (None, "REFUND_QR_INVALID_FORMAT")


async def test_opencv_camera_reads_qr_from_stream(tmp_path):
    cv2 = pytest.importorskip("cv2")
    from rvm.services.camera import OpenCVCamera, ZxingQRReader

    img = cv2.imread(str(QR_PNG))
    img = cv2.copyMakeBorder(img, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=(255, 255, 255))
    video = tmp_path / "bottle.avi"
    w = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"MJPG"), 10, (img.shape[1], img.shape[0]))
    for _ in range(30):
        w.write(img)
    w.release()

    cam = OpenCVCamera({1: str(video)}, frame_interval_s=0.05)
    cam.start()
    try:
        for _ in range(60):
            if cam.source(3).latest()[0] is not None:   # lane 3 shares the only camera
                break
            await asyncio.sleep(0.05)
        frame = await cam.capture(3, 0)
        assert frame.image is not None
        codes = await ZxingQRReader().decode(frame)
        assert codes and codes[0].startswith("TRQ1.")
    finally:
        cam.stop()
