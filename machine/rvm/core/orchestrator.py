"""RVM machine orchestrator - the customer workflow as an async state machine.

One session = one customer = a batch of up to N bottles (one per lane/inlet):

  health check -> READY -> first bottle -> COLLECTING (short window for the
  other inlets) -> CHECKING: every lane in parallel runs
      position -> inspect -> refund QR -> manufacturing QR -> eligibility
      invalid -> handed back at that inlet right away
      valid   -> parked in that lane's holding chamber
  -> (at least one valid) refund method -> confirm (valid count x Rs.10)
  -> payout -> SUCCESS: all held bottles to the bin, SMS
               FAILED : all held bottles handed back

Rules:
  * A bottle never reaches the bin before its payout is final
    (or the pending policy says so).
  * The customer is asked for the refund destination only after every
    bottle of the batch has been checked.
  * Any PLC fault takes the machine OUT_OF_SERVICE; recovery decides what
    to do with bottles still inside.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..config import MachineConfig
from ..plc.base import PLC, PLCCommandError, PLCError, PLCFault, PLCTimeout
from ..plc.registers import Cmd, CmdResult, LaneSensor, Sensor
from ..services import qr_codec
from ..services.backend import Backend, Destination, PayoutStatus
from ..services.customer import CustomerInterface
from ..services.session_log import SessionLog
from ..services.vision import BottleInspector, Camera, Frame, QRReader
from .events import EventBus, LaneStep, MachineState

log = logging.getLogger(__name__)

REFUND_AMOUNT_PAISE = 1000


class Rejected(Exception):
    """Session-level stop: every held bottle is handed back to the customer."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class LaneRejected(Exception):
    """One bottle of the batch is not accepted."""

    def __init__(self, reason: str, moved: bool = True):
        super().__init__(reason)
        self.reason = reason
        self.moved = moved   # False: the bottle never left the inlet (nothing to hand back)


class OutOfService(Exception):
    pass


@dataclass
class Bottle:
    lane: int
    step: LaneStep = LaneStep.DETECTED
    frames: list[Frame] = field(default_factory=list)
    codes: list[str] = field(default_factory=list)
    kinds: dict[str, str | None] = field(default_factory=dict)   # code -> refund | mfg | None (unreadable)
    refund_qr: str | None = None
    mfg_qr: str | None = None
    amount_paise: int = 0
    brand: str | None = None    # from the manufacturing QR (shown on the kiosk)
    step_at: float = 0.0        # loop time the current step was shown (demo step hold)
    reason: str = ""
    handed_back: bool = False   # physically returned to the inlet


