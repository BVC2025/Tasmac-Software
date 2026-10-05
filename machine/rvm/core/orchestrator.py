"""RVM machine orchestrator - the customer workflow as an async state machine.

Flow (see README):
  health check -> READY -> bottle detected -> position -> inspect ->
  refund QR -> manufacturing QR -> eligibility -> park in holding chamber ->
  refund method -> confirm -> payout -> accept bottle (or return it)

Rules:
  * The bottle is never sent to the bin before the payout is final
    (or the pending policy says so).
  * Any PLC fault takes the machine OUT_OF_SERVICE; recovery decides what
    to do with a bottle still inside.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..config import MachineConfig
from ..plc.base import PLC, PLCCommandError, PLCError, PLCFault, PLCTimeout
from ..plc.registers import Cmd, CmdResult, Sensor
from ..services import qr_codec
from ..services.backend import Backend, Destination, PayoutStatus
from ..services.customer import CustomerInterface
from ..services.session_log import SessionLog
from ..services.vision import BottleInspector, Camera, Frame, QRReader
from .events import EventBus, MachineState

log = logging.getLogger(__name__)

REFUND_AMOUNT_PAISE = 1000


class Rejected(Exception):
    """Session ends and the bottle is returned to the customer."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class Cancelled(Exception):
    """Session ends without any bottle movement (bottle still with customer)."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class OutOfService(Exception):
    pass


@dataclass
class Session:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    frames: list[Frame] = field(default_factory=list)
    codes: list[str] = field(default_factory=list)
    refund_qr: str | None = None
    mfg_qr: str | None = None
    reserved: bool = False
    destination: Destination | None = None
    sms_mobile: str | None = None
    input_source: str | None = None
    txn_id: str | None = None
    payout_status: PayoutStatus | None = None
    outcome: str = "IN_PROGRESS"   # ACCEPTED | RETURNED | CANCELLED | ABORTED
    reason: str = ""


class Orchestrator:
    def __init__(
        self,
        cfg: MachineConfig,
        plc: PLC,
        camera: Camera,
        inspector: BottleInspector,
        qr_reader: QRReader,
        backend: Backend,
        customer: CustomerInterface,
        bus: EventBus,
        session_log: SessionLog | None = None,
    ):
        self.cfg = cfg
        self.flow = cfg.flow
        self.plc = plc
        self.camera = camera
        self.inspector = inspector
        self.qr_reader = qr_reader
        self.backend = backend
        self.customer = customer
        self.bus = bus
        self.state = MachineState.STARTING
        self.sessions: list[Session] = []          # finished sessions (in-memory log)
        self._last_session: Session | None = None  # used by fault recovery
        self.session_log = session_log
        self.fault_reason: str | None = None       # reported in the heartbeat
        self.backend_ok = True                     # kept up to date by watch_backend()

    # ======================= main loop =======================

    async def run(self) -> None:
        watcher = asyncio.create_task(self.watch_backend())
        try:
            await self._run()
        finally:
            watcher.cancel()

    async def watch_backend(self) -> None:
        """Track central server reachability; the machine stops taking bottles while it is down."""
        failures = 0
        while True:
            ok = await self._safe_backend(self.backend.health(), default=False)
            failures = 0 if ok else failures + 1
            was_ok, self.backend_ok = self.backend_ok, failures < self.flow.backend_failures_before_oos
            if was_ok and not self.backend_ok:
                log.error("Central server unreachable (%s checks)", failures)
            elif not was_ok and self.backend_ok:
                log.info("Central server reachable again")
            await asyncio.sleep(self.flow.backend_check_interval_s)

    async def _run(self) -> None:
        while True:
            try:
                await self._health_check()
                while True:
                    await self._serve_one_customer()
            except (PLCError, OutOfService) as e:
                await self._out_of_service(str(e))

    def _set_state(self, state: MachineState, **data) -> None:
        if state != self.state:
            log.info("STATE %s -> %s %s", self.state.value, state.value, data or "")
        self.state = state
        self.bus.publish("state", state=state.value, **data)

    def _message(self, code: str, **data) -> None:
        """UI message code - the kiosk maps codes to Tamil/English text."""
        self.bus.publish("message", code=code, **data)

    # ======================= health / faults =======================

    async def _health_check(self) -> None:
        self._set_state(MachineState.HEALTH_CHECK)
        for _ in range(50):  # PLC may still be booting / connecting
            try:
                self.plc.check_healthy()
                break
            except PLCFault:
                await asyncio.sleep(0.2)
        self.plc.check_healthy()
        s = self.plc.status
        if s.has(Sensor.BIN_FULL):
            raise OutOfService("BIN_FULL")
        if s.has(Sensor.SERVICE_DOOR_OPEN):
            raise OutOfService("SERVICE_DOOR_OPEN")
        if not await self._safe_backend(self.backend.health(), default=False):
            raise OutOfService("BACKEND_UNREACHABLE")
        await self._dispose_leftover_bottle()
        log.info("Health check OK (PLC v%s, bin %s%%)", s.plc_version, s.bin_fill_pct)

    async def _out_of_service(self, reason: str) -> None:
        log.error("OUT OF SERVICE: %s", reason)
        self.fault_reason = reason
        self._set_state(MachineState.OUT_OF_SERVICE, reason=reason)
        self.bus.publish("fault", reason=reason)
        await asyncio.sleep(self.flow.fault_retry_interval_s)
        # Auto-reset only when the cause is gone (e-stop released, PLC reachable)
        s = self.plc.status
        if s.connected and not s.has(Sensor.ESTOP_ACTIVE):
            try:
                await self.plc.command(Cmd.RESET_FAULT, timeout=5)
                log.info("PLC fault reset OK")
            except PLCError as e:
                log.warning("PLC fault reset failed: %s", e)

    async def _dispose_leftover_bottle(self) -> None:
        """After a fault, a bottle may still be inside. Paid -> bin, otherwise -> customer."""
        s = self.plc.status
        if not (s.has(Sensor.BOTTLE_IN_SCAN_POSITION) or s.has(Sensor.BOTTLE_IN_HOLD)):
            return
        last = self._last_session
        paid = last is not None and last.payout_status in (PayoutStatus.SUCCESS, PayoutStatus.PENDING)
        log.warning("Leftover bottle found after fault (paid=%s)", paid)
        if paid:
            await self.plc.command(Cmd.ACCEPT_BOTTLE)
            await self._safe_backend(self.backend.bottle_accepted(last.id, last.txn_id))
        else:
            await self.plc.command(Cmd.REJECT_BOTTLE)
            if last:
                await self._safe_backend(self.backend.bottle_returned(last.id, "FAULT_RECOVERY"))
            await self._wait_bottle_taken()

    # ======================= one customer =======================

    async def _serve_one_customer(self) -> None:
        self.fault_reason = None
        self._set_state(MachineState.READY)
        await self.plc.command(Cmd.OPEN_INLET)
        self._message("INSERT_BOTTLE")
        await self._wait_for_bottle()

        session = Session()
        self._last_session = session
        self.bus.publish("session_started", session_id=session.id)
        try:
            await self._process(session)
        except Rejected as r:
            await self._return_bottle(session, r.reason)
        except Cancelled as c:
            session.outcome, session.reason = "CANCELLED", c.reason
            await self._safe_backend(self.backend.bottle_returned(session.id, c.reason))
        except PLCError as e:
            session.outcome, session.reason = "ABORTED", str(e)
            raise
        finally:
            self.sessions.append(session)
            if self.session_log:
                try:
                    self.session_log.record(session)
                except Exception:
                    log.exception("Local session log write failed")
            self.bus.publish(
                "session_ended", session_id=session.id, outcome=session.outcome,
                reason=session.reason, txn_id=session.txn_id,
            )
            log.info("SESSION %s %s %s", session.id[:8], session.outcome, session.reason)

    async def _wait_for_bottle(self) -> None:
        """Wait for a bottle; stop accepting bottles if the central server goes away."""
        while True:
            try:
                await self.plc.wait_for(Sensor.BOTTLE_AT_INLET, timeout=1.0)
                return
            except PLCTimeout:
                if not self.backend_ok:
                    try:
                        await self.plc.command(Cmd.CLOSE_INLET)
                    except PLCCommandError:
                        pass  # hand in inlet; out of service anyway
                    raise OutOfService("BACKEND_UNREACHABLE")

    async def _process(self, session: Session) -> None:
        # ---- 1. detection + positioning ----
        self._set_state(MachineState.BOTTLE_DETECTED, session_id=session.id)
        await self._close_inlet()
        self._set_state(MachineState.POSITIONING)
        try:
            await self.plc.command(Cmd.MOVE_TO_SCAN)
        except PLCCommandError as e:
            if e.result == CmdResult.NO_BOTTLE:
                raise Cancelled("BOTTLE_REMOVED")
            raise
        await self.plc.wait_for(Sensor.BOTTLE_IN_SCAN_POSITION, timeout=3)

        # ---- 2. image capture + condition inspection ----
        self._set_state(MachineState.INSPECTING)
        await self.plc.command(Cmd.LIGHT_ON)
        for _ in range(self.flow.inspection_angles):
            await self._capture_and_rotate(session)
        result = await self.inspector.inspect(session.frames)
        if not result.ok:
            raise Rejected(f"BOTTLE_{result.reason or 'INVALID'}")

        # ---- 3. refund QR ----
        self._set_state(MachineState.SCANNING_REFUND_QR)
        session.refund_qr = await self._find_qr(session, "refund")
        if not session.refund_qr:
            raise Rejected("REFUND_QR_NOT_FOUND")
        v = await self._backend_or_reject(self.backend.verify_refund_qr(session.id, session.refund_qr))
        if not v.ok:
            raise Rejected(v.reason)

        # ---- 4. manufacturing QR ----
        self._set_state(MachineState.SCANNING_MFG_QR)
        session.mfg_qr = await self._find_qr(session, "mfg")
        if not session.mfg_qr:
            raise Rejected("MFG_QR_NOT_FOUND")
        v = await self._backend_or_reject(self.backend.verify_mfg_qr(session.id, session.mfg_qr))
        if not v.ok:
            raise Rejected(v.reason)

        # ---- 5. eligibility (reserves the refund QR on the server) ----
        self._set_state(MachineState.VERIFYING)
        v = await self._backend_or_reject(
            self.backend.check_eligibility(session.id, session.refund_qr, session.mfg_qr)
        )
        if not v.ok:
            raise Rejected(v.reason)
        session.reserved = True
        amount = int(v.data.get("amount_paise", REFUND_AMOUNT_PAISE))
        await self.plc.command(Cmd.LIGHT_OFF)
        await self.plc.command(Cmd.MOVE_TO_HOLD)

        # ---- 6. refund destination + confirmation ----
        session.destination = await self._collect_destination(session, amount)

        # ---- 7. payout ----
        self._set_state(MachineState.PAYING)
        self._message("PROCESSING_PAYMENT")
        status = await self._payout(session, amount)

        # ---- 8. result ----
        if status == PayoutStatus.SUCCESS:
            await self._accept_bottle(session, "REFUND_SUCCESS")
        elif status == PayoutStatus.FAILED:
            raise Rejected("PAYOUT_FAILED")
        elif self.flow.on_payout_pending_timeout == "accept":
            # Server keeps reconciling; customer gets SMS when it completes.
            await self._accept_bottle(session, "REFUND_PENDING")
        else:
            raise Rejected("PAYOUT_PENDING")

    # ======================= steps =======================

    async def _close_inlet(self) -> None:
        for attempt in range(self.flow.close_inlet_retries):
            try:
                await self.plc.command(Cmd.CLOSE_INLET)
                return
            except PLCCommandError as e:
                if e.result != CmdResult.INTERLOCK:
                    raise
                self._message("REMOVE_HAND")
                await asyncio.sleep(self.flow.hand_retry_interval_s)
        raise Cancelled("HAND_IN_INLET")

    async def _capture_and_rotate(self, session: Session) -> None:
        frame = await self.camera.capture(len(session.frames))
        session.frames.append(frame)
        session.codes.extend(await self.qr_reader.decode(frame))
        step = 360 // max(self.flow.inspection_angles, 1)
        await self.plc.command(Cmd.ROTATE_BOTTLE, param=step)

    async def _find_qr(self, session: Session, kind: str) -> str | None:
        """Use codes from inspection frames; rotate further if not found yet."""
        extra = 0
        while True:
            for code in session.codes:
                if qr_codec.classify(code) == kind:
                    return code
            if extra >= self.flow.qr_scan_max_rotations:
                return None
            await self._capture_and_rotate(session)
            extra += 1

    async def _collect_destination(self, session: Session, amount: int) -> Destination:
        for attempt in range(1, self.flow.max_destination_attempts + 1):
            self._set_state(MachineState.SELECT_REFUND_METHOD, attempt=attempt,
                            max_attempts=self.flow.max_destination_attempts,
                            timeout_s=self.flow.customer_input_timeout_s)
            try:
                inp = await asyncio.wait_for(
                    self.customer.get_destination(session.id, attempt),
                    timeout=self.flow.customer_input_timeout_s,
                )
            except asyncio.TimeoutError:
                raise Rejected("CUSTOMER_TIMEOUT")
            if inp is None:
                raise Rejected("CUSTOMER_CANCELLED")

            dest = Destination.parse(inp.value)
            sms_mobile = None
            if inp.sms_mobile:
                sms = Destination.parse(inp.sms_mobile)
                if sms is None or sms.kind != "mobile":
                    self._message("INVALID_SMS_MOBILE", attempt=attempt)
                    continue
                sms_mobile = sms.value
            if dest is None:
                self._message("INVALID_DESTINATION", attempt=attempt)
                continue
            v = await self._backend_or_reject(self.backend.validate_destination(session.id, dest))
            if not v.ok:
                self._message("DESTINATION_NOT_FOUND", attempt=attempt)
                continue

            self._set_state(MachineState.CONFIRMING, timeout_s=self.flow.customer_input_timeout_s)
            self._message("CONFIRM_REFUND", destination=dest.masked(), kind=dest.kind,
                          name=v.data.get("name", ""), amount_paise=amount,
                          sms_mobile=("XXXXXX" + sms_mobile[-4:]) if sms_mobile else None,
                          sms=bool(sms_mobile or dest.sms_number))
            try:
                ok = await asyncio.wait_for(
                    self.customer.confirm(session.id, dest, v.data.get("name", ""), amount),
                    timeout=self.flow.customer_input_timeout_s,
                )
            except asyncio.TimeoutError:
                raise Rejected("CUSTOMER_TIMEOUT")
            if ok:
                session.sms_mobile, session.input_source = sms_mobile, inp.source
                return dest
        raise Rejected("INVALID_DESTINATION")

    async def _payout(self, session: Session, amount: int) -> PayoutStatus:
        session.txn_id = await self._backend_or_reject(
            self.backend.create_transaction(session.id, session.destination, amount, session.sms_mobile)
        )
        # From here on money may move: backend errors mean "unknown", i.e. PENDING.
        session.payout_status = PayoutStatus.PENDING
        status = await self._safe_backend(self.backend.request_payout(session.txn_id), PayoutStatus.PENDING)
        session.payout_status = status
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.flow.payout_pending_wait_s
        while status == PayoutStatus.PENDING and loop.time() < deadline:
            await asyncio.sleep(self.flow.payout_poll_interval_s)
            status = await self._safe_backend(self.backend.get_payout_status(session.txn_id), PayoutStatus.PENDING)
            session.payout_status = status
        log.info("Payout %s -> %s", session.txn_id, status.value)
        return status

    async def _accept_bottle(self, session: Session, message: str) -> None:
        self._set_state(MachineState.ACCEPTING)
        await self.plc.command(Cmd.ACCEPT_BOTTLE)
        await self._safe_backend(self.backend.bottle_accepted(session.id, session.txn_id))
        session.outcome = "ACCEPTED"
        session.reason = message
        self._message(message, txn_id=session.txn_id)

    async def _return_bottle(self, session: Session, reason: str) -> None:
        self._set_state(MachineState.REJECTING, reason=reason)
        self._message("BOTTLE_REJECTED", reason=reason)
        session.outcome, session.reason = "RETURNED", reason
        await self.plc.command(Cmd.LIGHT_OFF)
        await self.plc.command(Cmd.REJECT_BOTTLE)
        await self._safe_backend(self.backend.bottle_returned(session.id, reason))
        self._message("TAKE_BACK_BOTTLE")
        await self._wait_bottle_taken()

    async def _wait_bottle_taken(self) -> None:
        """Returned bottle must first appear at the inlet, then be taken away -
        otherwise it would be picked up as a new insertion."""
        try:
            await self.plc.wait_for(Sensor.BOTTLE_AT_INLET, present=True, timeout=3)
        except PLCTimeout:
            log.warning("Returned bottle not seen at inlet")
        await self.plc.wait_for(Sensor.BOTTLE_AT_INLET, present=False)

    # ======================= backend helpers =======================

    async def _backend_or_reject(self, coro):
        try:
            return await coro
        except (PLCError, Rejected, Cancelled):
            raise
        except Exception as e:  # network / server error before money moved
            log.error("Backend call failed: %s", e)
            raise Rejected("BACKEND_UNAVAILABLE") from e

    async def _safe_backend(self, coro, default=None):
        try:
            return await coro
        except Exception as e:
            log.error("Backend call failed (ignored): %s", e)
            return default
