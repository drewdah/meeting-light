# Meeting Light System - Implementation Plan

## Context

The user wants a professional-looking status display for their office window that shows coworkers (primarily CEO and HR) whether they're in a meeting, working from home, or out of office. The system uses a Waveshare ESP32-C6 1.8" Touch AMOLED (battery-powered, BLE only) controlled by a Linux mini PC at the desk that polls Outlook calendar via Microsoft Graph API. A web UI on the mini PC (accessible remotely via Tailscale) allows manual overrides and custom messages/images.

## Architecture

```
┌──────────────┐  BLE   ┌──────────────────┐  Graph API  ┌─────────────┐
│  ESP32-C6    │◄──────►│  Mini PC Service  │◄───────────►│  Microsoft  │
│  AMOLED      │        │  (Docker)         │             │  365        │
│  display     │        │                   │             └─────────────┘
└──────────────┘        │  Web UI :8080     │◄── Tailscale ── User (remote)
                        └──────────────────┘
```

**State priority**: Manual override (web UI/buttons) > Calendar-detected > Schedule-based (sleep outside hours) > Off

## Project Structure

```
meeting-light/
├── firmware/                    # ESP32-C6 (PlatformIO + ESP-IDF)
│   ├── platformio.ini
│   ├── src/
│   │   ├── main.cpp
│   │   ├── ble_service.h/.cpp   # NimBLE GATT server
│   │   ├── display.h/.cpp       # SH8601 AMOLED via esp_lcd
│   │   ├── power.h/.cpp         # AXP2101 PMIC, deep sleep
│   │   ├── state.h/.cpp         # Local state + NVS persistence
│   │   └── buttons.h/.cpp       # GPIO interrupt + debounce
│   └── include/
│       └── config.h             # Pin defs, BLE UUIDs, constants
├── service/                     # Mini PC (Python + FastAPI)
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── requirements.txt
│   ├── src/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── graph_client.py      # MS Graph polling (MSAL + aiohttp)
│   │   ├── ble_client.py        # BLE central (bleak)
│   │   ├── state_machine.py     # State engine with priorities
│   │   ├── scheduler.py         # Business hours logic
│   │   ├── image_processor.py   # Resize/compress images for BLE
│   │   └── web/
│   │       ├── app.py           # FastAPI + routes
│   │       ├── static/
│   │       └── templates/       # Jinja2 + HTMX
│   └── tests/
└── docs/
```

## Technology Choices

| Component | Choice | Why |
|-----------|--------|-----|
| ESP32 framework | ESP-IDF v5.3+ via PlatformIO | Full control over NimBLE power save, AXP2101 PMIC, deep sleep |
| ESP32 BLE stack | NimBLE | ~50KB less RAM than Bluedroid, built-in power save |
| Display driver | `esp_lcd` + `esp_lcd_sh8601` | Official Espressif QSPI component for SH8601 |
| Mini PC language | Python 3.12+ | Best MS Graph SDK (MSAL), excellent BLE lib (bleak), async-native |
| Web framework | FastAPI + Jinja2 + HTMX + Tailwind | Server-rendered, no JS build step, HTMX for dynamic updates |
| BLE library (PC) | bleak | Cross-platform async BLE, works in Docker with host BT passthrough |
| Graph auth | MSAL device code flow | Right pattern for headless service, auto token refresh |
| Container | Docker with `--net=host` + privileged | Required for BlueZ/BLE access |

## BLE Protocol

Custom GATT service with three characteristics:

**State Command (Write)** - opcodes:
- `0x01 SET_PRESET_STATE [state_id]` — 0=Off, 1=In Meeting, 2=WFH, 3=OOF
- `0x02 SET_CUSTOM_TEXT [r][g][b][utf8 text]` — colored background + text
- `0x03 SLEEP` — enter deep sleep
- `0x05 IMAGE_START [size][w][h][format]` — begin image transfer
- `0x06 IMAGE_CHUNK [index][payload]` — chunked data (write-without-response for speed)
- `0x07 IMAGE_END [crc32]` — finalize + verify
- `0x08 SET_BRIGHTNESS [0-255]`

**Device Status (Read + Notify)** — current state, battery %, charging flag, voltage. ESP32 notifies on every state change (serves as ACK) and periodically while awake.

**Image transfer**: Service compresses to JPEG (~30KB for 368x448), sends in ~507-byte chunks at ~50-100 KB/s. Transfer completes in under 1 second.

## Web UI

