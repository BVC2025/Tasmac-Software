"""End-to-end customer workflow tests (simulated PLC + mock services)."""

import asyncio
from datetime import datetime

from rvm.core.events import MachineState
from rvm.plc.registers import LaneSensor
from rvm.services import qr_codec

from .conftest import SECRET, bottle


async def test_happy_path_upi(make_rig):
    async with make_rig([bottle()]) as rig:
        s = await rig.insert_and_wait()
        assert s.outcome == "ACCEPTED" and s.reason == "REFUND_SUCCESS"
        assert rig.sim.bin_count == 1
        assert len(rig.backend.sms_log) == 1


async def test_happy_path_mobile_number(make_rig):
    async with make_rig([bottle(destination="+91 98765 43210")]) as rig:
        s = await rig.insert_and_wait()
        assert s.outcome == "ACCEPTED"
        assert s.destination.kind == "mobile" and s.destination.value == "9876543210"


async def test_damaged_bottle_returned(make_rig):
    async with make_rig([bottle(condition="damaged")]) as rig:
        s = await rig.insert_and_wait()
        assert (s.outcome, s.reason) == ("RETURNED", "BOTTLE_DAMAGED")
        assert rig.sim.bin_count == 0


async def test_missing_refund_qr(make_rig):
    async with make_rig([bottle(refund_qr=None)]) as rig:
        s = await rig.insert_and_wait()
        assert s.reason == "REFUND_QR_NOT_FOUND"


async def test_qr_found_after_extra_rotation(make_rig):
    # 4 inspection frames cover angles 0-3; QR at angle 6 needs extra rotations
    async with make_rig([bottle(refund_angle=6, mfg_angle=1)]) as rig:
        rig.orch.qr_reader.angles_per_turn = 8
        s = await rig.insert_and_wait()
        assert len(s.bottles[1].frames) == 7
        assert s.outcome == "ACCEPTED"


async def test_forged_qr(make_rig):
    b = bottle()
    b.refund_qr = b.refund_qr[:-4] + "0000"
    async with make_rig([b]) as rig:
        s = await rig.insert_and_wait()
        assert s.reason == "REFUND_QR_FORGED"


async def test_refund_qr_cannot_be_used_twice(make_rig):
    b = bottle()
    second = bottle(refund_qr=b.refund_qr)  # same refund sticker on another bottle
    async with make_rig([b, second]) as rig:
        assert (await rig.insert_and_wait()).outcome == "ACCEPTED"
        s = await rig.insert_and_wait()
        assert s.reason == "REFUND_QR_ALREADY_USED"
        assert rig.sim.bin_count == 1


async def test_brand_not_eligible(make_rig):
    b = bottle(mfg_qr=qr_codec.make_mfg_qr(SECRET, "XX", "B1", "M1"))
    async with make_rig([b]) as rig:
        s = await rig.insert_and_wait()
        assert s.reason == "BRAND_NOT_ELIGIBLE"


async def test_payout_failed_returns_bottle_and_releases_qr(make_rig):
    async with make_rig([bottle(payout="failed")]) as rig:
        s = await rig.insert_and_wait()
        assert s.reason == "PAYOUT_FAILED"
        assert rig.sim.bin_count == 0
        assert rig.backend.reservations == {}


async def test_payout_pending_then_success(make_rig):
    async with make_rig([bottle(payout="pending_then_success")]) as rig:
        s = await rig.insert_and_wait()
        assert s.reason == "REFUND_SUCCESS"


async def test_payout_pending_timeout_accept_policy(make_rig):
    async with make_rig([bottle(payout="pending")]) as rig:
        s = await rig.insert_and_wait()
        assert (s.outcome, s.reason) == ("ACCEPTED", "REFUND_PENDING")


async def test_invalid_destination_then_gives_up(make_rig):
    async with make_rig([bottle(destination="12345")]) as rig:
        s = await rig.insert_and_wait()
        assert s.reason == "INVALID_DESTINATION"
        assert rig.backend.reservations == {}


async def test_customer_walks_away(make_rig):
    async with make_rig([bottle(destination=None)]) as rig:
        s = await rig.insert_and_wait()
        assert s.reason == "CUSTOMER_CANCELLED"


