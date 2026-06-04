#include "display.h"
#include "config.h"
#include <Arduino_GFX_Library.h>
#include <Adafruit_XCA9554.h>
#include <Wire.h>
#include <JPEGDEC.h>
#include "icon_data.h"
#include "boot_splash.h"
#include "preset_images.h"

static JPEGDEC jpeg;

// RGB565 color constants
#define BLACK   0x0000
#define WHITE   0xFFFF
#define RED     0xF800
#define GREEN   0x07E0
#define BLUE    0x001F

static Arduino_DataBus* bus = nullptr;
static Arduino_SH8601* gfx = nullptr;
static Adafruit_XCA9554 expander;
static bool screen_on = false;

static void expander_init() {
    if (!expander.begin(ADDR_TCA9554)) {
        Serial.println("XCA9554 expander not found!");
        return;
    }
    expander.pinMode(4, OUTPUT);
    expander.pinMode(5, OUTPUT);
    expander.digitalWrite(4, 1);
    expander.digitalWrite(5, 1);
    delay(500);
}

void display_init() {
    expander_init();

    bus = new Arduino_ESP32QSPI(
        LCD_CS, LCD_SCLK,
        LCD_SDIO0, LCD_SDIO1, LCD_SDIO2, LCD_SDIO3
    );

    gfx = new Arduino_SH8601(bus, GFX_NOT_DEFINED, 0 /* rotation */,
                              (uint16_t)LCD_WIDTH, (uint16_t)LCD_HEIGHT);

    if (!gfx->begin()) {
        Serial.println("SH8601 display init failed!");
    }
    gfx->fillScreen(BLACK);
    gfx->setTextWrap(true);

    display_set_brightness(128);
    screen_on = true;
}

// PROGMEM data lives in read-only flash; JPEGDEC's openRAM() writes into the
// buffer as scratch space, so copy to heap RAM before decoding.
static void show_progmem_jpeg(const uint8_t* pgm_data, size_t len) {
    uint8_t* buf = (uint8_t*)malloc(len);
    if (!buf) { Serial.println("show_progmem_jpeg: malloc failed"); return; }
    memcpy_P(buf, pgm_data, len);
    display_show_image(buf, len);
    free(buf);
}

void display_show_boot_splash() {
    show_progmem_jpeg(BOOT_SPLASH_DATA, BOOT_SPLASH_LEN);
}

// Draw each line of text individually centered on screen.
// y_start: top of the text block. If -1, vertically centers the whole block.
static void draw_centered_text_block(const char* text, uint16_t fg_color, uint8_t text_size,
                                     int16_t y_start = -1) {
    gfx->setTextColor(fg_color);
    gfx->setTextSize(text_size);

    int16_t char_w = 6 * text_size;
    int16_t char_h = 8 * text_size;

    // Split text into lines and measure each
    char lines[8][64];
    int line_count = 0;
    const char* p = text;
    int i = 0;
    while (*p && line_count < 8) {
        if (*p == '\n' || i >= 63) {
            lines[line_count][i] = '\0';
            line_count++;
            i = 0;
        } else {
            lines[line_count][i++] = *p;
        }
        p++;
    }
    if (i > 0 || line_count == 0) {
        lines[line_count][i] = '\0';
        line_count++;
    }

    int16_t total_h = line_count * char_h;
    int16_t y = (y_start < 0) ? (LCD_HEIGHT - total_h) / 2 : y_start;
    y = max(y, (int16_t)4);
    y &= ~1;

    for (int l = 0; l < line_count; l++) {
        int16_t line_w = (int16_t)(strlen(lines[l])) * char_w;
        int16_t x = (LCD_WIDTH - line_w) / 2;
        x = max(x, (int16_t)4);
        x &= ~1;
        gfx->setCursor(x, y);
        gfx->print(lines[l]);
        y += char_h;
    }
}

static void draw_centered_text(const char* text, uint16_t fg_color, uint16_t bg_color,
                                uint8_t text_size) {
    gfx->fillScreen(bg_color);
    draw_centered_text_block(text, fg_color, text_size);
}

void display_show_preset(DisplayState state) {
    if (!gfx) return;
    switch (state) {
        case STATE_IN_MEETING:
            show_progmem_jpeg(PRESET_IN_MEETING_DATA, PRESET_IN_MEETING_LEN);
            break;
        case STATE_WFH:
            show_progmem_jpeg(PRESET_WFH_DATA, PRESET_WFH_LEN);
            break;
        case STATE_OOF:
            show_progmem_jpeg(PRESET_OOF_DATA, PRESET_OOF_LEN);
            break;
        case STATE_OFF:
        default:
            gfx->fillScreen(BLACK);
            screen_on = false;
            return;
    }
    screen_on = true;
}

