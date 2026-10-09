"""Service hours: set in the admin portal, handed to the machine with every heartbeat."""

API = "/api/admin/v1"


async def test_service_hours_reach_the_machine(client, machine, operator_h):
    assert (await machine.post("/heartbeat", {"state": "READY"})).json() == {"service_hours": None}   # 24 hours

    hours = [{"start": "10:00", "end": "11:30"}, {"start": "17:00", "end": "21:00"}]
    r = await client.patch(f"{API}/machines/RVM-T1", headers=operator_h, json={"service_hours": hours})
    assert r.status_code == 200 and r.json()["service_hours"] == hours
    assert (await machine.post("/heartbeat", {"state": "READY"})).json() == {"service_hours": hours}

    r = await client.patch(f"{API}/machines/RVM-T1", headers=operator_h, json={"service_hours": []})
    assert r.json()["service_hours"] is None


async def test_service_hours_validation(client, operator_h, viewer_h):
    bad = [
        [{"start": "25:00", "end": "11:00"}],
        [{"start": "10:00", "end": "10:00"}],
        [{"start": "10:00", "end": "11:00"}] * 5,
    ]
    for hours in bad:
        r = await client.patch(f"{API}/machines/RVM-T1", headers=operator_h, json={"service_hours": hours})
        assert r.status_code == 422, hours
    r = await client.patch(f"{API}/machines/RVM-T1", headers=viewer_h, json={"service_hours": []})
    assert r.status_code == 403
