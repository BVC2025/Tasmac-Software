"""API used by the RVM machines. Auth: X-Machine-Id + X-Api-Key headers."""

import base64
import binascii
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from .. import services as svc
from ..db import get_db
from ..models import Machine
from ..schemas import (
    AcceptedIn, BottleRejectedIn, ClassifyIn, EvidenceIn, DestinationIn, EligibilityIn, HeartbeatIn, QRIn, ReturnedIn, TransactionIn, TxnOut,
    VerdictOut,
)
from ..security import current_machine

router = APIRouter(prefix="/api/machine/v1", tags=["machine"])


@router.post("/heartbeat")
async def heartbeat(body: HeartbeatIn, m: Machine = Depends(current_machine), db: AsyncSession = Depends(get_db)):
    """Status in; settings out (the machine keeps the last ones it got, for offline use)."""
    await svc.heartbeat(db, m, body.state, body.bin_fill_pct, body.software_version, body.fault_reason)
    return {"service_hours": m.service_hours}


@router.post("/qr/classify")
async def classify_qr(body: ClassifyIn, m: Machine = Depends(current_machine), db: AsyncSession = Depends(get_db)):
    """Which of the codes read from a bottle is its refund / manufacturing QR."""
    codes = [c[:512] for c in body.codes]
    return {"kinds": await svc.classify_codes(db, m, codes, body.record)}


@router.post("/sessions/{session_id}/refund-qr", response_model=VerdictOut)
async def refund_qr(session_id: str, body: QRIn, m: Machine = Depends(current_machine),
                    db: AsyncSession = Depends(get_db)):
    return asdict(await svc.verify_refund_qr(db, m, session_id, body.raw, body.lane))


@router.post("/sessions/{session_id}/mfg-qr", response_model=VerdictOut)
async def mfg_qr(session_id: str, body: QRIn, m: Machine = Depends(current_machine),
                 db: AsyncSession = Depends(get_db)):
    return asdict(await svc.verify_mfg_qr(db, m, session_id, body.raw, body.lane))


@router.post("/sessions/{session_id}/eligibility", response_model=VerdictOut)
async def eligibility(session_id: str, body: EligibilityIn, m: Machine = Depends(current_machine),
                      db: AsyncSession = Depends(get_db)):
    return asdict(await svc.check_eligibility(db, m, session_id, body.refund_raw, body.mfg_raw, body.lane))


@router.post("/sessions/{session_id}/bottles/{lane}/rejected", status_code=204)
async def bottle_rejected(session_id: str, lane: int, body: BottleRejectedIn, m: Machine = Depends(current_machine),
                          db: AsyncSession = Depends(get_db)):
    await svc.bottle_rejected(db, m, session_id, lane, body.reason)


@router.post("/sessions/{session_id}/bottles/{lane}/evidence", status_code=204)
async def bottle_evidence(session_id: str, lane: int, body: EvidenceIn, m: Machine = Depends(current_machine),
                          db: AsyncSession = Depends(get_db)):
    """Photo of a bottle the camera rejected (proof shown in the admin portal)."""
    try:
        image = base64.b64decode(body.image_b64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(422, "image_b64 is not valid base64")
    magic = {"image/jpeg": b"\xff\xd8\xff", "image/png": b"\x89PNG"}[body.content_type]
    if not image.startswith(magic):
        raise HTTPException(422, "Not a JPEG / PNG image")
    if not 1 <= lane <= 3:
        raise HTTPException(422, "Invalid lane")
    await svc.store_evidence(db, m, session_id, lane, body.reason, body.content_type, image, body.box)


@router.post("/sessions/{session_id}/destination", response_model=VerdictOut)
async def destination(session_id: str, body: DestinationIn, m: Machine = Depends(current_machine)):
    return asdict(await svc.validate_destination(body.kind, body.value))


@router.post("/sessions/{session_id}/transaction", response_model=TxnOut)
async def create_transaction(session_id: str, body: TransactionIn, m: Machine = Depends(current_machine),
                             db: AsyncSession = Depends(get_db)):
    return await svc.create_transaction(db, m, session_id, body.kind, body.value, body.sms_mobile)


@router.post("/transactions/{txn_id}/payout", response_model=TxnOut)
async def payout(txn_id: str, m: Machine = Depends(current_machine), db: AsyncSession = Depends(get_db)):
    txn = await svc.get_txn_for_machine(db, m, txn_id, lock=True)
    return await svc.request_payout(db, txn)


@router.get("/transactions/{txn_id}", response_model=TxnOut)
async def payout_status(txn_id: str, m: Machine = Depends(current_machine), db: AsyncSession = Depends(get_db)):
    txn = await svc.get_txn_for_machine(db, m, txn_id, lock=True)
    return await svc.refresh_payout(db, txn)


@router.post("/sessions/{session_id}/accepted", status_code=204)
async def accepted(session_id: str, body: AcceptedIn, m: Machine = Depends(current_machine),
                   db: AsyncSession = Depends(get_db)):
    await svc.bottle_accepted(db, m, session_id, body.txn_id)


@router.post("/sessions/{session_id}/returned", status_code=204)
async def returned(session_id: str, body: ReturnedIn, m: Machine = Depends(current_machine),
                   db: AsyncSession = Depends(get_db)):
    await svc.bottle_returned(db, m, session_id, body.reason)
