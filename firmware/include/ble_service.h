#pragma once
#include <Arduino.h>
#include "config.h"

void ble_init();
void ble_notify_status(DisplayState state, uint8_t battery_pct, bool charging, uint16_t battery_mv);
bool ble_is_connected();
