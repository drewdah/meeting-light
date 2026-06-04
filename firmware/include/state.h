#pragma once
#include <Arduino.h>
#include "config.h"

// Pending command — set by BLE callback, executed by main loop
struct PendingCommand {
    bool valid = false;
    DisplayState state = STATE_OFF;
    // Custom text / icon fields
    uint8_t r = 255, g = 255, b = 255;
    char text[201] = {};
    uint8_t icon_id = 0;      // 0 = no icon
    uint8_t brightness = 0;   // 0 = no brightness change
    bool sleep = false;
};

void state_init();
DisplayState state_get_current();
void state_set(DisplayState new_state);
void state_save_to_nvs();
DisplayState state_load_from_nvs();

// Pending command queue (single-slot, written by BLE task, read by main loop)
void pending_set(const PendingCommand& cmd);
bool pending_get(PendingCommand& cmd);  // returns true and clears if pending