void display_show_custom_text(const char* text, uint8_t r, uint8_t g, uint8_t b,
                              uint8_t fg_r, uint8_t fg_g, uint8_t fg_b) {
    if (!gfx) return;

    uint16_t bg_color = gfx->color565(r, g, b);
    uint16_t fg_color = gfx->color565(fg_r, fg_g, fg_b);

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

void display_show_icon_text(uint8_t icon_id, const char* text, uint8_t r, uint8_t g, uint8_t b) {
    if (!gfx) return;

    uint16_t bg_color = gfx->color565(r, g, b);
    float lum = 0.299f * r + 0.587f * g + 0.114f * b;
    uint16_t fg_color = (lum > 128) ? BLACK : WHITE;

    gfx->fillScreen(bg_color);

    // Draw icon bitmap in the upper portion of the screen
    if (icon_id > 0 && icon_id < ICON_COUNT && ICON_TABLE[icon_id]) {
        int16_t ix = (LCD_WIDTH - ICON_SIZE) / 2;
        int16_t iy = LCD_HEIGHT / 6;  // ~1/6 from top
        ix &= ~1; iy &= ~1;
        gfx->draw16bitRGBBitmap(ix, iy, (uint16_t*)ICON_TABLE[icon_id], ICON_SIZE, ICON_SIZE);
    }

    // Draw text in the lower portion
    if (text && text[0] != '\0') {
        // Auto-size: find longest line and shrink until it fits
        uint8_t text_size = 5;
        int max_len = 0, cur_len = 0;
        for (const char* p = text; *p; p++) {
            if (*p == '\n') { if (cur_len > max_len) max_len = cur_len; cur_len = 0; }
            else cur_len++;
        }
        if (cur_len > max_len) max_len = cur_len;
        if (max_len == 0) max_len = 1;
        while (text_size > 1 && max_len * 6 * text_size > LCD_WIDTH - 8) text_size--;

        // Count lines to figure out block height
        int line_count = 1;
        for (const char* p = text; *p; p++) if (*p == '\n') line_count++;
        int16_t text_block_h = line_count * 8 * text_size;

        // Place text block: center it in the lower 40% of screen
        int16_t text_area_top = (int16_t)(LCD_HEIGHT * 0.60f);
        int16_t text_area_h = LCD_HEIGHT - text_area_top;
        int16_t y_start = text_area_top + (text_area_h - text_block_h) / 2;
        y_start = max(y_start, text_area_top);
        y_start &= ~1;

        draw_centered_text_block(text, fg_color, text_size, y_start);
    }

    screen_on = true;
}

// JPEGDEC draw callback — write one row at a time to stay within QSPI DMA limits
static int jpeg_draw_callback(JPEGDRAW* pDraw) {
    if (!gfx) return 0;
    for (int row = 0; row < pDraw->iHeight; row++) {
        gfx->draw16bitRGBBitmap(
            pDraw->x, pDraw->y + row,
            pDraw->pPixels + (row * pDraw->iWidth),
            pDraw->iWidth, 1
        );
    }
    return 1;
}

void display_show_image(const uint8_t* jpeg_data, size_t jpeg_len) {
    if (!gfx || !jpeg_data || jpeg_len == 0) return;

    gfx->fillScreen(BLACK);  // clear previous content before decoding
    if (jpeg.openRAM((uint8_t*)jpeg_data, (int)jpeg_len, jpeg_draw_callback)) {
        jpeg.setPixelType(RGB565_LITTLE_ENDIAN);
        // Note: do NOT wrap in startWrite/endWrite — JPEGDEC calls the draw
        // callback repeatedly and draw16bitRGBBitmap manages its own transactions
        int result = jpeg.decode(0, 0, 0);
        jpeg.close();
        if (result) {
            screen_on = true;
            Serial.printf("JPEG decoded OK: %dx%d\n", jpeg.getWidth(), jpeg.getHeight());
        } else {
            Serial.println("JPEG decode failed");
        }
    } else {
        Serial.println("JPEG open failed");
    }
}

void display_set_brightness(uint8_t level) {
    if (!gfx) return;
    // SH8601 brightness via Arduino_SH8601::setBrightness (available on this class)
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
