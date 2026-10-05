"""API used by the RVM machines. Auth: X-Machine-Id + X-Api-Key headers."""

from dataclasses import asdict

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from .. import services as svc
from ..db import get_db
from ..models import Machine
from ..schemas import (
    AcceptedIn, DestinationIn, EligibilityIn, HeartbeatIn, QRIn, ReturnedIn, TransactionIn, TxnOut, VerdictOut,
)
from ..security import current_machine

router = APIRouter(prefix="/api/machine/v1", tags=["machine"])


@router.post("/heartbeat", status_code=204)
async def heartbeat(body: HeartbeatIn, m: Machine = Depends(current_machine), db: AsyncSession = Depends(get_db)):
    await svc.heartbeat(db, m, body.state, body.bin_fill_pct, body.software_version, body.fault_reason)


@router.post("/sessions/{session_id}/refund-qr", response_model=VerdictOut)
async def refund_qr(session_id: str, body: QRIn, m: Machine = Depends(current_machine),
                    db: AsyncSession = Depends(get_db)):
    return asdict(await svc.verify_refund_qr(db, m, session_id, body.raw))


@router.post("/sessions/{session_id}/mfg-qr", response_model=VerdictOut)
async def mfg_qr(session_id: str, body: QRIn, m: Machine = Depends(current_machine),
                 db: AsyncSession = Depends(get_db)):
    return asdict(await svc.verify_mfg_qr(db, m, session_id, body.raw))


@router.post("/sessions/{session_id}/eligibility", response_model=VerdictOut)
async def eligibility(session_id: str, body: EligibilityIn, m: Machine = Depends(current_machine),
                      db: AsyncSession = Depends(get_db)):
    return asdict(await svc.check_eligibility(db, m, session_id, body.refund_raw, body.mfg_raw))


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
