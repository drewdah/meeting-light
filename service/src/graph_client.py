"""
Microsoft Graph API client.
Polls calendar and presence to determine display state.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import aiohttp
import msal

from .calendar_base import CalendarProvider
from .config import settings
from .state_machine import DisplayState

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
SCOPES = ["Calendars.Read", "Presence.Read", "User.Read", "MailboxSettings.Read"]
TOKEN_CACHE_PATH = os.path.join(settings.data_dir, "token_cache.json")


class GraphClient(CalendarProvider):
    def __init__(self):
        self._token_cache = msal.SerializableTokenCache()
        self._app: Optional[msal.PublicClientApplication] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._device_code_info: Optional[dict] = None
        self._auth_complete = False

        # Load cached tokens
        if os.path.exists(TOKEN_CACHE_PATH):
            with open(TOKEN_CACHE_PATH, "r") as f:
                self._token_cache.deserialize(f.read())
            self._auth_complete = True

    def _save_cache(self):
        if self._token_cache.has_state_changed:
            os.makedirs(settings.data_dir, exist_ok=True)
            with open(TOKEN_CACHE_PATH, "w") as f:
                f.write(self._token_cache.serialize())

    def _get_app(self) -> msal.PublicClientApplication:
        if not self._app:
            self._app = msal.PublicClientApplication(
                client_id=settings.ms_graph_client_id,
                authority=f"https://login.microsoftonline.com/{settings.ms_graph_tenant_id}",
                token_cache=self._token_cache,
            )
        return self._app

    # CalendarProvider interface aliases
    async def start_auth_flow(self) -> dict:
        return await self.start_device_code_flow()

    async def poll_auth(self) -> bool:
        return await self.poll_device_code()

    async def start_device_code_flow(self) -> dict:
        """Start device code auth flow. Returns dict with user_code and verification_uri."""
        app = self._get_app()
        flow = app.initiate_device_flow(scopes=SCOPES)
        self._device_code_info = flow
        logger.info(f"Device code auth: go to {flow['verification_uri']} and enter {flow['user_code']}")
        return flow

    async def poll_device_code(self) -> bool:
        """Poll for device code completion. Returns True when authenticated."""
        if not self._device_code_info:
            return False
        app = self._get_app()
        result = app.acquire_token_by_device_flow(self._device_code_info)
        if "access_token" in result:
            self._save_cache()
            self._auth_complete = True
            self._device_code_info = None
            logger.info("Authentication successful")
            return True
        logger.warning(f"Device code poll: {result.get('error_description', 'pending')}")
        return False

    def _get_token(self) -> Optional[str]:
        app = self._get_app()
        accounts = app.get_accounts()
        if not accounts:
            return None
        result = app.acquire_token_silent(scopes=SCOPES, account=accounts[0])
        if result and "access_token" in result:
            self._save_cache()
            return result["access_token"]
        return None

    async def _get(self, path: str) -> Optional[dict]:
        token = self._get_token()
        if not token:
            return None
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession()
        try:
            async with self._session.get(
                f"{GRAPH_BASE}{path}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                elif resp.status == 401:
                    logger.warning("Graph API 401 — token expired, re-auth needed")
                    self._auth_complete = False
                else:
                    logger.warning(f"Graph API {resp.status} for {path}")
                return None
        except Exception as e:
            logger.error(f"Graph API error: {e}")
            return None

    async def get_current_state(self) -> DisplayState:
        """Determine the display state from calendar and presence."""
        if not self._auth_complete:
            return DisplayState.OFF

        now = datetime.now(settings.tz)
        now_iso = now.isoformat()

        # --- Check calendar events happening right now ---
        data = await self._get(
            f"/me/calendarView"
            f"?startDateTime={now_iso}&endDateTime={now_iso}"
            f"&$select=subject,showAs,isAllDay,location"
            f"&$filter=showAs ne 'free' and showAs ne 'unknown'"
            f"&$top=10"
        )

        if data and data.get("value"):
            for event in data["value"]:
                show_as = event.get("showAs", "").lower()

                if show_as == "oof":
                    return DisplayState.OOF

                # Non-all-day busy/tentative event = in a meeting
                if not event.get("isAllDay") and show_as in ("busy", "tentative", "workingelsewhere"):
                    return DisplayState.IN_MEETING

                # All-day event with WFH location
                if event.get("isAllDay"):
                    loc = event.get("location", {}).get("displayName", "").lower()
                    subject = event.get("subject", "").lower()
                    if any(w in loc or w in subject for w in ("home", "remote", "wfh")):
                        return DisplayState.WFH

        # --- Check OOF via mailbox settings ---
        mailbox = await self._get("/me/mailboxSettings")
        if mailbox:
            oof = mailbox.get("automaticRepliesSetting", {})
            if oof.get("status") == "alwaysEnabled":
                return DisplayState.OOF
            if oof.get("status") == "scheduled":
                # Check if we're within the scheduled window
                start = oof.get("scheduledStartDateTime", {}).get("dateTime")
                end = oof.get("scheduledEndDateTime", {}).get("dateTime")
                if start and end:
                    oof_start = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
                    oof_end = datetime.fromisoformat(end).replace(tzinfo=timezone.utc)
                    if oof_start <= now.astimezone(timezone.utc) <= oof_end:
                        return DisplayState.OOF

        return DisplayState.OFF

    @property
    def is_authenticated(self) -> bool:
        return self._auth_complete

    @property
    def device_code_info(self) -> Optional[dict]:
        return self._device_code_info


graph_client = GraphClient()
