"""
BLE central client — connects to the ESP32 and sends state commands.
Runs as a background asyncio task. All BLE writes happen inside the
connection loop task to avoid cross-task issues.
"""

import asyncio
import logging
import struct
import zlib
from typing import Optional

from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic

from .config import settings
from .state_machine import DisplayState, CustomPayload, state_machine
from .image_processor import render_screen

logger = logging.getLogger(__name__)

# BLE UUIDs (must match firmware config.h)
BLE_SERVICE_UUID         = "00001000-4d45-4554-4c49-544500000001"
BLE_CHAR_STATE_CMD_UUID  = "00001001-4d45-4554-4c49-544500000001"
BLE_CHAR_DEV_STATUS_UUID = "00001002-4d45-4554-4c49-544500000001"

# Opcodes (must match firmware config.h)
OP_SET_PRESET      = 0x01
OP_SET_CUSTOM_TEXT = 0x02
OP_SLEEP           = 0x03
OP_IMAGE_START     = 0x05
OP_IMAGE_CHUNK     = 0x06
OP_IMAGE_END       = 0x07
OP_SET_BRIGHTNESS  = 0x08
OP_PING            = 0x09
OP_SET_ICON_TEXT   = 0x0A

RECONNECT_INTERVAL = 3  # seconds between reconnect attempts
KEEPALIVE_INTERVAL = 30  # seconds between pings when idle

# Preset state rendering config: (emoji, text, bg_r, bg_g, bg_b)
_PRESET_CONFIG = {
    DisplayState.IN_MEETING: ("🔴", "In a\nMeeting",      200, 20,  20),
    DisplayState.WFH:        ("🏠", "Working\nFrom Home",  10,  30, 120),
    DisplayState.OOF:        ("✈️", "Out of\nOffice",      60,  0,  120),
}


