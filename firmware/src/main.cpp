#include <Arduino.h>
#include <Wire.h>
#include "config.h"
#include "display.h"
#include "power.h"
#include "ble_service.h"
#include "state.h"
#include "buttons.h"

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
    state_save_to_nvs();

    ble_notify_status(new_state,
                      power_get_battery_percent(),
                      power_is_charging(),
                      power_get_battery_mv());

    Serial.printf("Button: state -> %d\n", new_state);
}

void setup() {
    Serial.begin(115200);
    delay(500);
    Serial.println("\n=== Meeting Light v0.1.0 ===");

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

    buttons_on_boot_press(on_boot_button);

    // Restore last display state after boot
    DisplayState saved = state_get_current();
    if (saved != STATE_OFF) {
        display_show_preset(saved);
        // Sync cycle_index
        for (uint8_t i = 0; i < PRESET_COUNT; i++) {
            if (PRESET_CYCLE[i] == saved) {
                cycle_index = i;
                break;
            }
        }
    } else {
        display_off();
    }

    Serial.printf("Ready. State: %d, Battery: %d%% (%dmV)\n",
                  saved, power_get_battery_percent(), power_get_battery_mv());
}

void loop() {
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
        state_set(cmd.state);
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
