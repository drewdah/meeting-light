#pragma once
#include <Arduino.h>
#include "config.h"

// Pending command — set by BLE callback, executed by main loop
struct PendingCommand {
    bool valid = false;
    bool set_state = false;    // true only when a display state change is intended
    DisplayState state = STATE_OFF;
    // Background color
    uint8_t r = 0, g = 0, b = 0;
    // Foreground (text) color — 0,0,0 = auto
    uint8_t fg_r = 255, fg_g = 255, fg_b = 255;
    char text[201] = {};
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
