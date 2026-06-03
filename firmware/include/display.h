#pragma once
#include <Arduino.h>
#include "config.h"

void display_init();
void display_show_preset(DisplayState state);
void display_show_custom_text(const char* text, uint8_t r, uint8_t g, uint8_t b);
void display_show_image(const uint8_t* jpeg_data, size_t jpeg_len);
void display_set_brightness(uint8_t level);
void display_off();
void display_on();
bool display_is_on();