async def test_estop_mid_session_goes_out_of_service_then_recovers(make_rig):
    async with make_rig([bottle(), bottle()]) as rig:
        await rig.wait_state(MachineState.READY)
        await asyncio.sleep(0.1)
        rig.sim.insert_bottle()
        await rig.wait_state(MachineState.CHECKING)

        async def inspecting():
            while True:
                b = rig.orch._last_session.bottles.get(1)
                if b and b.step.value == "INSPECTING":
                    return
                await asyncio.sleep(0.01)
        await asyncio.wait_for(inspecting(), 5)
        rig.sim.set_estop(True)
        await rig.wait_state(MachineState.OUT_OF_SERVICE)
        assert rig.orch.sessions[-1].outcome == "ABORTED"

        rig.sim.set_estop(False)
        await rig.wait_state(MachineState.READY, timeout=8)
        # unpaid leftover bottle went back to the customer
        assert rig.sim.bin_count == 0
        assert not rig.sim.lane_sensors[1] & (LaneSensor.BOTTLE_IN_SCAN_POSITION | LaneSensor.BOTTLE_IN_HOLD)

        s = await rig.insert_and_wait()
        assert s.outcome == "ACCEPTED"


async def test_jam_goes_out_of_service(make_rig):
    async with make_rig([bottle()]) as rig:
        rig.sim.jam_next()
        await rig.wait_state(MachineState.READY)
        await asyncio.sleep(0.1)
        rig.sim.insert_bottle()
        await rig.wait_state(MachineState.OUT_OF_SERVICE)
        assert "JAM" in rig.orch.sessions[-1].reason


def test_refresh_serials_keeps_scenarios():
    from rvm.services.sim_feed import SimBottleFeed

    good, forged = bottle(), bottle()
    forged.refund_qr = forged.refund_qr[:-4] + "0000"
    reused = bottle(refund_qr=good.refund_qr)
    feed = SimBottleFeed([good, forged, reused, bottle(refund_qr=None)])
    old = good.refund_qr
    feed.refresh_serials(SECRET)
    assert good.refund_qr != old and qr_codec.verify_signature(SECRET, good.refund_qr)
    assert not qr_codec.verify_signature(SECRET, forged.refund_qr)
    assert reused.refund_qr == good.refund_qr
    assert feed.bottles[3].refund_qr is None


async def test_backend_outage_takes_machine_out_of_service(make_rig):
    async with make_rig([bottle()]) as rig:
        await rig.wait_state(MachineState.READY)
        healthy = True

        async def health():
            return healthy

        rig.backend.health = health
        healthy = False
        await rig.wait_state(MachineState.OUT_OF_SERVICE, timeout=5)
        assert rig.orch.fault_reason == "BACKEND_UNREACHABLE"
        assert all(ls & LaneSensor.INLET_DOOR_CLOSED for ls in rig.sim.lane_sensors.values())  # no bottles while down
        healthy = True
        await rig.wait_state(MachineState.READY, timeout=5)
        assert rig.orch.fault_reason is None
        assert (await rig.insert_and_wait()).outcome == "ACCEPTED"


async def test_sessions_written_to_local_log(make_rig):
    async with make_rig([bottle(), bottle(condition="damaged")]) as rig:
        await rig.insert_and_wait()
        await rig.insert_and_wait()
        rows = rig.orch.session_log.recent()
        assert [r["outcome"] for r in rows] == ["RETURNED", "ACCEPTED"]
        assert rows[1]["destination"] == "ra***@okaxis" and rows[1]["txn_id"]



# ---------------- multi-lane batches ----------------

async def test_three_bottles_at_once_one_damaged(make_rig):
    async with make_rig([bottle("a"), bottle("b", condition="damaged"), bottle("c")]) as rig:
        s = await rig.insert_and_wait(3)
        steps = {ln: b.step.value for ln, b in s.bottles.items()}
        assert steps == {1: "ACCEPTED", 2: "REJECTED", 3: "ACCEPTED"}
        assert s.bottles[2].reason == "BOTTLE_DAMAGED"
        assert s.outcome == "ACCEPTED" and rig.sim.bin_count == 2
        txn = rig.backend.transactions[s.txn_id]
        assert txn["amount_paise"] == 2000 and txn["bottles"] == 2
        assert [(lane, reason) for _, lane, reason in rig.backend.rejected] == [(2, "BOTTLE_DAMAGED")]
        assert "Rs.20" in rig.backend.sms_log[0]


