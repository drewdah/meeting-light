"""
Background scheduler — polls Graph API and drives the state machine.
"""

import asyncio
import logging

from .config import settings
from .calendar_factory import get_calendar_provider
from .state_machine import state_machine

logger = logging.getLogger(__name__)


async def graph_poll_loop():
    """Poll calendar provider every N seconds and update state machine."""
    provider = get_calendar_provider()
    logger.info(f"Calendar poll loop started ({settings.calendar_provider})")
    while True:
        try:
            if provider.is_authenticated:
                state = await provider.get_current_state()
                await state_machine.update_calendar_state(state)
            else:
                logger.debug("Not authenticated, skipping poll")
        except Exception as e:
            logger.error(f"Calendar poll error: {e}")

        await asyncio.sleep(settings.graph_poll_interval_seconds)


async def tick_loop():
    """Tick the state machine every 30s to handle schedule transitions and override expiry."""
    while True:
        await asyncio.sleep(30)
        try:
            await state_machine.tick()
        except Exception as e:
            logger.error(f"State machine tick error: {e}")
