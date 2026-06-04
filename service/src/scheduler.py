"""
Background scheduler — polls Graph API and drives the state machine.
"""

import asyncio
import logging

from .config import settings
from .graph_client import graph_client
from .state_machine import state_machine

logger = logging.getLogger(__name__)


async def graph_poll_loop():
    """Poll Graph API every N seconds and update state machine."""
    logger.info("Graph poll loop started")
    while True:
        try:
            if graph_client.is_authenticated:
                state = await graph_client.get_current_state()
                await state_machine.update_calendar_state(state)
            else:
                logger.debug("Not authenticated, skipping poll")
        except Exception as e:
            logger.error(f"Graph poll error: {e}")

        await asyncio.sleep(settings.graph_poll_interval_seconds)


async def tick_loop():
    """Tick the state machine every 30s to handle schedule transitions and override expiry."""
    while True:
        await asyncio.sleep(30)
        try:
            await state_machine.tick()
        except Exception as e:
            logger.error(f"State machine tick error: {e}")
