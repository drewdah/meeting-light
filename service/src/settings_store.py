"""
Persistent settings — overlays .env defaults with user-editable values
stored in data/settings.json.
"""

import json
import logging
import os
from typing import Any

from .config import settings as _base

logger = logging.getLogger(__name__)

SETTINGS_PATH = os.path.join(_base.data_dir, "settings.json")

# Keys that are user-editable via the UI
EDITABLE_KEYS = {
    "business_hours_start",
    "business_hours_end",
    "timezone",
    "esp32_mac_address",
    "graph_poll_interval_seconds",
    "default_brightness",
    "calendar_provider",
    "google_client_id",
    "google_client_secret",
}

_overrides: dict[str, Any] = {}


def _load():
    global _overrides
    os.makedirs(_base.data_dir, exist_ok=True)
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH) as f:
                _overrides = json.load(f)
            logger.info(f"Loaded settings overrides: {_overrides}")
        except Exception as e:
            logger.warning(f"Could not load settings.json: {e}")
            _overrides = {}


def _save():
    os.makedirs(_base.data_dir, exist_ok=True)
    with open(SETTINGS_PATH, "w") as f:
        json.dump(_overrides, f, indent=2)


def get(key: str, default=None):
    """Get a setting, preferring JSON override over .env default."""
    if key in _overrides:
        return _overrides[key]
    return getattr(_base, key, default)


def update(values: dict[str, Any]):
    """Update editable settings and persist to disk."""
    for k, v in values.items():
        if k in EDITABLE_KEYS:
            _overrides[k] = v
    _save()
    logger.info(f"Settings updated: {values}")


def all_settings() -> dict:
    """Return all settings as a dict for the UI."""
    return {
        "business_hours_start": get("business_hours_start"),
        "business_hours_end": get("business_hours_end"),
        "timezone": get("timezone"),
        "esp32_mac_address": get("esp32_mac_address"),
        "graph_poll_interval_seconds": get("graph_poll_interval_seconds"),
        "default_brightness": get("default_brightness"),
        "calendar_provider": get("calendar_provider", "microsoft"),
        "google_client_id": get("google_client_id", ""),
        "google_client_secret": get("google_client_secret", ""),
    }


# Load on import
_load()
