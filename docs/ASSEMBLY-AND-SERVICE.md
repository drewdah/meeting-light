# Meeting Light — Assembly & Service Cheat Sheet

Quick reference for building, wiring, and servicing the Meeting Light enclosure.
Dimensions are measured from the current `enclosure/stl/FrontLid.stl` (v11). Last updated 2026-06-11.

---

## 1. Nameplate paper insert

| Spec | Value |
|---|---|
| **Cut size** | **194 × 46 mm** (≈ 7‑5/8″ × 1‑13/16″) |
| Visible window | ~194 × 42.6 mm (the top & bottom ~1.7 mm tuck under the retaining lips) |
| Channel location | Right-hand zone of the front lid, **X55 → X249** |
| Insertion | Slides in from the **screen end**, stops at the far wall |
| Template | [`enclosure/nameplate/MeetingLight-Nameplate-Drew.docx`](../enclosure/nameplate/MeetingLight-Nameplate-Drew.docx) |

**Printing:** Print at **100% / "Actual Size"** — turn OFF "Fit to page" / "Shrink oversized pages."
Verify with the **50 mm check bar** on the template: if it doesn't measure exactly 50 mm with a ruler, your printer is scaling and the insert will come out short. Fix the scale setting and reprint.

---

## 2. PIR sensor (AM312) — wiring & connector

### Wiring
| PIR pin | Connects to | Notes |
|---|---|---|
| **VIN** | **3V3** | Power at 3.3 V, **not 5 V** (keeps OUT at a safe 3.3 V logic level) |
| **OUT** | **GPIO17** | `PIR_PIN 17` in [`firmware/include/config.h`](../firmware/include/config.h) |
| **GND** | **GND** | |

- ⚠️ **AM312 pin order varies by board** (`GND-OUT-VCC` vs `VCC-OUT-GND`). Match **your** board's silkscreen — do not trust an online photo or a connector's "pin 1."
- The PIR is **not a wake source** — it's read while the screen is already awake to drive the sleep timeout (`PIR_TIMEOUT_MS = 60000`, 1 min no-motion → display off). A cold/iffy joint just shows up as "no motion" in the logs; low-consequence to get wrong on the first try and reflow.

### Make it swappable (one connector, at the PIR)
You only need ONE connector. Solder the pigtail to the board **once**; the connector at the PIR end is what makes the sensor swappable.

```
ESP32 board ──solder once──┐                       ┌── PIR sensor
 GPIO17 ──────────────────[ wires ]──[ connector ]── 3-pin header
 3V3   ──────────────────[ wires ]──[  (keyed)  ]──
 GND   ──────────────────[ wires ]──┘                       └──
        (do this once)                unplug here to swap the PIR
```

**Path 1 — fastest, no crimp tool, no soldering the PIR:** a 3‑pin **servo extension lead**. Female end plugs onto the PIR's existing 0.1″ pins (semi-keyed); cut the male end off and solder those 3 wires to the board.

