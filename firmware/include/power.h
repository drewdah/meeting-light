#pragma once
#include <Arduino.h>

void power_init();
uint8_t power_get_battery_percent();
uint16_t power_get_battery_mv();
bool power_is_charging();
bool power_is_vbus_in();
void power_enter_deep_sleep();
void power_disable_display_rail();
void power_enable_display_rail();