class BLEClient:
    def __init__(self):
        self._client: Optional[BleakClient] = None
        self._cmd_char: Optional[BleakGATTCharacteristic] = None
        self._connected = False
        self._running = False
        self._pending_state: Optional[tuple[DisplayState, Optional[CustomPayload]]] = None
        # Event set whenever there's a pending state to send
        self._send_event: Optional[asyncio.Event] = None

    async def start(self):
        self._running = True
        self._send_event = asyncio.Event()
        state_machine.on_transition(self._on_state_transition)
        await self._connection_loop()

    async def stop(self):
        self._running = False
        if self._client and self._client.is_connected:
            await self._client.disconnect()

    async def _on_state_transition(self, state: DisplayState, custom: Optional[CustomPayload]):
        """Called by state machine — store pending state and wake connection loop."""
        self._pending_state = (state, custom)
        if self._send_event:
            self._send_event.set()

    async def _connection_loop(self):
        while self._running:
            try:
                await self._connect_and_run()
            except Exception as e:
                logger.warning(f"BLE connection error: {e}")
            if self._running:
                logger.info(f"Reconnecting in {RECONNECT_INTERVAL}s...")
                await asyncio.sleep(RECONNECT_INTERVAL)

    async def _connect_and_run(self):
        mac = settings_store_get_mac()
        if not mac:
            logger.info("No ESP32 MAC configured, scanning for 'MeetingLight'...")
            device = await BleakScanner.find_device_by_name("MeetingLight", timeout=10)
            if not device:
                logger.warning("MeetingLight device not found")
                return
            mac = device.address
            logger.info(f"Found MeetingLight at {mac}")

        logger.info(f"Connecting to {mac}...")
        async with BleakClient(mac, disconnected_callback=self._on_disconnect) as client:
            self._client = client
            self._connected = True
            logger.info("BLE connected")

            # Find command characteristic
            self._cmd_char = client.services.get_characteristic(BLE_CHAR_STATE_CMD_UUID)
            if self._cmd_char:
                logger.info("Command characteristic found")
            else:
                logger.error("Command characteristic NOT found! Available:")
                for svc in client.services:
                    for char in svc.characteristics:
                        logger.error(f"  {char.uuid} [{','.join(char.properties)}]")
                return

            # Subscribe to status notifications
            status_char = client.services.get_characteristic(BLE_CHAR_DEV_STATUS_UUID)
            if status_char:
                await client.start_notify(status_char, self._on_status_notify)

            # Send current state immediately on connect
            if self._pending_state:
                await self._send_pending(client)

            # Main send loop — wait for events, send when triggered
            while self._running and client.is_connected:
                try:
                    await asyncio.wait_for(
                        self._send_event.wait(),
                        timeout=KEEPALIVE_INTERVAL
                    )
                    self._send_event.clear()
                    if self._pending_state:
                        await self._send_pending(client)
                except asyncio.TimeoutError:
                    # Keepalive ping
                    await self._write(client, [OP_PING])

    def _on_disconnect(self, client: BleakClient):
        self._connected = False
        self._cmd_char = None
        logger.warning("BLE disconnected — will reconnect")
        # Wake connection loop so it exits the wait and reconnects
        if self._send_event:
            self._send_event.set()

    async def _on_status_notify(self, char: BleakGATTCharacteristic, data: bytearray):
        if len(data) < 5:
            return
        batt_pct = data[1]
        charging = bool(data[2])
        batt_mv = data[3] | (data[4] << 8)
        await state_machine.update_battery(batt_pct, batt_mv, True)
        logger.debug(f"Battery: {batt_pct}% ({batt_mv}mV) {'[charging]' if charging else ''}")

    async def _send_pending(self, client: BleakClient):
        if not self._pending_state:
            return
        state, custom = self._pending_state
        await self._send_state(client, state, custom)

    async def _send_state(self, client: BleakClient, state: DisplayState,
                          custom: Optional[CustomPayload]):
        try:
            if state == DisplayState.SLEEPING:
                await self._write(client, [OP_SLEEP])
                logger.info("Sent: SLEEP")

            elif state == DisplayState.CUSTOM_TEXT and custom:
                if custom.emoji:
                    # Render full screen JPEG and transfer via image protocol
                    await self._send_screen_image(client, custom)
                else:
                    text_bytes = custom.text.encode("utf-8")[:200]
                    # Include fg color: [OP][r][g][b][fg_r][fg_g][fg_b][text]
                    # Use auto fg (255,255,255) if not set
                    fg_r = custom.fg_r if custom.fg_r >= 0 else 255
                    fg_g = custom.fg_g if custom.fg_g >= 0 else 255
                    fg_b = custom.fg_b if custom.fg_b >= 0 else 255
                    payload = bytes([OP_SET_CUSTOM_TEXT, custom.r, custom.g, custom.b,
                                     fg_r, fg_g, fg_b]) + text_bytes
                    await self._write(client, payload)
                    logger.info(f"Sent: CUSTOM_TEXT '{custom.text}'")

            elif state == DisplayState.OFF:
                await self._write(client, [OP_SET_PRESET, int(state)])
                logger.info("Sent: PRESET OFF")

            elif state in (DisplayState.IN_MEETING, DisplayState.WFH, DisplayState.OOF):
                # Render preset states as full-screen JPEG with emoji + text
                preset_payload = _PRESET_CONFIG.get(state)
                if preset_payload:
                    emoji, text, bg_r, bg_g, bg_b = preset_payload
                    fake_custom = CustomPayload(text=text, r=bg_r, g=bg_g, b=bg_b,
                                                emoji=emoji, fg_r=-1, fg_g=-1, fg_b=-1)
                    await self._send_screen_image(client, fake_custom)
                    logger.info(f"Sent: PRESET {state.name} as image")
                else:
                    await self._write(client, [OP_SET_PRESET, int(state)])
                    logger.info(f"Sent: PRESET {state.name}")

        except Exception as e:
            logger.error(f"BLE write error: {e} — disconnecting to force reconnect")
            self._connected = False
            await client.disconnect()

    async def _send_screen_image(self, client: BleakClient, custom: CustomPayload):
        """Render and transfer a full-screen JPEG via IMAGE_START/CHUNK/END."""
        logger.info(f"Rendering screen: emoji={custom.emoji!r} text={custom.text!r}")
        jpeg_data = render_screen(
            emoji=custom.emoji or None,
            text=custom.text,
            bg_r=custom.r, bg_g=custom.g, bg_b=custom.b,
            fg_r=custom.fg_r, fg_g=custom.fg_g, fg_b=custom.fg_b,
        )

        total = len(jpeg_data)
        crc = zlib.crc32(jpeg_data) & 0xFFFFFFFF
        logger.info(f"Sending {total} byte JPEG in chunks...")

        # IMAGE_START: [opcode(1)][total_size(4)][w(2)][h(2)][format(1)]
        # format 1 = full-screen JPEG
        from .image_processor import SCREEN_W, SCREEN_H
        start_payload = struct.pack("<BIHHB", OP_IMAGE_START, total,
                                    SCREEN_W, SCREEN_H, 1)
        await self._write(client, start_payload)
        await asyncio.sleep(0.05)

        # IMAGE_CHUNK: [opcode(1)][chunk_idx(2)][data...]
        chunk_size = 200  # conservative for write-without-response reliability
        chunk_idx = 0
        for offset in range(0, total, chunk_size):
            chunk = jpeg_data[offset:offset + chunk_size]
            header = struct.pack("<BH", OP_IMAGE_CHUNK, chunk_idx)
            await self._write(client, header + chunk)
            chunk_idx += 1
            # Small yield to avoid flooding the BLE stack
            if chunk_idx % 10 == 0:
                await asyncio.sleep(0.01)

        # IMAGE_END: [opcode(1)][crc32(4)]
        await asyncio.sleep(0.05)
        end_payload = struct.pack("<BI", OP_IMAGE_END, crc)
        await self._write(client, end_payload)
        logger.info(f"Image transfer complete: {chunk_idx} chunks")

    async def _write(self, client: BleakClient, data: list[int] | bytes):
        if self._cmd_char:
            await client.write_gatt_char(self._cmd_char, bytes(data), response=False)

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def force_reconnect(self):
        """Force disconnect — connection loop will reconnect automatically."""
        self._connected = False
        if self._client and self._client.is_connected:
            await self._client.disconnect()
        if self._send_event:
            self._send_event.set()


def settings_store_get_mac() -> str:
    """Get MAC from settings store (allows runtime updates)."""
    try:
        from . import settings_store
        return settings_store.get("esp32_mac_address", settings.esp32_mac_address)
    except Exception:
        return settings.esp32_mac_address


ble_client = BLEClient()
