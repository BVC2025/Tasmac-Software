"""Android SMS gateway adapter (test phone in Local Server mode)."""

import json

import httpx

from app.providers import AndroidGatewaySmsProvider


async def test_sends_to_indian_number_with_basic_auth():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(202, json={"id": "abc123", "state": "Pending"})

    p = AndroidGatewaySmsProvider("http://phone:8080/", "sms", "secret", transport=httpx.MockTransport(handler))
    assert await p.send("9876543210", "hello") == (True, "abc123")
    assert seen["url"] == "http://phone:8080/message"
    assert seen["auth"].startswith("Basic ")
    assert seen["body"] == {"textMessage": {"text": "hello"}, "phoneNumbers": ["+919876543210"]}


async def test_gateway_errors_do_not_raise():
    refused = AndroidGatewaySmsProvider("http://phone:8080", "u", "p",
                                        transport=httpx.MockTransport(lambda r: httpx.Response(401)))
    assert await refused.send("9876543210", "x") == (False, "gateway HTTP 401")

    def down(request):
        raise httpx.ConnectError("no route")

    offline = AndroidGatewaySmsProvider("http://phone:8080", "u", "p", transport=httpx.MockTransport(down))
    sent, ref = await offline.send("9876543210", "x")
    assert not sent and "unreachable" in ref
