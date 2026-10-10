"""Evidence photo for bottles the camera rejects: saved, shown on the kiosk, sent to the server."""

import io

import httpx
import numpy as np
from PIL import Image

from rvm.api.server import create_app
from rvm.services.evidence import EvidenceStore, make_evidence
from rvm.services.vision import Frame, InspectionResult

from .conftest import bottle


def test_real_frame_is_used_and_marked():
    frame = np.zeros((480, 640, 3), np.uint8)
    frame[:, :, 2] = 200   # BGR: a red picture
    jpeg = make_evidence([Frame(1, 0, frame)], InspectionResult(False, "DAMAGED", details={"box": [0.1, 0.1, 0.3, 0.3]}),
                         lane=1, simulated=False)
    img = Image.open(io.BytesIO(jpeg))
    assert img.format == "JPEG" and img.size == (640, 480)
    r, g, b = img.convert("RGB").getpixel((320, 200))
    assert r > 150 and b < 80          # the camera frame, colours converted from BGR


def test_simulation_picture_without_camera():
    jpeg = make_evidence([Frame(1, 0)], InspectionResult(False, "DAMAGED", details={"box": [0.4, 0.4, 0.2, 0.2]}),
                         lane=2, simulated=True)
    assert Image.open(io.BytesIO(jpeg)).format == "JPEG"


def test_store_rejects_unsafe_ids(tmp_path):
    s = EvidenceStore(str(tmp_path))
    assert s.path("../../etc", 1) is None
    assert s.save("abc123", 1, b"x").read_bytes() == b"x"


async def test_damaged_bottle_gets_evidence(make_rig, tmp_path):
    async with make_rig([bottle(condition="damaged")], lanes=1) as rig:
        rig.orch.evidence = EvidenceStore(str(tmp_path))
        q = rig.bus.subscribe()
        s = await rig.insert_and_wait(1)
        assert s.reason == "BOTTLE_DAMAGED" and s.bottles[1].evidence
        assert rig.backend.evidence[0][:3] == (s.id, 1, "BOTTLE_DAMAGED")
        rejected = [e for e in iter(q.get_nowait, None) if e.type == "lane" and e.data["step"] == "REJECTED"] \
            if False else []
        while not q.empty():
            e = q.get_nowait()
            if e.type == "lane" and e.data["step"] == "REJECTED":
                rejected.append(e)
        assert rejected[0].data["evidence"] is True and rejected[0].data["session_id"] == s.id

        app = create_app(rig.orch, rig.bus, None, rig.sim, rig.feed, [])
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://k") as k:
            r = await k.get(f"/api/evidence/{s.id}/1")
            assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
            assert (await k.get(f"/api/evidence/{s.id}/2")).status_code == 404


async def test_qr_rejection_has_no_photo(make_rig, tmp_path):
    async with make_rig([bottle(refund_qr=None)], lanes=1) as rig:
        rig.orch.evidence = EvidenceStore(str(tmp_path))
        s = await rig.insert_and_wait(1)
        assert s.reason == "REFUND_QR_NOT_FOUND" and not s.bottles[1].evidence and rig.backend.evidence == []


async def test_all_rejected_session_is_closed_on_the_server(make_rig):
    async with make_rig([bottle(condition="damaged")], lanes=1) as rig:
        returned = []

        async def bottle_returned(sid, reason):
            returned.append((sid, reason))

        rig.backend.bottle_returned = bottle_returned
        s = await rig.insert_and_wait(1)
        assert returned == [(s.id, "BOTTLE_DAMAGED")]
