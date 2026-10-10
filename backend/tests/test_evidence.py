"""Photos of bottles the camera rejected: uploaded by the machine, viewed in the admin portal."""

import base64

API = "/api/admin/v1"
JPEG = b"\xff\xd8\xff\xe0" + b"fake-jpeg-body" * 10


def body(image: bytes = JPEG, **kw) -> dict:
    return {"reason": "BOTTLE_DAMAGED", "content_type": "image/jpeg", "box": [0.4, 0.4, 0.2, 0.2],
            "image_b64": base64.b64encode(image).decode(), **kw}


async def test_machine_uploads_and_admin_views(machine, client, viewer_h):
    await machine.post("/sessions/s1/bottles/1/rejected", {"reason": "BOTTLE_DAMAGED"})
    assert (await machine.post("/sessions/s1/bottles/1/evidence", body())).status_code == 204

    sessions = (await client.get(f"{API}/sessions", headers=viewer_h)).json()
    assert sessions[0]["bottles"][0]["evidence"] is True

    r = await client.get(f"{API}/sessions/s1/bottles/1/evidence", headers=viewer_h)
    assert r.status_code == 200 and r.content == JPEG and r.headers["content-type"] == "image/jpeg"
    assert r.headers["x-evidence-reason"] == "BOTTLE_DAMAGED"
    assert (await client.get(f"{API}/sessions/s1/bottles/2/evidence", headers=viewer_h)).status_code == 404
    assert (await client.get(f"{API}/sessions/s1/bottles/1/evidence")).status_code == 401   # login needed


async def test_resend_replaces_and_bad_images_refused(machine, client, viewer_h):
    assert (await machine.post("/sessions/s1/bottles/1/evidence", body())).status_code == 204
    newer = JPEG + b"v2"
    assert (await machine.post("/sessions/s1/bottles/1/evidence", body(newer))).status_code == 204
    assert (await client.get(f"{API}/sessions/s1/bottles/1/evidence", headers=viewer_h)).content == newer

    assert (await machine.post("/sessions/s1/bottles/1/evidence", body(b"GIF89a..."))).status_code == 422
    bad = body()
    bad["image_b64"] = "@@not-base64@@"
    assert (await machine.post("/sessions/s1/bottles/1/evidence", bad)).status_code == 422
    assert (await machine.post("/sessions/s1/bottles/9/evidence", body())).status_code == 422
