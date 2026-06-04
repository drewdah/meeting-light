#pragma once
#include <Arduino.h>
#include "config.h"

void ble_init();
void ble_notify_status(DisplayState state, uint8_t battery_pct, bool charging, uint16_t battery_mv);
bool ble_is_connected();

// Image buffer — valid immediately after STATE_CUSTOM_IMAGE pending command is consumed
const uint8_t* ble_get_image_data();
size_t ble_get_image_len();
void ble_free_image();