async def test_bottles_one_by_one_within_window_share_a_batch(make_rig):
    async with make_rig([bottle(), bottle()]) as rig:
        s = await rig.insert_and_wait([1, 2], gap_s=0.1)
        assert sorted(s.bottles) == [1, 2]
        assert rig.backend.transactions[s.txn_id]["amount_paise"] == 2000


async def test_destination_asked_only_after_all_bottles_checked(make_rig):
    async with make_rig([bottle(), bottle(refund_angle=6), bottle()]) as rig:
        rig.orch.qr_reader.angles_per_turn = 8   # lane 2 needs extra rotations -> finishes last
        q = rig.bus.subscribe()
        await rig.insert_and_wait(3)
        events = []
        while not q.empty():
            events.append(q.get_nowait())
        ask = next(i for i, e in enumerate(events) if e.type == "state" and e.data["state"] == "SELECT_REFUND_METHOD")
        valid_at = [i for i, e in enumerate(events) if e.type == "lane" and e.data["step"] == "VALID"]
        assert len(valid_at) == 3 and max(valid_at) < ask
        ask_event = events[ask].data
        assert ask_event["amount_paise"] == 3000 and ask_event["bottle_count"] == 3


async def test_payout_failed_hands_back_every_valid_bottle(make_rig):
    async with make_rig([bottle(payout="failed"), bottle(payout="failed")]) as rig:
        s = await rig.insert_and_wait(2)
        assert {b.step.value for b in s.bottles.values()} == {"RETURNED"}
        assert s.reason == "PAYOUT_FAILED" and rig.sim.bin_count == 0
        assert rig.backend.reservations == {}


async def test_all_bottles_invalid_no_refund_step(make_rig):
    async with make_rig([bottle(condition="damaged"), bottle(refund_qr=None)]) as rig:
        q = rig.bus.subscribe()
        s = await rig.insert_and_wait(2)
        assert s.outcome == "RETURNED" and s.txn_id is None
        states = []
        while not q.empty():
            e = q.get_nowait()
            if e.type == "state":
                states.append(e.data["state"])
        assert "SELECT_REFUND_METHOD" not in states


async def test_same_refund_qr_in_two_lanes_pays_once(make_rig):
    first = bottle()
    copy = bottle(refund_qr=first.refund_qr)
    async with make_rig([first, copy]) as rig:
        s = await rig.insert_and_wait(2)
        steps = sorted(b.step.value for b in s.bottles.values())
        assert steps == ["ACCEPTED", "REJECTED"]
        rejected = next(b for b in s.bottles.values() if b.step.value == "REJECTED")
        assert rejected.reason == "REFUND_QR_IN_USE"
        assert rig.backend.transactions[s.txn_id]["amount_paise"] == 1000


async def test_single_lane_machine(make_rig):
    async with make_rig([bottle()], lanes=1) as rig:
        s = await rig.insert_and_wait(1)
        assert s.outcome == "ACCEPTED" and list(s.bottles) == [1]


async def test_demo_step_hold_keeps_each_screen_up(make_rig):
    hold = 0.25
    async with make_rig([bottle()], lanes=1, step_min_display_s=hold) as rig:
        q = rig.bus.subscribe()
        s = await rig.insert_and_wait(1, timeout=15)
        assert s.outcome == "ACCEPTED"
        steps = []
        while not q.empty():
            ev = q.get_nowait()
            if ev.type == "lane":
                steps.append((ev.data["step"], ev.at))
        names = [n for n, _ in steps]
        assert names[:7] == ["DETECTED", "POSITIONING", "INSPECTING", "SCANNING_REFUND_QR",
                             "SCANNING_MFG_QR", "VERIFYING", "VALID"]
        # every screen after the first (DETECTED/POSITIONING share one) stayed up >= hold

        t = [datetime.fromisoformat(a).timestamp() for _, a in steps[1:7]]
        assert all(b - a >= hold * 0.9 for a, b in zip(t, t[1:])), list(zip(names[1:7], t))
