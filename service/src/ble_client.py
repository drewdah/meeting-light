"""
BLE central client — connects to the ESP32 and sends state commands.
Runs as a background asyncio task.
"""

import asyncio
import logging
import struct
from typing import Optional

from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic

from .config import settings
from .state_machine import DisplayState, CustomPayload, state_machine

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


class BLEClient:
    def __init__(self):
        self._client: Optional[BleakClient] = None
        self._cmd_char: Optional[BleakGATTCharacteristic] = None
        self._connected = False
        self._running = False
        self._pending_state: Optional[tuple[DisplayState, Optional[CustomPayload]]] = None
        self._lock = asyncio.Lock()

    async def start(self):
        """Start the BLE connection loop."""
        self._running = True
        state_machine.on_transition(self._on_state_transition)
        await self._connection_loop()

    async def stop(self):
        self._running = False
        if self._client and self._client.is_connected:
            await self._client.disconnect()

    async def _on_state_transition(self, state: DisplayState, custom: Optional[CustomPayload]):
        """Called by state machine on every transition — queue the command."""
        self._pending_state = (state, custom)
        if self._connected:
            await self._send_pending()

    async def _connection_loop(self):
        while self._running:
            try:
                await self._connect_and_run()
            except Exception as e:
                logger.warning(f"BLE connection error: {e}")
            if self._running:
                logger.info(f"Reconnecting in {settings.ble_reconnect_interval_seconds}s...")
                await asyncio.sleep(settings.ble_reconnect_interval_seconds)

    async def _connect_and_run(self):
        mac = settings.esp32_mac_address
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

            # Get command characteristic
            self._cmd_char = client.services.get_characteristic(BLE_CHAR_STATE_CMD_UUID)

            # Subscribe to status notifications
            status_char = client.services.get_characteristic(BLE_CHAR_DEV_STATUS_UUID)
            if status_char:
                await client.start_notify(status_char, self._on_status_notify)

            # Send current state immediately on connect
            await self._send_pending()

            # Keep alive loop
            while self._running and client.is_connected:
                await asyncio.sleep(30)
                await self._send_ping()

    def _on_disconnect(self, client: BleakClient):
        self._connected = False
        self._cmd_char = None
        logger.warning("BLE disconnected")

    async def _on_status_notify(self, char: BleakGATTCharacteristic, data: bytearray):
        """Parse status notification from ESP32: [state, batt%, charging, mv_lo, mv_hi]"""
        if len(data) < 5:
            return
        batt_pct = data[1]
        charging = bool(data[2])
        batt_mv = data[3] | (data[4] << 8)
        await state_machine.update_battery(batt_pct, batt_mv, True)
        logger.debug(f"Battery: {batt_pct}% ({batt_mv}mV) {'[charging]' if charging else ''}")

    async def _send_pending(self):
        if not self._pending_state or not self._cmd_char or not self._connected:
            return
        async with self._lock:
            state, custom = self._pending_state
            await self._send_state(state, custom)

    async def _send_state(self, state: DisplayState, custom: Optional[CustomPayload]):
        if not self._cmd_char or not self._client:
            return
        try:
            if state == DisplayState.SLEEPING:
                await self._write([OP_SLEEP])
                logger.info("Sent: SLEEP")
            elif state == DisplayState.CUSTOM_TEXT and custom:
                text_bytes = custom.text.encode("utf-8")[:200]
                payload = bytes([OP_SET_CUSTOM_TEXT, custom.r, custom.g, custom.b]) + text_bytes
                await self._write(payload)
                logger.info(f"Sent: CUSTOM_TEXT '{custom.text}'")
            elif state in (DisplayState.OFF, DisplayState.IN_MEETING,
                           DisplayState.WFH, DisplayState.OOF):
                await self._write([OP_SET_PRESET, int(state)])
                logger.info(f"Sent: PRESET {state.name}")
        except Exception as e:
            logger.error(f"BLE write error: {e}")
            self._connected = False

    async def _send_ping(self):
        if not self._cmd_char or not self._client:
            return
        try:
            await self._write([OP_PING])
        except Exception as e:
            logger.warning(f"Ping failed: {e}")
            self._connected = False

    async def _write(self, data: list[int] | bytes):
        if self._client and self._cmd_char:
            await self._client.write_gatt_char(self._cmd_char, bytes(data), response=False)

    @property
    def is_connected(self) -> bool:
        return self._connected


ble_client = BLEClient()
