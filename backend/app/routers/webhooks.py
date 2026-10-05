"""Payout provider webhooks.

Each real provider signs its webhook differently (RazorpayX: HMAC-SHA256 of the
raw body in X-Razorpay-Signature, Cashfree: x-webhook-signature). The generic
endpoint below uses HMAC-SHA256 with RVM_PAYOUT_WEBHOOK_SECRET; provider-specific
parsing is added with the real adapter.
"""

import hashlib
import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import services as svc
from ..config import get_settings
from ..db import get_db
from ..models import Transaction
from ..providers import PayoutResult

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


class PayoutEvent(BaseModel):
    provider_ref: str
    status: str            # PENDING | SUCCESS | FAILED
    failure_reason: str | None = None


@router.post("/payout", status_code=204)
async def payout_webhook(request: Request, x_signature: str = Header(...), db: AsyncSession = Depends(get_db)):
    raw = await request.body()
    expected = hmac.new(get_settings().payout_webhook_secret.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, x_signature):
        raise HTTPException(401, "Bad signature")
    event = PayoutEvent.model_validate_json(raw)
    if event.status not in ("PENDING", "SUCCESS", "FAILED"):
        raise HTTPException(422, "Unknown status")
    txn = (await db.execute(select(Transaction).where(Transaction.provider_ref == event.provider_ref)
                            .with_for_update())).scalar_one_or_none()
    if txn is None:
        raise HTTPException(404, "Unknown reference")
    await svc.apply_payout_result(db, txn, PayoutResult(event.status, event.provider_ref, event.failure_reason),
                                  actor="webhook")
    await db.commit()
