#include "buttons.h"
#include "config.h"

static button_callback_t boot_cb = nullptr;
static button_callback_t power_cb = nullptr;

static volatile bool boot_pressed = false;
static unsigned long last_boot_press = 0;

#define DEBOUNCE_MS 200

static void IRAM_ATTR boot_isr() {
    boot_pressed = true;
}

void buttons_init() {
    pinMode(BTN_BOOT, INPUT_PULLUP);
    attachInterrupt(digitalPinToInterrupt(BTN_BOOT), boot_isr, FALLING);
}

void buttons_check() {
    if (boot_pressed) {
        boot_pressed = false;
        unsigned long now = millis();
        if (now - last_boot_press > DEBOUNCE_MS) {
            last_boot_press = now;
            if (boot_cb) boot_cb();
        }
    }
    // AXP2101 power key is handled via PMU IRQ in main loop
}

void buttons_on_boot_press(button_callback_t cb) {
    boot_cb = cb;
}

void buttons_on_power_press(button_callback_t cb) {
    power_cb = cb;
}
