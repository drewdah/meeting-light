#pragma once
#include <Arduino.h>
#include "config.h"

void state_init();
DisplayState state_get_current();
void state_set(DisplayState new_state);
void state_save_to_nvs();
DisplayState state_load_from_nvs();
