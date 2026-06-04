#include "state.h"
#include <Preferences.h>

static Preferences prefs;
static DisplayState current_state = STATE_OFF;

// Single-slot pending command — written by BLE task, consumed by main loop
static volatile bool _pending_valid = false;
static PendingCommand _pending_cmd;

void pending_set(const PendingCommand& cmd) {
    _pending_cmd = cmd;
    _pending_valid = true;  // write last so reader sees consistent data
}

bool pending_get(PendingCommand& cmd) {
    if (!_pending_valid) return false;
    _pending_valid = false;
    cmd = _pending_cmd;
    return true;
}

void state_init() {
    prefs.begin("mlight", false);
    current_state = state_load_from_nvs();
}

DisplayState state_get_current() {
    return current_state;
}

void state_set(DisplayState new_state) {
    current_state = new_state;
}

void state_save_to_nvs() {
    prefs.putUChar("state", (uint8_t)current_state);
}

DisplayState state_load_from_nvs() {
    uint8_t val = prefs.getUChar("state", (uint8_t)STATE_OFF);
    if (val > STATE_CUSTOM_IMAGE) val = STATE_OFF;
    return (DisplayState)val;
}
