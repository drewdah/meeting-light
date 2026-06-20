"""
FastAPI web application — dashboard, overrides, and API.
"""

import asyncio
import base64
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..config import settings
from ..state_machine import DisplayState, CustomPayload, state_machine
from ..calendar_factory import get_calendar_provider
from ..ble_client import ble_client
from ..scheduler import graph_poll_loop, tick_loop
from .. import settings_store
from .. import log_buffer
from ..image_processor import render_screen

logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log_buffer.setup(level=logging.DEBUG)

    # Start background tasks
    tasks = [
        asyncio.create_task(ble_client.start(), name="ble"),
        asyncio.create_task(graph_poll_loop(), name="graph_poll"),
        asyncio.create_task(tick_loop(), name="tick"),
    ]

    yield

    # Cleanup
    for t in tasks:
        t.cancel()
    await ble_client.stop()


app = FastAPI(title="Meeting Light", lifespan=lifespan)

# Mount static files
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


# --- Template helpers ---

STATE_LABELS = {
    DisplayState.OFF: "Off",
    DisplayState.AVAILABLE: "Available",
    DisplayState.IN_MEETING: "In a Meeting",
    DisplayState.WFH: "Working From Home",
    DisplayState.OOF: "Out of Office",
    DisplayState.CUSTOM_TEXT: "Custom Message",
    DisplayState.SLEEPING: "Sleeping",
}

STATE_COLORS = {
    DisplayState.OFF: "gray",
    DisplayState.AVAILABLE: "yellow",
    DisplayState.IN_MEETING: "red",
    DisplayState.WFH: "blue",
    DisplayState.OOF: "purple",
    DisplayState.CUSTOM_TEXT: "yellow",
    DisplayState.SLEEPING: "gray",
}


def snapshot_to_dict(snap) -> dict:
    return {
        "state": snap.state.name,
        "state_label": STATE_LABELS.get(snap.state, snap.state.name),
        "state_color": STATE_COLORS.get(snap.state, "gray"),
        "calendar_state": snap.calendar_state.name,
        "calendar_label": STATE_LABELS.get(snap.calendar_state, snap.calendar_state.name),
        "source": snap.source,
        "battery_percent": snap.battery_percent,
        "battery_mv": snap.battery_mv,
        "charging": snap.charging,
        "vbus": snap.vbus,
        "pir_motion": snap.pir_motion,
        "ble_connected": snap.ble_connected,
        "last_seen": snap.last_seen.isoformat() if snap.last_seen else None,
        "override_expires": snap.override_expires.strftime("%I:%M %p").lstrip("0") if snap.override_expires else None,
        "authenticated": get_calendar_provider().is_authenticated,
        "device_code": get_calendar_provider().device_code_info,
        "calendar_provider": settings.calendar_provider,
    }


# --- Routes ---

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    snap = state_machine.get_snapshot()
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "snap": snapshot_to_dict(snap),
        "settings": settings_store.all_settings(),
    })


@app.get("/api/status")
async def api_status():
    snap = state_machine.get_snapshot()
    return snapshot_to_dict(snap)


@app.post("/api/override/preset")
async def set_preset_override(
    state: int = Form(...),
    duration_minutes: Optional[int] = Form(default=None)
):
    if state not in [s.value for s in DisplayState]:
        raise HTTPException(400, "Invalid state")
    ds = DisplayState(state)
    if ds == DisplayState.OFF:
        await state_machine.clear_override()
    else:
        await state_machine.set_override(ds, duration_minutes=duration_minutes)
    return {"ok": True}


