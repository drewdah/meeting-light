#include "pir.h"
#include "config.h"

static bool enabled = false;
static bool current_motion = false;
static unsigned long last_motion_time = 0;

void pir_init() {
    pinMode(PIR_PIN, INPUT);
}

void pir_update() {
    if (!enabled) return;
    current_motion = (digitalRead(PIR_PIN) == HIGH);
    if (current_motion) {
        last_motion_time = millis();
    }
}

bool pir_motion_detected() {
    return current_motion;
}

bool pir_has_timed_out() {
    return !current_motion && (millis() - last_motion_time >= PIR_TIMEOUT_MS);
}

void pir_reset_timer() {
    last_motion_time = millis();
}

void pir_set_enabled(bool en) {
    if (en && !enabled) {
        last_motion_time = millis();
    }
    enabled = en;
}

bool pir_is_enabled() {
    return enabled;
}
