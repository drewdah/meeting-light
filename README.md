# Meeting Light

<p align="center">
  <img src="assets/screenshot-1.png" width="45%" alt="Meeting Light in use" />
  <img src="assets/screenshot-2.jpg" width="45%" alt="Meeting Light web UI" />
</p>

A professional office status display for a Waveshare ESP32-C6 1.8" Touch AMOLED, mounted in an office window. Shows your current status — In a Meeting, Working From Home, Out of Office, or a custom message — to coworkers passing by.

## How It Works

A mini PC at your desk polls your Outlook calendar via the Microsoft Graph API and pushes status updates to the ESP32 over BLE. A web UI (accessible remotely via Tailscale) lets you set manual overrides, compose custom messages with emoji, and preview what will appear on screen before sending.

```
ESP32-C6 AMOLED  <──BLE──>  Mini PC Service  <──Graph API──>  Microsoft 365
                                   │
                             Web UI :8080  <──Tailscale──  Remote access
```

## Features

- **Automatic detection** — polls Outlook calendar every 60s for meetings, WFH location, and Out of Office status
- **Emoji + text display** — full-resolution images rendered service-side with any emoji and custom text, transferred to the display over BLE
- **Full emoji picker** — pick any emoji from the web UI; no pre-compilation required
- **Preview before send** — see exactly what will appear on screen, with font size +/− controls
- **Manual overrides** — preset buttons (In a Meeting, WFH, OOF) or custom message with background color and emoji
- **Override expiry** — set duration (30 min, 1 hr, end of day, etc.) before reverting to calendar state
- **Business hours scheduling** — device sleeps outside M–F 9–5; configurable in the web UI
- **Battery monitoring** — live battery % and voltage reported back via BLE notification
- **Real-time log panel** — connection and transfer logs visible in the web UI
- **Remote access** — web UI accessible via Tailscale from anywhere

## Display States

| State | Emoji | Background |
|-------|-------|------------|
| In a Meeting | 🔴 | Red |
| Working From Home | 🏠 | Dark blue |
| Out of Office | ✈️ | Dark purple |
| Custom | Any emoji | Any color |
| Off | — | Screen off |

## Hardware

- [Waveshare ESP32-C6 Touch AMOLED 1.8"](https://www.waveshare.com/esp32-c6-touch-amoled-1.8.htm) — 368×448 AMOLED, BLE 5, two hardware buttons, LiPo connector
- Always-on mini PC at desk (Raspberry Pi, mini PC, etc.)
- LiPo battery (~1000mAh+), swappable; device sleeps outside business hours
- The two side buttons cycle through preset states as a local override

## Project Structure

```
firmware/       # ESP32-C6 firmware (PlatformIO + Arduino)
service/        # Mini PC service (Python + FastAPI + Docker)
docs/           # Architecture plan and documentation
```

## Getting Started

### Windows USB Driver Note

The ESP32-C6 uses a built-in USB-Serial/JTAG controller. On Windows, if the device doesn't appear as a COM port, install the [ESP32 board support package in Arduino IDE](https://docs.espressif.com/projects/arduino-esp32/en/latest/installing.html) which installs the correct Windows USB drivers. A reboot is required after installation.

### Firmware

Requires [PlatformIO](https://platformio.org/) with the [pioarduino](https://github.com/pioarduino/platform-espressif32) platform fork for ESP32-C6 Arduino support. The easiest approach is the PlatformIO VS Code extension.

```bash
cd firmware
pio run                          # build
pio run -t upload --upload-port COM9   # flash via USB-C (adjust port)
```

To regenerate emoji bitmap assets (stored in `include/icon_data.h`):
```bash
cd firmware/tools
python gen_icons.py
```

### Service

Copy `.env.example` to `.env` and fill in your values:

```bash
cd service
cp .env.example .env
# Edit .env: set ESP32_MAC_ADDRESS, MS_GRAPH_CLIENT_ID, TIMEZONE, etc.
```

**Local development (no Docker):**
```bash
pip install -r requirements.txt
python -m uvicorn src.web.app:app --host 0.0.0.0 --port 8080
```

**Docker (for production mini PC deployment):**
```bash
docker compose up
```

On first run, the web UI at `http://<your-pc>:8080` will show a Microsoft device code. Visit the URL shown and enter the code to authenticate. The service will then start polling your calendar automatically.

### Calendar Provider

Set `CALENDAR_PROVIDER=microsoft` (default) or `CALENDAR_PROVIDER=google` in `.env`.

### Microsoft Graph App Registration

1. Go to [portal.azure.com](https://portal.azure.com) → Azure Active Directory → App registrations → New registration
2. Set as a **Public client / native app**
3. Add delegated permissions: `Calendars.Read`, `Presence.Read`, `User.Read`, `MailboxSettings.Read`
4. Copy the **Application (client) ID** into `.env` as `MS_GRAPH_CLIENT_ID`

### Google Calendar App Registration

1. Go to [console.cloud.google.com](https://console.cloud.google.com) → New project
2. Enable the **Google Calendar API**
3. Create credentials → **OAuth client ID** → Application type: **TV and Limited Input devices**
4. Copy the **Client ID** and **Client Secret** into `.env` as `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`
5. Set `CALENDAR_PROVIDER=google` in `.env`

On first run, visit the URL shown in the web UI and enter the code to authenticate (same flow as Microsoft).

**What gets detected with Google Calendar:**
- In a Meeting: any busy (opaque) event on your primary calendar
- Working From Home: [Working Location](https://support.google.com/calendar/answer/11896660) events set to Home Office
- Out of Office: native Out of Office events

### Finding Your ESP32 MAC Address

Run the BLE scanner to find the device address:
```bash
cd service
python scan.py
```
The ESP32 will appear as `MeetingLight` or as the closest unnamed device. Set `ESP32_MAC_ADDRESS` in `.env`.

## Configuration

All settings are configurable in the web UI under ⚙️ Settings:

| Setting | Default | Description |
|---------|---------|-------------|
| Business hours start | 9 | Hour (24h) to wake device |
| Business hours end | 17 | Hour (24h) to sleep device |
| Timezone | America/New_York | IANA timezone string |
| ESP32 MAC address | — | BLE MAC of the device |
| Poll interval | 60s | How often to check calendar |
| Brightness | 128 | Display brightness 0–255 |

## Architecture Notes

- **State priority**: Manual override > Calendar-detected > Schedule (sleep) > Off
- **Image transfer**: Service renders full 368×448 JPEG using Pillow (Segoe UI Emoji on Windows), transfers in ~490-byte acknowledged BLE chunks (~2–3 seconds)
- **BLE**: NimBLE peripheral on ESP32, bleak central on mini PC. Custom GATT service with state command + device status characteristics
- **Power**: AMOLED with mostly-dark backgrounds; device deep-sleeps outside business hours. Target ~1 week battery life with 1000mAh LiPo
