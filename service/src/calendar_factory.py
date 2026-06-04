"""
Returns the configured calendar provider singleton.
"""

from .config import settings
from .calendar_base import CalendarProvider

_provider: CalendarProvider | None = None


def get_calendar_provider() -> CalendarProvider:
    global _provider
    if _provider is None:
        p = settings.calendar_provider.lower()
        if p == "google":
            from .google_calendar import GoogleCalendarProvider
            _provider = GoogleCalendarProvider()
        else:
            from .graph_client import GraphClient
            _provider = GraphClient()
    return _provider
