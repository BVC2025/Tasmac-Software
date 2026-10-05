"""Customer interaction (refund method + confirmation).

In production this is the touchscreen UI (React kiosk over WebSocket).
`AutoCustomer` plays the customer in simulation using the bottle feed.
"""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass

from .backend import Destination
from .sim_feed import SimBottleFeed


@dataclass
class RefundInput:
    value: str                       # UPI ID or mobile number (from QR scan, voice or keypad)
    sms_mobile: str | None = None    # optional number for the SMS receipt
    source: str = "keypad"           # qr | voice | keypad


class CustomerInterface(ABC):
    @abstractmethod
    async def get_destination(self, session_id: str, attempt: int) -> RefundInput | None:
        """None = customer cancelled."""

    @abstractmethod
    async def confirm(self, session_id: str, dest: Destination, display_name: str, amount_paise: int) -> bool: ...


class AutoCustomer(CustomerInterface):
    def __init__(self, feed: SimBottleFeed, think_time_s: float = 0.2):
        self.feed = feed
        self.think_time_s = think_time_s

    async def get_destination(self, session_id: str, attempt: int) -> RefundInput | None:
        await asyncio.sleep(self.think_time_s)
        dest = self.feed.current.destination
        return RefundInput(dest) if dest is not None else None

    async def confirm(self, session_id: str, dest: Destination, display_name: str, amount_paise: int) -> bool:
        await asyncio.sleep(self.think_time_s)
        return True


class WebCustomer(CustomerInterface):
    """Customer input from the kiosk touchscreen (via the local API).

    The orchestrator awaits a future; the kiosk resolves it with a POST.
    Input that arrives when the machine is not asking for it is refused.
    """

    def __init__(self):
        self._dest: asyncio.Future | None = None
        self._confirm: asyncio.Future | None = None

    @property
    def waiting_for(self) -> str | None:
        if self._dest and not self._dest.done():
            return "destination"
        if self._confirm and not self._confirm.done():
            return "confirm"
        return None

    async def get_destination(self, session_id: str, attempt: int) -> RefundInput | None:
        self._dest = asyncio.get_running_loop().create_future()
        try:
            return await self._dest
        finally:
            self._dest = None

    async def confirm(self, session_id: str, dest: Destination, display_name: str, amount_paise: int) -> bool:
        self._confirm = asyncio.get_running_loop().create_future()
        try:
            return await self._confirm
        finally:
            self._confirm = None

    def submit_destination(self, value: RefundInput | None) -> bool:
        """value=None means the customer pressed cancel."""
        if self.waiting_for != "destination":
            return False
        self._dest.set_result(value)
        return True

    def submit_confirm(self, ok: bool) -> bool:
        if self.waiting_for != "confirm":
            return False
        self._confirm.set_result(ok)
        return True
