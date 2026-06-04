"""
FastAPI web application — dashboard, overrides, and API.
"""

import asyncio
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
from ..graph_client import graph_client
from ..ble_client import ble_client
from ..scheduler import graph_poll_loop, tick_loop
from .. import settings_store

logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

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
    DisplayState.OFF: "Available / Off",
    DisplayState.IN_MEETING: "In a Meeting",
    DisplayState.WFH: "Working From Home",
    DisplayState.OOF: "Out of Office",
    DisplayState.CUSTOM_TEXT: "Custom Message",
    DisplayState.SLEEPING: "Sleeping",
}

STATE_COLORS = {
    DisplayState.OFF: "gray",
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
        "ble_connected": snap.ble_connected,
        "last_seen": snap.last_seen.strftime("%H:%M:%S") if snap.last_seen else None,
        "override_expires": snap.override_expires.strftime("%H:%M") if snap.override_expires else None,
        "authenticated": graph_client.is_authenticated,
        "device_code": graph_client.device_code_info,
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


@app.post("/api/override/custom")
async def set_custom_override(
    text: str = Form(...),
    r: int = Form(default=255),
    g: int = Form(default=255),
    b: int = Form(default=0),
    icon_id: int = Form(default=0),
    duration_minutes: Optional[int] = Form(default=60)
):
    custom = CustomPayload(text=text[:200], r=r, g=g, b=b, icon_id=icon_id)
    await state_machine.set_override(DisplayState.CUSTOM_TEXT, custom=custom,
                                     duration_minutes=duration_minutes)
    return {"ok": True}


@app.delete("/api/override")
async def clear_override():
    await state_machine.clear_override()
    return {"ok": True}


@app.post("/api/auth/start")
async def start_auth():
    flow = await graph_client.start_device_code_flow()
    return {
        "user_code": flow.get("user_code"),
        "verification_uri": flow.get("verification_uri"),
        "message": flow.get("message"),
    }


@app.post("/api/auth/poll")
async def poll_auth():
    success = await graph_client.poll_device_code()
    return {"authenticated": success}


@app.post("/api/ble/reconnect")
async def ble_reconnect():
    """Force-disconnect and reconnect BLE."""
    await ble_client.force_reconnect()
    return {"ok": True}


@app.get("/api/settings")
async def get_settings():
    return settings_store.all_settings()


@app.post("/api/settings")
async def update_settings(
    business_hours_start: int = Form(...),
    business_hours_end: int = Form(...),
    timezone: str = Form(...),
    esp32_mac_address: str = Form(...),
    graph_poll_interval_seconds: int = Form(...),
    default_brightness: int = Form(...),
):
    settings_store.update({
        "business_hours_start": business_hours_start,
        "business_hours_end": business_hours_end,
        "timezone": timezone,
        "esp32_mac_address": esp32_mac_address,
        "graph_poll_interval_seconds": graph_poll_interval_seconds,
        "default_brightness": default_brightness,
    })
    # Trigger state machine tick to re-evaluate business hours
    await state_machine.tick()
    return {"ok": True}
