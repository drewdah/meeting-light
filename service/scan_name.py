import asyncio
from bleak import BleakScanner

async def scan():
    print("Scanning 10s for MeetingLight...")
    device = await BleakScanner.find_device_by_name("MeetingLight", timeout=10.0)
    if device:
        print(f"Found: {device.address}")
    else:
        print("Not found by name — all devices:")
        devices = await BleakScanner.discover(timeout=5.0)
        for d in sorted(devices, key=lambda x: x.rssi, reverse=True)[:10]:
            name = d.name if d.name else "(no name)"
            print(f"  {d.address}  {name}")

asyncio.run(scan())
