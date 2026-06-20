#pragma once

#include <Arduino.h>

void pir_init();
void pir_update();
bool pir_motion_detected();
bool pir_has_timed_out();
void pir_reset_timer();
void pir_set_enabled(bool en);
bool pir_is_enabled();
