"""
Google Calendar provider.
Uses Google's OAuth2 device flow (TV & Limited Input Devices) for headless auth.
Requires a Google Cloud project with the Calendar API enabled and
OAuth2 credentials for a "TV and Limited Input devices" app.
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Optional

import aiohttp

from .calendar_base import CalendarProvider
from .config import settings
from . import settings_store
from .state_machine import DisplayState

logger = logging.getLogger(__name__)

DEVICE_AUTH_URL  = "https://oauth2.googleapis.com/device/code"
TOKEN_URL        = "https://oauth2.googleapis.com/token"
CALENDAR_API     = "https://www.googleapis.com/calendar/v3"
SCOPES           = "https://www.googleapis.com/auth/calendar.readonly"
TOKEN_CACHE_PATH = os.path.join(settings.data_dir, "google_token.json")


class GoogleCalendarProvider(CalendarProvider):

    def __init__(self):
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._device_code_info: Optional[dict] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._auth_complete = False
        self._load_token_cache()

    # ── Token cache ──────────────────────────────────────────────────────────

    def _load_token_cache(self):
        if os.path.exists(TOKEN_CACHE_PATH):
            try:
                with open(TOKEN_CACHE_PATH) as f:
                    data = json.load(f)
                self._access_token = data.get("access_token")
                self._refresh_token = data.get("refresh_token")
                if self._refresh_token:
                    self._auth_complete = True
                    logger.info("Loaded Google token cache")
            except Exception as e:
                logger.warning(f"Could not load Google token cache: {e}")

    def _save_token_cache(self):
        os.makedirs(settings.data_dir, exist_ok=True)
        with open(TOKEN_CACHE_PATH, "w") as f:
            json.dump({
                "access_token": self._access_token,
                "refresh_token": self._refresh_token,
            }, f)

    # ── Auth flow ─────────────────────────────────────────────────────────────

    def _client_id(self):
        return settings_store.get("google_client_id", settings.google_client_id)

    def _client_secret(self):
        return settings_store.get("google_client_secret", settings.google_client_secret)

    async def start_auth_flow(self) -> dict:
        async with aiohttp.ClientSession() as s:
            resp = await s.post(DEVICE_AUTH_URL, data={
                "client_id": self._client_id(),
                "scope": SCOPES,
            })
            data = await resp.json()
        self._device_code_info = data
        logger.info(f"Google auth: visit {data.get('verification_url')} "
                    f"and enter {data.get('user_code')}")
        # Normalise key names to match Microsoft's convention in the UI
        return {
            "user_code": data.get("user_code"),
            "verification_uri": data.get("verification_url"),
            "message": (f"Go to {data.get('verification_url')} "
                        f"and enter code: {data.get('user_code')}"),
        }

    async def poll_auth(self) -> bool:
        if not self._device_code_info:
            return False
        device_code = self._device_code_info.get("device_code")
        async with aiohttp.ClientSession() as s:
            resp = await s.post(TOKEN_URL, data={
                "client_id": self._client_id(),
                "client_secret": self._client_secret(),
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            })
            data = await resp.json()

        if "access_token" in data:
            self._access_token = data["access_token"]
            self._refresh_token = data.get("refresh_token", self._refresh_token)
            self._auth_complete = True
            self._device_code_info = None
            self._save_token_cache()
            logger.info("Google authentication successful")
            return True

        error = data.get("error", "")
        if error == "authorization_pending":
            return False  # normal — keep polling
        logger.warning(f"Google auth poll: {error}")
        return False

    async def _refresh_access_token(self) -> bool:
        if not self._refresh_token:
            return False
        try:
            async with aiohttp.ClientSession() as s:
                resp = await s.post(TOKEN_URL, data={
                    "client_id": self._client_id(),
                    "client_secret": self._client_secret(),
                    "refresh_token": self._refresh_token,
                    "grant_type": "refresh_token",
                })
                data = await resp.json()
            if "access_token" in data:
                self._access_token = data["access_token"]
                self._save_token_cache()
                return True
            logger.warning(f"Token refresh failed: {data.get('error')}")
            self._auth_complete = False
            return False
        except Exception as e:
            logger.error(f"Token refresh error: {e}")
            return False

    # ── Calendar API ──────────────────────────────────────────────────────────

    async def _get(self, path: str, retry: bool = True) -> Optional[dict]:
        if not self._access_token:
            return None
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession()
        try:
            async with self._session.get(
                f"{CALENDAR_API}{path}",
                headers={"Authorization": f"Bearer {self._access_token}"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                elif resp.status == 401 and retry:
                    logger.info("Google token expired, refreshing...")
                    if await self._refresh_access_token():
                        return await self._get(path, retry=False)
                    self._auth_complete = False
                else:
                    logger.warning(f"Google Calendar API {resp.status} for {path}")
        except Exception as e:
            logger.error(f"Google Calendar API error: {e}")
        return None

    async def get_current_state(self) -> DisplayState:
        if not self._auth_complete:
            return DisplayState.OFF

        now = datetime.now(settings.tz)
        now_iso = now.isoformat()

        # Fetch all relevant event types happening right now
        params = (
            f"?calendarId=primary"
            f"&timeMin={now_iso}&timeMax={now_iso}"
            f"&singleEvents=true"
            f"&eventTypes=default,outOfOffice,workingLocation"
            f"&fields=items(summary,status,transparency,eventType,"
            f"workingLocationProperties,start,end,allDayEvent)"
        )
        data = await self._get(f"/calendars/primary/events{params}")

        if data and data.get("items"):
            for event in data["items"]:
                event_type = event.get("eventType", "default")

                # Out of office event (Google native OOF)
                if event_type == "outOfOffice":
                    return DisplayState.OOF

                # Working location event
                if event_type == "workingLocation":
                    props = event.get("workingLocationProperties", {})
                    location_type = props.get("type", "")
                    if location_type == "homeOffice":
                        return DisplayState.WFH
                    if location_type == "officeLocation":
                        return DisplayState.OFF  # in office, no special status

                # Regular event — busy = in a meeting
                if event_type == "default":
                    # transparent = free (show-as free), opaque = busy
                    if event.get("transparency", "opaque") == "opaque":
                        if event.get("status", "confirmed") != "cancelled":
                            return DisplayState.IN_MEETING

        return DisplayState.OFF

    # ── Properties ───────────────────────────────────────────────────────────

    @property
    def is_authenticated(self) -> bool:
        return self._auth_complete

    @property
    def device_code_info(self) -> Optional[dict]:
        return self._device_code_info
