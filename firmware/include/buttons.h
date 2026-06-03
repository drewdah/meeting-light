#pragma once
#include <Arduino.h>

void buttons_init();
void buttons_check();

typedef void (*button_callback_t)();
void buttons_on_boot_press(button_callback_t cb);
void buttons_on_power_press(button_callback_t cb);