@app.post("/api/preview")
async def preview_custom(
    text: str = Form(default=""),
    r: int = Form(default=255),
    g: int = Form(default=255),
    b: int = Form(default=0),
    emoji: str = Form(default=""),
    fg_r: int = Form(default=-1),
    fg_g: int = Form(default=-1),
    fg_b: int = Form(default=-1),
    font_size: int = Form(default=0),
):
    """Render the image and return it as base64 JPEG for preview — no BLE send."""
    jpeg_data = render_screen(
        emoji=emoji or None, text=text,
        bg_r=r, bg_g=g, bg_b=b, fg_r=fg_r, fg_g=fg_g, fg_b=fg_b,
        font_size_override=font_size,
    )
    b64 = base64.b64encode(jpeg_data).decode()
    return {"image": f"data:image/jpeg;base64,{b64}", "font_size": font_size}


@app.post("/api/override/custom")
async def set_custom_override(
    text: str = Form(...),
    r: int = Form(default=255),
    g: int = Form(default=255),
    b: int = Form(default=0),
    emoji: str = Form(default=""),
    fg_r: int = Form(default=-1),
    fg_g: int = Form(default=-1),
    fg_b: int = Form(default=-1),
    font_size: int = Form(default=0),
    duration_minutes: Optional[int] = Form(default=60)
):
    custom = CustomPayload(text=text[:200], r=r, g=g, b=b,
                           emoji=emoji, fg_r=fg_r, fg_g=fg_g, fg_b=fg_b,
                           font_size=font_size)
    await state_machine.set_override(DisplayState.CUSTOM_TEXT, custom=custom,
                                     duration_minutes=duration_minutes)
    return {"ok": True}


@app.delete("/api/override")
async def clear_override():
    await state_machine.clear_override()
    return {"ok": True}


@app.get("/api/logs")
async def get_logs(limit: int = 100):
    return log_buffer.get_logs(limit)


@app.delete("/api/logs")
async def clear_logs():
    log_buffer.clear_logs()
    return {"ok": True}


@app.post("/api/auth/start")
async def start_auth():
    try:
        flow = await get_calendar_provider().start_auth_flow()
    except Exception as e:
        logger.error(f"Auth start failed: {e}")
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=500, content={"error": str(e)})
    return {
        "user_code": flow.get("user_code"),
        "verification_uri": flow.get("verification_uri"),
        "message": flow.get("message"),
    }


@app.get("/api/calendar/info")
async def calendar_info():
    provider = get_calendar_provider()
    if not provider.is_authenticated or not hasattr(provider, "get_calendar_info"):
        return {}
    try:
        return await provider.get_calendar_info() or {}
    except Exception as e:
        logger.error(f"calendar_info error: {e}")
        return {}


@app.post("/api/auth/poll")
async def poll_auth():
    success = await get_calendar_provider().poll_auth()
    return {"authenticated": success}


@app.post("/api/ble/reconnect")
async def ble_reconnect():
    """Force-disconnect and reconnect BLE."""
    await ble_client.force_reconnect()
    return {"ok": True}


_device_muted = False

@app.post("/api/mute")
async def toggle_mute():
    global _device_muted
    _device_muted = not _device_muted
    await ble_client.set_mute(_device_muted)
    return {"muted": _device_muted}

@app.get("/api/mute")
async def get_mute():
    return {"muted": _device_muted}


@app.get("/api/settings")
async def get_settings():
    return settings_store.all_settings()


@app.post("/api/settings")
async def update_settings(
    business_hours_start: float = Form(...),
    business_hours_end: float = Form(...),
    timezone: str = Form(...),
    esp32_mac_address: str = Form(...),
    graph_poll_interval_seconds: int = Form(...),
    default_brightness: int = Form(...),
    calendar_provider: str = Form(default="microsoft"),
):
    settings_store.update({
        "business_hours_start": business_hours_start,
        "business_hours_end": business_hours_end,
        "timezone": timezone,
        "esp32_mac_address": esp32_mac_address,
        "graph_poll_interval_seconds": graph_poll_interval_seconds,
        "default_brightness": default_brightness,
        "calendar_provider": calendar_provider,
    })
    # Push brightness to device immediately
    await ble_client.set_brightness(default_brightness)
    # Trigger state machine tick to re-evaluate business hours
    await state_machine.tick()
    return {"ok": True}
