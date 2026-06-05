# Meeting Light
A professional office status display for a Waveshare ESP32-C6 1.8" Touch AMOLED, mounted in an office window. Shows your current status — In a Meeting, Working From Home, Out of Office, or a custom message — to coworkers passing by.

<p align="center">
  <img src="assets/screenshot-1.png" width="53%" alt="Meeting Light web UI" />
  <img src="assets/screenshot-2.jpg" width="45%" alt="Meeting Light on device" />
</p>

## How It Works

A mini PC at your desk polls your Outlook calendar via the Microsoft Graph API and pushes status updates to the ESP32 over BLE. A web UI (accessible remotely via Tailscale) lets you set manual overrides, compose custom messages with emoji, and preview what will appear on screen before sending.

```
ESP32-C6 AMOLED  <──BLE──>  Mini PC Service  <──Graph API──>  Microsoft 365
                                   │
                             Web UI :8080  <──Tailscale──  Remote access
```

## Features

- **Automatic detection** — polls Outlook or Google calendar for meetings, WFH location, and Out of Office status
- **Emoji + text display** — full-resolution images rendered service-side with any emoji and custom text, transferred to the display over BLE
- **Full emoji picker** — pick any emoji from the web UI; no pre-compilation required
- **Preview before send** — see exactly what will appear on screen, with font size +/− controls
- **Manual overrides** — preset buttons (In a Meeting, WFH, OOF) or custom message with background color and emoji
- **Override expiry** — set duration (30 min, 1 hr, end of day, etc.) before reverting to calendar state
- **Boot button controls** — tap to cycle through preset states; hold 3 seconds to reboot
- **Boot splash** — shows a 💡 Meeting Light logo on startup while connecting to the service
- **Business hours scheduling** — device sleeps outside M–F 9–5; configurable in the web UI
- **Power monitoring** — live battery %, voltage, charging state, and USB power detection reported via BLE; dashboard shows USB Powered, Charging, or battery % as appropriate
- **Brightness control** — adjustable in Settings, applied immediately to the device
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

### Button Controls

The device has two buttons — **BOOT** (side) and **PWR** (side):

| Gesture | Action |
|---------|--------|
| Tap BOOT | Cycle through Off → In a Meeting → WFH → Out of Office |
| Hold BOOT 3s | Reboot device |

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

To regenerate the pre-compiled preset and boot splash images (run from repo root after changing the service rendering):
```bash
python firmware/tools/gen_preset_images.py   # In a Meeting, WFH, OOF
python firmware/tools/gen_boot_splash.py     # Boot splash
```
Then reflash the firmware.

### Service

#### Prerequisites

- Python 3.11 or newer
- Bluetooth adapter (built-in or USB dongle)
- On Windows: no extra drivers needed; on Linux: `bluez` must be installed (`sudo apt install bluez`)

#### 1. Copy and edit `.env`

```bash
cd service
cp .env.example .env
```

Open `.env` and set at minimum:

| Variable | Description |
|----------|-------------|
| `ESP32_MAC_ADDRESS` | BLE MAC of your device (see *Finding Your ESP32 MAC Address* below) |
| `CALENDAR_PROVIDER` | `microsoft` or `google` |
| `MS_GRAPH_CLIENT_ID` | Azure app client ID (Microsoft only) |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | OAuth credentials (Google only) |
| `TIMEZONE` | Your local IANA timezone, e.g. `America/New_York` |

OAuth client credentials (client ID and secret) live in `.env` only — they are never entered through the web UI.

#### 2. Create a virtual environment and install dependencies

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

```bash
pip install -r requirements.txt
```

#### 3. Run the service

```bash
python -m uvicorn src.web.app:app --host 0.0.0.0 --port 8080
```

The web UI is available at `http://localhost:8080` (or `http://<your-pc>:8080` from another device on the same network / via Tailscale).

#### 4. Authenticate your calendar (first run)

1. Open the web UI and go to **⚙️ Settings → Calendar**.
2. Select your provider and click **Sign In**.
3. A device code will appear — visit the URL shown and enter the code in your browser.
4. Once authenticated the service starts polling your calendar automatically. Tokens are cached in `data/` and refreshed on subsequent runs.

#### Docker (production mini PC deployment)

```bash
docker compose up
```

The same `.env` file is used; Docker Compose passes it through automatically.

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
- **Image transfer**: Service renders full 368×448 JPEG using Pillow (Segoe UI Emoji on Windows), transfers in ~490-byte acknowledged BLE chunks
- **Preset images**: In a Meeting, WFH, OOF, and the boot splash are pre-compiled as JPEG byte arrays in firmware (`preset_images.h`, `boot_splash.h`). The boot button cycles through these instantly with no BLE transfer. Re-run the generator scripts and reflash to update them.
- **BLE**: NimBLE peripheral on ESP32, bleak central on mini PC. Custom GATT service with state command + device status characteristics
- **Power**: AXP2101 PMIC reports battery %, voltage, charging state, and USB/VBUS presence over BLE. AMOLED with mostly-dark backgrounds; device deep-sleeps outside business hours. Target ~1 week battery life with 1000mAh LiPo
