"""Real (non test-format) bottle QRs: seen as unknown, registered by an operator, then accepted once."""

from .conftest import mfg_qr, refund_qr

REAL_REFUND = "https://tasmac.example/r?id=A1B2C3D4E5"
REAL_MFG = "8901234567890|KF|BATCH77|SN000123"


async def register(client, h, raw: str, kind: str, brand: str | None = None):
    return await client.post("/api/admin/v1/qr-codes", headers=h,
                             json={"raw": raw, "kind": kind, "brand": brand, "label": "demo bottle"})


async def test_unknown_codes_are_recorded(machine, client, admin_h):
    r = await machine.post("/qr/classify", {"codes": [REAL_REFUND, refund_qr(), mfg_qr(), REAL_REFUND]})
    kinds = r.json()["kinds"]
    assert kinds[REAL_REFUND] is None
    assert sorted(v for v in kinds.values() if v) == ["mfg", "refund"]
    await machine.post("/qr/classify", {"codes": [REAL_REFUND]})
    rows = (await client.get("/api/admin/v1/qr-codes?status=unknown", headers=admin_h)).json()
    assert [(x["raw"], x["seen_count"], x["last_machine_id"]) for x in rows] == [(REAL_REFUND, 2, "RVM-T1")]


async def test_unregistered_real_qr_is_rejected(machine):
    v = (await machine.post("/sessions/s1/refund-qr", {"raw": REAL_REFUND})).json()
    assert v == {"ok": False, "reason": "REFUND_QR_INVALID_FORMAT", "data": {}}


async def test_registered_real_bottle_is_refunded_once(machine, client, operator_h):
    await machine.post("/qr/classify", {"codes": [REAL_REFUND]})          # seen first, registered later
    assert (await register(client, operator_h, REAL_REFUND, "refund")).status_code == 201
    assert (await register(client, operator_h, REAL_MFG, "mfg", "kf")).status_code == 201
    kinds = (await machine.post("/qr/classify", {"codes": [REAL_REFUND, REAL_MFG]})).json()["kinds"]
    assert kinds == {REAL_REFUND: "refund", REAL_MFG: "mfg"}

    assert (await machine.post("/sessions/s1/refund-qr", {"raw": REAL_REFUND})).json()["ok"]
    assert (await machine.post("/sessions/s1/mfg-qr", {"raw": REAL_MFG})).json()["data"]["brand"] == "KF"
    txn = await machine.full_refund("s1", REAL_REFUND, REAL_MFG)
    assert txn["status"] == "SUCCESS"
    await machine.post("/sessions/s1/accepted", {"txn_id": txn["id"]})

    again = (await machine.post("/sessions/s2/refund-qr", {"raw": REAL_REFUND})).json()
    assert again["reason"] == "REFUND_QR_ALREADY_USED"


async def test_disabled_qr_is_not_accepted(machine, client, operator_h):
    row = (await register(client, operator_h, REAL_REFUND, "refund")).json()
    r = await client.patch(f"/api/admin/v1/qr-codes/{row['code_hash']}", headers=operator_h, json={"active": False})
    assert r.json()["active"] is False
    v = (await machine.post("/sessions/s1/refund-qr", {"raw": REAL_REFUND})).json()
    assert v["reason"] == "REFUND_QR_INVALID_FORMAT"


async def test_registration_rules(client, operator_h, viewer_h):
    assert (await register(client, viewer_h, REAL_REFUND, "refund")).status_code == 403
    assert (await register(client, operator_h, REAL_MFG, "mfg")).status_code == 422           # no brand
    assert (await register(client, operator_h, REAL_MFG, "mfg", "NOPE")).status_code == 422   # unknown brand
    assert (await register(client, operator_h, refund_qr(), "refund")).status_code == 409    # test format
    assert (await register(client, operator_h, REAL_REFUND, "refund")).status_code == 201
    assert (await register(client, operator_h, REAL_REFUND, "mfg", "KF")).status_code == 409  # already registered


async def test_lookup_without_recording(machine, client, admin_h):
    kinds = (await machine.post("/qr/classify", {"codes": [REAL_REFUND], "record": False})).json()["kinds"]
    assert kinds == {REAL_REFUND: None}
    assert (await client.get("/api/admin/v1/qr-codes?status=all", headers=admin_h)).json() == []


async def test_product_barcode_is_shared_by_every_bottle(machine, client, operator_h):
    """The EAN on the label is the same on every bottle: the refund QR alone makes a bottle unique."""
    ean = "8902212000545"
    r1, r2 = "058880726627532399", "058880726627532400"
    for raw in (r1, r2):
        assert (await register(client, operator_h, raw, "refund")).status_code == 201
    assert (await register(client, operator_h, ean, "product", "KF")).status_code == 201
    kinds = (await machine.post("/qr/classify", {"codes": [r1, ean]})).json()["kinds"]
    assert kinds == {r1: "refund", ean: "mfg"}

    for sid, refund in (("s1", r1), ("s2", r2)):
        assert (await machine.post(f"/sessions/{sid}/mfg-qr", {"raw": ean})).json()["ok"]
        txn = await machine.full_refund(sid, refund, ean)
        assert txn["status"] == "SUCCESS"
        await machine.post(f"/sessions/{sid}/accepted", {"txn_id": txn["id"]})

    again = (await machine.post("/sessions/s3/eligibility", {"refund_raw": r1, "mfg_raw": ean})).json()
    assert again["reason"] == "REFUND_QR_ALREADY_USED"
