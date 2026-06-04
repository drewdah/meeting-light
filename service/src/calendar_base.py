"""
Abstract base class for calendar providers.
Implement this to add new calendar backends (Microsoft, Google, Apple, etc.)
"""

from abc import ABC, abstractmethod
from typing import Optional
from .state_machine import DisplayState


class CalendarProvider(ABC):

    @abstractmethod
    async def get_current_state(self) -> DisplayState:
        """Return the current display state based on calendar data."""
        ...

    @abstractmethod
    async def start_auth_flow(self) -> dict:
        """
        Start the authentication flow.
        Returns a dict with at minimum:
          - user_code: str
          - verification_uri: str
          - message: str (human-readable instruction)
        """
        ...

    @abstractmethod
    async def poll_auth(self) -> bool:
        """
        Poll for auth completion. Returns True when authenticated.
        Call repeatedly (every ~5s) until True or timeout.
        """
        ...

    @property
    @abstractmethod
    def is_authenticated(self) -> bool:
        """True if we have valid credentials."""
        ...

    @property
    @abstractmethod
    def device_code_info(self) -> Optional[dict]:
        """Current pending device code info, or None."""
        ...
