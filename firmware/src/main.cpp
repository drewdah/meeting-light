#include <Arduino.h>
#include <Wire.h>
#include <esp_system.h>
#include "config.h"
#include "display.h"
#include "power.h"
#include "ble_service.h"
#include "state.h"
#include "buttons.h"
#include "audio.h"

// Crash loop detection: RTC_NOINIT_ATTR survives software resets but is cleared on power-on.
// After 3 consecutive crash resets we enter safe mode (stable screen, no retry) to prevent
// USB re-enumeration thrashing that corrupts the Windows driver state.
#define CRASH_MAGIC    0xDEADC0DE
#define CRASH_LIMIT    3
#define SAFE_MODE_MS   30000  // reset counter after this many ms of clean uptime

RTC_NOINIT_ATTR static uint32_t crash_magic;
RTC_NOINIT_ATTR static uint32_t crash_count;

static bool safe_mode = false;
static unsigned long boot_ok_start = 0;
static bool audio_status_logged = false;

static unsigned long last_battery_report = 0;
static const DisplayState PRESET_CYCLE[] = {
    STATE_OFF, STATE_IN_MEETING, STATE_WFH, STATE_OOF
};
static const uint8_t PRESET_COUNT = sizeof(PRESET_CYCLE) / sizeof(PRESET_CYCLE[0]);
static uint8_t cycle_index = 0;

static void on_boot_button() {
    cycle_index = (cycle_index + 1) % PRESET_COUNT;
    DisplayState new_state = PRESET_CYCLE[cycle_index];
    state_set(new_state);

    if (new_state == STATE_OFF) {
        display_off();
    } else {
        display_on();
        display_show_preset(new_state);
    }

    audio_play_state_chime();
    state_save_to_nvs();

    ble_notify_status(new_state,
                      power_get_battery_percent(),
                      power_is_charging(),
                      power_get_battery_mv());

    Serial.printf("Button: state -> %d\n", new_state);
}

void setup() {
    Serial.begin(115200);
    // Wait up to 2s for CDC terminal so startup logs aren't silently dropped
    { uint32_t t = millis(); while (!Serial && (millis() - t) < 2000) delay(10); }
    delay(200);
    Serial.println("\n=== Meeting Light v0.1.0 ===");

    // Crash loop detection
    esp_reset_reason_t reset_reason = esp_reset_reason();
    bool is_crash_reset = (reset_reason == ESP_RST_PANIC ||
                           reset_reason == ESP_RST_WDT   ||
                           reset_reason == ESP_RST_TASK_WDT ||
                           reset_reason == ESP_RST_INT_WDT);

    if (reset_reason == ESP_RST_POWERON || crash_magic != CRASH_MAGIC) {
        crash_count = 0;
        crash_magic = CRASH_MAGIC;
    } else if (is_crash_reset) {
        crash_count++;
    }

    Serial.printf("Reset reason: %d, crash_count: %lu\n", reset_reason, crash_count);

    if (crash_count >= CRASH_LIMIT) {
        // Safe mode: minimal init only — stops USB thrashing
        Serial.printf("SAFE MODE: %lu consecutive crashes, halting\n", crash_count);
        Wire.begin(I2C_SDA, I2C_SCL, I2C_FREQ);
        power_init();
        display_init();
        display_show_custom_text("SAFE MODE\nHold BOOT 3s\nto restart", 255, 80, 0, 255, 255, 255);
        safe_mode = true;
        return;
    }

    // Check wake reason
    esp_sleep_wakeup_cause_t wakeup = esp_sleep_get_wakeup_cause();
    if (wakeup != ESP_SLEEP_WAKEUP_UNDEFINED) {
        Serial.printf("Woke from deep sleep, cause: %d\n", wakeup);
    }

    Wire.begin(I2C_SDA, I2C_SCL, I2C_FREQ);

    power_init();
    state_init();
    display_init();
    buttons_init();
    ble_init();
    audio_init();

    buttons_on_boot_press(on_boot_button);

    display_show_boot_splash();
    audio_play_boot_chime();

    // Restore saved state in NVS so button cycling and BLE stay in sync,
    // but don't re-render locally — the service pushes the correct JPEG on connect.
    DisplayState saved = state_get_current();
    for (uint8_t i = 0; i < PRESET_COUNT; i++) {
        if (PRESET_CYCLE[i] == saved) {
            cycle_index = i;
            break;
        }
    }
    if (saved == STATE_OFF) {
        display_off();
    }

    Serial.printf("Ready. State: %d, Battery: %d%% (%dmV)\n",
                  saved, power_get_battery_percent(), power_get_battery_mv());

    boot_ok_start = millis();
}

void loop() {
    if (safe_mode) {
        // Hold BOOT 3s still works via hardware reset; just idle here
        delay(100);
        return;
    }

    // Clear crash counter once we've been running cleanly long enough
    if (crash_count > 0 && boot_ok_start > 0 &&
        (millis() - boot_ok_start) > SAFE_MODE_MS) {
        crash_count = 0;
        boot_ok_start = 0;
    }

    // Log audio status once after BLE connects (startup logs missed during power cycle)
    if (!audio_status_logged && ble_is_connected()) {
        Serial.printf("Audio init: %s\n", audio_is_ok() ? "OK" : "FAILED");
        audio_status_logged = true;
    }

    buttons_check();

    // Execute any pending BLE command (deferred from BLE callback to avoid stack overflow)
    PendingCommand cmd;
    if (pending_get(cmd)) {
        if (cmd.sleep) {
            state_set(STATE_OFF);
            display_off();
            state_save_to_nvs();
            power_enter_deep_sleep();
            return;
        }
        if (cmd.brightness > 0) {
            display_set_brightness(cmd.brightness);
        }
        if (cmd.set_state) {
            state_set(cmd.state);
            audio_play_state_chime();
            if (cmd.state == STATE_OFF) {
                display_off();
            } else if (cmd.state == STATE_CUSTOM_TEXT) {
                display_on();
                display_show_custom_text(cmd.text, cmd.r, cmd.g, cmd.b,
                                         cmd.fg_r, cmd.fg_g, cmd.fg_b);
            } else if (cmd.state == STATE_CUSTOM_IMAGE) {
                display_on();
                display_show_image(ble_get_image_data(), ble_get_image_len());
                ble_free_image();
            } else {
                display_on();
                display_show_preset(cmd.state);
            }
        
            state_save_to_nvs();
            ble_notify_status(cmd.state,
                              power_get_battery_percent(),
                              power_is_charging(),
                              power_get_battery_mv());
        }
    }

    // Periodic battery status report
    unsigned long now = millis();
    if (now - last_battery_report > BATTERY_READ_INTERVAL_MS) {
        last_battery_report = now;
        if (ble_is_connected()) {
            ble_notify_status(state_get_current(),
                              power_get_battery_percent(),
                              power_is_charging(),
                              power_get_battery_mv());
        }
    }

    delay(10);
}