**Path 2 — keyed JST‑XH, the "do it once properly" version:** solder a 3‑pin **XH PCB header** onto the PIR, crimp an XH pigtail (keyed + latched, can't reverse-power), plug together, solder the pigtail's other end to the board. Needs a crimp tool (reusable).

> ⚠️ **Connector clearance:** the PIR sits in the slotted collar with pins clipped short. A bulky connector body may not fit right behind the PCB. The servo housing is chunkiest; JST‑XH is more compact; a **right-angle XH header** is best. If tight, put the connector a few cm away on short flying leads, out in the open lid cavity over the nameplate.

### Soldering checklist (the screen is NOT electrically at risk — these 3 nets don't touch the AMOLED)
1. **Power off, unplug USB, disconnect the battery** first.
2. **Pre-tin** the pad AND the wire separately, then join in ~1 s. (This is the anxiety-killer — no juggling.)
3. **Hot & fast:** ~350–370 °C, in and out under 2 s per joint. A *cool* iron held for 8 s does far more damage than a hot one for 2.
4. Use **thin 30 AWG silicone wire** — it won't lever the pad up like stiff wire.
5. **Protect the glass:** board face-down on a microfiber cloth, no hard point pressing under the AMOLED.
6. **Strain relief:** dab of hot glue / strip of Kapton over the wires.
7. **Verify before power:** loupe for solder bridges; multimeter continuity check that 3V3 / GND / GPIO17 aren't shorted to each other.

---

## 3. Battery — service extension cable

The board's battery port is an **MX1.25 2-pin** connector (1.25 mm pitch — confirmed on the
[Waveshare ESP32‑C6‑Touch‑AMOLED‑1.8 wiki](https://docs.waveshare.com/ESP32-C6-Touch-AMOLED-1.8)).
The on-board JST is tiny and awkward to cycle. Fix: plug a **male-to-female extension** into the board **once**, leave it, and do all battery swaps at the accessible extension end.

### ⚠️ Polarity — the one connector where a mistake can damage hardware
The extension only needs to be **straight-through (red → red, black → black)**. If it is, it's electrically invisible — whatever orientation your battery plugs in directly today works identically through it.

Before the **first** battery connection through the extension:
1. **Trace the wire colors** at both housings — red must land on the same pin at each end.
2. Better, **meter it:** continuity from one end's red pin to the other end's red pin; confirm red is NOT tied to black.
3. **Dry-fit unpowered:** one end must plug into the board where the battery was; the other end must accept the battery's plug.

### Practical notes
- **Strain-relieve the board end** (hot glue / Kapton) — that tiny MX1.25 is fragile and you'll never unplug it again, so don't let months of tugging stress its solder pads.
- **Never short the loose leads.** Treat the bare cell with respect; never bridge the two contacts with a tool.
- 20 cm is generous — coil the slack behind the nameplate area (it's empty) or trim-to-length later (after confirming fit + function).

---

## 4. Parts list (Amazon)

> Links were live as of 2026-06-11; verify contents/photos before buying — "male/female" naming on these is inconsistent. The links are listings, not endorsements.

### PIR connector
| Path | Part | Link |
|---|---|---|
| 1 (simplest) | 3‑pin servo male-to-female leads, 150 mm (10‑pk) | [B08RDNF5ZK](https://www.amazon.com/10pcs-Servo-Extension-Female-Futaba/dp/B08RDNF5ZK) |
| 2 (keyed JST‑XH) | WayinTop SN‑28B crimp kit + JST‑XH + DuPont | [B07VND42CF](https://www.amazon.com/WayinTop-Crimping-Connector-Connectors-28-18AWG/dp/B07VND42CF) |
| 2 (alt) | SN‑28B tool + JST‑XH terminal kit (2010 pc) | [B0FM3NYHBH](https://www.amazon.com/Sn-28b-Crimping-Pliers-Set-1550pcs-Connector/dp/B0FM3NYHBH) |
| 2 (no tool) | daier JST‑XH 3‑pin set w/ wire — *confirm it includes a PCB header* | [B01DUC1PGC](https://www.amazon.com/Sets-2-5-3-Connector-200mm-Female/dp/B01DUC1PGC) |

### Battery extension
| Part | Link |
|---|---|
| **BHUPWZE MX1.25 2‑pin male-to-female extension, 20 cm (10‑pk)** — the one | [B0FZNRT2JT](https://www.amazon.com/BHUPWZE-MX1-25-Extension-1-25mm-Connector/dp/B0FZNRT2JT) |
| XUGERIP MX 1.25 2‑pin, pre-crimped 100 mm leads (backup) | [B0DMSYJZ4T](https://us.amazon.com/XUGERIP-1-25mm-Connector-Connectors-Extension/dp/B0DMSYJZ4T) |
| Cermant MX1.25 connector + pre-crimped cable kit (assortment) | [B0DSFNXRQ5](https://www.amazon.com/Cermant-MX1-25mm-Connectors-Pre-Crimped-Premium/dp/B0DSFNXRQ5) |

### Wire
| Part | Link |
|---|---|
| Striveday 30 AWG silicone hook-up wire | [B01KQ2JPY8](https://www.amazon.com/StrivedayTM-Flexible-Silicone-electronic-electrics/dp/B01KQ2JPY8) |
| TUOFENG 30 AWG silicone wire, 6 colors | [B07G2SWB19](https://www.amazon.com/TUOFENG-30awg-Stranded-Wire-Kit/dp/B07G2SWB19) |

---

## 5. Pin quick reference

| Signal | Pin | Source |
|---|---|---|
| PIR OUT | GPIO17 | `config.h` → `PIR_PIN` |
| BOOT button | GPIO9 (active LOW) | board |
| Touch INT | GPIO15 | board |
| I2C | SCL=7, SDA=8 | board |
| Battery | MX1.25 2‑pin, AXP2101 PMIC | board |

*Full hardware/firmware details live in the project memory overview and the repo `README`.*
