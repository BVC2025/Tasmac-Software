"""Plays the kiosk UI against a running machine (machine.dev.yaml) to test
machine <-> backend end to end, using only the local kiosk API + WebSocket.

    python tools/kiosk_smoke.py --bottles 13
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

import httpx
import websockets

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rvm.services.sim_feed import SimBottleFeed  # noqa: E402


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--api", default="http://127.0.0.1:8765")
    p.add_argument("--bottles", type=int, default=13)
    a = p.parse_args()
    feed = SimBottleFeed.from_yaml(ROOT / "config/sim_bottles.yaml")
    ws_url = a.api.replace("http", "ws", 1) + "/ws"

    async with httpx.AsyncClient(base_url=a.api, timeout=10) as http, websockets.connect(ws_url) as ws:
        snap = json.loads(await ws.recv())
        print(f"Connected: machine={snap['machine_id']} state={snap['state']}")
        results = []
        for _ in range(a.bottles):
            # wait until READY
            while (await http.get("/api/status")).json()["state"] != "READY":
                await asyncio.sleep(0.2)
            await asyncio.sleep(0.5)
            r = (await http.post("/api/sim/insert")).json()
            name = r["bottle"]
            bottle = next(b for b in feed.bottles if b.name == name)
            while True:
                ev = json.loads(await ws.recv())
                if ev["type"] == "state" and ev["state"] == "SELECT_REFUND_METHOD":
                    await asyncio.sleep(0.3)
                    body = {"cancel": True} if bottle.destination is None else {"value": bottle.destination}
                    await http.post("/api/customer/destination", json=body)
                elif ev["type"] == "state" and ev["state"] == "CONFIRMING":
                    await asyncio.sleep(0.3)
                    await http.post("/api/customer/confirm", json={"ok": True})
                elif ev["type"] == "session_ended":
                    results.append((name, ev["outcome"], ev["reason"], ev.get("txn_id")))
                    print(f"  {name:45s} {ev['outcome']:9s} {ev['reason'] or ''} {ev.get('txn_id') or ''}")
                    break
        print(f"Done: {len(results)} sessions")


if __name__ == "__main__":
    asyncio.run(main())
