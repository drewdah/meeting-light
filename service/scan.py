import asyncio
from bleak import BleakScanner

async def scan():
    print("Scanning for BLE devices (5 seconds)...")
    devices = await BleakScanner.discover(timeout=5.0)
    for d in sorted(devices, key=lambda x: x.rssi, reverse=True):
        name = d.name if d.name else "(no name)"
        print(f"  {d.address}  RSSI:{d.rssi:4d}  {name}")

asyncio.run(scan())
