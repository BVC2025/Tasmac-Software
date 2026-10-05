"""Operational alerts.

Automatic alerts (offline, fault, bin full, payout stuck) are opened and closed
by `evaluate_alerts`, which runs in the background loop. Manual alerts (a paid
bottle that went back to the customer) stay open until an operator resolves them.
"""

from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .models import Alert, AlertType, Machine, Transaction, TxnStatus, utcnow

SEVERITY = {
    AlertType.MACHINE_OFFLINE: "critical",
    AlertType.MACHINE_FAULT: "critical",
    AlertType.BIN_FULL: "warning",
    AlertType.PAYOUT_STUCK: "warning",
    AlertType.PAID_BOTTLE_RETURNED: "critical",
}


async def raise_alert(db: AsyncSession, type_: AlertType, entity_id: str, message: str,
                      machine_id: str | None = None, auto: bool = True) -> None:
    """Open an alert unless the same one is already open (partial unique index)."""
    await db.execute(pg_insert(Alert).values(
        type=type_, severity=SEVERITY[type_], entity_id=entity_id, machine_id=machine_id,
        message=message[:255], status="OPEN", auto=auto, created_at=utcnow(),
    ).on_conflict_do_nothing())


async def clear_alert(db: AsyncSession, type_: AlertType, entity_id: str) -> None:
    await db.execute(update(Alert).where(
        Alert.type == type_, Alert.entity_id == entity_id, Alert.status == "OPEN", Alert.auto.is_(True),
    ).values(status="RESOLVED", resolved_at=utcnow(), resolved_by="system", note="Condition cleared"))


async def evaluate_alerts(db: AsyncSession) -> None:
    s = get_settings()
    now = utcnow()
    machines = (await db.execute(select(Machine).where(Machine.active.is_(True)))).scalars().all()
    for m in machines:
        offline = m.last_seen_at is None or m.last_seen_at < now - timedelta(seconds=s.machine_offline_after_s)
        if offline and m.last_seen_at is not None:
            await raise_alert(db, AlertType.MACHINE_OFFLINE, m.id, f"{m.id} has not reported since {m.last_seen_at:%d %b %H:%M} UTC", m.id)
        elif not offline:
            await clear_alert(db, AlertType.MACHINE_OFFLINE, m.id)

        # fault_reason stays set while the machine cycles OUT_OF_SERVICE <-> HEALTH_CHECK retries
        if not offline and (m.fault_reason or m.state == "OUT_OF_SERVICE"):
            await raise_alert(db, AlertType.MACHINE_FAULT, m.id, f"{m.id} out of service: {m.fault_reason or 'unknown'}", m.id)
        elif not offline:
            await clear_alert(db, AlertType.MACHINE_FAULT, m.id)

        if m.bin_fill_pct is not None and m.bin_fill_pct >= s.bin_full_alert_pct:
            await raise_alert(db, AlertType.BIN_FULL, m.id, f"{m.id} bin {m.bin_fill_pct}% full - schedule collection", m.id)
        elif m.bin_fill_pct is not None:
            await clear_alert(db, AlertType.BIN_FULL, m.id)

    stuck_before = now - timedelta(seconds=s.payout_stuck_after_s)
    stuck = (await db.execute(select(Transaction).where(
        Transaction.status == TxnStatus.PENDING, Transaction.created_at < stuck_before))).scalars().all()
    for t in stuck:
        await raise_alert(db, AlertType.PAYOUT_STUCK, t.id, f"Payout {t.id} pending since {t.created_at:%d %b %H:%M} UTC", t.machine_id)
    open_stuck = (await db.execute(select(Alert.entity_id).where(
        Alert.type == AlertType.PAYOUT_STUCK, Alert.status == "OPEN"))).scalars().all()
    for txn_id in open_stuck:
        t = await db.get(Transaction, txn_id)
        if t is None or t.status != TxnStatus.PENDING:
            await clear_alert(db, AlertType.PAYOUT_STUCK, txn_id)
    await db.commit()
