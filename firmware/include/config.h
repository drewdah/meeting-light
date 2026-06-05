#pragma once

// --- QSPI Display (SH8601) ---
#define LCD_SCLK   0
#define LCD_SDIO0  1
#define LCD_SDIO1  2
#define LCD_SDIO2  3
#define LCD_SDIO3  4
#define LCD_CS     5

#define LCD_WIDTH  368
#define LCD_HEIGHT 448

// --- I2C Bus (shared by 6 devices) ---
#define I2C_SCL    7
#define I2C_SDA    8
#define I2C_FREQ   200000

// --- I2C Addresses ---
#define ADDR_TCA9554   0x20
#define ADDR_AXP2101   0x34
#define ADDR_FT3168    0x38
#define ADDR_PCF85063  0x51
#define ADDR_QMI8658   0x6B
#define ADDR_ES8311    0x18

// --- TCA9554 IO Expander ---
// P4 and P5 control display/touch power
#define TCA_DISP_TOUCH_P4  4
#define TCA_DISP_TOUCH_P5  5

// --- I2S / ES8311 Audio ---
// Verified against Waveshare ESP32-C6-Touch-AMOLED-1.8 official pin_config.h
#define I2S_MCLK   19
#define I2S_BCLK   20
#define I2S_WS     22
#define I2S_DOUT   23   // Data out ESP32→codec (speaker)
#define I2S_DIN    21   // Data in codec→ESP32 (mic, unused)
// PA amp enable is TCA9554 IO expander pin P7, not a direct GPIO
#define TCA_PA_CTRL  7
// ADDR_ES8311 (0x18) already defined above

// --- Buttons ---
#define BTN_BOOT   9   // Active LOW, strapping pin

// --- Touch ---
#define TOUCH_INT  15  // Active LOW, strapping pin

// --- BLE ---
#define BLE_DEVICE_NAME "MeetingLight"

#define BLE_SERVICE_UUID        "00001000-4d45-4554-4c49-544500000001"
#define BLE_CHAR_STATE_CMD_UUID "00001001-4d45-4554-4c49-544500000001"
#define BLE_CHAR_DEV_STATUS_UUID "00001002-4d45-4554-4c49-544500000001"
#define BLE_CHAR_DEV_INFO_UUID  "00001003-4d45-4554-4c49-544500000001"

// --- BLE Protocol Opcodes ---
#define OP_SET_PRESET      0x01
#define OP_SET_CUSTOM_TEXT 0x02
#define OP_SLEEP           0x03
#define OP_WAKE            0x04
#define OP_IMAGE_START     0x05
#define OP_IMAGE_CHUNK     0x06
#define OP_IMAGE_END       0x07
#define OP_SET_BRIGHTNESS  0x08
#define OP_PING            0x09
#define OP_SET_ICON_TEXT   0x0A  // [icon_id][r][g][b][text...]
#define OP_SET_MUTE        0x0B  // [0=unmute, 1=mute]

// --- Display States ---
enum DisplayState : uint8_t {
    STATE_OFF = 0,
    STATE_IN_MEETING = 1,
    STATE_WFH = 2,
    STATE_OOF = 3,
    STATE_CUSTOM_TEXT = 4,
    STATE_CUSTOM_IMAGE = 5,
};

// --- Power ---
#define BATTERY_READ_INTERVAL_MS  300000  // 5 minutes
#define DUTY_CYCLE_ON_MS          30000   // 30 seconds on
#define DUTY_CYCLE_OFF_MS         90000   // 90 seconds off
