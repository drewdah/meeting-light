#include "buttons.h"
#include "config.h"

static button_callback_t boot_cb = nullptr;
static button_callback_t power_cb = nullptr;

static bool      boot_was_pressed = false;
static unsigned long boot_hold_start = 0;

#define DEBOUNCE_MS   50
#define LONG_HOLD_MS  3000

void buttons_init() {
    pinMode(BTN_BOOT, INPUT_PULLUP);
    // Polled in buttons_check() — no interrupt needed
}

void buttons_check() {
    unsigned long now = millis();
    bool pressed = (digitalRead(BTN_BOOT) == LOW);

    if (pressed && !boot_was_pressed) {
        // Falling edge
        boot_hold_start = now;
        boot_was_pressed = true;

    } else if (pressed && boot_was_pressed) {
        // Still held — check for long-hold reboot
        if (now - boot_hold_start >= LONG_HOLD_MS) {
            Serial.println("Boot button held 3s — rebooting");
            delay(100);
            ESP.restart();
        }

    } else if (!pressed && boot_was_pressed) {
        // Rising edge
        unsigned long held = now - boot_hold_start;
        boot_was_pressed = false;
        if (held >= DEBOUNCE_MS && held < LONG_HOLD_MS) {
            // Short tap → cycle state
            if (boot_cb) boot_cb();
        }
    }
}

void buttons_on_boot_press(button_callback_t cb)  { boot_cb  = cb; }
void buttons_on_power_press(button_callback_t cb) { power_cb = cb; }