@dataclass
class Session:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    bottles: dict[int, Bottle] = field(default_factory=dict)
    destination: Destination | None = None
    sms_mobile: str | None = None
    input_source: str | None = None
    txn_id: str | None = None
    payout_status: PayoutStatus | None = None
    outcome: str = "IN_PROGRESS"   # ACCEPTED | RETURNED | CANCELLED | ABORTED
    reason: str = ""

    @property
    def held(self) -> list[Bottle]:
        """Valid bottles waiting in their holding chambers."""
        return [b for b in self.bottles.values() if b.step == LaneStep.VALID]

    @property
    def amount_paise(self) -> int:
        return sum(b.amount_paise for b in self.held)

    def summary(self) -> list[dict]:
        return [{"lane": b.lane, "step": b.step.value, "reason": b.reason} for b in sorted(self.bottles.values(), key=lambda b: b.lane)]


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

    @property
    def lanes(self) -> list[int]:
        return self.plc.lanes

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

    def _lane_step(self, b: Bottle, step: LaneStep, **data) -> None:
        b.step = step
        self.bus.publish("lane", lane=b.lane, step=step.value, reason=b.reason or None, **data)

    async def _hold(self, since: float) -> None:
        """Demo pacing: wait until flow.step_min_display_s has passed since `since`."""
        left = self.flow.step_min_display_s - (asyncio.get_running_loop().time() - since)
        if left > 0:
            await asyncio.sleep(left)

    async def _show_step(self, b: Bottle, step: LaneStep, **data) -> None:
        """Next check step; the previous step's screen stays up for at least step_min_display_s.
        DETECTED and POSITIONING share one screen, so they are not held apart."""
        if b.step_at and step != LaneStep.POSITIONING:
            await self._hold(b.step_at)
        self._lane_step(b, step, **data)
        b.step_at = asyncio.get_running_loop().time()

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
        await self._dispose_leftover_bottles()
        log.info("Health check OK (PLC v%s, %s lanes, bin %s%%)", s.plc_version, len(self.lanes), s.bin_fill_pct)

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

    async def _dispose_leftover_bottles(self) -> None:
        """After a fault, bottles may still be inside. Paid -> bin, otherwise -> customer."""
        s = self.plc.status
        inside = [ln for ln in self.lanes
                  if s.lane_has(ln, LaneSensor.BOTTLE_IN_SCAN_POSITION) or s.lane_has(ln, LaneSensor.BOTTLE_IN_HOLD)]
        if not inside:
            return
        last = self._last_session
        paid = last is not None and last.payout_status in (PayoutStatus.SUCCESS, PayoutStatus.PENDING)
        log.warning("Leftover bottles in lanes %s after fault (paid=%s)", inside, paid)
        if paid:
            await self._parallel([self.plc.command(Cmd.ACCEPT_BOTTLE, lane=ln) for ln in inside])
            await self._safe_backend(self.backend.bottle_accepted(last.id, last.txn_id))
        else:
            await self._parallel([self.plc.command(Cmd.REJECT_BOTTLE, lane=ln) for ln in inside])
            if last:
                await self._safe_backend(self.backend.bottle_returned(last.id, "FAULT_RECOVERY"))
            await self._wait_taken(inside)

    # ======================= one customer =======================

    async def _serve_one_customer(self) -> None:
        self.fault_reason = None
        self._set_state(MachineState.READY, lanes=self.lanes)
        await self._parallel([self.plc.command(Cmd.OPEN_INLET, lane=ln) for ln in self.lanes])
        self._message("INSERT_BOTTLE")
        first = await self._wait_for_bottle()

        session = Session()
        self._last_session = session
        self.bus.publish("session_started", session_id=session.id, lane=first)
        try:
            try:
                await self._process(session, first)
            except Rejected as r:
                await self._return_held(session, r.reason)
            await self._wait_taken([b.lane for b in session.bottles.values() if b.handed_back])
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
            accepted = [b for b in session.bottles.values() if b.step == LaneStep.ACCEPTED]
            self.bus.publish(
                "session_ended", session_id=session.id, outcome=session.outcome, reason=session.reason,
                txn_id=session.txn_id, bottles=session.summary(), accepted=len(accepted),
                amount_paise=sum(b.amount_paise for b in accepted),
            )
            log.info("SESSION %s %s %s %s", session.id[:8], session.outcome, session.reason,
                     [(b["lane"], b["step"]) for b in session.summary()])

    async def _wait_for_bottle(self) -> int:
        """Wait for a bottle in any inlet; stop accepting bottles if the central server goes away."""
        while True:
            try:
                return await self.plc.wait_any_lane(LaneSensor.BOTTLE_AT_INLET, timeout=1.0)
            except PLCTimeout:
                if not self.backend_ok:
                    await self._close_inlets(self.lanes)
                    raise OutOfService("BACKEND_UNREACHABLE")

    async def _collect(self, session: Session, first: int) -> list[int]:
        """After the first bottle, give the customer a moment to fill the other inlets."""
        lanes = {first}
        if len(self.lanes) > 1 and self.flow.batch_window_s > 0:
            self._set_state(MachineState.COLLECTING, session_id=session.id, lanes=sorted(lanes),
                            timeout_s=self.flow.batch_window_s)
            loop = asyncio.get_running_loop()
            deadline = loop.time() + self.flow.batch_window_s
            while loop.time() < deadline and len(lanes) < len(self.lanes):
                await asyncio.sleep(0.1)
                self.plc.check_healthy()
                now = {ln for ln in self.lanes if self.plc.status.lane_has(ln, LaneSensor.BOTTLE_AT_INLET)}
                if now - lanes:
                    lanes |= now
                    self.bus.publish("state", state=MachineState.COLLECTING.value, session_id=session.id,
                                     lanes=sorted(lanes), timeout_s=self.flow.batch_window_s)
        return sorted(lanes)

    async def _process(self, session: Session, first: int) -> None:
        # ---- 1. collect the batch, close the inlets without a bottle ----
        lanes = await self._collect(session, first)
        await self._close_inlets([ln for ln in self.lanes if ln not in lanes])

        # ---- 2. every lane checks its bottle in parallel ----
        for ln in lanes:
            session.bottles[ln] = Bottle(lane=ln)
        self._set_state(MachineState.CHECKING, session_id=session.id, lanes=lanes)
        await self._parallel([self._check_lane(session, session.bottles[ln]) for ln in lanes])

        held = session.held
        rejected = [b for b in session.bottles.values() if b.step == LaneStep.REJECTED]
        if not held:
            session.outcome = "RETURNED"
            session.reason = rejected[0].reason if rejected else "NO_BOTTLE"
            self._set_state(MachineState.REJECTING, reason=session.reason, bottles=session.summary())
            self._message("TAKE_BACK_BOTTLE")
            return

        amount = session.amount_paise
        self._message("BATCH_RESULT", accepted=len(held), rejected=len(rejected), amount_paise=amount,
                      bottles=session.summary())

        # ---- 3. refund destination + confirmation (once, for the whole batch) ----
        session.destination = await self._collect_destination(session, amount, len(held))

        # ---- 4. payout ----
        self._set_state(MachineState.PAYING, amount_paise=amount, bottle_count=len(held))
        self._message("PROCESSING_PAYMENT", amount_paise=amount)
        paying_since = asyncio.get_running_loop().time()
        status = await self._payout(session, amount)
        await self._hold(paying_since)   # demo pacing only (0 on a real machine)

        # ---- 5. result ----
        if status == PayoutStatus.SUCCESS:
            await self._accept_held(session, "REFUND_SUCCESS")
        elif status == PayoutStatus.FAILED:
            raise Rejected("PAYOUT_FAILED")
        elif self.flow.on_payout_pending_timeout == "accept":
            # Server keeps reconciling; customer gets SMS when it completes.
            await self._accept_held(session, "REFUND_PENDING")
        else:
            raise Rejected("PAYOUT_PENDING")

    # ======================= one lane =======================

    async def _check_lane(self, session: Session, b: Bottle) -> None:
        ln = b.lane
        try:
            await self._show_step(b, LaneStep.DETECTED)
            await self._close_inlet(ln)

            await self._show_step(b, LaneStep.POSITIONING)
            try:
                await self.plc.command(Cmd.MOVE_TO_SCAN, lane=ln)
            except PLCCommandError as e:
                if e.result == CmdResult.NO_BOTTLE:
                    raise LaneRejected("BOTTLE_REMOVED", moved=False)
                raise
            await self.plc.wait_for_lane(ln, LaneSensor.BOTTLE_IN_SCAN_POSITION, timeout=3)

            await self._show_step(b, LaneStep.INSPECTING)
            await self.plc.command(Cmd.LIGHT_ON, lane=ln)
            for _ in range(self.flow.inspection_angles):
                await self._capture_and_rotate(b)
            result = await self.inspector.inspect(ln, b.frames)
            if not result.ok:
                raise LaneRejected(f"BOTTLE_{result.reason or 'INVALID'}")

            await self._show_step(b, LaneStep.SCANNING_REFUND_QR)
            b.refund_qr = await self._find_qr(b, "refund")
            if not b.refund_qr:
                # a code was read but it is not a TASMAC refund QR we know
                raise LaneRejected("REFUND_QR_INVALID_FORMAT" if None in b.kinds.values() else "REFUND_QR_NOT_FOUND")
            v = await self._backend_or_lane_reject(self.backend.verify_refund_qr(session.id, b.refund_qr, ln))
            if not v.ok:
                raise LaneRejected(v.reason)

            await self._show_step(b, LaneStep.SCANNING_MFG_QR)
            b.mfg_qr = await self._find_qr(b, "mfg")
            if not b.mfg_qr:
                raise LaneRejected("MFG_QR_INVALID_FORMAT" if None in b.kinds.values() else "MFG_QR_NOT_FOUND")
            v = await self._backend_or_lane_reject(self.backend.verify_mfg_qr(session.id, b.mfg_qr, ln))
            if not v.ok:
                raise LaneRejected(v.reason)
            b.brand = v.data.get("brand_name") or v.data.get("brand")

            # eligibility reserves the refund QR on the server for this session + lane
            await self._show_step(b, LaneStep.VERIFYING, brand=b.brand)
            v = await self._backend_or_lane_reject(
                self.backend.check_eligibility(session.id, b.refund_qr, b.mfg_qr, ln))
            if not v.ok:
                raise LaneRejected(v.reason)
            b.amount_paise = int(v.data.get("amount_paise", REFUND_AMOUNT_PAISE))
            await self.plc.command(Cmd.LIGHT_OFF, lane=ln)
            await self.plc.command(Cmd.MOVE_TO_HOLD, lane=ln)
            await self._show_step(b, LaneStep.VALID, amount_paise=b.amount_paise, brand=b.brand)
            await self._hold(b.step_at)   # "bottle verified" screen

        except LaneRejected as r:
            b.reason = r.reason
            if r.moved:
                try:
                    await self.plc.command(Cmd.LIGHT_OFF, lane=ln)
                except PLCCommandError:
                    pass
                await self.plc.command(Cmd.REJECT_BOTTLE, lane=ln)
                b.handed_back = True
            await self._safe_backend(self.backend.bottle_rejected(session.id, ln, r.reason))
            await self._show_step(b, LaneStep.REJECTED)
            self._message("BOTTLE_REJECTED", lane=ln, reason=r.reason)

    async def _close_inlet(self, lane: int) -> None:
        for _ in range(self.flow.close_inlet_retries):
            try:
                await self.plc.command(Cmd.CLOSE_INLET, lane=lane)
                return
            except PLCCommandError as e:
                if e.result != CmdResult.INTERLOCK:
                    raise
                self._message("REMOVE_HAND", lane=lane)
                await asyncio.sleep(self.flow.hand_retry_interval_s)
        raise LaneRejected("HAND_IN_INLET", moved=False)

    async def _close_inlets(self, lanes: list[int]) -> None:
        async def close(ln: int) -> None:
            try:
                await self.plc.command(Cmd.CLOSE_INLET, lane=ln)
            except PLCCommandError:
                pass  # a hand in an empty inlet: nothing to protect
        await self._parallel([close(ln) for ln in lanes])

    async def _capture_and_rotate(self, b: Bottle) -> None:
        frame = await self.camera.capture(b.lane, len(b.frames))
        b.frames.append(frame)
        for code in await self.qr_reader.decode(frame):
            if code not in b.codes:   # a real camera sees the same code in many frames
                b.codes.append(code)
        step = 360 // max(self.flow.inspection_angles, 1)
        await self.plc.command(Cmd.ROTATE_BOTTLE, param=step, lane=b.lane)

    async def _find_qr(self, b: Bottle, kind: str) -> str | None:
        """Use codes from inspection frames; rotate further if not found yet."""
        extra = 0
        while True:
            new = [c for c in b.codes if c not in b.kinds]
            if new:
                b.kinds.update(await self._classify(new))
            for code, k in b.kinds.items():
                if k == kind:
                    return code
            if extra >= self.flow.qr_scan_max_rotations:
                return None
            await self._capture_and_rotate(b)
            extra += 1

    async def _classify(self, codes: list[str]) -> dict[str, str | None]:
        """Which code is the refund / manufacturing QR: the server knows the real TASMAC QRs."""
        return await self._backend_or_lane_reject(self.backend.classify_qr(codes))

    # ======================= customer + payout =======================

    async def _collect_destination(self, session: Session, amount: int, count: int) -> Destination:
        for attempt in range(1, self.flow.max_destination_attempts + 1):
            self._set_state(MachineState.SELECT_REFUND_METHOD, attempt=attempt,
                            max_attempts=self.flow.max_destination_attempts,
                            timeout_s=self.flow.customer_input_timeout_s,
                            amount_paise=amount, bottle_count=count)
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
                          name=v.data.get("name", ""), amount_paise=amount, bottle_count=count,
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

    async def _accept_held(self, session: Session, message: str) -> None:
        held = session.held
        amount = session.amount_paise
        self._set_state(MachineState.ACCEPTING, bottle_count=len(held))
        await self._parallel([self.plc.command(Cmd.ACCEPT_BOTTLE, lane=b.lane) for b in held])
        for b in held:
            self._lane_step(b, LaneStep.ACCEPTED)
        await self._safe_backend(self.backend.bottle_accepted(session.id, session.txn_id))
        session.outcome = "ACCEPTED"
        session.reason = message
        self._message(message, txn_id=session.txn_id, amount_paise=amount, bottle_count=len(held))

    async def _return_held(self, session: Session, reason: str) -> None:
        """Hand back every bottle still parked in a holding chamber."""
        held = session.held
        self._set_state(MachineState.REJECTING, reason=reason, bottles=session.summary())
        self._message("BOTTLE_REJECTED", reason=reason)
        session.outcome, session.reason = "RETURNED", reason

        async def hand_back(b: Bottle) -> None:
            try:
                await self.plc.command(Cmd.LIGHT_OFF, lane=b.lane)
            except PLCCommandError:
                pass
            await self.plc.command(Cmd.REJECT_BOTTLE, lane=b.lane)
            b.handed_back = True
            b.reason = reason
            self._lane_step(b, LaneStep.RETURNED)

        await self._parallel([hand_back(b) for b in held])
        await self._safe_backend(self.backend.bottle_returned(session.id, reason))
        self._message("TAKE_BACK_BOTTLE")

    async def _wait_taken(self, lanes: list[int]) -> None:
        """Returned bottles must first appear at their inlet, then be taken away -
        otherwise they would be picked up as new insertions."""
        async def one(ln: int) -> None:
            try:
                await self.plc.wait_for_lane(ln, LaneSensor.BOTTLE_AT_INLET, present=True, timeout=3)
            except PLCTimeout:
                log.warning("Returned bottle not seen at inlet %s", ln)
            await self.plc.wait_for_lane(ln, LaneSensor.BOTTLE_AT_INLET, present=False)
        await self._parallel([one(ln) for ln in lanes])

    # ======================= helpers =======================

    @staticmethod
    async def _parallel(coros: list) -> None:
        """Run coroutines concurrently; if one fails, cancel the rest and re-raise."""
        tasks = [asyncio.ensure_future(c) for c in coros]
        if not tasks:
            return
        try:
            await asyncio.gather(*tasks)
        except BaseException:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

    async def _backend_or_reject(self, coro):
        try:
            return await coro
        except (PLCError, Rejected, LaneRejected):
            raise
        except Exception as e:  # network / server error before money moved
            log.error("Backend call failed: %s", e)
            raise Rejected("BACKEND_UNAVAILABLE") from e

    async def _backend_or_lane_reject(self, coro):
        try:
            return await coro
        except (PLCError, LaneRejected):
            raise
        except Exception as e:
            log.error("Backend call failed: %s", e)
            raise LaneRejected("BACKEND_UNAVAILABLE") from e

    async def _safe_backend(self, coro, default=None):
        try:
            return await coro
        except Exception as e:
            log.error("Backend call failed (ignored): %s", e)
            return default
