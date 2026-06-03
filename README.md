# Meeting Light

A professional office status display for a Waveshare ESP32-C6 1.8" Touch AMOLED, mounted in an office window. Shows your current status — In a Meeting, Working From Home, Out of Office, or a custom message — to coworkers passing by.

## How It Works

A Linux mini PC at your desk polls your Outlook calendar via the Microsoft Graph API and pushes status updates to the ESP32 over BLE. A web UI (accessible remotely via Tailscale) lets you set manual overrides, custom messages, and upload images.

```
ESP32-C6 AMOLED  <──BLE──>  Mini PC Service  <──Graph API──>  Microsoft 365
                                   │
                             Web UI :8080  <──Tailscale──  Remote access
```

## Project Structure

```
firmware/       # ESP32-C6 firmware (PlatformIO + Arduino)
service/        # Mini PC service (Python + FastAPI + Docker)
docs/           # Architecture plan and documentation
```

## Display States

| State | Description |
|-------|-------------|
| In a Meeting | Bold color display, screen stays on |
| Working From Home | Dark background, duty-cycled to save battery |
| Out of Office | Dark background, duty-cycled to save battery |
| Custom | User-defined text + background color, or uploaded image |
| Off | Screen off, deep sleep |

## Hardware

- [Waveshare ESP32-C6 Touch AMOLED 1.8"](https://www.waveshare.com/esp32-c6-touch-amoled-1.8.htm) — 368×448 display, BLE 5, two hardware buttons, LiPo connector
- Linux mini PC (always-on, at desk)
- LiPo battery (~1000mAh), target 1 week battery life

## Getting Started

See [docs/plan.md](docs/plan.md) for the full architecture and implementation plan.

### Firmware

Requires [PlatformIO](https://platformio.org/) with the pioarduino platform fork (for ESP32-C6 Arduino support). Recommended: use the PlatformIO VS Code extension.

```bash
cd firmware
pio run              # build
pio run -t upload    # flash via USB-C
```

### Service

```bash
cd service
docker compose up
```

On first run, the service will display a Microsoft device code URL. Complete authentication in your browser, then the service will begin polling your calendar automatically.