**Dashboard**: Current state, battery level, BLE connection status, Graph API status, active override countdown.

**Override panel**: Preset buttons, custom text input + color picker, image upload with preview/crop, duration selector (30m / 1h / 2h / end of day / until next calendar change / indefinite).

**Settings**: Business hours, timezone, Graph re-auth, ESP32 MAC, brightness slider, transition log.

**API endpoints** (for automation): `GET /api/status`, `POST /api/override`, `DELETE /api/override`, `GET /api/history`.

## Power Management

- **Business hours only (M-F 9-5)**: ESP32 deep sleeps nights and weekends
- **AMOLED efficiency**: All-day statuses (WFH/OOF) use mostly-black backgrounds to save power. Short-lived statuses (In Meeting) use bold colors to catch the eye of passersby. 30-50% brightness.
- **Duty cycling for all-day statuses (WFH/OOF)**: Screen on for 30s, off/dim for 90-120s, repeat. Meetings skip duty cycling (screen stays on for full duration since they're short-lived).
- **BLE tuning**: 1s connection interval idle, 100ms during image transfer, slave latency 4
- **Disable unused peripherals**: Touch controller (screen faces window), IMU (unless used for subtle burn-in prevention)
- **Target**: 1000mAh+ LiPo, battery-only operation, 1+ week battery life with duty cycling
- **Burn-in prevention**: Subtle 1-2px random shift every few minutes

## Microsoft Graph Integration

**Azure AD app registration** with delegated permissions: `Calendars.Read`, `Presence.Read`, `User.Read`, `MailboxSettings.Read`.

**Detection logic** (polled every 60s):
1. `calendarView` for current time window — busy/tentative non-all-day events = In Meeting
2. `showAs == "oof"` = Out of Office
3. Work location / all-day event location containing "home"/"remote" = WFH
4. Default = Off

**First-time auth**: Service shows device code on web UI and logs, user completes in browser, tokens cached and auto-refreshed.

## Implementation Phases

### Phase 1: ESP32 display proof-of-concept
- PlatformIO project, SH8601 init, display a static test image
- AXP2101 battery reading, deep sleep + button wake

### Phase 2: ESP32 BLE peripheral
- NimBLE GATT server, handle SET_PRESET_STATE
- ACK with battery level, test with nRF Connect app

### Phase 3: Mini PC BLE client
- Python + bleak, scan/connect/send commands
- Docker container with Bluetooth passthrough
- Verify round-trip command + ACK

### Phase 4: Web UI basics
- FastAPI + HTMX dashboard
- Connection/battery status display
- Preset override buttons with expiry timer

### Phase 5: Microsoft Graph integration
- MSAL device code auth flow
- Calendar polling + state machine
- Business hours scheduling

### Phase 6: Custom text and image support
- ESP32: text rendering with embedded font, JPEG decode (TJpgDec)
- Service: image upload/resize/compress, chunked BLE transfer
- Web UI: image upload, text input + color picker

### Phase 7: Polish and hardening
- Power optimization tuning
- Auto-reconnect on BLE disconnect
- Error handling, logging, settings page
- State transition history

### Phase 8: Production readiness
- Preset image design (professional graphics)
- Setup documentation
- Real Outlook calendar testing

## Key Risks

1. **BLE from Docker** — BlueZ in containers is finicky. Test in Phase 3 early. Fallback: run service on host with systemd.
2. **Deep sleep current** — Real-world with AXP2101 may be ~300uA vs 7uA spec. No power outlet near the window, so battery is the only option. Mitigate by disabling all unused peripherals and using 1000mAh+ LiPo. Accept weekly battery swaps.
3. **SH8601 driver** — Espressif component is v0.0.1. Fallback: port Waveshare's Arduino demo init sequence to ESP-IDF.
4. **Enterprise Graph API** — Some orgs restrict app registrations. Document exact permissions needed.
5. **AMOLED burn-in** — Mitigated by pixel shifting, dark backgrounds, and screen-off during idle.

## Verification

- **ESP32**: Flash firmware, verify display shows preset images, BLE connects from nRF Connect, battery reading is sane, deep sleep current measured with multimeter
- **Service**: `docker compose up`, authenticate via device code, verify calendar events are detected, state transitions appear in web UI, BLE commands reach ESP32
- **End-to-end**: Create a test meeting in Outlook, verify ESP32 shows "In Meeting" within 60s, verify it clears when meeting ends. Set WFH in calendar, verify display updates. Test manual override from web UI and verify it takes priority. Test override expiry reverts to calendar state.
