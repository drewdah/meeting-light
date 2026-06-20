#pragma once
#include <Arduino.h>
#include "config.h"

void ble_init();
void ble_notify_status(DisplayState state, uint8_t battery_pct, bool charging, uint16_t battery_mv, bool vbus, bool pir_motion);
bool ble_is_connected();
String ble_get_mac_address();  // Returns "AA:BB:CC:DD:EE:FF" (uppercase)

// Image buffer — valid immediately after STATE_CUSTOM_IMAGE pending command is consumed
const uint8_t* ble_get_image_data();
size_t ble_get_image_len();
void ble_free_image();
