"""
State machine for the meeting light.

Priority (highest wins):
  1. Manual override (set via web UI or buttons, with optional expiry)
  2. Calendar-detected state (from Graph API)
  3. Schedule-based state (sleeping outside business hours)
  4. Default: OFF
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import IntEnum
from typing import Optional, Callable

from .config import settings
from . import settings_store

logger = logging.getLogger(__name__)


class DisplayState(IntEnum):
    OFF = 0
    IN_MEETING = 1
    WFH = 2
    OOF = 3
    CUSTOM_TEXT = 4
    CUSTOM_IMAGE = 5
    SLEEPING = 6  # service-side only, sent as SLEEP command


@dataclass
class CustomPayload:
    """Payload for CUSTOM_TEXT state."""
    text: str
    r: int = 255       # background color
    g: int = 255
    b: int = 255
    emoji: str = ""    # emoji character(s) to render large, "" = none
    fg_r: int = -1     # text color, -1 = auto
    fg_g: int = -1
    fg_b: int = -1
    font_size: int = 0  # 0 = auto


@dataclass
class StateSnapshot:
    state: DisplayState
    custom: Optional[CustomPayload] = None
    override_expires: Optional[datetime] = None
    calendar_state: DisplayState = DisplayState.OFF
    battery_percent: Optional[int] = None
    battery_mv: Optional[int] = None
    ble_connected: bool = False
    last_seen: Optional[datetime] = None
    source: str = "default"  # "override", "calendar", "schedule", "default"


class StateMachine:
    def __init__(self):
        self._calendar_state: DisplayState = DisplayState.OFF
        self._override_state: Optional[DisplayState] = None
        self._override_custom: Optional[CustomPayload] = None
        self._override_expires: Optional[datetime] = None
        self._battery_percent: Optional[int] = None
        self._battery_mv: Optional[int] = None
        self._ble_connected: bool = False
        self._last_seen: Optional[datetime] = None
        self._lock = asyncio.Lock()
        self._on_transition: list[Callable] = []
        self._last_emitted: Optional[DisplayState] = None
        self._last_emitted_custom: Optional[CustomPayload] = None

    def on_transition(self, callback: Callable):
        """Register a callback for state transitions."""
        self._on_transition.append(callback)

    def _is_business_hours(self) -> bool:
        import zoneinfo
        tz = zoneinfo.ZoneInfo(settings_store.get("timezone", settings.timezone))
        now = datetime.now(tz)
        if now.weekday() not in settings.business_days:
            return False
        start = settings_store.get("business_hours_start", settings.business_hours_start)
        end = settings_store.get("business_hours_end", settings.business_hours_end)
        return start <= now.hour < end

    def _compute_state(self) -> tuple[DisplayState, Optional[CustomPayload], str]:
        """Compute the current effective state with priority."""
        now = datetime.now(settings.tz)

        # 1. Manual override
        if self._override_state is not None:
            if self._override_expires is None or now < self._override_expires:
                return self._override_state, self._override_custom, "override"
            else:
                # Override expired
                self._override_state = None
                self._override_custom = None
                self._override_expires = None
                logger.info("Override expired, reverting to calendar state")

        # 2. Outside business hours → sleep
        if not self._is_business_hours():
            return DisplayState.SLEEPING, None, "schedule"

        # 3. Calendar state
        if self._calendar_state != DisplayState.OFF:
            return self._calendar_state, None, "calendar"

        # 4. Default
        return DisplayState.OFF, None, "default"

    async def update_calendar_state(self, state: DisplayState):
        async with self._lock:
            if self._calendar_state != state:
                logger.info(f"Calendar state: {self._calendar_state.name} → {state.name}")
                self._calendar_state = state
            await self._maybe_emit()

    async def set_override(self, state: DisplayState, custom: Optional[CustomPayload] = None,
                           duration_minutes: Optional[int] = None):
        async with self._lock:
            self._override_state = state
            self._override_custom = custom
            if duration_minutes is not None:
                self._override_expires = datetime.now(settings.tz) + timedelta(minutes=duration_minutes)
            else:
                self._override_expires = None
            logger.info(f"Override set: {state.name}, expires: {self._override_expires}")
            await self._maybe_emit()

    async def clear_override(self):
        async with self._lock:
            self._override_state = None
            self._override_custom = None
            self._override_expires = None
            logger.info("Override cleared")
            await self._maybe_emit()

    async def update_battery(self, percent: int, mv: int, connected: bool):
        async with self._lock:
            self._battery_percent = percent
            self._battery_mv = mv
            self._ble_connected = connected
            self._last_seen = datetime.now(settings.tz)

    async def tick(self):
        """Call periodically to handle schedule transitions and override expiry."""
        async with self._lock:
            await self._maybe_emit()

    async def _maybe_emit(self):
        """Emit a transition event if the effective state changed."""
        state, custom, source = self._compute_state()

        state_changed = state != self._last_emitted
        custom_changed = custom != self._last_emitted_custom

        if state_changed or custom_changed:
            logger.info(f"State transition: {self._last_emitted} → {state.name} (source: {source})")
            self._last_emitted = state
            self._last_emitted_custom = custom
            for cb in self._on_transition:
                try:
                    await cb(state, custom)
                except Exception as e:
                    logger.error(f"Transition callback error: {e}")

    def get_snapshot(self) -> StateSnapshot:
        state, custom, source = self._compute_state()
        return StateSnapshot(
            state=state,
            custom=custom,
            override_expires=self._override_expires,
            calendar_state=self._calendar_state,
            battery_percent=self._battery_percent,
            battery_mv=self._battery_mv,
            ble_connected=self._ble_connected,
            last_seen=self._last_seen,
            source=source,
        )


# Global singleton
state_machine = StateMachine()
