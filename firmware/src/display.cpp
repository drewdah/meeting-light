#include "display.h"
#include "config.h"
#include <Arduino_GFX_Library.h>
#include <Wire.h>

static Arduino_DataBus* bus = nullptr;
static Arduino_GFX* gfx = nullptr;
static bool screen_on = false;

// TCA9554 register addresses
#define TCA9554_REG_OUTPUT    0x01
#define TCA9554_REG_CONFIG    0x03

static void tca9554_write_reg(uint8_t reg, uint8_t val) {
    Wire.beginTransmission(ADDR_TCA9554);
    Wire.write(reg);
    Wire.write(val);
    Wire.endTransmission();
}

static void expander_init() {
    // Configure P4 and P5 as outputs (0 = output in TCA9554 config register)
    // Bits 4 and 5 cleared = output, others input (don't care)
    tca9554_write_reg(TCA9554_REG_CONFIG, 0b11001111);

    // Pull P4 and P5 LOW for 200ms (power-cycle the display/touch)
    tca9554_write_reg(TCA9554_REG_OUTPUT, 0b00000000);
    delay(200);

    // Pull P4 and P5 HIGH to enable display and touch
    tca9554_write_reg(TCA9554_REG_OUTPUT, 0b00110000);
    delay(100);
}

void display_init() {
    expander_init();

    bus = new Arduino_ESP32QSPI(
        LCD_CS, LCD_SCLK,
        LCD_SDIO0, LCD_SDIO1, LCD_SDIO2, LCD_SDIO3
    );

    gfx = new Arduino_SH8601(bus, GFX_NOT_DEFINED, 0 /* rotation */,
                              false /* IPS */, LCD_WIDTH, LCD_HEIGHT);

    gfx->begin(LCD_QSPI_FREQ);
    gfx->fillScreen(BLACK);
    gfx->setTextWrap(true);

    display_set_brightness(128);
    screen_on = true;
}

static void draw_centered_text(const char* text, uint16_t fg_color, uint16_t bg_color, uint8_t text_size) {
    gfx->fillScreen(bg_color);
    gfx->setTextColor(fg_color);
    gfx->setTextSize(text_size);

    // Approximate centering: 6px per char at size 1
    int16_t char_w = 6 * text_size;
    int16_t char_h = 8 * text_size;

    // Handle multi-line text by finding the longest line and line count
    const char* p = text;
    int max_line_len = 0;
    int cur_line_len = 0;
    int line_count = 1;
    while (*p) {
        if (*p == '\n') {
            if (cur_line_len > max_line_len) max_line_len = cur_line_len;
            cur_line_len = 0;
            line_count++;
        } else {
            cur_line_len++;
        }
        p++;
    }
    if (cur_line_len > max_line_len) max_line_len = cur_line_len;

    int16_t x = (LCD_WIDTH - max_line_len * char_w) / 2;
    int16_t y = (LCD_HEIGHT - line_count * char_h) / 2;
    if (x < 4) x = 4;
    if (y < 4) y = 4;

    // SH8601 requires even coordinates
    x &= ~1;
    y &= ~1;

    gfx->setCursor(x, y);
    gfx->println(text);
}

void display_show_preset(DisplayState state) {
    if (!gfx) return;

    switch (state) {
        case STATE_IN_MEETING:
            draw_centered_text("IN A\nMEETING", WHITE, RED, 5);
            break;
        case STATE_WFH:
            // Mostly black for power savings on all-day status
            draw_centered_text("Working\nFrom\nHome", 0x07E0 /* green */, BLACK, 4);
            break;
        case STATE_OOF:
            // Mostly black for power savings on all-day status
            draw_centered_text("Out of\nOffice", 0x631F /* purple */, BLACK, 4);
            break;
        case STATE_OFF:
        default:
            gfx->fillScreen(BLACK);
            break;
    }
    screen_on = true;
}

void display_show_custom_text(const char* text, uint8_t r, uint8_t g, uint8_t b) {
    if (!gfx) return;

    uint16_t bg_color = gfx->color565(r, g, b);

    // Choose white or black text based on background luminance
    float lum = 0.299f * r + 0.587f * g + 0.114f * b;
    uint16_t fg_color = (lum > 128) ? BLACK : WHITE;

    // Auto-size text: start large, reduce if it doesn't fit
    uint8_t text_size = 5;
    int max_line_len = 0;
    int cur_len = 0;
    const char* p = text;
    while (*p) {
        if (*p == '\n') {
            if (cur_len > max_line_len) max_line_len = cur_len;
            cur_len = 0;
        } else {
            cur_len++;
        }
        p++;
    }
    if (cur_len > max_line_len) max_line_len = cur_len;
    if (max_line_len == 0) max_line_len = 1;

    while (text_size > 1 && (max_line_len * 6 * text_size) > (LCD_WIDTH - 8)) {
        text_size--;
    }

    draw_centered_text(text, fg_color, bg_color, text_size);
    screen_on = true;
}

void display_show_image(const uint8_t* jpeg_data, size_t jpeg_len) {
    // TODO: Phase 6 — JPEG decode and blit to framebuffer
    (void)jpeg_data;
    (void)jpeg_len;
}

void display_set_brightness(uint8_t level) {
    if (!gfx) return;
    gfx->setBrightness(level);
}

void display_off() {
    if (!gfx) return;
    gfx->displayOff();
    screen_on = false;
}

void display_on() {
    if (!gfx) return;
    gfx->displayOn();
    screen_on = true;
}

bool display_is_on() {
    return screen_on;
}
