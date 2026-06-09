#pragma once
#include <Arduino.h>
#include "config.h"

// Icon IDs (index into ICON_TABLE in icon_data.h)
#define ICON_ID_BLUETOOTH 4

void display_init();
void display_show_boot_splash();
void display_show_preset(DisplayState state);
void display_show_custom_text(const char* text, uint8_t r, uint8_t g, uint8_t b,
                              uint8_t fg_r=255, uint8_t fg_g=255, uint8_t fg_b=255);
void display_show_icon_text(uint8_t icon_id, const char* text, uint8_t r, uint8_t g, uint8_t b);
void display_show_image(const uint8_t* jpeg_data, size_t jpeg_len);
void display_show_waiting(const char* mac);
void display_set_brightness(uint8_t level);
void display_off();
void display_on();
bool display_is_on();
void display_pa_enable(bool enable);  // Control speaker amp via TCA9554 P7
